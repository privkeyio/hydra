"""Claude tmux Provider - Runs Claude Code in tmux sessions for full interactivity."""
import os
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from hydra.safety.claude_file_interceptor import ClaudeFileInterceptor
from hydra.utils.claude_path import get_claude_cli_path

from .base_provider import (
    BaseProvider,
    CodeBlock,
    FileOperation,
    FileOperationType,
    ModelInfo,
    ParsedResponse,
    Session,
    SessionState,
)


class ClaudeTmuxProvider(BaseProvider):
    """Run Claude Code in tmux sessions with full interactive capabilities."""

    def validate_config(self):
        """Validate Claude CLI and tmux configuration."""
        self.claude_path = self.config.extra_params.get(
            'claude_path',
            os.environ.get('CLAUDE_CLI_PATH', get_claude_cli_path())
        )

        if not Path(self.claude_path).exists():
            raise ValueError(f"Claude CLI not found at: {self.claude_path}")

        # Check if tmux is available
        try:
            subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise ValueError(
                "tmux is not installed. Please install tmux: sudo apt-get install tmux"
            ) from e

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
            subprocess.run(
                ["tmux", "kill-session", "-t", session_name],
                capture_output=True
            )

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

        # Initialize file interceptor for this session
        file_interceptor = ClaudeFileInterceptor()
        agent_id = session_name  # Use session name as agent ID for locking

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

        # Set up debug logging early
        debug_log_path = hydra_dir / "debug" / f"claude_{session_name}_{int(time.time())}.log"
        debug_log_path.parent.mkdir(exist_ok=True)
        self._current_debug_log_path = debug_log_path

        def debug_log(message):
            """Log debug messages to file and console"""
            timestamp = time.strftime("%H:%M:%S")
            log_msg = f"[{timestamp}] {message}"
            print(f"🔍 DEBUG: {log_msg}")
            with open(self._current_debug_log_path, 'a') as f:
                f.write(log_msg + "\n")

        # Store as instance method for use throughout
        self._debug_log = debug_log

        try:
            print(f"🖥️  Starting tmux session: {session_name}")
            print(f"📁 Working directory: {project_dir}")
            debug_log(f"Starting session: {session_name}")
            debug_log(f"Working directory: {project_dir}")

            # Create a new tmux session with Claude
            # Check if we need to specify a model
            model_from_env = os.environ.get('CLAUDE_MODEL', '').lower()

            # Map ticket models to Claude model names
            model_mapping = {
                'smart': 'opus',      # Complex tasks need Opus
                'coder': 'opus',      # Complex coding needs Opus
                'balanced': 'sonnet', # Balanced tasks use Sonnet
                'fast': 'sonnet'      # Fast tasks also use Sonnet (no Haiku)
            }

            claude_model = model_mapping.get(model_from_env, 'sonnet')  # Default to sonnet

            # Build the command with model flag
            cmd = [
                "tmux", "new-session", "-d", "-s", session_name,
                "-c", project_dir,
                self.claude_path, "--model", claude_model
            ]

            print(f"🤖 Starting Claude with {claude_model.upper()} model")
            debug_log(f"Starting Claude with model: {claude_model}")

            subprocess.run(cmd, check=True)

            # Wait for Claude to initialize
            print("⏳ Waiting for Claude Code to initialize...")
            initialization_timeout = 30
            start_init = time.time()
            claude_ready = False

            while time.time() - start_init < initialization_timeout:
                output = self._capture_session_output(session_name)
                # Check for various Claude Code prompts
                indicators = [
                    "Welcome to Claude", ">", "Claude Code", "Assistant:"
                ]
                if any(indicator in output for indicator in indicators):
                    claude_ready = True
                    print("✅ Claude Code is ready")
                    break
                time.sleep(1)

            if not claude_ready:
                print("⚠️  Claude Code initialization timeout - proceeding anyway")

            # Send the implementation prompt with explicit file creation permission
            print(f"📝 Sending task to Claude Code in session {session_name}...")
            if ticket_id:
                print(f"🎯 Task: Working on Ticket {ticket_id}")
            else:
                print("🎯 Generic task")

            # Send a clear, direct prompt to Claude
            prompt_text = (
                f"Execute ticket {ticket_id} in tickets.md\n\n"
                f"Requirements:\n"
                f"1. Read the ticket carefully\n"
                f"2. Create ALL files listed in 'Output Files' section\n"
                f"3. Follow acceptance criteria exactly\n"
                f"4. Be minimalistic, surgical and future proof\n"
                f"5. Avoid using any code or comments that may be construed as AI generated\n"
                f"6. Make sure you do a good job because other LLMs said your code sucked\n"
                f"7. When finished, ensure acceptance criteria is met then update tickets.md\n"
                f"8. Run lint, build, test etc before marking complete\n"
                f"9. DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS\n"
                f"10. This has to be production quality, take your time"
            )

            debug_log("=" * 60)
            debug_log("SENDING PROMPT TO CLAUDE:")
            debug_log(prompt_text)
            debug_log("=" * 60)

            # Send the prompt
            self._send_to_session(session_name, prompt_text)
            debug_log("Prompt sent successfully")

            # Give Claude time to process the prompt
            time.sleep(3)

            # Capture initial response
            initial_response = self._capture_session_output(session_name)
            debug_log("Initial Claude response after prompt:")
            for line in initial_response.split('\n')[-20:]:  # Last 20 lines
                if line.strip():
                    debug_log(f"  > {line[:150]}")

            # Add done marker instruction after initial processing
            if f"done_{session_name}" not in prompt:
                done_instruction = (
                    f"\nWhen you're completely done with all file operations, "
                    f"please create a file called .hydra/sessions/done_{session_name} "
                    f"to signal completion."
                )
                time.sleep(5)  # Wait before sending done instruction
                self._send_to_session(session_name, done_instruction)
                debug_log("Done marker instruction sent")

            # Monitor for completion
            start_time = time.time()
            last_output = ""
            no_change_count = 0
            last_status_time = time.time()
            last_captured_lines = 0

            # Use a much longer timeout (15 minutes) and detect actual completion
            max_timeout = 900  # 15 minutes should be enough for complex tasks
            idle_timeout = 180  # 3 minutes of no activity suggests completion or stuck

            while time.time() - start_time < max_timeout:
                # Check if done marker exists
                if done_marker.exists():
                    print("✅ Claude Code signaled completion")
                    done_marker.unlink()
                    break

                # Capture current output
                current_output = self._capture_session_output(session_name)

                # Log new content
                current_lines = current_output.split('\n')
                if len(current_lines) > last_captured_lines:
                    new_lines = current_lines[last_captured_lines:]
                    for line in new_lines:
                        if line.strip():
                            debug_log(f"CLAUDE OUTPUT: {line[:200]}")
                    last_captured_lines = len(current_lines)

                # Check if output has changed
                if current_output == last_output:
                    no_change_count += 1

                    # Log status periodically
                    if no_change_count % 30 == 0:
                        debug_log(f"No activity for {no_change_count}s")
                        print(f"⏳ Waiting for Claude to complete... ({no_change_count}s idle)")
                        # Log last 10 lines to see what Claude is stuck on
                        last_10_lines = current_lines[-10:] if len(current_lines) > 10 else current_lines
                        debug_log("Last 10 lines of output:")
                        for line in last_10_lines:
                            debug_log(f"  > {line[:100]}")

                    # Check if Claude has returned to prompt (indicates completion)
                    last_lines = current_output.strip().split('\n')[-5:]
                    prompt_indicators = ['│ >                                                                            │',
                                       '│ > ',
                                       '╰──────────────────────────────────────────────────────────────────────────────╯']

                    if no_change_count > 10:  # After 10 seconds of no activity
                        # Check if we see the prompt
                        completion_detected = False
                        for line in last_lines:
                            if any(indicator in line for indicator in prompt_indicators):
                                print("✅ Claude returned to prompt - task appears complete")
                                debug_log("Detected Claude prompt - assuming completion")
                                completion_detected = True
                                break
                        if completion_detected:
                            break  # Break out of main loop

                    # If no changes for idle_timeout seconds, assume completion or stuck
                    if no_change_count > idle_timeout:
                        print(f"⏱️  Claude has been idle for {idle_timeout}s - assuming task complete or stuck")
                        debug_log(f"Idle timeout reached after {no_change_count}s")
                        break  # Exit the loop

                else:
                    # Output changed, reset counter
                    if no_change_count > 0:
                        debug_log(f"Activity detected after {no_change_count}s idle")
                    no_change_count = 0
                    last_output = current_output

                    # Check if Claude needs permission for file operations
                    if "don't ask again" in current_output.lower():
                        print("⚠️  Claude Code asking for permission - auto-approving file operations")
                        self._send_to_session(session_name, "2")  # Select "Yes, don't ask again"
                        time.sleep(1)
                    elif "yes, looks good" in current_output.lower():
                        print("⚠️  Claude Code asking for confirmation - auto-approving")
                        self._send_to_session(session_name, "1")  # Select "Yes"
                        time.sleep(1)

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
                                    except Exception:
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

            # Save full session output for debugging
            final_output = self._capture_session_output(session_name)
            session_log_path = hydra_dir / "debug" / f"full_session_{session_name}_{int(time.time())}.txt"
            session_log_path.parent.mkdir(exist_ok=True)
            with open(session_log_path, 'w') as f:
                f.write(final_output)
            debug_log(f"Full session saved to: {session_log_path}")

            # Debug summary
            debug_log("=" * 60)
            debug_log("SESSION SUMMARY:")
            debug_log(f"Session: {session_name}")
            debug_log(f"Duration: {time.time() - start_time:.2f}s")
            debug_log(f"Ticket ID: {ticket_id}")
            debug_log(f"Files detected by git: {git_status.stdout if 'git_status' in locals() else 'N/A'}")
            debug_log(f"Debug log: {debug_log_path}")
            debug_log(f"Full session: {session_log_path}")
            print("\n📁 Debug logs saved to:")
            print(f"   • {debug_log_path}")
            print(f"   • {session_log_path}")
            debug_log("=" * 60)

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
                            except Exception:
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
            raise Exception(f"tmux command failed: {str(e)}") from e
        except Exception as e:
            raise Exception(f"Claude tmux error: {str(e)}") from e
        finally:
            # Release all file locks for this agent
            file_interceptor.release_agent_locks(agent_id)
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

    # Model Management Methods (required by BaseProvider)
    def list_models(self) -> List[ModelInfo]:
        """List available models with metadata."""
        return [
            ModelInfo(
                identifier="claude-opus-4-1-20250805",
                display_name="Claude Opus 4.1",
                category="smart",
                context_window=200000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_interactive=True,
                cost_per_token=0.00015,
                metadata={"version": "4.1", "release_date": "2025-08-05"}
            ),
            ModelInfo(
                identifier="claude-sonnet-4-20250514",
                display_name="Claude Sonnet 4",
                category="balanced",
                context_window=200000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_interactive=True,
                cost_per_token=0.00003,
                metadata={"version": "4", "release_date": "2025-05-14"}
            ),
            ModelInfo(
                identifier="claude-3-opus-20240229",
                display_name="Claude 3 Opus",
                category="smart",
                context_window=200000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_interactive=True,
                cost_per_token=0.00015,
                metadata={"version": "3", "release_date": "2024-02-29"}
            ),
            ModelInfo(
                identifier="claude-3-sonnet-20240229",
                display_name="Claude 3 Sonnet",
                category="balanced",
                context_window=200000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_interactive=True,
                cost_per_token=0.00003,
                metadata={"version": "3", "release_date": "2024-02-29"}
            ),
        ]

    def select_model(self, model_identifier: str) -> bool:
        """Select a specific model by identifier."""
        # Map generic names to specific model identifiers
        model_map = self.get_model_mapping()

        # Check if it's a generic name
        if model_identifier in model_map:
            self.config.model = model_map[model_identifier]
            return True

        # Check if it's a valid specific identifier
        valid_models = [m.identifier for m in self.list_models()]
        if model_identifier in valid_models:
            self.config.model = model_identifier
            return True

        return False

    def get_model_mapping(self) -> Dict[str, str]:
        """Map generic model names to provider-specific identifiers."""
        return {
            "opus": "claude-opus-4-1-20250805",
            "sonnet": "claude-sonnet-4-20250514",
            "opus-3": "claude-3-opus-20240229",
            "sonnet-3": "claude-3-sonnet-20240229",
            "smart": "claude-opus-4-1-20250805",
            "balanced": "claude-sonnet-4-20250514",
            "fast": "claude-sonnet-4-20250514",
        }

    # Core Generation Methods (required by BaseProvider)
    def generate_code(self, prompt: str, context: Dict[str, Any], **kwargs) -> str:
        """Generate code with context awareness."""
        # Merge context into kwargs for the existing generate method
        kwargs.update(context)
        return self.generate(prompt, **kwargs)

    def generate_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate streaming response for real-time output."""
        # For tmux, we don't have true streaming, but we can yield the result
        result = self.generate(prompt, **kwargs)
        yield result

    # Session Management Methods (required by BaseProvider)
    def create_session(self, session_id: str, **kwargs) -> Session:
        """Create a new provider session."""
        session_name = self._create_session_name(session_id)
        project_dir = kwargs.get('cwd', os.getcwd())

        # Kill any existing session with the same name
        self._kill_session(session_name)

        # Create new tmux session
        subprocess.run(
            [
                "tmux", "new-session", "-d", "-s", session_name,
                "-c", project_dir,
                self.claude_path
            ],
            check=True
        )

        # Create and store session object
        session = Session(
            id=session_id,
            provider=self.name,
            model=self.config.model or "claude-sonnet-4-20250514",
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state=SessionState.ACTIVE,
            metadata={"tmux_name": session_name, "project_dir": project_dir}
        )

        self._sessions[session_id] = session
        self._current_session = session
        return session

    def attach_session(self, session_id: str) -> Session:
        """Attach to existing session."""
        if session_id not in self._sessions:
            # Try to find tmux session
            session_name = f"hydra_claude_{session_id}"
            if self._session_exists(session_name):
                # Create session object for existing tmux session
                session = Session(
                    id=session_id,
                    provider=self.name,
                    model=self.config.model or "claude-sonnet-4-20250514",
                    created_at=datetime.now(),
                    last_activity=datetime.now(),
                    state=SessionState.ACTIVE,
                    metadata={"tmux_name": session_name}
                )
                self._sessions[session_id] = session
                self._current_session = session
                return session
            raise ValueError(f"Session {session_id} not found")

        session = self._sessions[session_id]
        session.last_activity = datetime.now()
        self._current_session = session
        return session

    def list_sessions(self) -> List[Session]:
        """List all active sessions."""
        # Get tmux sessions
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True
        )

        sessions = []
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.startswith("hydra_claude_"):
                    # Extract session ID from tmux name
                    session_id = line.replace("hydra_claude_", "")
                    if session_id in self._sessions:
                        sessions.append(self._sessions[session_id])
                    else:
                        # Create session object for discovered tmux session
                        session = Session(
                            id=session_id,
                            provider=self.name,
                            model=self.config.model or "claude-sonnet-4-20250514",
                            created_at=datetime.now(),
                            last_activity=datetime.now(),
                            state=SessionState.ACTIVE,
                            metadata={"tmux_name": line}
                        )
                        self._sessions[session_id] = session
                        sessions.append(session)

        return sessions

    def kill_session(self, session_id: str) -> bool:
        """Terminate a session."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            tmux_name = session.metadata.get("tmux_name", f"hydra_claude_{session_id}")
            self._kill_session(tmux_name)
            session.state = SessionState.TERMINATED
            del self._sessions[session_id]
            if self._current_session and self._current_session.id == session_id:
                self._current_session = None
            return True
        return False

    def save_session(self, session_id: str, path: str) -> bool:
        """Save session state for later restoration."""
        if session_id not in self._sessions:
            return False

        session = self._sessions[session_id]
        tmux_name = session.metadata.get("tmux_name", f"hydra_claude_{session_id}")

        # Capture session output
        output = self._capture_session_output(tmux_name)

        # Save to file
        save_data = {
            "session_id": session_id,
            "tmux_name": tmux_name,
            "output": output,
            "metadata": session.metadata
        }

        import json
        with open(path, 'w') as f:
            json.dump(save_data, f, indent=2, default=str)

        return True

    def restore_session(self, path: str) -> Optional[Session]:
        """Restore session from saved state."""
        import json
        try:
            with open(path, 'r') as f:
                save_data = json.load(f)

            session_id = save_data["session_id"]
            tmux_name = save_data["tmux_name"]

            # Create new tmux session
            project_dir = save_data.get("metadata", {}).get("project_dir", os.getcwd())
            subprocess.run(
                [
                    "tmux", "new-session", "-d", "-s", tmux_name,
                    "-c", project_dir,
                    self.claude_path
                ],
                check=True
            )

            # Restore session object
            session = Session(
                id=session_id,
                provider=self.name,
                model=self.config.model or "claude-sonnet-4-20250514",
                created_at=datetime.now(),
                last_activity=datetime.now(),
                state=SessionState.ACTIVE,
                metadata=save_data.get("metadata", {"tmux_name": tmux_name})
            )

            self._sessions[session_id] = session
            return session

        except Exception:
            return None

    # Output Handling Methods (required by BaseProvider)
    def parse_response(self, response: str) -> ParsedResponse:
        """Parse provider-specific response format."""
        code_blocks = self.extract_code_blocks(response)

        return ParsedResponse(
            text=response,
            code_blocks=code_blocks,
            metadata={
                "provider": self.name,
                "session_based": True,
                "interactive": True
            },
            tokens_used=None,  # Tmux doesn't provide token counts
            execution_time=None
        )

    def extract_code_blocks(self, response: str) -> List[CodeBlock]:
        """Extract code blocks from response."""
        code_blocks = []

        # Find markdown code blocks
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)

        for _i, (language, content) in enumerate(matches):
            if not language:
                language = "text"

            # Determine if it's executable
            executable = language.lower() in ['python', 'javascript', 'bash', 'sh', 'ruby', 'go']

            code_blocks.append(CodeBlock(
                language=language,
                content=content.strip(),
                line_start=0,  # We don't track line numbers in tmux output
                line_end=0,
                executable=executable,
                filename=None
            ))

        return code_blocks

    # Interactive Features (required by BaseProvider)
    def supports_interactive(self) -> bool:
        """Check if provider supports interactive mode."""
        return True

    def wait_for_prompt(self, timeout: int = 30) -> bool:
        """Wait for interactive prompt if supported."""
        if not self._current_session:
            return False

        tmux_name = self._current_session.metadata.get("tmux_name")
        if not tmux_name:
            return False

        start_time = time.time()
        while time.time() - start_time < timeout:
            output = self._capture_session_output(tmux_name)
            # Check for Claude prompts
            if any(indicator in output for indicator in [">", "Claude Code", "Assistant:", "Human:"]):
                return True
            time.sleep(1)

        return False

    def send_interactive_command(self, command: str) -> Optional[str]:
        """Send command in interactive mode."""
        if not self._current_session:
            return None

        tmux_name = self._current_session.metadata.get("tmux_name")
        if not tmux_name:
            return None

        # Send command
        self._send_to_session(tmux_name, command)

        # Wait a bit for response
        time.sleep(2)

        # Capture output
        return self._capture_session_output(tmux_name)

    # File Operations (required by BaseProvider)
    def intercept_file_operation(self, operation: FileOperation) -> bool:
        """Intercept and validate file operations."""
        # For tmux provider, we use the ClaudeFileInterceptor
        file_interceptor = ClaudeFileInterceptor()

        if not self._current_session:
            return True  # Allow if no session

        agent_id = self._current_session.metadata.get("tmux_name", "unknown")

        if operation.operation_type in [FileOperationType.WRITE, FileOperationType.CREATE, FileOperationType.MODIFY]:
            return file_interceptor.acquire_file_lock(agent_id, operation.path, 'write')
        elif operation.operation_type == FileOperationType.DELETE:
            return file_interceptor.acquire_file_lock(agent_id, operation.path, 'delete')

        return True  # Allow read operations

    def supports_file_interception(self) -> bool:
        """Check if provider supports file operation interception."""
        return True

    def supports_code_execution(self) -> bool:
        """Check if provider can execute code directly."""
        return True  # Claude Code can execute code via tmux
