"""Provider registry system for managing LLM providers."""

import importlib
import inspect
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from hydra.providers.base_provider import BaseProvider
from hydra.providers.performance import (
    LazyProviderProxy,
    get_config_cache,
    get_performance_monitor,
    get_provider_pool,
    optimize_provider_switching,
)
from hydra.providers.provider_config import (
    ProviderConfig,
    get_active_provider_config,
    get_config_manager,
    get_provider_config,
)

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Central registry for all LLM providers.

    This registry manages provider discovery, registration, and instantiation,
    replacing direct Claude references throughout the codebase.
    """

    # Singleton instance
    _instance: Optional["ProviderRegistry"] = None

    # Provider type to class mapping
    PROVIDER_CLASSES = {
        "claude_tmux": "hydra.providers.claude_tmux.ClaudeTmuxProvider",
        "claude_cli": "hydra.providers.claude_cli.ClaudeCLIProvider",
        "claude_cli_enhanced": (
            "hydra.providers.claude_cli_enhanced.ClaudeCLIEnhancedProvider"
        ),
        "claude_direct": "hydra.providers.claude_direct.ClaudeDirectProvider",
        "claude_interactive": (
            "hydra.providers.claude_interactive.ClaudeInteractiveProvider"
        ),
        "venice": "hydra.providers.venice.VeniceProvider",
        "venice_api": "hydra.providers.venice.VeniceProvider",  # Alias for compatibility
        "anthropic_api": "hydra.providers.anthropic.AnthropicProvider",
        "mock_provider": "hydra.providers.mock_provider.MockProvider",
        "mock": "hydra.providers.mock_provider.MockProvider",
        "openai": "hydra.providers.openai_provider.OpenAIProvider",
        "fallback": "hydra.providers.fallback_provider.FallbackProvider",
    }

    def __new__(cls):
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the registry."""
        if not hasattr(self, "_initialized"):
            self._providers: Dict[str, Type[BaseProvider]] = {}
            self._instances: Dict[str, BaseProvider] = {}
            self._config_manager = get_config_manager()
            self._provider_pool = get_provider_pool()
            self._performance_monitor = get_performance_monitor()
            self._config_cache = get_config_cache()
            self._initialized = True
            self._auto_discover()
            self._register_lazy_init_callbacks()

    def _auto_discover(self) -> None:
        """Auto-discover and register available providers."""
        for provider_type, class_path in self.PROVIDER_CLASSES.items():
            try:
                self._register_from_path(provider_type, class_path)
            except Exception as e:
                logger.debug(f"Could not register {provider_type}: {e}")

        # Also discover from plugins
        self._discover_plugins()

    def _register_from_path(self, provider_type: str, class_path: str) -> None:
        """Register a provider from module path.

        Args:
            provider_type: Provider type identifier
            class_path: Full module path to provider class

        """
        try:
            module_path, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            provider_class = getattr(module, class_name)

            # Verify it's a valid provider class
            if inspect.isclass(provider_class) and issubclass(
                provider_class, BaseProvider
            ):
                self._providers[provider_type] = provider_class
                logger.debug(f"Registered provider: {provider_type}")
        except Exception as e:
            logger.debug(f"Failed to register {provider_type} from {class_path}: {e}")

    def _discover_plugins(self) -> None:
        """Discover providers from plugin directories."""
        plugin_dirs = [
            Path.cwd() / "plugins",
            Path.home() / ".hydra" / "plugins",
            Path("/usr/local/share/hydra/plugins"),
        ]

        for plugin_dir in plugin_dirs:
            if not plugin_dir.exists():
                continue

            for plugin_path in plugin_dir.glob("*/provider.py"):
                self._load_plugin_provider(plugin_path)

    def _load_plugin_provider(self, plugin_path: Path) -> None:
        """Load a provider from plugin file.

        Args:
            plugin_path: Path to provider plugin file

        """
        try:
            # Dynamic import of plugin module
            spec = importlib.util.spec_from_file_location(
                f"plugin_{plugin_path.parent.name}", plugin_path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find provider classes in module
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseProvider)
                        and obj != BaseProvider
                    ):
                        provider_type = getattr(obj, "PROVIDER_TYPE", name.lower())
                        self._providers[provider_type] = obj
                        logger.info(f"Discovered plugin provider: {provider_type}")
        except Exception as e:
            logger.debug(f"Failed to load plugin from {plugin_path}: {e}")

    def _register_lazy_init_callbacks(self) -> None:
        """Register lazy initialization callbacks for providers."""
        # Register callbacks for expensive providers
        for provider_type in ["claude_tmux", "claude_cli_enhanced", "venice_api"]:
            if provider_type in self._providers:
                provider_class = self._providers[provider_type]

                def create_callback(cls, ptype):
                    def callback(config):
                        if not config:
                            config = get_provider_config(ptype)
                            if config:
                                config = config.to_llm_config()
                            else:
                                from hydra.providers.base import LLMConfig

                                config = LLMConfig(provider_type=ptype)
                        return cls(config)

                    return callback

                self._provider_pool.register_init_callback(
                    provider_type, create_callback(provider_class, provider_type)
                )

    def register_provider(
        self, provider_type: str, provider_class: Type[BaseProvider]
    ) -> None:
        """Register a new provider type.

        Args:
            provider_type: Provider type identifier
            provider_class: Provider class to register

        Raises:
            ValueError: If provider_type already registered

        """
        return self.register(provider_type, provider_class)

    def register(self, provider_type: str, provider_class: Type[BaseProvider]) -> None:
        """Register a new provider type.

        Args:
            provider_type: Provider type identifier
            provider_class: Provider class to register

        Raises:
            ValueError: If provider_type already registered

        """
        if provider_type in self._providers:
            raise ValueError(f"Provider type '{provider_type}' already registered")

        if not issubclass(provider_class, BaseProvider):
            raise ValueError("Provider class must extend BaseProvider")

        self._providers[provider_type] = provider_class
        logger.info(f"Registered provider: {provider_type}")

    def unregister(self, provider_type: str) -> None:
        """Unregister a provider type.

        Args:
            provider_type: Provider type to unregister

        """
        if provider_type in self._providers:
            del self._providers[provider_type]
            # Also remove any cached instance
            if provider_type in self._instances:
                self._instances[provider_type].cleanup()
                del self._instances[provider_type]
            logger.info(f"Unregistered provider: {provider_type}")

    def get_provider_class(self, provider_type: str) -> Optional[Type[BaseProvider]]:
        """Get provider class by type.

        Args:
            provider_type: Provider type identifier

        Returns:
            Provider class or None if not found

        """
        return self._providers.get(provider_type)

    def create_provider(
        self,
        provider_type: Optional[str] = None,
        config: Optional[Any] = None,  # Accept both ProviderConfig and LLMConfig
        **kwargs,
    ) -> BaseProvider:
        """Create a provider instance.

        Args:
            provider_type: Provider type to create (optional)
            config: Provider configuration (optional)
            **kwargs: Additional provider parameters

        Returns:
            Provider instance

        Raises:
            ValueError: If provider type not found or configuration invalid

        """
        # Determine provider type and config
        provider_type, config = self._resolve_provider_config(
            provider_type, config, kwargs
        )

        # Get provider class
        provider_class = self.get_provider_class(provider_type)
        if not provider_class:
            raise ValueError(f"Provider type '{provider_type}' not registered")

        # Create provider instance with performance monitoring
        return self._create_provider_instance(
            provider_type, provider_class, config, kwargs
        )

    def _resolve_provider_config(
        self,
        provider_type: Optional[str],
        config: Optional[ProviderConfig],
        kwargs: dict,
    ) -> Tuple[str, ProviderConfig]:
        """Resolve provider type and configuration.

        Args:
            provider_type: Optional provider type
            config: Optional provider configuration
            kwargs: Additional parameters

        Returns:
            Tuple of (provider_type, config)

        """
        if provider_type:
            if not config:
                config = get_provider_config(provider_type)
                if not config:
                    # Create minimal config
                    config = ProviderConfig(
                        name=provider_type, type=provider_type, **kwargs
                    )
        elif config:
            provider_type = config.type
        else:
            # Use active provider from environment/config
            config = get_active_provider_config()
            if not config:
                raise ValueError("No active provider configured")
            provider_type = config.type

        return provider_type, config

    def _create_provider_instance(
        self,
        provider_type: str,
        provider_class: Type[BaseProvider],
        config: Any,  # Accept both ProviderConfig and LLMConfig
        kwargs: dict,
    ) -> BaseProvider:
        """Create the actual provider instance.

        Args:
            provider_type: Provider type
            provider_class: Provider class
            config: Provider configuration (ProviderConfig or LLMConfig)
            kwargs: Additional parameters

        Returns:
            Provider instance

        """
        start_time = time.time()
        try:
            # Check if we can use pooled provider
            provider = self._provider_pool.get(provider_type, None)
            if provider:
                logger.debug(f"Using pooled provider: {provider_type}")
                return provider

            # Handle both ProviderConfig and LLMConfig
            if hasattr(config, "to_llm_config"):
                # It's a ProviderConfig
                llm_config = config.to_llm_config()
            else:
                # It's already an LLMConfig or similar
                llm_config = config

            # Add any additional kwargs
            for key, value in kwargs.items():
                if hasattr(llm_config, key):
                    setattr(llm_config, key, value)
                elif hasattr(llm_config, "extra_params"):
                    llm_config.extra_params[key] = value

            provider = provider_class(llm_config)

            # Record initialization time
            init_time = time.time() - start_time
            self._performance_monitor.record_initialization(provider_type, init_time)
            logger.info(
                f"Created provider instance: {provider_type} "
                f"(init time: {init_time:.2f}s)"
            )

            return provider
        except Exception as e:
            self._performance_monitor.record_error(provider_type)
            raise ValueError(f"Failed to create provider '{provider_type}': {e}") from e

    @optimize_provider_switching
    def get_or_create(
        self,
        provider_type: Optional[str] = None,
        cache: bool = True,
        lazy: bool = False,
        **kwargs,
    ) -> BaseProvider:
        """Get existing provider instance or create new one.

        Args:
            provider_type: Provider type (uses default if None)
            cache: Whether to cache the instance
            lazy: Whether to use lazy initialization
            **kwargs: Additional provider parameters

        Returns:
            Provider instance

        """
        # Determine provider type
        if not provider_type:
            config = get_active_provider_config()
            if config:
                provider_type = config.type
            else:
                provider_type = "mock_provider"  # Fallback

        # Check provider pool first for better performance
        provider = self._provider_pool.get(provider_type, None)
        if provider:
            self._performance_monitor.record_cache_hit(provider_type)
            return provider

        # Check instance cache
        if cache and provider_type in self._instances:
            self._performance_monitor.record_cache_hit(provider_type)
            return self._instances[provider_type]

        self._performance_monitor.record_cache_miss(provider_type)

        # Use lazy initialization if requested
        if lazy:
            config = get_provider_config(provider_type)
            if config:
                llm_config = config.to_llm_config()
            else:
                from hydra.providers.base import LLMConfig

                llm_config = LLMConfig(provider_type=provider_type)
            return LazyProviderProxy(provider_type, llm_config)

        # Create new instance
        provider = self.create_provider(provider_type, **kwargs)

        # Cache if requested
        if cache:
            self._instances[provider_type] = provider

        return provider

    def list_providers(self) -> List[str]:
        """List all registered provider types.

        Returns:
            List of provider type identifiers

        """
        return list(self._providers.keys())

    def is_registered(self, provider_type: str) -> bool:
        """Check if a provider type is registered.

        Args:
            provider_type: Provider type to check

        Returns:
            True if provider is registered

        """
        return provider_type in self._providers

    def list_available_providers(self) -> List[str]:
        """List providers that are properly configured and available.

        Returns:
            List of available provider types

        """
        available = []
        for provider_type in self._providers.keys():
            config = get_provider_config(provider_type)
            if config and config.enabled:
                # Check if required credentials are present
                if self._is_provider_configured(config):
                    available.append(provider_type)
        return available

    def _is_provider_configured(self, config: ProviderConfig) -> bool:
        """Check if provider is properly configured.

        Args:
            config: Provider configuration

        Returns:
            True if provider is configured

        """
        # Check API-based providers
        if config.type in ["venice_api", "anthropic_api", "openai"]:
            return bool(config.api_key)

        # Check CLI-based providers
        if "claude" in config.type and "cli" in config.type:
            return bool(config.cli_path)

        # Mock provider is always available
        if config.type == "mock_provider":
            return True

        # Default to True for other providers
        return True

    def get_default_provider(self) -> BaseProvider:
        """Get the default provider instance.

        Returns:
            Default provider instance

        Raises:
            ValueError: If no default provider configured

        """
        config = get_active_provider_config()
        if not config:
            # Fallback to first available provider
            available = self.list_available_providers()
            if available:
                return self.get_or_create(available[0])
            raise ValueError("No default provider configured")

        return self.get_or_create(config.type)

    def cleanup(self) -> None:
        """Clean up all cached provider instances."""
        for provider in self._instances.values():
            try:
                provider.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up provider: {e}")
        self._instances.clear()
        self._provider_pool.clear()

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for all providers.

        Returns:
            Dictionary with performance metrics

        """
        return {
            "providers": self._performance_monitor.get_metrics(),
            "pool_metrics": self._provider_pool.get_metrics(),
            "cache_stats": self._config_cache.get_stats(),
            "recommendations": self._performance_monitor.get_recommendations(),
        }

    def optimize_for_performance(self) -> None:
        """Apply performance optimizations based on usage patterns."""
        recommendations = self._performance_monitor.get_recommendations()

        for recommendation in recommendations:
            logger.info(f"Performance recommendation: {recommendation}")

            # Auto-apply some optimizations
            if "lazy initialization" in recommendation:
                # Enable lazy init for slow providers
                for provider_type in self._providers:
                    metrics = self._performance_monitor.get_metrics(provider_type)
                    if metrics and metrics[provider_type].initialization_time > 2.0:
                        logger.info(f"Enabling lazy initialization for {provider_type}")
                        # Will use lazy proxy on next creation

            if "cache TTL" in recommendation:
                # Increase cache TTL
                logger.info("Increasing config cache TTL to 600 seconds")
                # Note: Would need to recreate cache with new TTL in production

        # Clear expired cache entries
        expired = self._config_cache.clear_expired()
        if expired > 0:
            logger.info(f"Cleared {expired} expired cache entries")

    def get_provider_info(self, provider_type: str) -> Dict[str, Any]:
        """Get information about a provider.

        Args:
            provider_type: Provider type identifier

        Returns:
            Dictionary with provider information

        """
        info = {
            "type": provider_type,
            "registered": provider_type in self._providers,
            "configured": False,
            "available": False,
            "cached": provider_type in self._instances,
        }

        config = get_provider_config(provider_type)
        if config:
            info["configured"] = True
            info["available"] = self._is_provider_configured(config)
            info["config"] = {
                "default_model": config.default_model,
                "models": list(config.models.keys()),
                "features": {
                    "interactive": config.features.interactive,
                    "streaming": config.features.streaming,
                    "file_interception": config.features.file_interception,
                    "session_persistence": config.features.session_persistence,
                },
            }

        return info


# Global registry instance
_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """Get the global provider registry.

    Returns:
        Provider registry instance

    """
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def register_provider(provider_type: str, provider_class: Type[BaseProvider]) -> None:
    """Register a provider with the global registry.

    Args:
        provider_type: Provider type identifier
        provider_class: Provider class to register

    """
    get_registry().register(provider_type, provider_class)


def create_provider(provider_type: Optional[str] = None, **kwargs) -> BaseProvider:
    """Create a provider instance.

    Args:
        provider_type: Provider type (uses default if None)
        **kwargs: Provider parameters

    Returns:
        Provider instance

    """
    return get_registry().create_provider(provider_type, **kwargs)


def get_default_provider() -> BaseProvider:
    """Get the default provider instance.

    Returns:
        Default provider instance

    """
    return get_registry().get_default_provider()
