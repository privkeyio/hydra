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

    # Register core providers including Claude session provider
    provider_map = {
        'venice': 'VeniceProvider',
        'anthropic': 'AnthropicProvider', 
        'openai': 'OpenAIProvider',
        'mock': 'MockProvider',
        'claude_session': 'ClaudeSessionProvider',
        'claude_tmux': 'ClaudeTmuxProvider'
    }

    for filename in os.listdir(providers_dir):
        if (filename.endswith('.py') and
            filename not in ['__init__.py', 'base.py', 'factory.py']):
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
        # Auto-register core providers on first use
        if not any(p in ProviderRegistry._providers for p in ['venice', 'anthropic', 'openai', 'mock', 'claude_session']):
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


def create_claude_provider_factory():
    """Create a factory function for Claude providers suitable for WarmSessionPool.
    
    Returns:
        Callable that creates InteractiveAIProvider instances
    """
    def factory():
        try:
            # Try to import and create a Claude CLI provider
            from .interactive_base import InteractiveAIProvider, ProviderConfig
            from .claude_interactive_adapter import ClaudeInteractiveAdapter
            
            config = ProviderConfig(
                provider_name="claude_cli",
                auto_discover=True,
                session_timeout=300,
                max_concurrent_sessions=5
            )
            
            return ClaudeInteractiveAdapter(config)
            
        except ImportError:
            # Fallback to a basic Claude provider if interactive adapter not available
            try:
                from .claude_cli import ClaudeCLIProvider
                from .base import LLMConfig
                
                config = LLMConfig(
                    provider_type="claude_cli",
                    timeout=300
                )
                return ClaudeCLIProvider(config)
                
            except ImportError:
                raise RuntimeError("No Claude provider available for warm session pool")
                
    return factory


# Global factory instance
factory = LLMProviderFactory()
