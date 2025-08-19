"""Provider response time and reliability benchmarks.

This module provides detailed benchmarks for all available providers:
1. Response time measurements
2. Throughput testing  
3. Error rate analysis
4. Connection pooling efficiency
5. Concurrent request handling
"""

import asyncio
import json
import logging
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ProviderBenchmarkResult:
    """Result from a provider performance benchmark."""

    provider_name: str
    mean_response_time: float
    min_response_time: float
    max_response_time: float
    std_response_time: float
    throughput_rps: float  # Requests per second
    success_rate: float
    error_rate: float
    concurrent_performance: Optional[float] = None
    connection_pool_efficiency: Optional[float] = None


class ProviderResponseBenchmark:
    """Comprehensive provider response time and performance benchmarks."""

    def __init__(self, iterations: int = 10, concurrent_requests: int = 5):
        self.iterations = iterations
        self.concurrent_requests = concurrent_requests
        self.results: Dict[str, ProviderBenchmarkResult] = {}

        # Performance baselines
        self.baselines = {
            'max_response_time': 10.0,  # 10 seconds max response
            'min_throughput': 0.5,      # 0.5 requests per second minimum
            'min_success_rate': 0.9,    # 90% success rate minimum
            'max_error_rate': 0.1,      # 10% error rate maximum
        }

        # Test prompts of varying complexity
        self.test_prompts = [
            "Create a simple function that returns 'Hello World'",
            "Write a Python class with constructor and two methods",
            "Implement a basic calculator with add, subtract, multiply, divide",
            "Create a JSON parser function with error handling",
            "Write a file reader that handles different encodings",
        ]

    def get_available_providers(self) -> List[str]:
        """Get list of available providers for testing."""
        providers = ['mock']  # Always available

        # Check for other providers
        try:
            from hydra.providers.anthropic import AnthropicProvider
            providers.append('anthropic')
        except ImportError:
            pass

        try:
            from hydra.providers.claude_tmux import ClaudeTmuxProvider
            providers.append('claude_tmux')
        except ImportError:
            pass

        try:
            from hydra.providers.venice import VeniceProvider
            providers.append('venice')
        except ImportError:
            pass

        return providers

    async def benchmark_provider_response_time(self, provider_name: str) -> ProviderBenchmarkResult:
        """Benchmark a specific provider's response time."""
        logger.info(f"Benchmarking {provider_name} provider response times...")

        response_times = []
        errors = 0

        # Store original provider setting
        original_provider = os.environ.get('LLM_PROVIDER')
        os.environ['LLM_PROVIDER'] = provider_name

        try:
            from hydra.providers.provider_factory import (
                create_provider_from_environment,
            )

            for iteration in range(self.iterations):
                try:
                    # Use different prompts to test variety
                    prompt = self.test_prompts[iteration % len(self.test_prompts)]

                    start_time = time.time()

                    # Create fresh provider instance
                    provider = create_provider_from_environment()

                    # Execute generation
                    result = provider.generate(prompt, model="fast")

                    response_time = time.time() - start_time
                    response_times.append(response_time)

                    logger.info(f"{provider_name} iteration {iteration + 1}: {response_time:.2f}s")

                except Exception as e:
                    errors += 1
                    logger.warning(f"{provider_name} iteration {iteration + 1} failed: {e}")

        except Exception as e:
            logger.error(f"Could not test {provider_name} provider: {e}")
            errors = self.iterations  # All failed

        finally:
            # Restore original provider setting
            if original_provider:
                os.environ['LLM_PROVIDER'] = original_provider
            elif 'LLM_PROVIDER' in os.environ:
                del os.environ['LLM_PROVIDER']

        # Calculate metrics
        if response_times:
            mean_time = statistics.mean(response_times)
            throughput = len(response_times) / sum(response_times) if sum(response_times) > 0 else 0
            success_rate = len(response_times) / self.iterations
            error_rate = errors / self.iterations

            return ProviderBenchmarkResult(
                provider_name=provider_name,
                mean_response_time=mean_time,
                min_response_time=min(response_times),
                max_response_time=max(response_times),
                std_response_time=statistics.stdev(response_times) if len(response_times) > 1 else 0,
                throughput_rps=throughput,
                success_rate=success_rate,
                error_rate=error_rate
            )
        else:
            return ProviderBenchmarkResult(
                provider_name=provider_name,
                mean_response_time=float('inf'),
                min_response_time=float('inf'),
                max_response_time=float('inf'),
                std_response_time=0,
                throughput_rps=0,
                success_rate=0,
                error_rate=1.0
            )

    async def benchmark_concurrent_requests(self, provider_name: str) -> float:
        """Benchmark provider performance under concurrent load."""
        logger.info(f"Benchmarking {provider_name} concurrent request handling...")

        # Store original provider setting
        original_provider = os.environ.get('LLM_PROVIDER')
        os.environ['LLM_PROVIDER'] = provider_name

        try:
            from hydra.providers.provider_factory import (
                create_provider_from_environment,
            )

            async def single_request(request_id: int) -> Tuple[int, float, bool]:
                """Execute a single request and return timing."""
                try:
                    start_time = time.time()
                    provider = create_provider_from_environment()
                    prompt = f"Create a function that processes request {request_id}"
                    result = provider.generate(prompt, model="fast")
                    response_time = time.time() - start_time
                    return (request_id, response_time, True)
                except Exception as e:
                    response_time = time.time() - start_time
                    logger.warning(f"Concurrent request {request_id} failed: {e}")
                    return (request_id, response_time, False)

            # Run concurrent requests
            start_time = time.time()

            tasks = []
            for i in range(self.concurrent_requests):
                task = asyncio.create_task(single_request(i))
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            total_time = time.time() - start_time

            # Process results
            successful_requests = 0
            total_response_time = 0

            for result in results:
                if isinstance(result, tuple) and len(result) == 3:
                    request_id, response_time, success = result
                    if success:
                        successful_requests += 1
                        total_response_time += response_time

            # Calculate concurrent performance metric
            if successful_requests > 0:
                avg_response_time = total_response_time / successful_requests
                concurrent_efficiency = successful_requests / total_time
                return concurrent_efficiency
            else:
                return 0.0

        except Exception as e:
            logger.error(f"Concurrent benchmark for {provider_name} failed: {e}")
            return 0.0

        finally:
            # Restore original provider setting
            if original_provider:
                os.environ['LLM_PROVIDER'] = original_provider
            elif 'LLM_PROVIDER' in os.environ:
                del os.environ['LLM_PROVIDER']

    async def benchmark_connection_pooling(self, provider_name: str) -> float:
        """Benchmark connection pooling efficiency."""
        logger.info(f"Benchmarking {provider_name} connection pooling...")

        original_provider = os.environ.get('LLM_PROVIDER')
        os.environ['LLM_PROVIDER'] = provider_name

        try:
            from hydra.providers.provider_factory import (
                create_provider_from_environment,
            )

            # Test with connection reuse
            reuse_times = []
            provider = create_provider_from_environment()

            for i in range(5):
                start_time = time.time()
                result = provider.generate(f"Simple test {i}", model="fast")
                reuse_times.append(time.time() - start_time)

            # Test with new connections each time
            new_conn_times = []
            for i in range(5):
                start_time = time.time()
                fresh_provider = create_provider_from_environment()
                result = fresh_provider.generate(f"Simple test {i}", model="fast")
                new_conn_times.append(time.time() - start_time)

            # Calculate efficiency metric
            if reuse_times and new_conn_times:
                avg_reuse = statistics.mean(reuse_times)
                avg_new = statistics.mean(new_conn_times)
                efficiency = (avg_new - avg_reuse) / avg_new if avg_new > 0 else 0
                return max(0, efficiency)  # Return 0 if no improvement
            else:
                return 0.0

        except Exception as e:
            logger.warning(f"Connection pooling benchmark for {provider_name} failed: {e}")
            return 0.0

        finally:
            if original_provider:
                os.environ['LLM_PROVIDER'] = original_provider
            elif 'LLM_PROVIDER' in os.environ:
                del os.environ['LLM_PROVIDER']

    async def run_comprehensive_provider_benchmark(self) -> Dict[str, Any]:
        """Run comprehensive benchmarks for all available providers."""
        logger.info("Starting comprehensive provider performance benchmark...")

        providers = self.get_available_providers()
        logger.info(f"Testing providers: {providers}")

        # Benchmark each provider
        for provider_name in providers:
            try:
                # Basic response time benchmark
                basic_result = await self.benchmark_provider_response_time(provider_name)

                # Enhanced benchmarks
                concurrent_perf = await self.benchmark_concurrent_requests(provider_name)
                connection_efficiency = await self.benchmark_connection_pooling(provider_name)

                # Update result with enhanced metrics
                basic_result.concurrent_performance = concurrent_perf
                basic_result.connection_pool_efficiency = connection_efficiency

                self.results[provider_name] = basic_result

            except Exception as e:
                logger.error(f"Failed to benchmark {provider_name}: {e}")
                # Create error result
                self.results[provider_name] = ProviderBenchmarkResult(
                    provider_name=provider_name,
                    mean_response_time=float('inf'),
                    min_response_time=float('inf'),
                    max_response_time=float('inf'),
                    std_response_time=0,
                    throughput_rps=0,
                    success_rate=0,
                    error_rate=1.0
                )

        # Compile comprehensive report
        report = self._compile_report()
        return report

    def _compile_report(self) -> Dict[str, Any]:
        """Compile comprehensive provider benchmark report."""
        # Calculate overall statistics
        all_providers = [r for r in self.results.values() if r.success_rate > 0]

        if all_providers:
            fastest_provider = min(all_providers, key=lambda x: x.mean_response_time)
            most_reliable = max(all_providers, key=lambda x: x.success_rate)
            highest_throughput = max(all_providers, key=lambda x: x.throughput_rps)
        else:
            fastest_provider = most_reliable = highest_throughput = None

        # Check baseline compliance
        baseline_compliance = {}
        for provider_name, result in self.results.items():
            baseline_compliance[provider_name] = {
                'response_time': result.mean_response_time <= self.baselines['max_response_time'],
                'throughput': result.throughput_rps >= self.baselines['min_throughput'],
                'success_rate': result.success_rate >= self.baselines['min_success_rate'],
                'error_rate': result.error_rate <= self.baselines['max_error_rate'],
            }
            baseline_compliance[provider_name]['overall'] = all(baseline_compliance[provider_name].values())

        report = {
            'summary': {
                'providers_tested': list(self.results.keys()),
                'total_providers': len(self.results),
                'iterations_per_provider': self.iterations,
                'concurrent_requests_tested': self.concurrent_requests,
                'fastest_provider': fastest_provider.provider_name if fastest_provider else None,
                'most_reliable_provider': most_reliable.provider_name if most_reliable else None,
                'highest_throughput_provider': highest_throughput.provider_name if highest_throughput else None,
                'timestamp': time.time()
            },
            'provider_results': {
                name: {
                    'response_time_ms': result.mean_response_time * 1000,
                    'min_response_time_ms': result.min_response_time * 1000,
                    'max_response_time_ms': result.max_response_time * 1000,
                    'std_response_time_ms': result.std_response_time * 1000,
                    'throughput_rps': result.throughput_rps,
                    'success_rate': result.success_rate,
                    'error_rate': result.error_rate,
                    'concurrent_performance': result.concurrent_performance,
                    'connection_pool_efficiency': result.connection_pool_efficiency,
                }
                for name, result in self.results.items()
            },
            'baseline_compliance': baseline_compliance,
            'baselines': self.baselines,
            'recommendations': self._generate_recommendations()
        }

        return report

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on benchmark results."""
        recommendations = []

        # Performance recommendations
        for provider_name, result in self.results.items():
            if result.success_rate == 0:
                recommendations.append(
                    f"❌ {provider_name} provider is not working. Check configuration and dependencies."
                )
            elif result.mean_response_time > self.baselines['max_response_time']:
                recommendations.append(
                    f"⚠️ {provider_name} has high response times ({result.mean_response_time:.1f}s). "
                    f"Consider optimizing or using a faster provider for time-critical operations."
                )
            elif result.success_rate < self.baselines['min_success_rate']:
                recommendations.append(
                    f"⚠️ {provider_name} has low success rate ({result.success_rate:.1%}). "
                    f"Investigate error patterns and improve error handling."
                )
            elif result.throughput_rps < self.baselines['min_throughput']:
                recommendations.append(
                    f"⚠️ {provider_name} has low throughput ({result.throughput_rps:.2f} RPS). "
                    f"Consider connection pooling or concurrent request optimization."
                )
            else:
                recommendations.append(
                    f"✅ {provider_name} meets all performance baselines."
                )

        # General recommendations
        working_providers = [name for name, result in self.results.items() if result.success_rate > 0]
        if len(working_providers) > 1:
            recommendations.append(
                "💡 Multiple providers are available. Consider implementing provider fallback for reliability."
            )

        if any(result.connection_pool_efficiency and result.connection_pool_efficiency > 0.2
               for result in self.results.values()):
            recommendations.append(
                "💡 Connection pooling shows significant benefits. Ensure it's enabled in production."
            )

        recommendations.append(
            "💡 Monitor provider performance in production and set up alerting for degradation."
        )

        return recommendations

    def save_report(self, report: Dict[str, Any], filename: str = "provider_response_benchmark.json"):
        """Save benchmark report to file."""
        benchmark_dir = Path(__file__).parent
        report_path = benchmark_dir / filename

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Provider benchmark report saved to {report_path}")
        return str(report_path)

    def print_report(self, report: Dict[str, Any]):
        """Print formatted provider benchmark report."""
        print("\n" + "="*80)
        print("PROVIDER RESPONSE TIME BENCHMARK REPORT")
        print("="*80)

        summary = report['summary']
        print(f"\nProviders Tested: {', '.join(summary['providers_tested'])}")
        print(f"Iterations per Provider: {summary['iterations_per_provider']}")
        print(f"Concurrent Requests: {summary['concurrent_requests_tested']}")

        if summary['fastest_provider']:
            print(f"Fastest Provider: {summary['fastest_provider']}")
        if summary['most_reliable_provider']:
            print(f"Most Reliable: {summary['most_reliable_provider']}")
        if summary['highest_throughput_provider']:
            print(f"Highest Throughput: {summary['highest_throughput_provider']}")

        # Provider details
        print("\n" + "-"*60)
        print("PROVIDER PERFORMANCE DETAILS:")
        print("-"*60)

        for provider_name, results in report['provider_results'].items():
            compliance = report['baseline_compliance'][provider_name]
            status = "✅ PASSED" if compliance['overall'] else "❌ FAILED"

            print(f"\n{provider_name.upper()} {status}:")
            print(f"  Response Time: {results['response_time_ms']:.1f}ms (min: {results['min_response_time_ms']:.1f}ms, max: {results['max_response_time_ms']:.1f}ms)")
            print(f"  Throughput: {results['throughput_rps']:.2f} RPS")
            print(f"  Success Rate: {results['success_rate']:.1%}")
            print(f"  Error Rate: {results['error_rate']:.1%}")

            if results['concurrent_performance'] is not None:
                print(f"  Concurrent Performance: {results['concurrent_performance']:.2f} req/sec")

            if results['connection_pool_efficiency'] is not None:
                print(f"  Connection Pool Efficiency: {results['connection_pool_efficiency']:.1%}")

        # Baselines
        print("\n" + "-"*60)
        print("PERFORMANCE BASELINES:")
        print("-"*60)
        baselines = report['baselines']
        print(f"Max Response Time: {baselines['max_response_time']}s")
        print(f"Min Throughput: {baselines['min_throughput']} RPS")
        print(f"Min Success Rate: {baselines['min_success_rate']:.1%}")
        print(f"Max Error Rate: {baselines['max_error_rate']:.1%}")

        # Recommendations
        print("\n" + "-"*60)
        print("RECOMMENDATIONS:")
        print("-"*60)
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"{i}. {rec}")

        print("\n" + "="*80)


async def main():
    """Run the provider response benchmark suite."""
    print("Starting provider response time benchmarks...")
    print("This will test all available providers and may take several minutes.\n")

    benchmark = ProviderResponseBenchmark(iterations=5, concurrent_requests=3)

    try:
        # Run comprehensive benchmark
        report = await benchmark.run_comprehensive_provider_benchmark()

        # Print and save report
        benchmark.print_report(report)
        report_path = benchmark.save_report(report)

        # Check if any provider passed baselines
        any_passed = any(
            compliance['overall']
            for compliance in report['baseline_compliance'].values()
        )

        return any_passed

    except Exception as e:
        logger.error(f"Provider benchmark failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
