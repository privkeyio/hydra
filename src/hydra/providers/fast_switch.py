"""Fast provider switching module with minimal overhead.

This module provides optimized provider switching capabilities
to minimize the performance impact of the abstraction layer.
"""

import logging
import threading
from contextlib import contextmanager
from typing import Optional

from hydra.providers.base_provider import BaseProvider
from hydra.providers.performance import get_performance_monitor, get_provider_pool
from hydra.providers.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class FastProviderSwitch:
    """Fast provider switching with minimal overhead."""

    def __init__(self):
        """Initialize fast switch."""
        self._registry = ProviderRegistry()
        self._current_provider: Optional[BaseProvider] = None
        self._provider_stack: list[BaseProvider] = []
        self._lock = threading.RLock()
        self._provider_pool = get_provider_pool()
        self._performance_monitor = get_performance_monitor()

    @property
    def current(self) -> Optional[BaseProvider]:
        """Get current active provider."""
        with self._lock:
            return self._current_provider

    def switch_to(self, provider_type: str, **kwargs) -> BaseProvider:
        """Switch to a different provider with minimal overhead.
        
        Args:
            provider_type: Type of provider to switch to
            **kwargs: Additional provider parameters
            
        Returns:
            The new active provider

        """
        with self._lock:
            # Try to get from pool first (fastest)
            provider = self._provider_pool.get(provider_type, None)

            if not provider:
                # Fall back to registry with caching
                provider = self._registry.get_or_create(
                    provider_type,
                    cache=True,
                    lazy=False,  # Don't use lazy for immediate switch
                    **kwargs
                )

            # Update current provider
            if self._current_provider:
                self._provider_stack.append(self._current_provider)
            self._current_provider = provider

            logger.debug(f"Switched to provider: {provider_type}")
            return provider

    def switch_back(self) -> Optional[BaseProvider]:
        """Switch back to previous provider.
        
        Returns:
            The previous provider or None if stack is empty

        """
        with self._lock:
            if self._provider_stack:
                self._current_provider = self._provider_stack.pop()
                logger.debug(f"Switched back to provider: {self._current_provider.name}")
                return self._current_provider
            return None

    @contextmanager
    def temporary_switch(self, provider_type: str, **kwargs):
        """Context manager for temporary provider switch.
        
        Args:
            provider_type: Type of provider to switch to temporarily
            **kwargs: Additional provider parameters
            
        Yields:
            The temporary provider

        """
        previous = self._current_provider
        try:
            provider = self.switch_to(provider_type, **kwargs)
            yield provider
        finally:
            with self._lock:
                self._current_provider = previous
                logger.debug(f"Restored provider: {previous.name if previous else 'None'}")

    def preload_providers(self, provider_types: list[str]) -> None:
        """Preload providers into pool for fast switching.
        
        Args:
            provider_types: List of provider types to preload

        """
        for provider_type in provider_types:
            try:
                # This will initialize and cache the provider
                provider = self._registry.get_or_create(
                    provider_type,
                    cache=True,
                    lazy=False
                )
                logger.info(f"Preloaded provider: {provider_type}")
            except Exception as e:
                logger.warning(f"Failed to preload provider {provider_type}: {e}")

    def get_fastest_provider(self, category: str = "fast") -> BaseProvider:
        """Get the fastest available provider for a category.
        
        Args:
            category: Provider category (fast, balanced, smart)
            
        Returns:
            The fastest provider for the category

        """
        metrics = self._performance_monitor.get_metrics()

        # Find providers in the requested category
        candidates = []
        for provider_type in self._registry.list_providers():
            try:
                info = self._registry.get_provider_info(provider_type)
                # Check if provider matches category and is available
                if info.get("available") and info.get("category") == category:
                    provider_metrics = metrics.get(provider_type)
                    if provider_metrics:
                        avg_time = provider_metrics.average_response_time
                    else:
                        avg_time = float('inf')
                    candidates.append((provider_type, avg_time))
            except Exception:
                continue

        # Sort by average response time
        candidates.sort(key=lambda x: x[1])

        if candidates:
            fastest_type = candidates[0][0]
            logger.info(f"Selected fastest provider for {category}: {fastest_type}")
            return self.switch_to(fastest_type)

        # Fallback to any available provider
        return self._registry.get_default_provider()

    def clear_cache(self) -> None:
        """Clear all provider caches for memory optimization."""
        self._registry.cleanup()
        self._provider_pool.clear()
        self._provider_stack.clear()
        self._current_provider = None
        logger.info("Cleared all provider caches")


# Global instance for convenience
_fast_switch = None


def get_fast_switch() -> FastProviderSwitch:
    """Get global fast switch instance."""
    global _fast_switch
    if _fast_switch is None:
        _fast_switch = FastProviderSwitch()
    return _fast_switch


def switch_provider(provider_type: str, **kwargs) -> BaseProvider:
    """Quick function to switch providers.
    
    Args:
        provider_type: Type of provider to switch to
        **kwargs: Additional provider parameters
        
    Returns:
        The new active provider

    """
    return get_fast_switch().switch_to(provider_type, **kwargs)


@contextmanager
def use_provider(provider_type: str, **kwargs):
    """Context manager for using a specific provider temporarily.
    
    Args:
        provider_type: Type of provider to use
        **kwargs: Additional provider parameters
        
    Yields:
        The provider instance

    """
    with get_fast_switch().temporary_switch(provider_type, **kwargs) as provider:
        yield provider
