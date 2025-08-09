"""Claude tmux Provider - Runs Claude Code in tmux sessions for full interactivity."""
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .base import LLMProvider


class ClaudeTmuxProvider(LLMProvider):
    """Run Claude Code in tmux sessions with full interactive capabilities."""

    def validate_config(self):
        """Validate Claude CLI and tmux configuration."""
        self.claude_path = self.config.extra_params.get(
            'claude_path',
            os.environ.get('CLAUDE_CLI_PATH', '/home/kyle/.claude/local/claude')
        )

        if not Path(self.claude_path).exists():
            raise ValueError(f"Claude CLI not found at: {self.claude_path}")

        # Check if tmux is available
        try:
            subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise ValueError("tmux is not installed. Please install tmux: sudo apt-get install tmux")

    @property
    def name(self) -> str:
        return "claude_tmux"

    def _create_session_name(self, ticket_id: Optional[str] = None) -> str:
        """Create a unique tmux session name."""
        if ticket_id:
            return f"hydra_claude_{ticket_id}"
        return f"hydra_claude_{uuid.uuid4().hex[:8]}"

    def _session_exists(self, session_name: str) -> bool:
        """Check if a tmux session exists."""
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True
        )
        return result.returncode == 0

    def _kill_session(self, session_name: str):
        """Kill a tmux session if it exists."""
        if self._session_exists(session_name):
            subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)

    def _send_to_session(self, session_name: str, text: str):
        """Send text to a tmux session."""
        # For multiline text, use tmux's literal mode
        # First, create a temp file with the text
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(text)
            temp_file = f.name

        try:
            # Use tmux load-buffer and paste-buffer for accurate text transmission
            subprocess.run(
                ["tmux", "load-buffer", "-t", session_name, temp_file],
                capture_output=True
            )
            subprocess.run(
                ["tmux", "paste-buffer", "-t", session_name],
                capture_output=True
            )
            # Send Enter to submit
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "Enter"],
                capture_output=True
            )
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def _capture_session_output(self, session_name: str) -> str:
        """Capture the output from a tmux session."""
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p"],
            capture_output=True,
            text=True
        )
        return result.stdout if result.returncode == 0 else ""

    def generate(self, prompt: str, **kwargs) -> str:
        """Execute Claude in a tmux session for file operations."""
        project_dir = kwargs.get('cwd', os.getcwd())
        ticket_id = kwargs.get('ticket_id', None)
        session_name = self._create_session_name(ticket_id)

        # Kill any existing session with the same name
        self._kill_session(session_name)

        # Marker file to detect when Claude is done
        done_marker = Path(project_dir) / f".hydra_done_{session_name}"
        if done_marker.exists():
            done_marker.unlink()

        try:
            print(f"🖥️  Starting tmux session: {session_name}")
            print(f"📁 Working directory: {project_dir}")

            # Create a new tmux session with Claude
            subprocess.run(
                [
                    "tmux", "new-session", "-d", "-s", session_name,
                    "-c", project_dir,
                    self.claude_path
                ],
                check=True
            )

            # Wait for Claude to initialize
            print("⏳ Waiting for Claude Code to initialize...")
            initialization_timeout = 30
            start_init = time.time()
            claude_ready = False

            while time.time() - start_init < initialization_timeout:
                output = self._capture_session_output(session_name)
                # Check for various Claude Code prompts
                if any(indicator in output for indicator in ["Welcome to Claude", ">", "Claude Code", "Assistant:"]):
                    claude_ready = True
                    print("✅ Claude Code is ready")
                    break
                time.sleep(1)

            if not claude_ready:
                print("⚠️  Claude Code initialization timeout - proceeding anyway")

            # Send the implementation prompt with auto-approval instruction
            print("📝 Sending task to Claude Code...")
            enhanced_prompt = prompt + "\n\nIMPORTANT: When you show file creation confirmations, please use option 2 'Yes, and don't ask again this session' to proceed automatically with all file operations."
            self._send_to_session(session_name, enhanced_prompt)

            # Give Claude time to process the prompt
            time.sleep(3)

            # Add instruction to create done marker (only if not already in prompt)
            if f".hydra_done_{session_name}" not in prompt:
                done_instruction = f"\nWhen you're completely done with all file operations, please create a file called .hydra_done_{session_name} to signal completion."
                self._send_to_session(session_name, done_instruction)

            # Monitor for completion
            start_time = time.time()
            last_output = ""
            no_change_count = 0
            last_status_time = time.time()

            while time.time() - start_time < self.config.timeout:
                # Check if done marker exists
                if done_marker.exists():
                    print("✅ Claude Code signaled completion")
                    done_marker.unlink()
                    break

                # Capture current output
                current_output = self._capture_session_output(session_name)

                # Check if output has changed
                if current_output == last_output:
                    no_change_count += 1
                    # If no changes for 120 seconds, check if Claude needs input
                    if no_change_count > 120:
                        # Extract last few lines to check for prompts
                        last_lines = current_output.split('\n')[-5:]
                        print("⏱️  No activity for 120s. Last output:")
                        for line in last_lines:
                            if line.strip():
                                print(f"   > {line[:100]}")

                        # Check for common prompts that need user input
                        prompt_indicators = [
                            '(y/n)', '(yes/no)', 'Continue?', 'Proceed?', 'overwrite',
                            'Yes, looks good', 'make changes', 'tell Claude'
                        ]

                        # Check if Claude Code is showing its confirmation menu
                        if "don't ask again" in current_output:
                            print("⚠️  Claude Code confirmation menu - selecting option 2 (Yes, don't ask again)")
                            self._send_to_session(session_name, "2")
                        elif "Yes, looks good" in current_output or "tell Claude what to do" in current_output:
                            print("⚠️  Claude Code showing confirmation menu - selecting option 1 (Yes)")
                            self._send_to_session(session_name, "1")
                            no_change_count = 0  # Reset counter
                        elif any(indicator in current_output.lower() for indicator in prompt_indicators):
                            print("⚠️  Detected prompt for user input - sending 'y' to continue")
                            self._send_to_session(session_name, "y")
                            no_change_count = 0  # Reset counter
                        else:
                            print("⏱️  Assuming completion after 120s of inactivity")
                            break
                else:
                    no_change_count = 0
                    # Check for tool usage patterns in the new output
                    new_content = current_output[len(last_output):] if len(current_output) > len(last_output) else ""
                    if new_content:
                        # Immediately check for Claude Code confirmation prompts
                        if "don't ask again" in new_content:
                            print("🔔 Claude Code confirmation - selecting option 2 (don't ask again)...")
                            self._send_to_session(session_name, "2")
                            time.sleep(2)  # Give Claude time to process
                        elif "Yes, looks good" in new_content or "tell Claude what to do" in new_content:
                            print("🔔 Claude Code is asking for confirmation - auto-approving...")
                            self._send_to_session(session_name, "1")
                            time.sleep(2)  # Give Claude time to process
                        # Look for Claude Code tool usage patterns
                        elif any(pattern in new_content for pattern in ["Reading", "Writing", "Editing", "Creating", "Running"]):
                            print("⚙️  Claude Code is actively working on files...")
                    last_output = current_output

                # Show periodic status updates
                if time.time() - last_status_time > 10:
                    last_status_time = time.time()
                    elapsed = int(time.time() - start_time)
                    print(f"⏳ Elapsed time: {elapsed}s")

                # Check for file changes periodically
                if int(time.time() - start_time) % 10 == 0:
                    git_status = subprocess.run(
                        ["git", "status", "--short"],
                        capture_output=True,
                        text=True,
                        cwd=project_dir
                    )
                    changed_files = [
                        line for line in git_status.stdout.strip().split('\n')
                        if line and not line.endswith("tickets.md")
                    ]
                    if changed_files:
                        print(f"📝 Files modified: {len(changed_files)} files")

                time.sleep(1)

            # Send exit command to Claude
            print("🛑 Ending Claude session...")
            self._send_to_session(session_name, "/exit")
            time.sleep(2)

            # Check final results
            git_status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                cwd=project_dir
            )

            changed_files = [
                line for line in git_status.stdout.strip().split('\n')
                if line and not line.endswith("tickets.md")
            ]

            if changed_files:
                print("\n✅ Files successfully modified by Claude Code:")
                for line in changed_files:
                    print(f"   {line}")
                return "Files have been successfully edited"
            else:
                # Check if any new files were created
                src_dir = Path(project_dir) / "src"
                if src_dir.exists():
                    new_files = subprocess.run(
                        ["find", str(src_dir), "-type", "f", "-mmin", "-2"],
                        capture_output=True,
                        text=True
                    )
                    if new_files.stdout.strip():
                        print("✅ New files created")
                        return "Implementation completed"

                return self._capture_session_output(session_name) or "Claude session completed"

        except subprocess.CalledProcessError as e:
            raise Exception(f"tmux command failed: {str(e)}")
        except Exception as e:
            raise Exception(f"Claude tmux error: {str(e)}")
        finally:
            # Kill the tmux session
            self._kill_session(session_name)
            # Clean up marker file
            done_marker.unlink(missing_ok=True)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Not used for tmux mode."""
        result = self.generate(prompt, **kwargs)
        return {"result": result}

    def stream_generate(self, prompt: str, **kwargs):
        """Not used for tmux mode."""
        yield self.generate(prompt, **kwargs)

    def list_models(self):
        """Return available models."""
        return ["claude-3-opus", "claude-3-sonnet"]
