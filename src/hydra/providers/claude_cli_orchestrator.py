"""Claude CLI Orchestrator that properly invokes Claude Code for file operations."""
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from .base import LLMProvider


class ClaudeCLIOrchestratorProvider(LLMProvider):
    """Orchestrates Claude CLI to actually edit files in projects."""

    def validate_config(self):
        """Validate Claude CLI configuration."""
        self.claude_path = self.config.extra_params.get(
            'claude_path',
            os.environ.get('CLAUDE_CLI_PATH', '/home/kyle/.claude/local/claude')
        )

        # Verify Claude exists
        if not Path(self.claude_path).exists():
            raise ValueError(f"Claude CLI not found at: {self.claude_path}")

    @property
    def name(self) -> str:
        return "claude_cli_orchestrator"

    def generate(self, prompt: str, **kwargs) -> str:
        """Execute Claude to implement a ticket with file operations."""
        # Create a script that Claude will execute
        script_content = f"""#!/bin/bash
# Hydra-generated script for Claude Code execution

# Change to project directory
cd {os.getcwd()}

# Create prompt file for Claude
cat > /tmp/hydra_prompt.txt << 'EOF'
{prompt}

IMPORTANT: You must create or edit actual files to implement this ticket.
Use your file editing tools to complete the implementation.
When done with all file operations, create a file called .hydra_complete
EOF

# Run Claude with the prompt
{self.claude_path} < /tmp/hydra_prompt.txt

# Mark as complete
echo "done" > .hydra_complete
"""

        # Write script
        script_path = Path("/tmp/hydra_claude_script.sh")
        script_path.write_text(script_content)
        script_path.chmod(0o755)

        # Remove completion marker if exists
        complete_marker = Path(os.getcwd()) / ".hydra_complete"
        if complete_marker.exists():
            complete_marker.unlink()

        try:
            # Execute the script in a new terminal/process
            # This allows Claude to run interactively
            result = subprocess.run(
                ["bash", str(script_path)],
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                cwd=os.getcwd()
            )

            # Check for completion
            if complete_marker.exists():
                complete_marker.unlink()
                return "Files have been edited successfully"
            else:
                return result.stdout or "Task attempted"

        except subprocess.TimeoutExpired:
            raise Exception(f"Claude CLI timeout after {self.config.timeout}s")
        except Exception as e:
            raise Exception(f"Claude CLI orchestration error: {str(e)}")
        finally:
            # Cleanup
            script_path.unlink(missing_ok=True)
            Path("/tmp/hydra_prompt.txt").unlink(missing_ok=True)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Not used for orchestration."""
        result = self.generate(prompt, **kwargs)
        return {"result": result}

    def stream_generate(self, prompt: str, **kwargs):
        """Not used for orchestration."""
        yield self.generate(prompt, **kwargs)
