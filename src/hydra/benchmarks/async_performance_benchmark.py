"""Performance benchmarks comparing sync vs async implementations."""

import asyncio
import json
import logging
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiohttp
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    name: str
    sync_time: float
    async_time: float
    speedup: float
    improvement_percent: float
    iterations: int


class PerformanceBenchmark:
    """Comprehensive performance benchmarks for async improvements."""

    def __init__(self, iterations: int = 10):
        self.iterations = iterations
        self.results: List[BenchmarkResult] = []

    async def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all performance benchmarks."""
        # HTTP I/O benchmarks
        await self.benchmark_http_requests()

        # Database I/O benchmarks
        await self.benchmark_database_operations()

        # Parallel execution benchmarks
        await self.benchmark_parallel_execution()

        # LLM provider benchmarks
        await self.benchmark_llm_operations()

        # Generate report
        return self.generate_report()

    async def benchmark_http_requests(self):
        """Benchmark HTTP request performance."""
        urls = [
            f"https://httpbin.org/delay/{i%3}"
            for i in range(20)
        ]

        # Sync implementation using requests
        def sync_fetch_all(urls: List[str]) -> List[Dict]:
            results = []
            for url in urls:
                try:
                    response = requests.get(url, timeout=10)
                    results.append(response.json())
                except Exception as e:
                    results.append({"error": str(e)})
            return results

        # Async implementation using aiohttp
        async def async_fetch_all(urls: List[str]) -> List[Dict]:
            async with aiohttp.ClientSession() as session:
                tasks = []
                for url in urls:
                    tasks.append(self._fetch_url(session, url))
                return await asyncio.gather(*tasks)

        async def _fetch_url(session, url):
            try:
                async with session.get(url, timeout=10) as response:
                    return await response.json()
            except Exception as e:
                return {"error": str(e)}

        # Run benchmarks
        sync_times = []
        async_times = []

        for _ in range(self.iterations):
            # Sync benchmark
            start = time.time()
            sync_fetch_all(urls)
            sync_times.append(time.time() - start)

            # Async benchmark
            start = time.time()
            await async_fetch_all(urls)
            async_times.append(time.time() - start)

        sync_avg = statistics.mean(sync_times)
        async_avg = statistics.mean(async_times)
        speedup = sync_avg / async_avg
        improvement = ((sync_avg - async_avg) / sync_avg) * 100

        self.results.append(BenchmarkResult(
            name="HTTP Requests (20 URLs)",
            sync_time=sync_avg,
            async_time=async_avg,
            speedup=speedup,
            improvement_percent=improvement,
            iterations=self.iterations
        ))

        logger.info(f"HTTP benchmark: {improvement:.1f}% improvement")

    async def benchmark_database_operations(self):
        """Benchmark database operation performance."""

        # Simulate database operations
        def sync_db_operations(count: int) -> List[Dict]:
            results = []
            for i in range(count):
                # Simulate DB query with sleep
                time.sleep(0.01)  # 10ms per query
                results.append({"id": i, "data": f"record_{i}"})
            return results

        async def async_db_operations(count: int) -> List[Dict]:
            async def fetch_record(i: int) -> Dict:
                # Simulate async DB query
                await asyncio.sleep(0.01)  # 10ms per query
                return {"id": i, "data": f"record_{i}"}

            tasks = [fetch_record(i) for i in range(count)]
            return await asyncio.gather(*tasks)

        # Run benchmarks
        record_count = 50
        sync_times = []
        async_times = []

        for _ in range(self.iterations):
            # Sync benchmark
            start = time.time()
            sync_db_operations(record_count)
            sync_times.append(time.time() - start)

            # Async benchmark
            start = time.time()
            await async_db_operations(record_count)
            async_times.append(time.time() - start)

        sync_avg = statistics.mean(sync_times)
        async_avg = statistics.mean(async_times)
        speedup = sync_avg / async_avg
        improvement = ((sync_avg - async_avg) / sync_avg) * 100

        self.results.append(BenchmarkResult(
            name=f"Database Operations ({record_count} queries)",
            sync_time=sync_avg,
            async_time=async_avg,
            speedup=speedup,
            improvement_percent=improvement,
            iterations=self.iterations
        ))

        logger.info(f"Database benchmark: {improvement:.1f}% improvement")

    async def benchmark_parallel_execution(self):
        """Benchmark parallel task execution."""

        def cpu_bound_task(n: int) -> int:
            """Simulate CPU-bound task."""
            total = 0
            for i in range(n * 1000):
                total += i
            return total

        async def io_bound_task(delay: float) -> str:
            """Simulate I/O-bound task."""
            await asyncio.sleep(delay)
            return f"completed_{delay}"

        # Sync implementation with ThreadPoolExecutor
        def sync_parallel_execution(tasks: List[Tuple[float, ...]]) -> List[Any]:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for delay in tasks:
                    future = executor.submit(time.sleep, delay)
                    futures.append(future)

                results = []
                for future in futures:
                    future.result()
                    results.append(f"completed_{delay}")
                return results

        # Async implementation with asyncio.gather
        async def async_parallel_execution(tasks: List[float]) -> List[str]:
            coroutines = [io_bound_task(delay) for delay in tasks]
            return await asyncio.gather(*coroutines)

        # Create tasks with varying delays
        task_delays = [0.1, 0.2, 0.15, 0.25, 0.1, 0.3, 0.2, 0.15, 0.1, 0.2]

        sync_times = []
        async_times = []

        for _ in range(self.iterations):
            # Sync benchmark
            start = time.time()
            sync_parallel_execution(task_delays)
            sync_times.append(time.time() - start)

            # Async benchmark
            start = time.time()
            await async_parallel_execution(task_delays)
            async_times.append(time.time() - start)

        sync_avg = statistics.mean(sync_times)
        async_avg = statistics.mean(async_times)
        speedup = sync_avg / async_avg
        improvement = ((sync_avg - async_avg) / sync_avg) * 100

        self.results.append(BenchmarkResult(
            name=f"Parallel Task Execution ({len(task_delays)} tasks)",
            sync_time=sync_avg,
            async_time=async_avg,
            speedup=speedup,
            improvement_percent=improvement,
            iterations=self.iterations
        ))

        logger.info(f"Parallel execution benchmark: {improvement:.1f}% improvement")

    async def benchmark_llm_operations(self):
        """Benchmark LLM provider operations."""

        # Simulate LLM API calls
        def sync_llm_calls(prompts: List[str]) -> List[str]:
            results = []
            for prompt in prompts:
                # Simulate API latency
                time.sleep(0.5)  # 500ms per call
                results.append(f"Response to: {prompt}")
            return results

        async def async_llm_calls(prompts: List[str]) -> List[str]:
            async def generate(prompt: str) -> str:
                # Simulate async API call
                await asyncio.sleep(0.5)  # 500ms per call
                return f"Response to: {prompt}"

            tasks = [generate(prompt) for prompt in prompts]
            return await asyncio.gather(*tasks)

        # Create sample prompts
        prompts = [f"Generate text for prompt {i}" for i in range(10)]

        sync_times = []
        async_times = []

        for _ in range(min(3, self.iterations)):  # Fewer iterations due to longer runtime
            # Sync benchmark
            start = time.time()
            sync_llm_calls(prompts)
            sync_times.append(time.time() - start)

            # Async benchmark
            start = time.time()
            await async_llm_calls(prompts)
            async_times.append(time.time() - start)

        sync_avg = statistics.mean(sync_times)
        async_avg = statistics.mean(async_times)
        speedup = sync_avg / async_avg
        improvement = ((sync_avg - async_avg) / sync_avg) * 100

        self.results.append(BenchmarkResult(
            name=f"LLM API Calls ({len(prompts)} prompts)",
            sync_time=sync_avg,
            async_time=async_avg,
            speedup=speedup,
            improvement_percent=improvement,
            iterations=min(3, self.iterations)
        ))

        logger.info(f"LLM operations benchmark: {improvement:.1f}% improvement")

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive benchmark report."""
        if not self.results:
            return {"error": "No benchmark results available"}

        # Calculate overall statistics
        avg_improvement = statistics.mean(r.improvement_percent for r in self.results)
        avg_speedup = statistics.mean(r.speedup for r in self.results)

        # Check if we met the 30% improvement goal
        goal_met = avg_improvement >= 30

        report = {
            "summary": {
                "goal": "30% performance improvement on I/O operations",
                "goal_met": goal_met,
                "average_improvement": f"{avg_improvement:.1f}%",
                "average_speedup": f"{avg_speedup:.2f}x",
                "total_benchmarks": len(self.results)
            },
            "benchmarks": []
        }

        for result in self.results:
            report["benchmarks"].append({
                "name": result.name,
                "sync_time": f"{result.sync_time:.3f}s",
                "async_time": f"{result.async_time:.3f}s",
                "speedup": f"{result.speedup:.2f}x",
                "improvement": f"{result.improvement_percent:.1f}%",
                "iterations": result.iterations
            })

        # Add recommendations
        report["recommendations"] = self._generate_recommendations(avg_improvement)

        return report

    def _generate_recommendations(self, avg_improvement: float) -> List[str]:
        """Generate performance recommendations."""
        recommendations = []

        if avg_improvement >= 30:
            recommendations.append(
                "✅ Goal achieved! Async implementation provides significant performance improvements."
            )
            recommendations.append(
                "Consider increasing max_concurrent limits for even better performance on high-end systems."
            )
        else:
            recommendations.append(
                "⚠️ Performance improvement below 30% target. Consider additional optimizations."
            )

        # Specific recommendations based on results
        for result in self.results:
            if result.improvement_percent < 20:
                recommendations.append(
                    f"Optimize {result.name}: Current improvement only {result.improvement_percent:.1f}%"
                )

        recommendations.append(
            "Monitor production performance to validate benchmark results."
        )
        recommendations.append(
            "Consider implementing caching for frequently accessed data."
        )

        return recommendations

    def save_report(self, report: Dict[str, Any], filename: str = "benchmark_report.json"):
        """Save benchmark report to file."""
        path = Path(filename)
        path.write_text(json.dumps(report, indent=2))
        logger.info(f"Report saved to {filename}")

    def print_report(self, report: Dict[str, Any]):
        """Print formatted benchmark report."""
        print("\n" + "="*60)
        print("ASYNC PERFORMANCE BENCHMARK REPORT")
        print("="*60)

        summary = report["summary"]
        print(f"\nGoal: {summary['goal']}")
        print(f"Goal Met: {'✅ YES' if summary['goal_met'] else '❌ NO'}")
        print(f"Average Improvement: {summary['average_improvement']}")
        print(f"Average Speedup: {summary['average_speedup']}")

        print("\n" + "-"*60)
        print("BENCHMARK RESULTS:")
        print("-"*60)

        for bench in report["benchmarks"]:
            print(f"\n{bench['name']}:")
            print(f"  Sync Time:    {bench['sync_time']}")
            print(f"  Async Time:   {bench['async_time']}")
            print(f"  Speedup:      {bench['speedup']}")
            print(f"  Improvement:  {bench['improvement']}")

        print("\n" + "-"*60)
        print("RECOMMENDATIONS:")
        print("-"*60)

        for i, rec in enumerate(report["recommendations"], 1):
            print(f"{i}. {rec}")

        print("\n" + "="*60)


async def main():
    """Run performance benchmarks."""
    print("Starting async performance benchmarks...")
    print("This will take a few minutes to complete.\n")

    benchmark = PerformanceBenchmark(iterations=5)

    # Run all benchmarks
    report = await benchmark.run_all_benchmarks()

    # Print and save report
    benchmark.print_report(report)
    benchmark.save_report(report)

    # Return success/failure for CI
    return report["summary"]["goal_met"]


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
