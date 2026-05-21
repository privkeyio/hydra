"""Comprehensive performance optimizations module for Hydra.

This module implements multiple performance enhancements:
- uvloop as default event loop for 2-5x async performance
- Singleton pattern for all connection pools
- LLM request batching for parallel tickets
- TTL-based response caching with configurable expiry
- Performance profiling and monitoring
"""

import asyncio
import cProfile
import functools
import hashlib
import json
import logging
import os
import pstats
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

import aiohttp

# Import performance module components
from hydra.cache import get_cache
from hydra.providers.session_manager import get_session_manager

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Try to import uvloop for better async performance
try:
    import uvloop
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False
    logger.warning("uvloop not available, falling back to standard asyncio")


def setup_uvloop() -> bool:
    """Set up uvloop as the default event loop policy for improved async performance.

    Returns:
        True if uvloop was successfully installed, False otherwise

    """
    if not UVLOOP_AVAILABLE:
        logger.info("uvloop not installed. Install with: pip install uvloop")
        return False

    try:
        if sys.platform != 'win32':  # uvloop doesn't support Windows
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("Successfully configured uvloop as default event loop")
            return True
        else:
            logger.info("uvloop not supported on Windows platform")
            return False
    except Exception as e:
        logger.error(f"Failed to setup uvloop: {e}")
        return False


@dataclass
class PerformanceConfig:
    """Configuration for performance optimizations."""

    enable_uvloop: bool = True
    enable_batching: bool = True
    enable_caching: bool = True
    batch_size: int = 10
    batch_timeout: float = 0.1
    cache_ttl_seconds: int = 3600
    profile_enabled: bool = False
    profile_output_dir: str = "profiling_results"


class SingletonMeta(type):
    """Metaclass for implementing singleton pattern."""

    _instances: Dict[type, Any] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class ConnectionPoolManager(metaclass=SingletonMeta):
    """Singleton manager for all connection pools.

    Ensures efficient resource usage and connection reuse.
    """

    def __init__(self):
        self._pools: Dict[str, Any] = {}
        self._session_manager = get_session_manager()
        self._cache = get_cache()
        self._aiohttp_session: Optional[aiohttp.ClientSession] = None
        logger.info("Initialized singleton ConnectionPoolManager")

    @property
    def http_session_manager(self):
        """Get the HTTP session manager for synchronous requests."""
        return self._session_manager

    @property
    def redis_cache(self):
        """Get the Redis cache instance."""
        return self._cache

    async def get_aiohttp_session(self) -> aiohttp.ClientSession:
        """Get or create singleton aiohttp session for async requests."""
        if self._aiohttp_session is None or self._aiohttp_session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=30)
            self._aiohttp_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
            logger.info("Created new aiohttp session with connection pooling")
        return self._aiohttp_session

    async def close_all(self):
        """Close all managed connections."""
        if self._aiohttp_session and not self._aiohttp_session.closed:
            await self._aiohttp_session.close()
        self._session_manager.close_all_sessions()
        self._cache.close()
        logger.info("Closed all connection pools")


