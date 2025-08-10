"""Performance profiler and optimizer for provider abstraction layer.

This module provides detailed profiling and optimization capabilities
to identify and eliminate performance bottlenecks in provider operations.
"""

import cProfile
import functools
import io
import logging
import pstats
import threading
import traceback
import tracemalloc
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OperationMetrics:
    """Detailed metrics for a provider operation."""

    operation: str
    provider_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    memory_before: int = 0
    memory_after: int = 0
    memory_delta: int = 0
    success: bool = True
    error: Optional[str] = None
    call_stack: List[str] = field(default_factory=list)

    def complete(self, success: bool = True, error: Optional[str] = None) -> None:
        """Mark operation as complete."""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.success = success
        self.error = error


@dataclass
class ProviderProfileData:
    """Aggregated profile data for a provider."""

    provider_type: str
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_time_ms: float = 0.0
    avg_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    max_time_ms: float = 0.0
    p50_time_ms: float = 0.0
    p95_time_ms: float = 0.0
    p99_time_ms: float = 0.0
    total_memory_kb: int = 0
    avg_memory_kb: int = 0
    hotspots: List[Tuple[str, float]] = field(default_factory=list)


class PerformanceProfiler:
    """Advanced performance profiler for provider operations."""

    def __init__(self, max_history: int = 10000):
        """Initialize profiler.
        
        Args:
            max_history: Maximum number of operations to keep in history
            
        """
        self._operations: deque[OperationMetrics] = deque(maxlen=max_history)
        self._active_operations: Dict[int, OperationMetrics] = {}
        self._provider_profiles: Dict[str, ProviderProfileData] = defaultdict(
            lambda: ProviderProfileData("")
        )
        self._lock = threading.RLock()
        self._profiling_enabled = False
        self._memory_profiling = False
        self._profile_data: Optional[pstats.Stats] = None

    def enable_profiling(self, memory: bool = False) -> None:
        """Enable performance profiling.
        
        Args:
            memory: Whether to enable memory profiling
            
        """
        self._profiling_enabled = True
        self._memory_profiling = memory
        if memory:
            tracemalloc.start()
        logger.info(f"Profiling enabled (memory={memory})")

    def disable_profiling(self) -> None:
        """Disable performance profiling."""
        self._profiling_enabled = False
        if self._memory_profiling:
            tracemalloc.stop()
            self._memory_profiling = False
        logger.info("Profiling disabled")

    @contextmanager
    def profile_operation(
        self,
        operation: str,
        provider_type: str,
        capture_stack: bool = False
    ):
        """Context manager to profile an operation.
        
        Args:
            operation: Name of the operation
            provider_type: Type of provider
            capture_stack: Whether to capture call stack
            
        Yields:
            OperationMetrics instance
            
        """
        if not self._profiling_enabled:
            yield None
            return

        # Create metrics
        metrics = OperationMetrics(
            operation=operation,
            provider_type=provider_type,
            start_time=datetime.now()
        )

        # Capture memory before
        if self._memory_profiling:
            metrics.memory_before = tracemalloc.get_traced_memory()[0]

        # Capture call stack
        if capture_stack:
            metrics.call_stack = [
                f"{frame.filename}:{frame.lineno} ({frame.name})"
                for frame in traceback.extract_stack()[:-1]
            ][-10:]  # Keep last 10 frames

        # Track active operation
        op_id = id(metrics)
        with self._lock:
            self._active_operations[op_id] = metrics

        try:
            yield metrics
            metrics.complete(success=True)
        except Exception as e:
            metrics.complete(success=False, error=str(e))
            raise
        finally:
            # Capture memory after
            if self._memory_profiling:
                metrics.memory_after = tracemalloc.get_traced_memory()[0]
                metrics.memory_delta = metrics.memory_after - metrics.memory_before

            # Record operation
            with self._lock:
                self._operations.append(metrics)
                del self._active_operations[op_id]
                self._update_provider_profile(metrics)

    def _update_provider_profile(self, metrics: OperationMetrics) -> None:
        """Update provider profile with operation metrics."""
        profile = self._provider_profiles[metrics.provider_type]
        profile.provider_type = metrics.provider_type
        profile.total_operations += 1

        if metrics.success:
            profile.successful_operations += 1
        else:
            profile.failed_operations += 1

        profile.total_time_ms += metrics.duration_ms
        profile.avg_time_ms = profile.total_time_ms / profile.total_operations
        profile.min_time_ms = min(profile.min_time_ms, metrics.duration_ms)
        profile.max_time_ms = max(profile.max_time_ms, metrics.duration_ms)

        if self._memory_profiling:
            profile.total_memory_kb += metrics.memory_delta // 1024
            profile.avg_memory_kb = profile.total_memory_kb // profile.total_operations

    def profile_function(self, func: Callable) -> pstats.Stats:
        """Profile a function using cProfile.
        
        Args:
            func: Function to profile
            
        Returns:
            Profile statistics
            
        """
        profiler = cProfile.Profile()
        profiler.enable()

        try:
            func()
        finally:
            profiler.disable()

        # Get statistics
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats('cumulative')

        return stats

    def get_hotspots(self, provider_type: Optional[str] = None, top_n: int = 10) -> List[Tuple[str, float]]:
        """Get performance hotspots.
        
        Args:
            provider_type: Provider to analyze (None for all)
            top_n: Number of top hotspots to return
            
        Returns:
            List of (operation, avg_time_ms) tuples
            
        """
        with self._lock:
            # Group operations by name
            op_times: Dict[str, List[float]] = defaultdict(list)

            for op in self._operations:
                if provider_type and op.provider_type != provider_type:
                    continue
                op_times[op.operation].append(op.duration_ms)

            # Calculate averages
            hotspots = []
            for operation, times in op_times.items():
                if times:
                    avg_time = sum(times) / len(times)
                    hotspots.append((operation, avg_time))

            # Sort by average time
            hotspots.sort(key=lambda x: x[1], reverse=True)

            return hotspots[:top_n]

    def get_provider_profile(self, provider_type: str) -> ProviderProfileData:
        """Get profile data for a provider.
        
        Args:
            provider_type: Provider type
            
        Returns:
            Provider profile data
            
        """
        with self._lock:
            profile = self._provider_profiles.get(provider_type)
            if profile:
                # Calculate percentiles
                times = [
                    op.duration_ms for op in self._operations
                    if op.provider_type == provider_type and op.success
                ]
                if times:
                    times.sort()
                    n = len(times)
                    profile.p50_time_ms = times[n // 2]
                    profile.p95_time_ms = times[int(n * 0.95)]
                    profile.p99_time_ms = times[int(n * 0.99)]

                # Add hotspots
                profile.hotspots = self.get_hotspots(provider_type, top_n=5)

            return profile or ProviderProfileData(provider_type)

    def get_slow_operations(
        self,
        threshold_ms: float = 1000,
        limit: int = 10
    ) -> List[OperationMetrics]:
        """Get operations slower than threshold.
        
        Args:
            threshold_ms: Time threshold in milliseconds
            limit: Maximum number of operations to return
            
        Returns:
            List of slow operations
            
        """
        with self._lock:
            slow_ops = [
                op for op in self._operations
                if op.duration_ms > threshold_ms
            ]
            slow_ops.sort(key=lambda x: x.duration_ms, reverse=True)
            return slow_ops[:limit]

    def get_memory_leaks(self, threshold_kb: int = 1024) -> List[OperationMetrics]:
        """Find operations with potential memory leaks.
        
        Args:
            threshold_kb: Memory delta threshold in KB
            
        Returns:
            List of operations with high memory usage
            
        """
        if not self._memory_profiling:
            return []

        with self._lock:
            leaks = [
                op for op in self._operations
                if op.memory_delta > threshold_kb * 1024
            ]
            leaks.sort(key=lambda x: x.memory_delta, reverse=True)
            return leaks

    def generate_report(self) -> str:
        """Generate performance report.
        
        Returns:
            Formatted performance report
            
        """
        with self._lock:
            report = ["=" * 80]
            report.append("PROVIDER PERFORMANCE REPORT")
            report.append("=" * 80)
            report.append(f"Total operations profiled: {len(self._operations)}")
            report.append("")

            # Provider summaries
            for provider_type, profile in self._provider_profiles.items():
                if profile.total_operations == 0:
                    continue

                report.append(f"\nProvider: {provider_type}")
                report.append("-" * 40)
                report.append(f"  Total operations: {profile.total_operations}")
                report.append(f"  Success rate: {profile.successful_operations / profile.total_operations:.1%}")
                report.append(f"  Average time: {profile.avg_time_ms:.2f}ms")
                report.append(f"  Min/Max time: {profile.min_time_ms:.2f}ms / {profile.max_time_ms:.2f}ms")
                report.append(f"  P50/P95/P99: {profile.p50_time_ms:.2f}ms / {profile.p95_time_ms:.2f}ms / {profile.p99_time_ms:.2f}ms")

                if self._memory_profiling:
                    report.append(f"  Average memory: {profile.avg_memory_kb}KB")

                if profile.hotspots:
                    report.append("  Top hotspots:")
                    for op, time_ms in profile.hotspots[:3]:
                        report.append(f"    - {op}: {time_ms:.2f}ms")

            # Slow operations
            slow_ops = self.get_slow_operations(threshold_ms=500, limit=5)
            if slow_ops:
                report.append("\nSlowest Operations:")
                report.append("-" * 40)
                for op in slow_ops:
                    report.append(
                        f"  {op.operation} ({op.provider_type}): "
                        f"{op.duration_ms:.2f}ms"
                    )

            # Memory leaks
            if self._memory_profiling:
                leaks = self.get_memory_leaks(threshold_kb=512)
                if leaks:
                    report.append("\nPotential Memory Leaks:")
                    report.append("-" * 40)
                    for op in leaks[:5]:
                        report.append(
                            f"  {op.operation} ({op.provider_type}): "
                            f"+{op.memory_delta // 1024}KB"
                        )

            report.append("=" * 80)
            return "\n".join(report)

    def optimize_recommendations(self) -> List[str]:
        """Generate optimization recommendations based on profiling data.
        
        Returns:
            List of optimization recommendations
            
        """
        recommendations = []

        with self._lock:
            for provider_type, profile in self._provider_profiles.items():
                if profile.total_operations < 10:
                    continue

                # Check for slow initialization
                init_ops = [
                    op for op in self._operations
                    if op.provider_type == provider_type and "init" in op.operation.lower()
                ]
                if init_ops:
                    avg_init = sum(op.duration_ms for op in init_ops) / len(init_ops)
                    if avg_init > 1000:
                        recommendations.append(
                            f"Provider '{provider_type}' has slow initialization "
                            f"({avg_init:.0f}ms). Consider lazy loading or caching."
                        )

                # Check for high failure rate
                if profile.failed_operations > profile.successful_operations * 0.1:
                    recommendations.append(
                        f"Provider '{provider_type}' has high failure rate "
                        f"({profile.failed_operations / profile.total_operations:.1%}). "
                        f"Consider implementing retry logic or fallback providers."
                    )

                # Check for high variance in response times
                if profile.p99_time_ms > profile.p50_time_ms * 10:
                    recommendations.append(
                        f"Provider '{provider_type}' has high response time variance "
                        f"(P99={profile.p99_time_ms:.0f}ms vs P50={profile.p50_time_ms:.0f}ms). "
                        f"Consider implementing request timeouts or batching."
                    )

                # Check for memory issues
                if self._memory_profiling and profile.avg_memory_kb > 10240:  # 10MB
                    recommendations.append(
                        f"Provider '{provider_type}' has high memory usage "
                        f"({profile.avg_memory_kb}KB average). "
                        f"Consider optimizing data structures or implementing cleanup."
                    )

        return recommendations


# Global profiler instance
_profiler: Optional[PerformanceProfiler] = None


def get_profiler() -> PerformanceProfiler:
    """Get global performance profiler instance."""
    global _profiler
    if _profiler is None:
        _profiler = PerformanceProfiler()
    return _profiler


def profile_provider_operation(operation: str):
    """Decorator to profile provider operations.
    
    Args:
        operation: Name of the operation
        
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Get provider type from self if available
            provider_type = getattr(self, 'provider_type', 'unknown')

            profiler = get_profiler()
            with profiler.profile_operation(operation, provider_type):
                return func(self, *args, **kwargs)

        return wrapper
    return decorator


def enable_profiling(memory: bool = False) -> None:
    """Enable global performance profiling.
    
    Args:
        memory: Whether to enable memory profiling
        
    """
    get_profiler().enable_profiling(memory=memory)


def disable_profiling() -> None:
    """Disable global performance profiling."""
    get_profiler().disable_profiling()


def get_performance_report() -> str:
    """Get performance report from global profiler.
    
    Returns:
        Formatted performance report
        
    """
    return get_profiler().generate_report()


def get_optimization_recommendations() -> List[str]:
    """Get optimization recommendations from global profiler.
    
    Returns:
        List of recommendations
        
    """
    return get_profiler().optimize_recommendations()
