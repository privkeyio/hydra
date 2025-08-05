"""Anthropic Claude provider implementation.
"""
import json
from typing import Any, Dict, List

from anthropic import Anthropic

from .base import LLMConfig, LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def validate_config(self):
        """Validate Anthropic-specific configuration."""
        if not self.config.api_key:
            raise ValueError("Anthropic provider requires api_key")

        # Default to Sonnet if not specified
        if not self.config.model:
            self.config.model = "claude-3-5-sonnet-20241022"

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.client = Anthropic(api_key=self.config.api_key)

    @property
    def name(self) -> str:
        return "anthropic"

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response from Claude."""
        try:
            # Merge kwargs with config
            temperature = kwargs.get('temperature', self.config.temperature)
            max_tokens = kwargs.get('max_tokens', self.config.max_tokens)

            response = self.client.messages.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                **self.config.extra_params
            )

            return response.content[0].text

        except Exception as e:
            raise Exception(f"Anthropic API error: {str(e)}")

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from Claude."""
        # Add JSON instruction to prompt
        json_prompt = f"{prompt}\n\nRespond with ONLY valid JSON, no other text or formatting."

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
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response}")

    def list_models(self) -> List[str]:
        """List available Anthropic models."""
        # Anthropic doesn't provide a models endpoint, so return known models
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]