class LLMRequestBatcher:
    """Batches LLM requests for efficient parallel processing.

    Reduces API calls and improves throughput for multiple tickets.
    """

    def __init__(self, batch_size: int = 10, batch_timeout: float = 0.1):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self._queues: Dict[str, asyncio.Queue] = defaultdict(lambda: asyncio.Queue())
        self._batch_tasks: Dict[str, asyncio.Task] = {}
        self._pool_manager = ConnectionPoolManager()
        logger.info(
            f"Initialized LLMRequestBatcher with size={batch_size}, "
            f"timeout={batch_timeout}"
        )

    async def add_request(
        self,
        provider: str,
        request: Dict[str, Any],
        ticket_id: Optional[str] = None
    ) -> Any:
        """Add a request to the batch queue."""
        queue = self._queues[provider]
        future = asyncio.Future()

        # Add metadata for tracking
        request_with_metadata = {
            **request,
            "_ticket_id": ticket_id,
            "_timestamp": time.time()
        }

        await queue.put((request_with_metadata, future))

        # Start batch processor if not running
        if provider not in self._batch_tasks or self._batch_tasks[provider].done():
            self._batch_tasks[provider] = asyncio.create_task(
                self._process_batch(provider)
            )

        return await future

    async def _process_batch(self, provider: str):
        """Process a batch of requests for a provider."""
        queue = self._queues[provider]
        batch = []
        start_time = time.time()

        # Collect requests up to batch size or timeout
        elapsed = time.time() - start_time
        while len(batch) < self.batch_size and elapsed < self.batch_timeout:
            elapsed = time.time() - start_time
            try:
                timeout = self.batch_timeout - (time.time() - start_time)
                request, future = await asyncio.wait_for(
                    queue.get(),
                    timeout=max(0.01, timeout)
                )
                batch.append((request, future))
            except asyncio.TimeoutError:
                break

        if batch:
            logger.info(f"Processing batch of {len(batch)} requests for {provider}")
            await self._execute_batch(provider, batch)

    async def _execute_batch(
        self,
        provider: str,
        batch: List[Tuple[Dict, asyncio.Future]]
    ):
        """Execute a batch of requests in parallel."""
        try:
            session = await self._pool_manager.get_aiohttp_session()

            # Prepare requests
            tasks = []
            for request, _ in batch:
                # Remove metadata before sending
                clean_request = {
                    k: v for k, v in request.items()
                    if not k.startswith('_')
                }
                task = self._send_request(session, provider, clean_request)
                tasks.append(task)

            # Execute in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Set results
            for (request, future), result in zip(batch, results, strict=False):
                if isinstance(result, Exception):
                    future.set_exception(result)
                else:
                    # Cache successful results
                    if result and "_ticket_id" in request:
                        await self._cache_result(
                            provider,
                            request["_ticket_id"],
                            result
                        )
                    future.set_result(result)

        except Exception as e:
            logger.error(f"Batch execution failed: {e}")
            for _, future in batch:
                future.set_exception(e)

    async def _send_request(
        self,
        session: aiohttp.ClientSession,
        provider: str,
        request: Dict
    ) -> Any:
        """Send individual request to provider."""
        # Provider-specific endpoint configuration
        endpoints = {
            "openai": (
                os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
                + "/chat/completions"
            ),
            "anthropic": "https://api.anthropic.com/v1/messages",
            "venice": (
                os.getenv("VENICE_BASE_URL", "https://api.venice.ai/api/v1")
                + "/chat/completions"
            ),
            "nearai": (
                os.getenv("NEARAI_BASE_URL", "https://cloud-api.near.ai/v1")
                + "/chat/completions"
            ),
            "nearai_api": (
                os.getenv("NEARAI_BASE_URL", "https://cloud-api.near.ai/v1")
                + "/chat/completions"
            ),
        }

        headers = self._get_headers(provider)
        url = endpoints.get(provider, endpoints["venice"])

        async with session.post(url, json=request, headers=headers) as response:
            return await response.json()

    def _get_headers(self, provider: str) -> Dict[str, str]:
        """Get provider-specific headers."""
        if provider == "openai":
            return {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}
        elif provider == "anthropic":
            return {
                "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                "anthropic-version": "2023-06-01"
            }
        elif provider in ["nearai", "nearai_api"]:
            return {"Authorization": f"Bearer {os.getenv('NEARAI_API_KEY')}"}
        else:  # venice or default
            return {"Authorization": f"Bearer {os.getenv('VENICE_API_KEY')}"}

    async def _cache_result(self, provider: str, ticket_id: str, result: Any):
        """Cache the result for future use."""
        cache_key = f"batch_{provider}_{ticket_id}"
        try:
            self._pool_manager.redis_cache.set_task_result(
                cache_key,
                result,
                ttl=3600  # 1 hour TTL
            )
        except Exception as e:
            logger.debug(f"Failed to cache batch result: {e}")


