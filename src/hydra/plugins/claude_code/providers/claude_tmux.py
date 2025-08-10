"""Claude tmux Provider - Runs Claude Code in tmux sessions for full interactivity."""
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from hydra.providers.base import LLMProvider


class ClaudeTmuxProvider(LLMProvider):
    """Run Claude Code in tmux sessions with full interactive capabilities."""

    def validate_config(self):
        """Validate Claude CLI and tmux configuration."""
        self.claude_path = self.config.extra_params.get(
            'claude_path',
            os.environ.get('CLAUDE_CLI_PATH', 'claude')
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

        # Create .hydra folder if it doesn't exist
        hydra_dir = Path(project_dir) / ".hydra"
        hydra_dir.mkdir(exist_ok=True)

        # Marker file to detect when Claude is done
        sessions_dir = hydra_dir / "sessions"
        sessions_dir.mkdir(exist_ok=True)
        done_marker = sessions_dir / f"done_{session_name}"
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

            # Send the implementation prompt with explicit file creation permission
            print(f"📝 Sending task to Claude Code in session {session_name}...")
            print(f"🎯 Task: Working on Ticket {ticket_id}" if ticket_id else "🎯 Generic task")

            # Make the prompt VERY explicit about using tools
            enhanced_prompt = f"""You have permission to use ALL tools to complete this task.
Please use the Write, Edit, and Bash tools as needed to create and modify files.
Do NOT ask for permission - you already have it. Just proceed with implementation.

{prompt}

IMPORTANT: Use the Write tool to create new files and Edit tool to modify existing files.
You have full permission to create any files needed for this task.
When asked about file creation, always select option 2 'Yes, and don't ask again this session'.

SAFETY NOTE: Do NOT perform any git operations (commit, push, merge, etc.) without explicit user approval."""

            # Log the first part of the prompt to verify it's ticket-specific
            print(f"📋 Prompt preview: {prompt[:200]}..." if len(prompt) > 200 else f"📋 Full prompt: {prompt}")

            self._send_to_session(session_name, enhanced_prompt)

            # Give Claude time to process the prompt
            time.sleep(3)

            # Add instruction to create done marker (only if not already in prompt)
            if f"done_{session_name}" not in prompt:
                done_instruction = f"\nWhen you're completely done with all file operations, please create a file called .hydra/sessions/done_{session_name} to signal completion."
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

                        # Check for git-related dangerous operations
                        git_indicators = [
                            'git commit', 'git push', 'git merge', 'git rebase',
                            'git reset', 'git checkout', 'git branch -d', 'git branch -D',
                            'force push', 'git clean', 'git stash drop'
                        ]

                        # SAFETY: Never auto-approve git operations
                        if any(git_cmd in current_output.lower() for git_cmd in git_indicators):
                            print("🛑 SAFETY: Git operation detected - requires manual approval")
                            print("⚠️  Stopping automation for safety. Please handle git operations manually.")
                            # Don't auto-respond, let it timeout or wait for user
                            break

                        # Check for common prompts that need user input
                        prompt_indicators = [
                            '(y/n)', '(yes/no)', 'Continue?', 'Proceed?', 'overwrite',
                            'Yes, looks good', 'make changes', 'tell Claude'
                        ]

                        # Check if Claude Code is showing its confirmation menu (for FILE operations only)
                        if "don't ask again" in current_output:
                            # Make sure it's about file creation, not git
                            if not any(git_cmd in current_output.lower() for git_cmd in git_indicators):
                                print("⚠️  Claude Code confirmation menu - selecting option 2 (Yes, don't ask again)")
                                self._send_to_session(session_name, "2")
                            else:
                                print("🛑 Git operation detected - manual approval required")
                                break
                        elif "Yes, looks good" in current_output or "tell Claude what to do" in current_output:
                            # Only auto-approve if it's not git-related
                            if not any(git_cmd in current_output.lower() for git_cmd in git_indicators):
                                print("⚠️  Claude Code showing confirmation menu - selecting option 1 (Yes)")
                                self._send_to_session(session_name, "1")
                            else:
                                print("🛑 Git operation detected - manual approval required")
                                break
                            no_change_count = 0  # Reset counter
                        elif any(indicator in current_output.lower() for indicator in prompt_indicators):
                            # Only auto-respond if it's not git-related
                            if not any(git_cmd in current_output.lower() for git_cmd in git_indicators):
                                print("⚠️  Detected prompt for user input - sending 'y' to continue")
                                self._send_to_session(session_name, "y")
                            else:
                                print("🛑 Git operation detected - manual approval required")
                                break
                            no_change_count = 0  # Reset counter
                        else:
                            print("⏱️  Assuming completion after 120s of inactivity")
                            break
                else:
                    no_change_count = 0
                    # Check for tool usage patterns in the new output
                    new_content = current_output[len(last_output):] if len(current_output) > len(last_output) else ""
                    if new_content:
                        # SAFETY CHECK: Look for git operations first
                        git_indicators = [
                            'git commit', 'git push', 'git merge', 'git rebase',
                            'git reset', 'git checkout', 'git branch -d', 'git branch -D',
                            'force push', 'git clean', 'git stash drop'
                        ]

                        if any(git_cmd in new_content.lower() for git_cmd in git_indicators):
                            print("🛑 SAFETY: Git operation detected in output - stopping automation")
                            print("⚠️  Please handle git operations manually for safety")
                            break  # Stop automation immediately

                        # Immediately check for Claude Code confirmation prompts (only for safe operations)
                        if "don't ask again" in new_content:
                            print("🔔 Claude Code confirmation - selecting option 2 (don't ask again)...")
                            self._send_to_session(session_name, "2")
                            time.sleep(2)  # Give Claude time to process
                        elif "Yes, looks good" in new_content or "tell Claude what to do" in new_content:
                            print("🔔 Claude Code is asking for confirmation - auto-approving...")
                            self._send_to_session(session_name, "1")
                            time.sleep(2)  # Give Claude time to process
                        # Look for Claude Code tool usage patterns and show what it's doing
                        elif "Reading" in new_content:
                            # Extract file being read if possible
                            import re
                            file_match = re.search(r'Reading[:\s]+([^\s]+)', new_content)
                            if file_match:
                                print(f"👁️  Reading: {file_match.group(1)}")
                            else:
                                print("👁️  Reading files...")
                        elif "Writing" in new_content or "Creating" in new_content:
                            file_match = re.search(r'(?:Writing|Creating)[:\s]+([^\s]+)', new_content)
                            if file_match:
                                print(f"✍️  Writing: {file_match.group(1)}")
                            else:
                                print("✍️  Writing new content...")
                        elif "Editing" in new_content:
                            file_match = re.search(r'Editing[:\s]+([^\s]+)', new_content)
                            if file_match:
                                print(f"✏️  Editing: {file_match.group(1)}")
                            else:
                                print("✏️  Editing files...")
                        elif "Running" in new_content or "Executing" in new_content:
                            cmd_match = re.search(r'(?:Running|Executing)[:\s]+(.+?)(?:\n|$)', new_content)
                            if cmd_match:
                                cmd = cmd_match.group(1).strip()
                                if len(cmd) > 50:
                                    cmd = cmd[:50] + "..."
                                print(f"🚀 Running: {cmd}")
                            else:
                                print("🚀 Executing commands...")
                        elif "npm" in new_content or "yarn" in new_content or "pip" in new_content:
                            print("📦 Installing dependencies...")
                        elif "test" in new_content.lower():
                            print("🧪 Running tests...")
                        elif any(pattern in new_content for pattern in ["Analyzing", "Checking", "Reviewing"]):
                            print("🔍 Analyzing code structure...")
                    last_output = current_output

                # Show periodic status updates with progress indicator
                if time.time() - last_status_time > 10:
                    last_status_time = time.time()
                    elapsed = int(time.time() - start_time)

                    # Create a progress indicator based on activity
                    if elapsed < 30:
                        phase = "🔍 Analyzing requirements"
                    elif elapsed < 60:
                        phase = "🏗️  Building implementation"
                    elif elapsed < 90:
                        phase = "✅ Finalizing changes"
                    elif elapsed < 120:
                        phase = "🧹 Cleaning up"
                    else:
                        phase = "⏳ Working"

                    # Show time in a more readable format
                    mins = elapsed // 60
                    secs = elapsed % 60
                    if mins > 0:
                        print(f"{phase} ({mins}m {secs}s)...")
                    else:
                        print(f"{phase} ({elapsed}s)...")

                # Check for file changes periodically - but only for THIS ticket's session
                if int(time.time() - start_time) % 10 == 0 and ticket_id:
                    # Only report on files likely related to this specific ticket
                    # to avoid confusion with concurrent tickets
                    git_status = subprocess.run(
                        ["git", "status", "--short"],
                        capture_output=True,
                        text=True,
                        cwd=project_dir
                    )
                    # Filter to only show files in the current project directory
                    changed_files = []
                    project_path = Path(project_dir).resolve()
                    for line in git_status.stdout.strip().split('\n'):
                        if line and not line.endswith("tickets.md"):
                            # Parse the file path
                            parts = line.strip().split(maxsplit=1)
                            if len(parts) >= 2:
                                filepath = parts[1]
                                # Special case: if the path is just "./" it means the entire directory is untracked
                                if filepath == "./":
                                    # List actual files in the directory instead
                                    try:
                                        for f in Path(project_dir).iterdir():
                                            if f.is_file() and f.name != "tickets.md":
                                                changed_files.append(f"?? {f.name}")
                                    except:
                                        changed_files.append(line)
                                else:
                                    # Convert to absolute path and check if it's within project directory
                                    try:
                                        file_abs_path = (project_path / filepath).resolve()
                                        # Check if the file is within the project directory
                                        if str(file_abs_path).startswith(str(project_path)):
                                            changed_files.append(line)
                                    except (ValueError, OSError):
                                        # Skip files that can't be resolved
                                        pass
                    if changed_files:
                        # Show what files are being modified
                        print(f"📝 Working on {len(changed_files)} files:")
                        for file in changed_files[:3]:  # Show first 3 files
                            file_parts = file.strip().split()
                            if len(file_parts) >= 2:
                                status = file_parts[0]
                                filepath = ' '.join(file_parts[1:])
                                if status == "M":
                                    print(f"   ✏️  Editing: {filepath}")
                                elif status == "A" or status == "??":
                                    print(f"   ➕ Creating: {filepath}")
                                elif status == "D":
                                    print(f"   ➖ Removing: {filepath}")
                                else:
                                    print(f"   📄 {status}: {filepath}")
                        if len(changed_files) > 3:
                            print(f"   ... and {len(changed_files) - 3} more")

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

            # Filter to only show files in the current project directory
            changed_files = []
            project_path = Path(project_dir).resolve()
            for line in git_status.stdout.strip().split('\n'):
                if line and not line.endswith("tickets.md"):
                    # Parse the file path
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) >= 2:
                        filepath = parts[1]
                        # Special case: if the path is just "./" it means the entire directory is untracked
                        if filepath == "./":
                            # List actual files in the directory instead
                            try:
                                for f in Path(project_dir).iterdir():
                                    if f.is_file() and f.name != "tickets.md":
                                        changed_files.append(f"?? {f.name}")
                            except:
                                changed_files.append(line)
                        else:
                            # Convert to absolute path and check if it's within project directory
                            try:
                                file_abs_path = (project_path / filepath).resolve()
                                # Check if the file is within the project directory
                                if str(file_abs_path).startswith(str(project_path)):
                                    changed_files.append(line)
                            except (ValueError, OSError):
                                # Skip files that can't be resolved
                                pass

            if changed_files:
                print("\n✅ Files successfully modified by Claude Code:")
                created_files = []
                modified_files = []
                deleted_files = []

                for line in changed_files:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        status = parts[0]
                        filepath = ' '.join(parts[1:])
                        if status == "M":
                            modified_files.append(filepath)
                        elif status == "A" or status == "??":
                            created_files.append(filepath)
                        elif status == "D":
                            deleted_files.append(filepath)

                # Show categorized summary
                if created_files:
                    print(f"\n   ➕ Created {len(created_files)} new file(s):")
                    for f in created_files[:5]:
                        print(f"      • {f}")
                    if len(created_files) > 5:
                        print(f"      ... and {len(created_files) - 5} more")

                if modified_files:
                    print(f"\n   ✏️  Modified {len(modified_files)} file(s):")
                    for f in modified_files[:5]:
                        print(f"      • {f}")
                    if len(modified_files) > 5:
                        print(f"      ... and {len(modified_files) - 5} more")

                if deleted_files:
                    print(f"\n   ➖ Deleted {len(deleted_files)} file(s):")
                    for f in deleted_files[:3]:
                        print(f"      • {f}")

                # Show quick summary of what was likely done
                if "index.html" in str(created_files + modified_files):
                    print("\n   📄 HTML structure updated")
                if "style.css" in str(created_files + modified_files):
                    print("   🎨 Styles applied")
                if any(".js" in f for f in created_files + modified_files):
                    print("   ⚙️  JavaScript functionality added")
                if any("test" in f.lower() for f in created_files + modified_files):
                    print("   🧪 Tests implemented")

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
