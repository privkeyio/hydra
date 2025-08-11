"""Performance optimization utilities for provider abstraction.

This module provides caching, lazy initialization, and performance monitoring
capabilities to minimize the overhead of provider abstraction.
"""

import functools
import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from hydra.providers.base import LLMConfig
from hydra.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetrics:
    """Metrics for provider performance monitoring."""

    initialization_time: float = 0.0
    total_requests: int = 0
    total_response_time: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    last_used: Optional[datetime] = None
    errors: int = 0

    @property
    def average_response_time(self) -> float:
        """Calculate average response time."""
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time / self.total_requests

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total


class ConfigCache:
    """Thread-safe configuration cache with TTL support."""

    def __init__(self, ttl_seconds: int = 300):
        """Initialize config cache.
        
        Args:
            ttl_seconds: Time-to-live for cached configs in seconds

        """
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._lock = threading.RLock()
        self._ttl = timedelta(seconds=ttl_seconds)
        self._access_count: Dict[str, int] = defaultdict(int)

    def _make_key(self, config: Dict[str, Any]) -> str:
        """Create a cache key from configuration."""
        # Sort dict for consistent hashing
        sorted_config = json.dumps(config, sort_keys=True)
        return hashlib.md5(sorted_config.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get cached configuration if valid."""
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if datetime.now() - timestamp < self._ttl:
                    self._access_count[key] += 1
                    return value
                else:
                    # Expired
                    del self._cache[key]
            return None

    def set(self, key: str, value: Any) -> None:
        """Cache a configuration."""
        with self._lock:
            self._cache[key] = (value, datetime.now())

    def clear_expired(self) -> int:
        """Clear expired entries and return count."""
        with self._lock:
            now = datetime.now()
            expired_keys = [
                k for k, (_, ts) in self._cache.items()
                if now - ts >= self._ttl
            ]
            for key in expired_keys:
                del self._cache[key]
                self._access_count.pop(key, None)
            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "total_accesses": sum(self._access_count.values()),
                "top_accessed": sorted(
                    self._access_count.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
            }


class ProviderPool:
    """Pool of pre-initialized providers for fast switching."""

    def __init__(self, max_size: int = 10):
        """Initialize provider pool.
        
        Args:
            max_size: Maximum number of providers to keep in pool

        """
        self._pool: Dict[str, BaseProvider] = {}
        self._metrics: Dict[str, ProviderMetrics] = defaultdict(ProviderMetrics)
        self._lock = threading.RLock()
        self._max_size = max_size
        self._initialization_callbacks: Dict[str, Callable] = {}

    def register_init_callback(self, provider_type: str, callback: Callable) -> None:
        """Register a callback for lazy provider initialization."""
        self._initialization_callbacks[provider_type] = callback

    def get(self, provider_type: str, config: Optional[LLMConfig] = None) -> Optional[BaseProvider]:
        """Get a provider from the pool, initializing if necessary."""
        with self._lock:
            # Check if provider exists and is healthy
            if provider_type in self._pool:
                provider = self._pool[provider_type]
                self._metrics[provider_type].last_used = datetime.now()
                return provider

            # Initialize new provider if we have capacity
            if len(self._pool) >= self._max_size:
                # Evict least recently used
                self._evict_lru()

            # Initialize provider
            start_time = time.time()
            provider = self._initialize_provider(provider_type, config)
            if provider:
                self._pool[provider_type] = provider
                self._metrics[provider_type].initialization_time = time.time() - start_time
                self._metrics[provider_type].last_used = datetime.now()
                logger.info(f"Initialized provider {provider_type} in {time.time() - start_time:.2f}s")

            return provider

    def _initialize_provider(self, provider_type: str, config: Optional[LLMConfig]) -> Optional[BaseProvider]:
        """Initialize a provider using registered callback or config."""
        if provider_type in self._initialization_callbacks:
            try:
                return self._initialization_callbacks[provider_type](config)
            except Exception as e:
                logger.error(f"Failed to initialize provider {provider_type}: {e}")
                self._metrics[provider_type].errors += 1
                return None

        # Fallback to factory if no callback registered
        try:
            from hydra.providers.factory import LLMProviderFactory
            factory = LLMProviderFactory()
            if not config:
                config = LLMConfig(provider_type=provider_type)
            return factory.create(config)
        except Exception as e:
            logger.error(f"Failed to create provider {provider_type} via factory: {e}")
            self._metrics[provider_type].errors += 1
            return None

    def _evict_lru(self) -> None:
        """Evict least recently used provider."""
        if not self._pool:
            return

        lru_type = min(
            self._pool.keys(),
            key=lambda k: self._metrics[k].last_used or datetime.min
        )

        provider = self._pool.pop(lru_type)
        logger.info(f"Evicted provider {lru_type} from pool")

        # Clean up provider resources if needed
        if hasattr(provider, 'cleanup'):
            try:
                provider.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up provider {lru_type}: {e}")

    def get_metrics(self) -> Dict[str, ProviderMetrics]:
        """Get metrics for all providers."""
        with self._lock:
            return dict(self._metrics)

    def clear(self) -> None:
        """Clear the pool and cleanup all providers."""
        with self._lock:
            for provider_type, provider in self._pool.items():
                if hasattr(provider, 'cleanup'):
                    try:
                        provider.cleanup()
                    except Exception as e:
                        logger.warning(f"Error cleaning up provider {provider_type}: {e}")
            self._pool.clear()
            self._metrics.clear()


class LazyProviderProxy:
    """Proxy for lazy provider initialization."""

    def __init__(self, provider_type: str, config: Optional[LLMConfig] = None):
        """Initialize lazy proxy.
        
        Args:
            provider_type: Type of provider to create
            config: Provider configuration

        """
        self._provider_type = provider_type
        self._config = config
        self._provider: Optional[BaseProvider] = None
        self._lock = threading.Lock()

    def _ensure_initialized(self) -> BaseProvider:
        """Ensure provider is initialized."""
        if self._provider is None:
            with self._lock:
                if self._provider is None:  # Double-check
                    from hydra.providers.factory import LLMProviderFactory
                    factory = LLMProviderFactory()
                    if not self._config:
                        self._config = LLMConfig(provider_type=self._provider_type)
                    self._provider = factory.create(self._config)
        return self._provider

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to real provider."""
        provider = self._ensure_initialized()
        return getattr(provider, name)

    def __repr__(self) -> str:
        """String representation."""
        initialized = "initialized" if self._provider else "lazy"
        return f"<LazyProviderProxy({self._provider_type}, {initialized})>"


def memoize_provider_config(ttl_seconds: int = 300):
    """Decorator to memoize provider configurations.
    
    Args:
        ttl_seconds: Time-to-live for cached configs

    """
    cache = ConfigCache(ttl_seconds=ttl_seconds)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from args and kwargs
            cache_data = {
                "args": args,
                "kwargs": kwargs
            }
            key = cache._make_key(cache_data)

            # Check cache
            result = cache.get(key)
            if result is not None:
                logger.debug(f"Config cache hit for {func.__name__}")
                return result

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(key, result)
            logger.debug(f"Config cache miss for {func.__name__}, cached result")
            return result

        # Add cache management methods
        wrapper.clear_cache = cache.clear_expired
        wrapper.cache_stats = cache.get_stats

        return wrapper

    return decorator


class PerformanceMonitor:
    """Monitor provider performance and suggest optimizations."""

    def __init__(self):
        """Initialize performance monitor."""
        self._metrics: Dict[str, ProviderMetrics] = defaultdict(ProviderMetrics)
        self._lock = threading.Lock()

    def record_initialization(self, provider_type: str, duration: float) -> None:
        """Record provider initialization time."""
        with self._lock:
            self._metrics[provider_type].initialization_time = duration

    def record_request(self, provider_type: str, duration: float) -> None:
        """Record a provider request."""
        with self._lock:
            metrics = self._metrics[provider_type]
            metrics.total_requests += 1
            metrics.total_response_time += duration
            metrics.last_used = datetime.now()

    def record_cache_hit(self, provider_type: str) -> None:
        """Record a cache hit."""
        with self._lock:
            self._metrics[provider_type].cache_hits += 1

    def record_cache_miss(self, provider_type: str) -> None:
        """Record a cache miss."""
        with self._lock:
            self._metrics[provider_type].cache_misses += 1

    def record_error(self, provider_type: str) -> None:
        """Record a provider error."""
        with self._lock:
            self._metrics[provider_type].errors += 1

    def get_metrics(self, provider_type: Optional[str] = None) -> Dict[str, ProviderMetrics]:
        """Get metrics for provider(s)."""
        with self._lock:
            if provider_type:
                return {provider_type: self._metrics.get(provider_type, ProviderMetrics())}
            return dict(self._metrics)

    def get_recommendations(self) -> List[str]:
        """Get performance optimization recommendations."""
        recommendations = []

        with self._lock:
            for provider_type, metrics in self._metrics.items():
                # Check initialization time
                if metrics.initialization_time > 2.0:
                    recommendations.append(
                        f"Provider {provider_type} has slow initialization ({metrics.initialization_time:.2f}s). "
                        "Consider using lazy initialization or provider pooling."
                    )

                # Check cache hit rate
                if metrics.cache_hit_rate < 0.5 and metrics.cache_hits + metrics.cache_misses > 10:
                    recommendations.append(
                        f"Provider {provider_type} has low cache hit rate ({metrics.cache_hit_rate:.1%}). "
                        "Consider increasing cache TTL or improving cache key generation."
                    )

                # Check error rate
                if metrics.errors > 0 and metrics.total_requests > 0:
                    error_rate = metrics.errors / metrics.total_requests
                    if error_rate > 0.05:
                        recommendations.append(
                            f"Provider {provider_type} has high error rate ({error_rate:.1%}). "
                            "Consider implementing retry logic or fallback providers."
                        )

                # Check response time
                if metrics.average_response_time > 5.0:
                    recommendations.append(
                        f"Provider {provider_type} has slow average response time ({metrics.average_response_time:.2f}s). "
                        "Consider implementing request batching or async processing."
                    )

        return recommendations


# Global instances
_config_cache = ConfigCache()
_provider_pool = ProviderPool()
_performance_monitor = PerformanceMonitor()


def get_config_cache() -> ConfigCache:
    """Get global config cache instance."""
    return _config_cache


def get_provider_pool() -> ProviderPool:
    """Get global provider pool instance."""
    return _provider_pool


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance."""
    return _performance_monitor


def optimize_provider_switching(func: Callable) -> Callable:
    """Decorator to optimize provider switching in functions.
    
    This decorator:
    1. Caches provider instances
    2. Monitors performance
    3. Provides metrics
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()

        # Extract provider type if available
        provider_type = kwargs.get('provider_type') or (args[0] if args else None)

        try:
            result = func(*args, **kwargs)

            # Record successful request
            if provider_type:
                duration = time.time() - start_time
                _performance_monitor.record_request(provider_type, duration)

            return result

        except Exception as e:
            # Record error
            if provider_type:
                _performance_monitor.record_error(provider_type)
            raise e

    # Add metrics access
    wrapper.get_metrics = lambda: _performance_monitor.get_metrics()
    wrapper.get_recommendations = lambda: _performance_monitor.get_recommendations()

    return wrapper
