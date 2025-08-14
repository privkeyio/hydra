"""OpenAI provider implementation."""
from typing import Any, Dict, List

import orjson
from openai import OpenAI

from hydra.caching import lru_cache_with_bypass

from .base import LLMConfig, LLMProvider
from .session_manager import get_session_manager


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""

    def validate_config(self):
        """Validate OpenAI-specific configuration."""
        if not self.config.api_key:
            raise ValueError("OpenAI provider requires api_key")

        # Default to GPT-4 if not specified
        if not self.config.model:
            self.config.model = "gpt-4-turbo-preview"

    def __init__(self, config: LLMConfig):
        super().__init__(config)

        # Use shared session manager for HTTP connections
        session_manager = get_session_manager()
        http_client = session_manager.get_session("openai")

        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,  # Allow custom endpoints
            http_client=http_client
        )

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response from OpenAI."""
        try:
            # Merge kwargs with config
            temperature = kwargs.get('temperature', self.config.temperature)
            max_tokens = kwargs.get('max_tokens', self.config.max_tokens)

            # Add system message for better code generation
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert Python programmer. "
                        "Always respond with clean, well-structured code."
                    )
                },
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
            raise Exception(f"OpenAI API error: {str(e)}") from e

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from OpenAI."""
        # Use response_format for better JSON generation
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that responds in JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature),
                **self.config.extra_params
            )

            return orjson.loads(response.choices[0].message.content)

        except Exception:
            # Fallback to regular generation
            json_prompt = f"{prompt}\n\nRespond with ONLY valid JSON."
            response = self.generate(json_prompt, **kwargs)

            try:
                return orjson.loads(response.strip())
            except orjson.JSONDecodeError as e:
                raise ValueError(f"Failed to parse JSON response: {e}") from e

    @lru_cache_with_bypass(maxsize=16)
    def list_models(self) -> List[str]:
        """List available OpenAI models."""
        try:
            models = self.client.models.list()
            # Filter for chat models
            return [
                model.id for model in models.data
                if 'gpt' in model.id.lower() or 'o1' in model.id.lower()
            ]
        except Exception:
            # Return known models if API call fails
            return [
                "gpt-4-turbo-preview",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-3.5-turbo",
                "o1-preview",
                "o1-mini"
            ]

    def cleanup(self) -> None:
        """Clean up provider resources."""
        super().cleanup()
        # Close HTTP session for this provider
        session_manager = get_session_manager()
        session_manager.close_session("openai")
