"""Venice AI provider implementation.
"""
import json
from typing import Any, Dict, List

from openai import OpenAI

from .base import LLMConfig, LLMProvider


class VeniceProvider(LLMProvider):
    """Venice AI provider using OpenAI-compatible API."""

    def validate_config(self):
        """Validate Venice-specific configuration."""
        if not self.config.api_key:
            raise ValueError("Venice provider requires api_key")

        # Set default Venice values
        if not self.config.base_url:
            self.config.base_url = "https://api.venice.ai/api/v1"

        # Default to coding model if not specified
        if not self.config.model:
            self.config.model = "qwen-2.5-coder-32b"

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )

    @property
    def name(self) -> str:
        return "venice"

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response from Venice AI."""
        try:
            # Merge kwargs with config
            temperature = kwargs.get('temperature', self.config.temperature)
            max_tokens = kwargs.get('max_tokens', self.config.max_tokens)

            # Add system message for better code generation
            messages = [
                {"role": "system", "content": "You are an expert Python programmer. Always respond with clean, well-structured code."},
                {"role": "user", "content": prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **self.config.extra_params
            )

            return response.choices[0].message.content

        except Exception as e:
            raise Exception(f"Venice API error: {str(e)}")

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from Venice AI."""
        # Add JSON instruction to prompt
        json_prompt = f"{prompt}\n\nIMPORTANT: Respond with ONLY valid JSON, no other text."

        response = self.generate(json_prompt, **kwargs)

        # Try to extract JSON from response
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
            # Fallback: try to find JSON in the response
            import re
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass

            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response}")

    def list_models(self) -> List[str]:
        """List available Venice models."""
        try:
            models = self.client.models.list()
            return [model.id for model in models.data]
        except Exception:
            # Return known models if API call fails
            return [
                "venice-uncensored",
                "qwen-2.5-coder-32b",
                "llama-3.3-70b",
                "llama-3.1-405b",
                "deepseek-coder-v2-lite",
                "qwen-2.5-qwq-32b"
            ]
