"""Factory for creating LLM providers dynamically."""

import importlib
import os
from typing import Dict, Optional, Type

from .base import LLMConfig, LLMProvider


class ProviderRegistry:
    """Registry for available LLM providers."""

    _providers: Dict[str, Type[LLMProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: Type[LLMProvider]):
        """Register a provider class."""
        cls._providers[name.lower()] = provider_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[LLMProvider]]:
        """Get a provider class by name."""
        # First check registered providers
        provider_class = cls._providers.get(name.lower())
        if provider_class:
            return provider_class

        # Check plugins if not found in core providers
        try:
            from hydra.plugins.loader import get_plugin_loader

            plugin_loader = get_plugin_loader()
            return plugin_loader.get_provider_class(name)
        except ImportError:
            # Plugin system not available
            pass

        return None

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered providers."""
        providers = list(cls._providers.keys())

        # Add plugin providers
        try:
            from hydra.plugins.loader import get_plugin_loader

            plugin_loader = get_plugin_loader()
            providers.extend(plugin_loader.list_available_providers())
        except ImportError:
            # Plugin system not available
            pass

        return list(set(providers))  # Remove duplicates


def auto_register_providers():
    """Automatically register core providers in the providers directory."""
    providers_dir = os.path.dirname(__file__)

    # Register core providers including unified Claude provider
    provider_map = {
        "venice": "VeniceProvider",
        "anthropic": "AnthropicProvider",
        "openai": "OpenAIProvider",
        "mock": "MockProvider",
        "mock_provider": "MockProvider",  # Alias for compatibility
        "claude": "ClaudeUnifiedProvider",
        "claude_cli": "ClaudeUnifiedProvider",  # Legacy alias
        "claude_tmux": "ClaudeUnifiedProvider",  # Legacy alias
        "claude_enhanced": "ClaudeUnifiedProvider",  # Legacy alias
    }

    for filename in os.listdir(providers_dir):
        if filename.endswith(".py") and filename not in [
            "__init__.py",
            "base.py",
            "factory.py",
        ]:
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f"hydra.providers.{module_name}")
                # Look for classes that inherit from LLMProvider
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, LLMProvider)
                        and attr is not LLMProvider
                    ):
                        # Register using known provider names
                        for provider_name, class_name in provider_map.items():
                            if attr.__name__ == class_name:
                                ProviderRegistry.register(provider_name, attr)
            except Exception as e:
                # Only show warning for import errors, not instantiation errors
                if "requires api_key" not in str(e):
                    print(f"Warning: Failed to import provider {module_name}: {e}")


class LLMProviderFactory:
    """Factory for creating LLM provider instances."""

    def __init__(self):
        # Auto-register core providers on first use
        if not any(
            p in ProviderRegistry._providers
            for p in ["venice", "anthropic", "openai", "mock", "claude"]
        ):
            auto_register_providers()

    def create(self, config: LLMConfig) -> LLMProvider:
        """Create an LLM provider instance from configuration."""
        from .error_handler import get_error_handler
        from .fallback_provider import FallbackProvider

        # Check if fallback mode is requested
        if config.provider_type == "fallback" or config.extra_params.get(
            "enable_fallback"
        ):
            return FallbackProvider(config)

        provider_class = ProviderRegistry.get(config.provider_type)

        if not provider_class:
            available = ProviderRegistry.list_providers()
            error_msg = (
                f"Unknown provider type: {config.provider_type}. "
                f"Available providers: {', '.join(available)}"
            )

            # Log error for tracking
            error_handler = get_error_handler()
            from .error_handler import ErrorCategory, ErrorSeverity, ProviderError

            error_handler.error_history.append(
                ProviderError(
                    provider=config.provider_type,
                    category=ErrorCategory.INITIALIZATION,
                    severity=ErrorSeverity.CRITICAL,
                    message=error_msg,
                    original_error=ValueError(error_msg),
                )
            )
            raise ValueError(error_msg)

        try:
            provider = provider_class(config)

            # Validate provider if possible
            if hasattr(provider, "validate_config"):
                provider.validate_config()

            return provider

        except Exception as e:
            # Handle initialization errors
            error_handler = get_error_handler()
            from .error_handler import ErrorCategory, ErrorSeverity

            provider_error = error_handler.handle_error(
                provider=config.provider_type,
                error=e,
                context={"initialization": True, "config": config.__dict__},
            )

            # If fallback is available and error is critical, try fallback
            if config.extra_params.get("auto_fallback") and provider_error.severity in [
                ErrorSeverity.CRITICAL,
                ErrorSeverity.HIGH,
            ]:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Provider {config.provider_type} failed to initialize, attempting fallback"
                )

                fallback_config = LLMConfig(
                    provider_type="fallback",
                    model=config.model,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    timeout=config.timeout,
                    api_key=config.api_key,
                    base_url=config.base_url,
                    extra_params={
                        **config.extra_params,
                        "fallback_providers": config.extra_params.get(
                            "fallback_providers", []
                        ),
                    },
                )
                return FallbackProvider(fallback_config)

            # Re-raise with better error message
            raise Exception(
                f"Failed to initialize provider {config.provider_type}: {provider_error}"
            ) from e

    def list_providers(self) -> list[str]:
        """List available provider types."""
        return ProviderRegistry.list_providers()


def create_claude_provider_factory():
    """Create a factory function for Claude providers suitable for WarmSessionPool.

    Returns:
        Callable that creates InteractiveAIProvider instances

    """

    def factory():
        try:
            # Try to import and create a Claude CLI provider
            from .claude_interactive_adapter import ClaudeInteractiveAdapter
            from .interactive_base import InteractiveAIProvider, ProviderConfig

            config = ProviderConfig(
                provider_name="claude_cli",
                auto_discover=True,
                session_timeout=300,
                max_concurrent_sessions=5,
            )

            return ClaudeInteractiveAdapter(config)

        except ImportError:
            # Fallback to the unified Claude provider
            try:
                from .base import LLMConfig
                from .claude_unified import ClaudeUnifiedProvider

                config = LLMConfig(provider_type="claude", timeout=300)
                return ClaudeUnifiedProvider(config)

            except ImportError:
                raise RuntimeError("No Claude provider available for warm session pool")

    return factory


# Global factory instance
factory = LLMProviderFactory()