class ResponseCache:
    """TTL-based caching system for LLM responses with configurable expiry.

    Reduces redundant API calls and improves response times.
    """

    def __init__(self, default_ttl: int = 3600):
        self.default_ttl = default_ttl
        self._cache = get_cache()
        self._stats = defaultdict(lambda: {"hits": 0, "misses": 0})

    def _generate_cache_key(
        self,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate a unique cache key for the request."""
        data = {
            "provider": provider,
            "prompt": prompt,
            "model": model,
            **kwargs
        }
        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    async def get_cached_response(
        self,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        **kwargs
    ) -> Optional[Any]:
        """Get cached response if available."""
        self._generate_cache_key(provider, prompt, model, **kwargs)

        try:
            result = self._cache.get_code_cache(
                prompt, language=provider, max_tokens=None
            )
            if result:
                self._stats[provider]["hits"] += 1
                logger.debug(f"Cache hit for {provider}")
                return result
        except Exception as e:
            logger.debug(f"Cache retrieval error: {e}")

        self._stats[provider]["misses"] += 1
        return None

    async def set_cached_response(
        self,
        provider: str,
        prompt: str,
        response: Any,
        model: Optional[str] = None,
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """Cache a response with TTL."""
        ttl = ttl or self.default_ttl

        try:
            return self._cache.set_code_cache(
                prompt,
                response,
                language=provider,
                ttl=ttl
            )
        except Exception as e:
            logger.debug(f"Cache storage error: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = dict(self._stats)

        # Calculate hit rates
        for provider in stats:
            hits = stats[provider]["hits"]
            misses = stats[provider]["misses"]
            total = hits + misses
            stats[provider]["hit_rate"] = (hits / total * 100) if total > 0 else 0.0

        return stats

    def invalidate_provider_cache(self, provider: str) -> int:
        """Invalidate all cache entries for a provider."""
        return self._cache.invalidate_pattern(f"code:{provider}:*")


class PerformanceProfiler:
    """Profile and optimize hot paths using cProfile.

    Identifies performance bottlenecks and generates reports.
    """

    def __init__(self, output_dir: str = "profiling_results"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._profiles: Dict[str, cProfile.Profile] = {}

    @contextmanager
    def profile(self, name: str):
        """Context manager for profiling code blocks."""
        profiler = cProfile.Profile()
        profiler.enable()

        try:
            yield profiler
        finally:
            profiler.disable()
            self._profiles[name] = profiler
            self._save_profile(name, profiler)

    def _save_profile(self, name: str, profiler: cProfile.Profile):
        """Save profile results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.output_dir, f"{name}_{timestamp}.prof")

        # Save binary profile
        profiler.dump_stats(filename)

        # Generate text report
        report_file = os.path.join(self.output_dir, f"{name}_{timestamp}.txt")
        with open(report_file, 'w') as f:
            stats = pstats.Stats(profiler, stream=f)
            stats.strip_dirs()
            stats.sort_stats('cumulative')
            stats.print_stats(50)  # Top 50 functions

    def profile_function(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorate functions for profiling."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self.profile(func.__name__):
                return func(*args, **kwargs)
        return wrapper

    def profile_async_function(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorate async functions for profiling."""
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            with self.profile(func.__name__):
                return await func(*args, **kwargs)
        return wrapper

    def get_hot_paths(self, name: str, top_n: int = 10) -> List[Dict[str, Any]]:
        """Get the top N hot paths from a profile."""
        if name not in self._profiles:
            return []

        stats = pstats.Stats(self._profiles[name])
        stats.strip_dirs()
        stats.sort_stats('cumulative')

        hot_paths = []
        for func, (_cc, nc, tt, ct, _callers) in list(stats.stats.items())[:top_n]:
            hot_paths.append({
                "function": f"{func[0]}:{func[1]}:{func[2]}",
                "calls": nc,
                "total_time": tt,
                "cumulative_time": ct,
                "time_per_call": tt / nc if nc > 0 else 0
            })

        return hot_paths


class PerformanceMonitor:
    """Monitor and track performance metrics.

    Provides insights into system performance and bottlenecks.
    """

    def __init__(self):
        self._metrics: Dict[str, List[float]] = defaultdict(list)
        self._start_times: Dict[str, float] = {}

    def start_timer(self, operation: str):
        """Start timing an operation."""
        self._start_times[operation] = time.time()

    def stop_timer(self, operation: str) -> float:
        """Stop timing an operation and record the duration."""
        if operation not in self._start_times:
            return 0.0

        duration = time.time() - self._start_times[operation]
        self._metrics[operation].append(duration)
        del self._start_times[operation]
        return duration

    @contextmanager
    def measure(self, operation: str):
        """Context manager for measuring operation duration."""
        self.start_timer(operation)
        try:
            yield
        finally:
            duration = self.stop_timer(operation)
            logger.debug(f"{operation} took {duration:.3f}s")

    def get_statistics(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """Get performance statistics."""
        if operation:
            if operation not in self._metrics:
                return {}

            durations = self._metrics[operation]
            return self._calculate_stats(operation, durations)

        # Return stats for all operations
        stats = {}
        for op, durations in self._metrics.items():
            stats[op] = self._calculate_stats(op, durations)

        return stats

    def _calculate_stats(
        self, operation: str, durations: List[float]
    ) -> Dict[str, Any]:
        """Calculate statistics for a set of durations."""
        if not durations:
            return {}

        durations_sorted = sorted(durations)
        count = len(durations)

        return {
            "operation": operation,
            "count": count,
            "total": sum(durations),
            "mean": sum(durations) / count,
            "min": durations_sorted[0],
            "max": durations_sorted[-1],
            "p50": durations_sorted[count // 2],
            "p95": (
                durations_sorted[int(count * 0.95)]
                if count > 20
                else durations_sorted[-1]
            ),
            "p99": (
                durations_sorted[int(count * 0.99)]
                if count > 100
                else durations_sorted[-1]
            )
        }

    def generate_report(self) -> str:
        """Generate a performance report."""
        stats = self.get_statistics()

        if not stats:
            return "No performance data collected"

        report = ["Performance Report", "=" * 50]

        for op, data in stats.items():
            report.append(f"\nOperation: {op}")
            report.append(f"  Calls: {data['count']}")
            report.append(f"  Total: {data['total']:.3f}s")
            report.append(f"  Mean: {data['mean']:.3f}s")
            report.append(f"  Min: {data['min']:.3f}s")
            report.append(f"  Max: {data['max']:.3f}s")
            report.append(f"  P50: {data['p50']:.3f}s")
            report.append(f"  P95: {data['p95']:.3f}s")

        return "\n".join(report)


# Global instances
_pool_manager: Optional[ConnectionPoolManager] = None
_request_batcher: Optional[LLMRequestBatcher] = None
_response_cache: Optional[ResponseCache] = None
_profiler: Optional[PerformanceProfiler] = None
_monitor: Optional[PerformanceMonitor] = None


def initialize_performance_optimizations(
    config: Optional[PerformanceConfig] = None,
) -> Dict[str, Any]:
    """Initialize all performance optimizations.

    Returns:
        Dictionary with initialization status for each component

    """
    global _pool_manager, _request_batcher, _response_cache, _profiler, _monitor

    config = config or PerformanceConfig()
    results = {}

    # Setup uvloop if enabled
    if config.enable_uvloop:
        results["uvloop"] = setup_uvloop()

    # Initialize singleton connection pool manager
    _pool_manager = ConnectionPoolManager()
    results["connection_pools"] = True

    # Initialize request batcher if enabled
    if config.enable_batching:
        _request_batcher = LLMRequestBatcher(
            batch_size=config.batch_size,
            batch_timeout=config.batch_timeout
        )
        results["request_batching"] = True

    # Initialize response cache if enabled
    if config.enable_caching:
        _response_cache = ResponseCache(default_ttl=config.cache_ttl_seconds)
        results["response_caching"] = True

    # Initialize profiler if enabled
    if config.profile_enabled:
        _profiler = PerformanceProfiler(output_dir=config.profile_output_dir)
        results["profiling"] = True

    # Initialize performance monitor
    _monitor = PerformanceMonitor()
    results["monitoring"] = True

    logger.info(f"Performance optimizations initialized: {results}")
    return results


def get_pool_manager() -> ConnectionPoolManager:
    """Get the global connection pool manager."""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = ConnectionPoolManager()
    return _pool_manager


def get_request_batcher() -> Optional[LLMRequestBatcher]:
    """Get the global request batcher."""
    return _request_batcher


def get_response_cache() -> Optional[ResponseCache]:
    """Get the global response cache."""
    return _response_cache


def get_profiler() -> Optional[PerformanceProfiler]:
    """Get the global profiler."""
    return _profiler


def get_monitor() -> PerformanceMonitor:
    """Get the global performance monitor."""
    global _monitor
    if _monitor is None:
        _monitor = PerformanceMonitor()
    return _monitor


async def cleanup_performance_resources():
    """Clean up all performance optimization resources."""
    global _pool_manager

    if _pool_manager:
        await _pool_manager.close_all()

    logger.info("Performance optimization resources cleaned up")


def create_performance_report() -> Dict[str, Any]:
    """Create a comprehensive performance report.

    Returns:
        Dictionary containing performance metrics and statistics

    """
    report = {
        "timestamp": datetime.now().isoformat(),
        "optimizations": {}
    }

    # Check uvloop status
    report["optimizations"]["uvloop"] = {
        "available": UVLOOP_AVAILABLE,
        "active": UVLOOP_AVAILABLE and isinstance(
            asyncio.get_event_loop_policy(),
            uvloop.EventLoopPolicy if UVLOOP_AVAILABLE else type(None)
        )
    }

    # Connection pool status
    if _pool_manager:
        report["optimizations"]["connection_pools"] = {
            "status": "active",
            "http_sessions": True,
            "redis_cache": True
        }

    # Request batching status
    if _request_batcher:
        report["optimizations"]["request_batching"] = {
            "status": "active",
            "batch_size": _request_batcher.batch_size,
            "batch_timeout": _request_batcher.batch_timeout
        }

    # Cache statistics
    if _response_cache:
        report["optimizations"]["response_caching"] = {
            "status": "active",
            "stats": _response_cache.get_cache_stats()
        }

    # Performance metrics
    if _monitor:
        report["performance_metrics"] = _monitor.get_statistics()

    return report
