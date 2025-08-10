"""Direct Claude CLI invocation that allows file editing."""
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from hydra.utils.claude_path import get_claude_cli_path
from .base import LLMProvider


class ClaudeCLIDirectProvider(LLMProvider):
    """Claude CLI provider that runs Claude directly to edit files."""

    def validate_config(self):
        """Validate Claude CLI configuration."""
        claude_path = self.config.extra_params.get('claude_path', get_claude_cli_path())

        if not Path(claude_path).exists():
            # Try to find it
            result = subprocess.run(["which", "claude"], capture_output=True, text=True)
            if result.returncode == 0:
                claude_path = result.stdout.strip()
            else:
                raise ValueError(f"Claude CLI not found at: {claude_path}")

        self.claude_path = claude_path

    @property
    def name(self) -> str:
        return "claude_cli_direct"

    def generate(self, prompt: str, **kwargs) -> str:
        """Execute Claude with the ability to edit files."""
        # Create a temporary script file with the prompt
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(prompt)
            f.write("\n\nWhen done, write 'COMPLETE' to a file called .claude_done\n")
            prompt_file = f.name

        try:
            # Remove any existing completion marker
            done_file = Path('.claude_done')
            if done_file.exists():
                done_file.unlink()

            # Run Claude with the prompt file as input
            # This allows Claude to actually edit files in the current directory
            process = subprocess.Popen(
                [self.claude_path],
                stdin=open(prompt_file, 'r'),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.getcwd()
            )

            # Wait for completion with timeout
            timeout = self.config.timeout
            start_time = time.time()

            while time.time() - start_time < timeout:
                # Check if Claude created the done marker
                if done_file.exists():
                    process.terminate()
                    done_file.unlink()
                    return "Implementation complete - files have been edited"

                # Check if process ended
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    if process.returncode == 0:
                        return stdout or "Implementation complete"
                    else:
                        raise Exception(f"Claude CLI error: {stderr}")

                time.sleep(1)

            # Timeout
            process.terminate()
            raise Exception(f"Claude CLI timeout after {timeout}s")

        finally:
            # Clean up temp file
            Path(prompt_file).unlink(missing_ok=True)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Not supported for direct file editing mode."""
        raise NotImplementedError("JSON generation not supported in direct mode")

    def stream_generate(self, prompt: str, **kwargs):
        """Not supported for direct file editing mode."""
        raise NotImplementedError("Streaming not supported in direct mode")
