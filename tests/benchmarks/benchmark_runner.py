"""Benchmark runner and result tracking."""

import gc
import os
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import psutil


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    name: str
    iterations: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    median_time: float
    std_dev: float
    throughput: float  # operations per second
    memory_delta: int  # bytes
    cpu_percent: float
    success_count: int
    error_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.error_count
        return self.success_count / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "iterations": self.iterations,
            "total_time": self.total_time,
            "avg_time": self.avg_time,
            "min_time": self.min_time,
            "max_time": self.max_time,
            "median_time": self.median_time,
            "std_dev": self.std_dev,
            "throughput": self.throughput,
            "memory_delta_mb": self.memory_delta / (1024 * 1024),
            "cpu_percent": self.cpu_percent,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": self.success_rate,
            "metadata": self.metadata,
        }


class BenchmarkRunner:
    """Runner for performance benchmarks."""

    def __init__(self, warmup_iterations: int = 5):
        self.warmup_iterations = warmup_iterations
        self.results: List[BenchmarkResult] = []

    def run_benchmark(
        self,
        name: str,
        func: Callable,
        iterations: int = 100,
        setup: Optional[Callable] = None,
        teardown: Optional[Callable] = None,
        **kwargs,
    ) -> BenchmarkResult:
        """Run a benchmark with timing and resource monitoring."""
        # Warmup runs
        if self.warmup_iterations > 0:
            for _ in range(self.warmup_iterations):
                try:
                    if setup:
                        setup()
                    func(**kwargs)
                    if teardown:
                        teardown()
                except Exception:
                    pass  # Ignore warmup errors

        # Force garbage collection before benchmark
        gc.collect()

        # Track memory and CPU
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        cpu_times = []

        times = []
        success_count = 0
        error_count = 0

        with self._cpu_monitor(cpu_times):
            for i in range(iterations):
                if setup:
                    setup()

                start_time = time.perf_counter()
                try:
                    func(**kwargs)
                    success_count += 1
                except Exception:
                    error_count += 1
                end_time = time.perf_counter()

                times.append(end_time - start_time)

                if teardown:
                    teardown()

        # Calculate memory delta
        final_memory = process.memory_info().rss
        memory_delta = final_memory - initial_memory

        # Calculate statistics
        total_time = sum(times)
        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        median_time = statistics.median(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0.0
        throughput = iterations / total_time if total_time > 0 else 0.0
        avg_cpu = statistics.mean(cpu_times) if cpu_times else 0.0

        result = BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time=total_time,
            avg_time=avg_time,
            min_time=min_time,
            max_time=max_time,
            median_time=median_time,
            std_dev=std_dev,
            throughput=throughput,
            memory_delta=memory_delta,
            cpu_percent=avg_cpu,
            success_count=success_count,
            error_count=error_count,
        )

        self.results.append(result)
        return result

    @contextmanager
    def _cpu_monitor(self, cpu_times: List[float]):
        """Monitor CPU usage during benchmark."""
        import threading

        monitoring = True

        def monitor():
            process = psutil.Process(os.getpid())
            while monitoring:
                try:
                    cpu_times.append(process.cpu_percent())
                    time.sleep(0.1)
                except Exception:
                    break

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

        try:
            yield
        finally:
            monitoring = False

    def compare_results(self, baseline: str, comparison: str) -> Dict[str, float]:
        """Compare two benchmark results."""
        baseline_result = next((r for r in self.results if r.name == baseline), None)
        comparison_result = next(
            (r for r in self.results if r.name == comparison), None
        )

        if not baseline_result or not comparison_result:
            raise ValueError("Both benchmark results must exist for comparison")

        return {
            "speedup": baseline_result.avg_time / comparison_result.avg_time,
            "throughput_improvement": (
                comparison_result.throughput - baseline_result.throughput
            )
            / baseline_result.throughput,
            "memory_delta": comparison_result.memory_delta
            - baseline_result.memory_delta,
            "cpu_delta": comparison_result.cpu_percent - baseline_result.cpu_percent,
            "success_rate_delta": comparison_result.success_rate
            - baseline_result.success_rate,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all benchmark results."""
        if not self.results:
            return {"message": "No benchmarks run"}

        summary = {"total_benchmarks": len(self.results), "benchmarks": []}

        for result in self.results:
            summary["benchmarks"].append(
                {
                    "name": result.name,
                    "avg_time_ms": result.avg_time * 1000,
                    "throughput_ops_sec": result.throughput,
                    "success_rate": result.success_rate,
                    "memory_delta_mb": result.memory_delta / (1024 * 1024),
                }
            )

        return summary

    def save_results(self, filename: str):
        """Save benchmark results to file."""
        import json

        data = {
            "timestamp": time.time(),
            "system_info": {
                "cpu_count": psutil.cpu_count(),
                "memory_total": psutil.virtual_memory().total,
                "platform": os.name,
            },
            "results": [result.to_dict() for result in self.results],
        }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

    def clear_results(self):
        """Clear all benchmark results."""
        self.results.clear()
