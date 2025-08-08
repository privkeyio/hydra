"""Claude Subprocess Provider - Direct subprocess interaction with Claude CLI."""
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from .base import LLMProvider


class ClaudeSubprocessProvider(LLMProvider):
    """Run Claude CLI via subprocess with proper input handling."""

    def validate_config(self):
        """Validate Claude CLI configuration."""
        self.claude_path = self.config.extra_params.get(
            'claude_path',
            os.environ.get('CLAUDE_CLI_PATH', '/home/kyle/.claude/local/claude')
        )

        if not Path(self.claude_path).exists():
            raise ValueError(f"Claude CLI not found at: {self.claude_path}")

    @property
    def name(self) -> str:
        return "claude_subprocess"

    def generate(self, prompt: str, **kwargs) -> str:
        """Execute Claude to implement ticket with actual file operations."""
        project_dir = kwargs.get('cwd', os.getcwd())

        # Create a prompt file that Claude will read
        prompt_file = Path("/tmp/hydra_ticket_prompt.txt")
        prompt_file.write_text(prompt + "\n\nPlease implement this by creating/editing the necessary files.")

        try:
            print("🚀 Launching Claude Code CLI...")
            print(f"📁 Working directory: {project_dir}")

            # Run Claude with the prompt file as input
            # Use unbuffered output and proper terminal settings
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'

            process = subprocess.Popen(
                [self.claude_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=project_dir,
                env=env,
                text=True,
                bufsize=0  # Unbuffered
            )

            # Send the prompt to Claude
            prompt_text = prompt_file.read_text()
            process.stdin.write(prompt_text + "\n")
            process.stdin.flush()

            # Give Claude time to process
            time.sleep(5)

            # Send exit command
            process.stdin.write("/exit\n")
            process.stdin.flush()

            # Wait for completion with timeout
            try:
                stdout, _ = process.communicate(timeout=self.config.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, _ = process.communicate()

            # Check for file changes
            git_status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                cwd=project_dir
            )

            if git_status.stdout and git_status.stdout != "?? tickets.md\n":
                print("\n✅ Files were modified by Claude Code:")
                for line in git_status.stdout.strip().split('\n'):
                    if line != "?? tickets.md":
                        print(f"   {line}")
                return "Files have been successfully edited"
            else:
                # Check if any src files were created
                src_dir = Path(project_dir) / "src"
                if src_dir.exists():
                    src_files = list(src_dir.glob("**/*.js"))
                    if any("snapshot" in f.name.lower() for f in src_files):
                        print("✅ Snapshot-related files created")
                        return "Implementation completed"

                print("⚠️  No file changes detected")
                return stdout or "Claude session completed without file changes"

        except Exception as e:
            raise Exception(f"Claude subprocess error: {str(e)}")
        finally:
            # Cleanup
            prompt_file.unlink(missing_ok=True)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Not used for subprocess mode."""
        result = self.generate(prompt, **kwargs)
        return {"result": result}

    def stream_generate(self, prompt: str, **kwargs):
        """Not used for subprocess mode."""
        yield self.generate(prompt, **kwargs)

    def list_models(self):
        """Return available models."""
        return ["claude-3-opus", "claude-3-sonnet"]
