"""Interactive Claude CLI provider using pexpect for file operations."""
import os
import time
from pathlib import Path
from hydra.utils.claude_path import get_claude_cli_path
from typing import Any, Dict

import pexpect

from .base import LLMProvider


class ClaudeInteractiveProvider(LLMProvider):
    """Run Claude CLI interactively so it can edit files."""

    def validate_config(self):
        """Validate Claude CLI configuration."""
        self.claude_path = self.config.extra_params.get(
            'claude_path',
            os.environ.get('CLAUDE_CLI_PATH', get_claude_cli_path())
        )

        if not Path(self.claude_path).exists():
            raise ValueError(f"Claude CLI not found at: {self.claude_path}")

    @property
    def name(self) -> str:
        return "claude_interactive"

    def generate(self, prompt: str, **kwargs) -> str:
        """Run Claude interactively to implement a ticket."""
        # Start Claude in the project directory
        child = pexpect.spawn(
            self.claude_path,
            cwd=os.getcwd(),
            timeout=self.config.timeout,
            encoding='utf-8'
        )

        try:
            # Wait for Claude to be ready (look for prompt or welcome message)
            child.expect(['Welcome to Claude', '>', pexpect.TIMEOUT], timeout=10)

            # Send the implementation prompt
            child.sendline(prompt)

            # Add completion marker request
            child.sendline("\nWhen you're done implementing, please create a file called .hydra_done")

            # Monitor for completion
            start_time = time.time()
            output_lines = []
            done_marker = Path(os.getcwd()) / ".hydra_done"

            # Remove marker if exists
            if done_marker.exists():
                done_marker.unlink()

            while time.time() - start_time < self.config.timeout:
                try:
                    # Check for output
                    child.expect(['\n', pexpect.TIMEOUT], timeout=1)
                    line = child.before
                    if line:
                        output_lines.append(line)
                        print(f"Claude: {line}")  # Debug output

                    # Check if done marker exists
                    if done_marker.exists():
                        print("✅ Claude created completion marker")
                        done_marker.unlink()
                        child.sendline("/exit")
                        child.expect(pexpect.EOF, timeout=5)
                        return "Implementation complete - files have been edited"

                except pexpect.TIMEOUT:
                    # Check for done file periodically even without output
                    if done_marker.exists():
                        print("✅ Found completion marker")
                        done_marker.unlink()
                        child.sendline("/exit")
                        child.expect(pexpect.EOF, timeout=5)
                        return "Implementation complete - files have been edited"
                except pexpect.EOF:
                    # Claude exited
                    return '\n'.join(output_lines) or "Claude session ended"

            # Timeout reached
            child.sendline("/exit")
            child.expect(pexpect.EOF, timeout=5)
            raise Exception(f"Claude timeout after {self.config.timeout}s")

        except Exception as e:
            # Clean up
            try:
                child.terminate()
            except Exception:
                pass
            raise Exception(f"Claude interactive error: {str(e)}")
        finally:
            # Ensure child process is closed
            if child.isalive():
                child.close()

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Not used for interactive mode."""
        result = self.generate(prompt, **kwargs)
        return {"result": result}

    def stream_generate(self, prompt: str, **kwargs):
        """Not used for interactive mode."""
        yield self.generate(prompt, **kwargs)

    def list_models(self):
        """Return available models."""
        return ["claude-3-opus", "claude-3-sonnet"]
