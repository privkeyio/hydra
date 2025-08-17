"""Anthropic Claude provider implementation."""

from typing import Any, Dict, List, Optional

import orjson
from anthropic import Anthropic

from hydra.token_tracker import get_token_tracker

from .base import LLMConfig, LLMProvider
from .session_manager import get_session_manager


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

        # Use shared session manager for HTTP connections
        session_manager = get_session_manager()
        http_client = session_manager.get_session("anthropic")

        self.client = Anthropic(api_key=self.config.api_key, http_client=http_client)

        # Initialize token tracker
        self.token_tracker = get_token_tracker()
        self.ticket_id: Optional[int] = None
        self.session_id: Optional[int] = None

    @property
    def name(self) -> str:
        return "anthropic"

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response from Claude."""
        try:
            # Check budget before making request
            estimated_tokens = (
                self.token_tracker.count_tokens(prompt, "anthropic") + 1000
            )
            budget_ok, message = self.token_tracker.check_budget_available(
                estimated_tokens, self.config.model
            )
            if not budget_ok:
                raise ValueError(f"Token budget exceeded: {message}")

            # Merge kwargs with config
            temperature = kwargs.get("temperature", self.config.temperature)
            max_tokens = kwargs.get("max_tokens", self.config.max_tokens)

            response = self.client.messages.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                **self.config.extra_params,
            )

            response_text = response.content[0].text

            # Track token usage
            self.token_tracker.track_usage(
                provider="anthropic",
                model=self.config.model,
                prompt=prompt,
                response=response_text,
                ticket_id=self.ticket_id,
                session_id=self.session_id,
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "usage": getattr(response, "usage", None),
                },
            )

            return response_text

        except Exception as e:
            raise Exception(f"Anthropic API error: {str(e)}") from e

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from Claude."""
        # Add JSON instruction to prompt
        json_prompt = (
            f"{prompt}\n\nRespond with ONLY valid JSON, no other text or formatting."
        )

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

            return orjson.loads(response.strip())
        except orjson.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse JSON response: {e}\nResponse: {response}"
            ) from e

    def list_models(self) -> List[str]:
        """List available Anthropic models."""
        # Anthropic doesn't provide a models endpoint, so return known models
        return [
            "claude-3-5-sonnet-20241022",
            "claude-opus-4-1-20250805",
            "claude-3-sonnet-20240229",
        ]

    def set_tracking_context(
        self, ticket_id: Optional[int] = None, session_id: Optional[int] = None
    ) -> None:
        """Set context for token tracking.

        Args:
            ticket_id: Optional ticket ID for tracking
            session_id: Optional session ID for tracking

        """
        self.ticket_id = ticket_id
        self.session_id = session_id

    def cleanup(self) -> None:
        """Clean up provider resources."""
        super().cleanup()
        # Close HTTP session for this provider
        session_manager = get_session_manager()
        session_manager.close_session("anthropic")
