"""Claude Session Provider - Runs Claude Code with configurable session backends."""
import os
import re
import time
from pathlib import Path
from hydra.utils.claude_path import get_claude_cli_path
from typing import Any, Dict, Optional

from .base import LLMProvider
from hydra.safety.claude_file_interceptor import ClaudeFileInterceptor
from hydra.sessions import (
    SessionConfig,
    SessionManager,
    SessionBackendType
)


class ClaudeSessionProvider(LLMProvider):
    """Run Claude Code using the best available session backend."""

    def __init__(self, config):
        self.session_manager = None
        super().__init__(config)

    def validate_config(self):
        """Validate Claude CLI configuration and initialize session manager."""
        self.claude_path = self.config.extra_params.get(
            'claude_path',
            os.environ.get('CLAUDE_CLI_PATH', get_claude_cli_path())
        )

        if not Path(self.claude_path).exists():
            raise ValueError(f"Claude CLI not found at: {self.claude_path}")

        # Get preferred backend from config
        preferred_backend = self.config.extra_params.get('preferred_backend', None)
        if preferred_backend:
            try:
                preferred_backend = SessionBackendType(preferred_backend)
            except ValueError:
                preferred_backend = None

        # Initialize session manager
        self.session_manager = SessionManager(preferred_backend=preferred_backend)
        
        # Check if any backend is available
        available_backends = self.session_manager.get_available_backends()
        if not available_backends:
            raise ValueError("No session backend available. Please install tmux or ensure Docker is running.")

    @property
    def name(self) -> str:
        return "claude_session"

    def generate(self, prompt: str, **kwargs) -> str:
        """Execute Claude using the best available session backend."""
        project_dir = kwargs.get('cwd', os.getcwd())
        ticket_id = kwargs.get('ticket_id', None)
        
        # Create session config
        session_config = SessionConfig(
            session_id=f"hydra_claude_{ticket_id}" if ticket_id else None,
            project_path=project_dir,
            timeout=self.config.timeout,
            metadata={'ticket_id': ticket_id} if ticket_id else None
        )

        # Initialize file interceptor for this session
        file_interceptor = ClaudeFileInterceptor()
        
        # Create session
        session_id, backend = self.session_manager.create_session(
            command=[self.claude_path],
            config=session_config
        )
        
        agent_id = session_id  # Use session ID as agent ID for locking

        # Create .hydra folder if it doesn't exist
        hydra_dir = Path(project_dir) / ".hydra"
        hydra_dir.mkdir(exist_ok=True)
        
        # Marker file to detect when Claude is done
        sessions_dir = hydra_dir / "sessions"
        sessions_dir.mkdir(exist_ok=True)
        done_marker = sessions_dir / f"done_{session_id}"
        if done_marker.exists():
            done_marker.unlink()

        try:
            print(f"🖥️  Starting {backend.backend_type.value} session: {session_id}")
            print(f"📁 Working directory: {project_dir}")

            # Wait for Claude to initialize
            print("⏳ Waiting for Claude Code to initialize...")
            initialization_timeout = 30
            start_init = time.time()
            claude_ready = False

            while time.time() - start_init < initialization_timeout:
                output = backend.capture_output(session_id)
                # Check for various Claude Code prompts
                if any(indicator in output for indicator in ["Welcome to Claude", ">", "Claude Code", "Assistant:"]):
                    claude_ready = True
                    print("✅ Claude Code is ready")
                    break
                time.sleep(1)

            if not claude_ready:
                print("⚠️  Claude Code initialization timeout - proceeding anyway")

            # Send the implementation prompt with explicit file creation permission
            print(f"📝 Sending task to Claude Code in session {session_id}...")
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
            
            backend.send_input(session_id, enhanced_prompt)

            # Give Claude time to process the prompt
            time.sleep(3)

            # Add instruction to create done marker (only if not already in prompt)
            if f"done_{session_id}" not in prompt:
                done_instruction = f"\nWhen you're completely done with all file operations, please create a file called .hydra/sessions/done_{session_id} to signal completion."
                backend.send_input(session_id, done_instruction)

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
                current_output = backend.capture_output(session_id)

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
                                backend.send_input(session_id, "2")
                            else:
                                print("🛑 Git operation detected - manual approval required")
                                break
                        elif "Yes, looks good" in current_output or "tell Claude what to do" in current_output:
                            # Only auto-approve if it's not git-related
                            if not any(git_cmd in current_output.lower() for git_cmd in git_indicators):
                                print("⚠️  Claude Code showing confirmation menu - selecting option 1 (Yes)")
                                backend.send_input(session_id, "1")
                            else:
                                print("🛑 Git operation detected - manual approval required")
                                break
                            no_change_count = 0  # Reset counter
                        elif any(indicator in current_output.lower() for indicator in prompt_indicators):
                            # Only auto-respond if it's not git-related
                            if not any(git_cmd in current_output.lower() for git_cmd in git_indicators):
                                print("⚠️  Detected prompt for user input - sending 'y' to continue")
                                backend.send_input(session_id, "y")
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
                            backend.send_input(session_id, "2")
                            time.sleep(2)  # Give Claude time to process
                        elif "Yes, looks good" in new_content or "tell Claude what to do" in new_content:
                            print("🔔 Claude Code is asking for confirmation - auto-approving...")
                            backend.send_input(session_id, "1")
                            time.sleep(2)  # Give Claude time to process
                        # Look for Claude Code tool usage patterns and show what it's doing
                        elif "Reading" in new_content:
                            # Extract file being read if possible
                            file_match = re.search(r'Reading[:\s]+([^\s]+)', new_content)
                            if file_match:
                                filepath = file_match.group(1)
                                print(f"👁️  Reading: {filepath}")
                            else:
                                print("👁️  Reading files...")
                        elif "Writing" in new_content or "Creating" in new_content:
                            file_match = re.search(r'(?:Writing|Creating)[:\s]+([^\s]+)', new_content)
                            if file_match:
                                filepath = file_match.group(1)
                                # Acquire file lock for write operation
                                if file_interceptor.acquire_file_lock(agent_id, filepath, 'write'):
                                    print(f"✍️  Writing: {filepath} [locked]")
                                else:
                                    print(f"⏳ Waiting for lock on: {filepath}")
                            else:
                                print("✍️  Writing new content...")
                        elif "Editing" in new_content:
                            file_match = re.search(r'Editing[:\s]+([^\s]+)', new_content)
                            if file_match:
                                filepath = file_match.group(1)
                                # Acquire file lock for edit operation
                                if file_interceptor.acquire_file_lock(agent_id, filepath, 'edit'):
                                    print(f"✏️  Editing: {filepath} [locked]")
                                else:
                                    print(f"⏳ Waiting for lock on: {filepath}")
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

                time.sleep(1)

            # Send exit command to Claude
            print("🛑 Ending Claude session...")
            backend.send_input(session_id, "/exit")
            time.sleep(2)

            # Check final results
            import subprocess
            git_status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                cwd=project_dir
            )

            if git_status.stdout.strip():
                changed_files = [line for line in git_status.stdout.strip().split('\n') 
                               if line and not line.endswith("tickets.md")]
                
                if changed_files:
                    print("\n✅ Files successfully modified by Claude Code:")
                    created_files = []
                    modified_files = []
                    
                    for line in changed_files:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            status = parts[0]
                            filepath = ' '.join(parts[1:])
                            if status == "M":
                                modified_files.append(filepath)
                            elif status == "A" or status == "??":
                                created_files.append(filepath)
                    
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
                    
                    return "Files have been successfully edited"

            return backend.capture_output(session_id) or "Claude session completed"

        except Exception as e:
            raise Exception(f"Claude session error: {str(e)}")
        finally:
            # Release all file locks for this agent
            file_interceptor.release_agent_locks(agent_id)
            # Terminate the session
            backend.terminate_session(session_id)
            # Clean up marker file
            done_marker.unlink(missing_ok=True)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response."""
        result = self.generate(prompt, **kwargs)
        return {"result": result}

    def stream_generate(self, prompt: str, **kwargs):
        """Stream generation (not implemented for session mode)."""
        yield self.generate(prompt, **kwargs)

    def list_models(self):
        """Return available models."""
        return ["claude-3-opus", "claude-3-sonnet"]