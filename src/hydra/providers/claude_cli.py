"""Claude CLI provider implementation."""
import json
import os
import subprocess
from typing import Any, Dict, List

from .base import LLMProvider


class ClaudeCLIProvider(LLMProvider):
    """Claude CLI provider for local Claude installation."""

    def validate_config(self):
        """Validate Claude CLI configuration."""
        # Check if claude_path is provided or claude is in PATH
        claude_path = self.config.extra_params.get('claude_path', 'claude')

        # Test if claude is accessible by checking if it exists
        try:
            # For Claude Code CLI, we just check if the command exists
            result = subprocess.run(
                ["which", claude_path],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                raise ValueError(f"Claude CLI not found at: {claude_path}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            raise ValueError(
                "Claude CLI not accessible. Please set 'claude_path' in extra_params "
                "or ensure 'claude' is in your PATH"
            ) from None

        self.claude_path = claude_path

    @property
    def name(self) -> str:
        return "claude_cli"

    def _clean_claude_output(self, output: str) -> str:
        """Clean Claude CLI output by removing interface artifacts."""
        lines = output.split('\n')
        response_lines = []
        in_response = False

        for line in lines:
            # Skip welcome box and prompts
            if any(char in line for char in ['┃', '╭', '╰', '│']):
                continue
            if line.strip().startswith('cwd:'):
                continue
            if line.strip() == '':
                if in_response:
                    response_lines.append(line)
                continue

            # Start collecting response after welcome
            if not in_response and not line.startswith('Welcome'):
                in_response = True

            if in_response:
                response_lines.append(line)

        return '\n'.join(response_lines).strip()

    def _execute_claude_command(self, prompt: str) -> subprocess.CompletedProcess:
        """Execute Claude CLI command."""
        full_prompt = f"{prompt}\n/exit\n"
        return subprocess.run(
            [self.claude_path],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=self.config.timeout,
            env=os.environ.copy()
        )

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response using Claude CLI."""
        try:
            result = self._execute_claude_command(prompt)

            if result.returncode == 0:
                return self._clean_claude_output(result.stdout)
            else:
                raise Exception(f"Claude CLI error: {result.stderr}")

        except subprocess.TimeoutExpired as e:
            raise Exception(f"Claude CLI timeout after {self.config.timeout}s") from e
        except Exception as e:
            raise Exception(f"Claude CLI error: {str(e)}") from e

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from Claude CLI."""
        # Add JSON instruction to prompt
        json_prompt = f"{prompt}\n\nRespond with ONLY valid JSON, no other text."

        response = self.generate(json_prompt, **kwargs)

        # Try to parse JSON
        try:
            # Clean up common issues
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            return json.loads(response.strip())
        except json.JSONDecodeError as e:
            # Try to find JSON in response
            import re
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            raise ValueError(f"Failed to parse JSON response: {e}") from e

    def list_models(self) -> List[str]:
        """List available models (CLI doesn't support multiple models)."""
        return ["claude-cli-default"]
