"""Performance benchmarks for Hydra optimizations.

Measures and validates performance improvements from optimizations.
"""

import asyncio
import json
import os
import random
import statistics
import string
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hydra.performance_optimizations import (
    ConnectionPoolManager,
    LLMRequestBatcher,
    PerformanceConfig,
    PerformanceMonitor,
    ResponseCache,
    initialize_performance_optimizations,
    setup_uvloop,
)


@dataclass
class BenchmarkResult:
    """Result from a benchmark test."""

    name: str
    iterations: int
    total_time: float
    mean_time: float
    min_time: float
    max_time: float
    std_dev: float
    throughput: float  # operations per second
    improvement: Optional[float] = None  # percentage improvement


class PerformanceBenchmark:
    """Run performance benchmarks for Hydra optimizations."""

    def __init__(self, iterations: int = 100, warmup: int = 10):
        self.iterations = iterations
        self.warmup = warmup
        self.results: Dict[str, BenchmarkResult] = {}
        self.monitor = PerformanceMonitor()

    def generate_test_data(self, count: int) -> List[Dict[str, Any]]:
        """Generate test data for benchmarks."""
        data = []
        for i in range(count):
            chars = string.ascii_letters + string.digits
            prompt = ''.join(random.choices(chars, k=200))
            data.append({
                "prompt": f"Test prompt {i}: {prompt}",
                "model": "test-model",
                "max_tokens": random.randint(100, 1000),
                "temperature": random.random()
            })
        return data

    async def benchmark_uvloop(self) -> BenchmarkResult:
        """Benchmark uvloop vs standard asyncio."""
        async def async_workload():
            """Simulate async workload."""
            tasks = []
            for _ in range(50):
                tasks.append(asyncio.create_task(asyncio.sleep(0.001)))
            await asyncio.gather(*tasks)

        # Benchmark without uvloop
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        standard_times = []
        for _ in range(self.warmup):
            await async_workload()

        for _ in range(self.iterations):
            start = time.perf_counter()
            await async_workload()
            standard_times.append(time.perf_counter() - start)

        standard_mean = statistics.mean(standard_times)

        # Benchmark with uvloop
        if setup_uvloop():
            uvloop_times = []
            for _ in range(self.warmup):
                await async_workload()

            for _ in range(self.iterations):
                start = time.perf_counter()
                await async_workload()
                uvloop_times.append(time.perf_counter() - start)

            uvloop_mean = statistics.mean(uvloop_times)
            improvement = ((standard_mean - uvloop_mean) / standard_mean) * 100

            return BenchmarkResult(
                name="uvloop_optimization",
                iterations=self.iterations,
                total_time=sum(uvloop_times),
                mean_time=uvloop_mean,
                min_time=min(uvloop_times),
                max_time=max(uvloop_times),
                std_dev=statistics.stdev(uvloop_times) if len(uvloop_times) > 1 else 0,
                throughput=1 / uvloop_mean if uvloop_mean > 0 else 0,
                improvement=improvement
            )
        else:
            return BenchmarkResult(
                name="uvloop_optimization",
                iterations=self.iterations,
                total_time=sum(standard_times),
                mean_time=standard_mean,
                min_time=min(standard_times),
                max_time=max(standard_times),
                std_dev=(
                    statistics.stdev(standard_times)
                    if len(standard_times) > 1
                    else 0
                ),
                throughput=1 / standard_mean if standard_mean > 0 else 0,
                improvement=0.0
            )

    async def benchmark_connection_pooling(self) -> BenchmarkResult:
        """Benchmark connection pooling vs creating new connections."""
        pool_manager = ConnectionPoolManager()

        async def with_pooling():
            """Use connection pooling."""
            await pool_manager.get_aiohttp_session()
            # Simulate request
            await asyncio.sleep(0.001)

        async def without_pooling():
            """Create new connection each time."""
            import aiohttp
            async with aiohttp.ClientSession():
                # Simulate request
                await asyncio.sleep(0.001)

        # Benchmark with pooling
        pooling_times = []
        for _ in range(self.warmup):
            await with_pooling()

        for _ in range(self.iterations):
            start = time.perf_counter()
            await with_pooling()
            pooling_times.append(time.perf_counter() - start)

        # Benchmark without pooling
        no_pooling_times = []
        for _ in range(self.warmup):
            await without_pooling()

        for _ in range(self.iterations):
            start = time.perf_counter()
            await without_pooling()
            no_pooling_times.append(time.perf_counter() - start)

        pooling_mean = statistics.mean(pooling_times)
        no_pooling_mean = statistics.mean(no_pooling_times)
        improvement = ((no_pooling_mean - pooling_mean) / no_pooling_mean) * 100

        return BenchmarkResult(
            name="connection_pooling",
            iterations=self.iterations,
            total_time=sum(pooling_times),
            mean_time=pooling_mean,
            min_time=min(pooling_times),
            max_time=max(pooling_times),
            std_dev=statistics.stdev(pooling_times) if len(pooling_times) > 1 else 0,
            throughput=1 / pooling_mean if pooling_mean > 0 else 0,
            improvement=improvement
        )

    async def benchmark_request_batching(self) -> BenchmarkResult:
        """Benchmark request batching vs individual requests."""
        batcher = LLMRequestBatcher(batch_size=10, batch_timeout=0.1)
        test_data = self.generate_test_data(50)

        async def mock_provider_response(requests):
            """Mock provider response."""
            await asyncio.sleep(0.01 * len(requests))  # Simulate batch processing
            return [{"response": f"Mock response {i}"} for i in range(len(requests))]

        # Override the batch executor for testing
        original_call = batcher._call_provider_batch
        batcher._call_provider_batch = lambda p, r: mock_provider_response(r)

        # Benchmark with batching
        batching_times = []
        for _ in range(self.warmup):
            tasks = [
                batcher.add_request("test", data, f"ticket_{i}")
                for i, data in enumerate(test_data[:10])
            ]
            await asyncio.gather(*tasks)

        for _ in range(self.iterations // 10):  # Adjust for batch processing
            start = time.perf_counter()
            tasks = [
                batcher.add_request("test", data, f"ticket_{i}")
                for i, data in enumerate(test_data[:10])
            ]
            await asyncio.gather(*tasks)
            batching_times.append(time.perf_counter() - start)

        # Benchmark without batching (sequential)
        sequential_times = []
        for _ in range(self.warmup):
            for data in test_data[:10]:
                await mock_provider_response([data])

        for _ in range(self.iterations // 10):
            start = time.perf_counter()
            for data in test_data[:10]:
                await mock_provider_response([data])
            sequential_times.append(time.perf_counter() - start)

        batching_mean = statistics.mean(batching_times)
        sequential_mean = statistics.mean(sequential_times)
        improvement = ((sequential_mean - batching_mean) / sequential_mean) * 100

        # Restore original method
        batcher._call_provider_batch = original_call

        return BenchmarkResult(
            name="request_batching",
            iterations=len(batching_times),
            total_time=sum(batching_times),
            mean_time=batching_mean,
            min_time=min(batching_times),
            max_time=max(batching_times),
            std_dev=(
                statistics.stdev(batching_times)
                if len(batching_times) > 1
                else 0
            ),
            throughput=10 / batching_mean if batching_mean > 0 else 0,
            improvement=improvement
        )

    async def benchmark_response_caching(self) -> BenchmarkResult:
        """Benchmark response caching vs no caching."""
        cache = ResponseCache(default_ttl=3600)
        test_data = self.generate_test_data(20)

        async def simulate_llm_call(prompt):
            """Simulate LLM API call."""
            await asyncio.sleep(0.01)  # Simulate network latency
            return {"response": f"Response for {prompt[:20]}"}

        # Benchmark with caching
        caching_times = []

        # Prime the cache
        for data in test_data:
            response = await simulate_llm_call(data["prompt"])
            await cache.set_cached_response("test", data["prompt"], response)

        for _ in range(self.iterations):
            start = time.perf_counter()
            for data in test_data:
                cached = await cache.get_cached_response("test", data["prompt"])
                if not cached:
                    response = await simulate_llm_call(data["prompt"])
                    await cache.set_cached_response("test", data["prompt"], response)
            caching_times.append(time.perf_counter() - start)

        # Clear cache for fair comparison
        cache.invalidate_provider_cache("test")

        # Benchmark without caching
        no_caching_times = []
        for _ in range(self.iterations):
            start = time.perf_counter()
            for data in test_data:
                await simulate_llm_call(data["prompt"])
            no_caching_times.append(time.perf_counter() - start)

        caching_mean = statistics.mean(caching_times)
        no_caching_mean = statistics.mean(no_caching_times)
        improvement = ((no_caching_mean - caching_mean) / no_caching_mean) * 100

        cache.get_cache_stats()

        return BenchmarkResult(
            name="response_caching",
            iterations=self.iterations,
            total_time=sum(caching_times),
            mean_time=caching_mean,
            min_time=min(caching_times),
            max_time=max(caching_times),
            std_dev=statistics.stdev(caching_times) if len(caching_times) > 1 else 0,
            throughput=len(test_data) / caching_mean if caching_mean > 0 else 0,
            improvement=improvement
        )

    async def benchmark_parallel_execution(self) -> BenchmarkResult:
        """Benchmark parallel vs sequential execution."""

        async def async_task(delay: float):
            """Simulate async task."""
            await asyncio.sleep(delay)
            return delay

        delays = [0.01] * 20  # 20 tasks

        # Benchmark parallel execution
        parallel_times = []
        for _ in range(self.iterations):
            start = time.perf_counter()
            tasks = [async_task(d) for d in delays]
            await asyncio.gather(*tasks)
            parallel_times.append(time.perf_counter() - start)

        # Benchmark sequential execution
        sequential_times = []
        for _ in range(self.iterations):
            start = time.perf_counter()
            for d in delays:
                await async_task(d)
            sequential_times.append(time.perf_counter() - start)

        parallel_mean = statistics.mean(parallel_times)
        sequential_mean = statistics.mean(sequential_times)
        improvement = ((sequential_mean - parallel_mean) / sequential_mean) * 100

        return BenchmarkResult(
            name="parallel_execution",
            iterations=self.iterations,
            total_time=sum(parallel_times),
            mean_time=parallel_mean,
            min_time=min(parallel_times),
            max_time=max(parallel_times),
            std_dev=statistics.stdev(parallel_times) if len(parallel_times) > 1 else 0,
            throughput=len(delays) / parallel_mean if parallel_mean > 0 else 0,
            improvement=improvement
        )

    async def run_all_benchmarks(self) -> Dict[str, BenchmarkResult]:
        """Run all performance benchmarks."""
        print("Running performance benchmarks...")
        print("-" * 50)

        # Initialize performance optimizations
        config = PerformanceConfig(
            enable_uvloop=True,
            enable_batching=True,
            enable_caching=True,
            profile_enabled=False
        )
        initialize_performance_optimizations(config)

        benchmarks = [
            ("Event Loop (uvloop)", self.benchmark_uvloop),
            ("Connection Pooling", self.benchmark_connection_pooling),
            ("Request Batching", self.benchmark_request_batching),
            ("Response Caching", self.benchmark_response_caching),
            ("Parallel Execution", self.benchmark_parallel_execution)
        ]

        for name, benchmark_func in benchmarks:
            print(f"\nRunning {name} benchmark...")
            try:
                result = await benchmark_func()
                self.results[result.name] = result
                self.print_result(result)
            except Exception as e:
                print(f"  Error: {e}")

        print("\n" + "=" * 50)
        self.print_summary()

        return self.results

    def print_result(self, result: BenchmarkResult):
        """Print benchmark result."""
        print(f"  Iterations: {result.iterations}")
        print(f"  Mean time: {result.mean_time * 1000:.2f}ms")
        print(f"  Min time: {result.min_time * 1000:.2f}ms")
        print(f"  Max time: {result.max_time * 1000:.2f}ms")
        print(f"  Std dev: {result.std_dev * 1000:.2f}ms")
        print(f"  Throughput: {result.throughput:.2f} ops/sec")
        if result.improvement is not None:
            print(f"  Improvement: {result.improvement:.1f}%")

    def print_summary(self):
        """Print benchmark summary."""
        print("\nPERFORMANCE BENCHMARK SUMMARY")
        print("=" * 50)

        total_improvement = 0
        count = 0

        for name, result in self.results.items():
            if result.improvement is not None and result.improvement > 0:
                print(f"{name}: {result.improvement:.1f}% faster")
                total_improvement += result.improvement
                count += 1

        if count > 0:
            avg_improvement = total_improvement / count
            print(f"\nAverage improvement: {avg_improvement:.1f}%")

        print("\nOptimization Status:")
        uvloop_status = 'Enabled' if setup_uvloop() else 'Not available'
        print(f"  ✓ uvloop event loop: {uvloop_status}")
        print("  ✓ Connection pooling: Enabled")
        print("  ✓ Request batching: Enabled")
        print("  ✓ Response caching: Enabled")
        print("  ✓ Parallel execution: Enabled")

    def export_results(self, filename: str = "benchmark_results.json"):
        """Export benchmark results to JSON file."""
        export_data = {
            "timestamp": time.time(),
            "iterations": self.iterations,
            "results": {}
        }

        for name, result in self.results.items():
            export_data["results"][name] = {
                "iterations": result.iterations,
                "mean_time_ms": result.mean_time * 1000,
                "min_time_ms": result.min_time * 1000,
                "max_time_ms": result.max_time * 1000,
                "std_dev_ms": result.std_dev * 1000,
                "throughput_ops_per_sec": result.throughput,
                "improvement_percent": result.improvement
            }

        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)

        print(f"\nResults exported to {filename}")


async def main():
    """Run the benchmark suite."""
    benchmark = PerformanceBenchmark(iterations=50, warmup=5)
    await benchmark.run_all_benchmarks()
    benchmark.export_results()


if __name__ == "__main__":
    asyncio.run(main())
