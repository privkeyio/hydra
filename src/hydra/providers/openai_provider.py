"""OpenAI provider implementation."""

from typing import Any, Dict, List, Optional

import orjson
from openai import OpenAI

from hydra.caching import lru_cache_with_bypass
from hydra.prompts.injection import (
    InjectionContext,
    InjectorRegistry,
    initialize_default_injectors,
)
from hydra.prompts.optimization import optimize_prompt
from hydra.prompts.system_prompts import get_system_prompt
from hydra.token_tracker import get_token_tracker

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
            http_client=http_client,
        )

        # Initialize token tracker
        self.token_tracker = get_token_tracker()
        self.ticket_id: Optional[int] = None
        self.session_id: Optional[int] = None

        # Initialize prompt injection system
        self._injector_registry = InjectorRegistry()
        if not self._injector_registry.injectors:
            initialize_default_injectors()

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response from OpenAI."""
        try:
            # Check budget before making request
            estimated_tokens = self.token_tracker.count_tokens(prompt, "openai") + 1000
            budget_ok, message = self.token_tracker.check_budget_available(
                estimated_tokens, self.config.model
            )
            if not budget_ok:
                raise ValueError(f"Token budget exceeded: {message}")

            # Merge kwargs with config
            temperature = kwargs.get("temperature", self.config.temperature)
            max_tokens = kwargs.get("max_tokens", self.config.max_tokens)

            # Use injection system to prepare prompt
            injection_context = InjectionContext(
                operation="code_execution",
                provider=self.name,
                model=self.config.model,
                user_prompt=prompt,
                metadata={"temperature": temperature, "max_tokens": max_tokens}
            )

            injected_prompt = self._inject_prompts(injection_context)

            # Add system message and user prompt
            messages = [
                {"role": "system", "content": get_system_prompt("code")},
                {"role": "user", "content": injected_prompt},
            ]

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **self.config.extra_params,
            )

            response_text = response.choices[0].message.content

            # Track token usage (OpenAI provides usage in response)
            usage_data = response.usage if hasattr(response, "usage") else None
            if usage_data:
                # Use actual token counts from OpenAI
                input_tokens = usage_data.prompt_tokens
                output_tokens = usage_data.completion_tokens
            else:
                # Estimate if not provided
                input_tokens = self.token_tracker.count_tokens(str(messages), "openai")
                output_tokens = self.token_tracker.count_tokens(response_text, "openai")

            # Track usage with actual or estimated counts
            self.token_tracker.track_usage(
                provider="openai",
                model=self.config.model,
                prompt=prompt,
                response=response_text,
                ticket_id=self.ticket_id,
                session_id=self.session_id,
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "actual_input_tokens": input_tokens,
                    "actual_output_tokens": output_tokens,
                },
            )

            return response_text

        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}") from e

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from OpenAI."""
        # Use injection system for JSON generation
        injection_context = InjectionContext(
            operation="json_generation",
            provider=self.name,
            model=self.config.model,
            user_prompt=prompt,
            metadata={"format": "json"}
        )

        injected_prompt = self._inject_prompts(injection_context)

        # Use response_format for better JSON generation
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": get_system_prompt("json")},
                    {"role": "user", "content": injected_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=kwargs.get("temperature", self.config.temperature),
                **self.config.extra_params,
            )

            return orjson.loads(response.choices[0].message.content)

        except Exception:
            # Fallback to regular generation
            json_prompt = optimize_prompt(f"{prompt}\nJSON only.", "json_gen")
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
                model.id
                for model in models.data
                if "gpt" in model.id.lower() or "o1" in model.id.lower()
            ]
        except Exception:
            # Return known models if API call fails
            return [
                "gpt-4-turbo-preview",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-3.5-turbo",
                "o1-preview",
                "o1-mini",
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
        session_manager.close_session("openai")

    def _inject_prompts(self, context: InjectionContext) -> str:
        """Apply prompt injection based on context."""
        # Get appropriate injector for operation
        if "execution" in context.operation:
            injector = self._injector_registry.get("production")
        elif "verification" in context.operation:
            injector = self._injector_registry.get("verification")
        elif "ticket" in context.operation:
            injector = self._injector_registry.get("ticket")
        elif "json" in context.operation:
            # Apply minimal injection for JSON to preserve format
            return context.user_prompt + "\nJSON only."
        else:
            # Use production as default for safety
            injector = self._injector_registry.get("production")

        if injector:
            return injector.inject(context)

        return context.user_prompt
