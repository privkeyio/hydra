"""Provider factory for creating provider instances with configuration.

This module provides the factory pattern for creating provider instances
as specified in the provider interface specification from Ticket 002.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from hydra.prompts.injection import initialize_default_injectors
from hydra.providers.base_provider import BaseProvider
from hydra.providers.error_handler import get_error_handler
from hydra.providers.provider_config import (
    ProviderConfig,
    get_active_provider_config,
    get_config_manager,
    get_provider_config,
)
from hydra.providers.provider_registry import get_registry

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating provider instances with configuration.

    This factory handles provider instantiation with proper configuration,
    environment variable handling, and error management.
    """

    def __init__(self):
        """Initialize the provider factory."""
        self.registry = get_registry()
        self.config_manager = get_config_manager()
        self.error_handler = get_error_handler()

        # Initialize default prompt injectors
        initialize_default_injectors()

    def create(
        self, provider_type: str, config: Optional[Dict[str, Any]] = None, **kwargs
    ) -> BaseProvider:
        """Create provider instance with configuration.

        Args:
            provider_type: Type of provider to create
            config: Optional configuration dictionary
            **kwargs: Additional provider parameters

        Returns:
            Configured provider instance

        Raises:
            ValueError: If provider type is not registered
            RuntimeError: If provider initialization fails

        """
        # Get provider configuration
        provider_config = self._get_provider_config(provider_type, config)

        # Create provider using registry
        try:
            provider = self.registry.create_provider(
                provider_type=provider_type, config=provider_config, **kwargs
            )

            logger.info(f"Created provider instance: {provider_type}")
            return provider

        except Exception as e:
            error = self.error_handler.handle_error(
                provider=provider_type,
                error=e,
                context={"factory": "create", "config": config},
            )
            raise RuntimeError(f"Failed to create provider: {error}") from e

    def from_environment(self) -> BaseProvider:
        """Create provider from environment variables.

        Uses LLM_PROVIDER environment variable to determine provider type,
        falling back to default configuration if not set.

        Returns:
            Provider instance configured from environment

        Raises:
            ValueError: If no provider can be determined

        """
        # Check environment variable
        provider_type = os.getenv("LLM_PROVIDER")

        if provider_type:
            logger.info(f"Creating provider from environment: {provider_type}")
            config = get_provider_config(provider_type)
            if not config:
                # Create minimal config from environment
                config = self._create_config_from_env(provider_type)
        else:
            # Use active provider from configuration
            config = get_active_provider_config()
            if not config:
                # Default to claude_tmux if nothing is configured
                logger.warning("No provider configured, defaulting to claude_tmux")
                provider_type = "claude_tmux"
                config = self._create_config_from_env(provider_type)
            else:
                provider_type = config.type

        # Apply environment overrides
        config = self._apply_env_overrides(config)

        # Handle provider type mismatches and fallbacks
        try:
            return self.create(provider_type, config.__dict__ if config else None)
        except RuntimeError as e:
            if "not registered" in str(e):
                # Try common fallbacks
                logger.warning(
                    f"Provider {provider_type} not available, trying claude_tmux"
                )
                fallback_config = self._create_config_from_env("claude_tmux")
                return self.create(
                    "claude_tmux", fallback_config.__dict__ if fallback_config else None
                )
            raise

    def create_with_fallback(
        self,
        primary_type: str,
        fallback_types: List[str],
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> BaseProvider:
        """Create provider with fallback options.

        Attempts to create primary provider, falling back to alternatives
        if initialization fails.

        Args:
            primary_type: Primary provider type to try
            fallback_types: List of fallback provider types
            config: Optional configuration
            **kwargs: Additional parameters

        Returns:
            First successfully created provider

        Raises:
            RuntimeError: If all providers fail to initialize

        """
        providers_to_try = [primary_type] + fallback_types
        errors = []

        for provider_type in providers_to_try:
            try:
                logger.info(f"Attempting to create provider: {provider_type}")
                return self.create(provider_type, config, **kwargs)
            except Exception as e:
                errors.append((provider_type, str(e)))
                logger.warning(f"Failed to create {provider_type}: {e}")
                continue

        # All providers failed
        error_msg = "Failed to create any provider:\n"
        for provider_type, error in errors:
            error_msg += f"  - {provider_type}: {error}\n"
        raise RuntimeError(error_msg)

    def _get_provider_config(
        self, provider_type: str, config_dict: Optional[Dict[str, Any]] = None
    ) -> Optional[ProviderConfig]:
        """Get or create provider configuration.

        Args:
            provider_type: Provider type
            config_dict: Optional configuration dictionary

        Returns:
            Provider configuration or None

        """
        if config_dict:
            # Create config from dictionary
            # Remove 'name' and 'type' if they exist to avoid duplicates
            config_copy = config_dict.copy()
            config_copy.pop("name", None)
            config_copy.pop("type", None)

            # Handle legacy 'model' parameter by mapping to 'default_model'
            if "model" in config_copy:
                config_copy["default_model"] = config_copy.pop("model")

            return ProviderConfig(name=provider_type, type=provider_type, **config_copy)

        # Get from configuration manager
        return get_provider_config(provider_type)

    def _create_config_from_env(self, provider_type: str) -> ProviderConfig:
        """Create minimal configuration from environment variables.

        Args:
            provider_type: Provider type

        Returns:
            Minimal provider configuration

        """
        config = ProviderConfig(name=provider_type, type=provider_type, enabled=True)

        # Check for common environment variables
        if provider_type == "venice" or provider_type == "venice_api":
            config.api_key = os.getenv("VENICE_API_KEY")
            config.base_url = os.getenv("VENICE_BASE_URL", "https://api.venice.ai/v1")

        elif "anthropic" in provider_type:
            config.api_key = os.getenv("ANTHROPIC_API_KEY")
            config.base_url = os.getenv(
                "ANTHROPIC_BASE_URL", "https://api.anthropic.com"
            )

        elif "openai" in provider_type:
            config.api_key = os.getenv("OPENAI_API_KEY")
            config.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

        elif "claude" in provider_type:
            config.cli_path = os.getenv("CLAUDE_CLI_PATH", "claude")

        # Apply common overrides
        if os.getenv("LLM_MODEL"):
            config.default_model = os.getenv("LLM_MODEL")

        if os.getenv("LLM_TIMEOUT"):
            config.extra_params["timeout"] = int(os.getenv("LLM_TIMEOUT"))

        if os.getenv("LLM_MAX_RETRIES"):
            config.extra_params["max_retries"] = int(os.getenv("LLM_MAX_RETRIES"))

        return config

    def _apply_env_overrides(self, config: ProviderConfig) -> ProviderConfig:
        """Apply environment variable overrides to configuration.

        Args:
            config: Base configuration

        Returns:
            Configuration with environment overrides applied

        """
        # Override model if specified
        if os.getenv("LLM_MODEL"):
            config.default_model = os.getenv("LLM_MODEL")

        # Override timeout
        if os.getenv("LLM_TIMEOUT"):
            config.extra_params["timeout"] = int(os.getenv("LLM_TIMEOUT"))

        # Override max retries
        if os.getenv("LLM_MAX_RETRIES"):
            config.extra_params["max_retries"] = int(os.getenv("LLM_MAX_RETRIES"))

        # Provider-specific overrides
        if config.type == "venice_api" and os.getenv("VENICE_API_KEY"):
            config.api_key = os.getenv("VENICE_API_KEY")

        elif "anthropic" in config.type and os.getenv("ANTHROPIC_API_KEY"):
            config.api_key = os.getenv("ANTHROPIC_API_KEY")

        elif "openai" in config.type and os.getenv("OPENAI_API_KEY"):
            config.api_key = os.getenv("OPENAI_API_KEY")

        return config

    def validate_provider(self, provider: BaseProvider) -> bool:
        """Validate that a provider is properly configured and functional.

        Args:
            provider: Provider instance to validate

        Returns:
            True if provider is valid and functional

        """
        try:
            # Check basic attributes
            if not hasattr(provider, "config"):
                logger.error("Provider missing config attribute")
                return False

            # Check if provider can list models
            models = provider.list_models()
            if not models:
                logger.warning("Provider has no available models")
                return False

            # Check if provider supports required operations
            capabilities = provider.get_capabilities()
            logger.info(f"Provider capabilities: {capabilities}")

            return True

        except Exception as e:
            logger.error(f"Provider validation failed: {e}")
            return False


# Global factory instance
_factory: Optional[ProviderFactory] = None


def get_factory() -> ProviderFactory:
    """Get global provider factory instance.

    Returns:
        Provider factory instance

    """
    global _factory
    if _factory is None:
        _factory = ProviderFactory()
    return _factory


def create_provider(provider_type: str, **kwargs) -> BaseProvider:
    """Create a provider instance using the global factory.

    Args:
        provider_type: Type of provider to create
        **kwargs: Provider configuration parameters

    Returns:
        Provider instance

    """
    return get_factory().create(provider_type, **kwargs)


def create_provider_from_environment() -> BaseProvider:
    """Create provider from environment variables.

    Returns:
        Provider configured from environment

    """
    return get_factory().from_environment()


def create_provider_with_fallback(
    primary: str, fallbacks: List[str], **kwargs
) -> BaseProvider:
    """Create provider with fallback options.

    Args:
        primary: Primary provider type
        fallbacks: Fallback provider types
        **kwargs: Configuration parameters

    Returns:
        First successfully created provider

    """
    return get_factory().create_with_fallback(primary, fallbacks, **kwargs)
