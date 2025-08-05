"""
Claude CLI provider implementation.
"""
import json
import subprocess
import os
from typing import Dict, Any, List
from .base import LLMProvider, LLMConfig


class ClaudeCLIProvider(LLMProvider):
    """Claude CLI provider for local Claude installation."""
    
    def validate_config(self):
        """Validate Claude CLI configuration."""
        # Check if claude_path is provided or claude is in PATH
        claude_path = self.config.extra_params.get('claude_path', 'claude')
        
        # Test if claude is accessible
        try:
            result = subprocess.run(
                [claude_path, "--version"],
                capture_output=True,
                timeout=5,
                shell=True if ' ' in claude_path else False
            )
            if result.returncode != 0:
                raise ValueError(f"Claude CLI not found at: {claude_path}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            raise ValueError(
                f"Claude CLI not accessible. Please set 'claude_path' in extra_params "
                f"or ensure 'claude' is in your PATH"
            )
        
        self.claude_path = claude_path
    
    @property
    def name(self) -> str:
        return "claude_cli"
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response using Claude CLI."""
        try:
            # Build command
            cmd = f'{self.claude_path} "{prompt}"'
            
            # Add any CLI flags from extra_params
            cli_flags = self.config.extra_params.get('cli_flags', '')
            if cli_flags:
                cmd = f'{self.claude_path} {cli_flags} "{prompt}"'
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                raise Exception(f"Claude CLI error: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            raise Exception(f"Claude CLI timeout after {self.config.timeout}s")
        except Exception as e:
            raise Exception(f"Claude CLI error: {str(e)}")
    
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
                except:
                    pass
            
            raise ValueError(f"Failed to parse JSON response: {e}")
    
    def list_models(self) -> List[str]:
        """List available models (CLI doesn't support multiple models)."""
        return ["claude-cli-default"]