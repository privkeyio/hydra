"""Factory for creating LLM providers dynamically.
"""
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
        return cls._providers.get(name.lower())

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered providers."""
        return list(cls._providers.keys())


def auto_register_providers():
    """Automatically register all providers in the providers directory."""
    providers_dir = os.path.dirname(__file__)

    # Manual provider registration with known names
    provider_map = {
        'venice': 'VeniceProvider',
        'anthropic': 'AnthropicProvider',
        'openai': 'OpenAIProvider',
        'claude_cli': 'ClaudeCLIProvider'
    }

    for filename in os.listdir(providers_dir):
        if filename.endswith('.py') and filename not in ['__init__.py', 'base.py', 'factory.py']:
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f'hydra.providers.{module_name}')
                # Look for classes that inherit from LLMProvider
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        issubclass(attr, LLMProvider) and
                        attr is not LLMProvider):
                        # Register using known provider names
                        for provider_name, class_name in provider_map.items():
                            if attr.__name__ == class_name:
                                ProviderRegistry.register(provider_name, attr)
                                break
            except Exception as e:
                # Only show warning for import errors, not instantiation errors
                if "requires api_key" not in str(e):
                    print(f"Warning: Failed to import provider {module_name}: {e}")


class LLMProviderFactory:
    """Factory for creating LLM provider instances."""

    def __init__(self):
        # Auto-register providers on first use
        if not ProviderRegistry.list_providers():
            auto_register_providers()

    def create(self, config: LLMConfig) -> LLMProvider:
        """Create an LLM provider instance from configuration."""
        provider_class = ProviderRegistry.get(config.provider_type)

        if not provider_class:
            available = ProviderRegistry.list_providers()
            raise ValueError(
                f"Unknown provider type: {config.provider_type}. "
                f"Available providers: {', '.join(available)}"
            )

        return provider_class(config)

    def list_providers(self) -> list[str]:
        """List available provider types."""
        return ProviderRegistry.list_providers()


# Global factory instance
factory = LLMProviderFactory()
