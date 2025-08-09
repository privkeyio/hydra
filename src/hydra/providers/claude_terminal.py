"""Claude Terminal Provider - Runs Claude Code in a proper terminal environment."""
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from .base import LLMProvider


class ClaudeTerminalProvider(LLMProvider):
    """Run Claude Code in a terminal with proper TTY for file operations."""

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
        return "claude_terminal"

    def generate(self, prompt: str, **kwargs) -> str:
        """Execute Claude in a terminal environment for file operations."""
        project_dir = kwargs.get('cwd', os.getcwd())

        # Escape the prompt for shell
        prompt.replace("'", "'\\''").replace('"', '\\"')

        # Create a temporary script that will be executed in the terminal
        script_content = f"""#!/bin/bash
set -e

# Change to project directory
cd "{project_dir}"

echo "Starting Claude Code session for ticket implementation..."
echo "Project directory: {project_dir}"
echo ""

# Create prompt file
cat > /tmp/claude_prompt.txt << 'PROMPT_EOF'
{prompt}
PROMPT_EOF

# Run Claude with the prompt file
{self.claude_path} < /tmp/claude_prompt.txt

# Clean up
rm -f /tmp/claude_prompt.txt

echo ""
echo "Claude Code session completed."
"""

        # Write the script
        script_path = Path("/tmp/hydra_claude_terminal.sh")
        script_path.write_text(script_content)
        script_path.chmod(0o755)

        try:
            # Use script command to provide a proper terminal environment
            # This ensures Claude has a TTY and can use all its interactive features
            terminal_cmd = [
                "script", "-q", "-c", str(script_path), "/dev/null"
            ]

            print("🖥️  Launching Claude Code in terminal mode...")
            print(f"📁 Working directory: {project_dir}")

            # Execute with proper terminal
            result = subprocess.run(
                terminal_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                cwd=project_dir,
                env={**os.environ, "TERM": "xterm-256color"}
            )

            # Check for created/modified files
            git_status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                cwd=project_dir
            )

            if git_status.stdout:
                print("✅ Files were modified:")
                for line in git_status.stdout.strip().split('\n'):
                    print(f"   {line}")
                return "Files have been successfully edited by Claude Code"
            else:
                # Even if git doesn't show changes, Claude may have worked on non-git files
                return result.stdout or "Claude Code session completed"

        except subprocess.TimeoutExpired:
            raise Exception(f"Claude terminal timeout after {self.config.timeout}s")
        except Exception as e:
            raise Exception(f"Claude terminal error: {str(e)}")
        finally:
            # Cleanup
            script_path.unlink(missing_ok=True)
            Path("/tmp/claude_instructions.txt").unlink(missing_ok=True)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Not used for terminal mode."""
        result = self.generate(prompt, **kwargs)
        return {"result": result}

    def stream_generate(self, prompt: str, **kwargs):
        """Not used for terminal mode."""
        yield self.generate(prompt, **kwargs)

    def list_models(self):
        """Return available models."""
        return ["claude-3-opus", "claude-3-sonnet"]
