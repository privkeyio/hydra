"""Performance benchmarks for ticket execution workflow.

This module provides comprehensive benchmarks for:
1. Single ticket execution performance
2. Parallel ticket execution performance  
3. Provider response times
4. End-to-end workflow performance

The benchmarks are designed to validate the performance improvements
from the async/await implementation and measure against baseline metrics.
"""

import asyncio
import json
import logging
import os
import shutil
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TicketBenchmarkResult:
    """Result from a ticket execution benchmark."""

    name: str
    single_ticket_time: float
    parallel_ticket_time: float
    speedup_factor: float
    improvement_percent: float
    tickets_completed: int
    errors_count: int
    provider_type: str
    iterations: int
    baseline_met: bool  # Whether we met performance baseline


class TicketExecutionBenchmark:
    """Comprehensive benchmarks for ticket execution performance."""

    def __init__(self, iterations: int = 5, test_tickets_count: int = 6):
        self.iterations = iterations
        self.test_tickets_count = test_tickets_count
        self.results: List[TicketBenchmarkResult] = []
        self.temp_dirs: List[str] = []

        # Performance baselines (in seconds)
        self.baselines = {
            "single_ticket_max": 60.0,  # Single ticket should complete within 60s
            "parallel_speedup_min": 2.0,  # Parallel should be at least 2x faster
            "provider_response_max": 5.0,  # Provider should respond within 5s
        }

    def cleanup_temp_dirs(self):
        """Clean up temporary directories."""
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        self.temp_dirs.clear()

    def create_test_tickets(self, tickets_path: str, count: int = 6) -> None:
        """Create test tickets file for benchmarking."""
        tickets_content = """version: '1.0'
project:
  name: Benchmark Test Project
  description: Performance benchmark test tickets
  created_at: '2025-08-18T00:00:00'

tickets:
"""

        for i in range(1, count + 1):
            ticket_id = str(i).zfill(3)
            tickets_content += f"""- id: '{ticket_id}'
  title: 'Benchmark Test Ticket {i}'
  status: TODO
  priority: {i}
  model: fast
  description: |
    Simple test ticket for performance benchmarking.
    Creates a basic Python file with minimal functionality.
  acceptance_criteria:
  - Create a Python file named 'test_{ticket_id}.py'
  - Add a simple function that returns "Hello from ticket {ticket_id}"
  - Add basic docstring and type hints
  dependencies: []
  
"""

        with open(tickets_path, 'w') as f:
            f.write(tickets_content)

        logger.info(f"Created {count} test tickets in {tickets_path}")

    def create_test_environment(self) -> Tuple[str, str]:
        """Create a temporary test environment."""
        temp_dir = tempfile.mkdtemp(prefix="hydra_bench_")
        self.temp_dirs.append(temp_dir)

        # Initialize git repo
        os.chdir(temp_dir)
        os.system("git init")
        os.system("git config user.email 'test@benchmark.com'")
        os.system("git config user.name 'Benchmark Test'")

        # Create tickets file
        tickets_path = os.path.join(temp_dir, "tickets.yaml")
        self.create_test_tickets(tickets_path, self.test_tickets_count)

        # Initial commit
        os.system("git add .")
        os.system("git commit -m 'Initial benchmark setup'")

        return temp_dir, tickets_path

    async def benchmark_single_ticket_execution(self) -> Dict[str, float]:
        """Benchmark single ticket execution performance."""
        logger.info("Running single ticket execution benchmark...")

        execution_times = []
        provider_response_times = []

        for iteration in range(self.iterations):
            # Create fresh test environment
            test_dir, tickets_path = self.create_test_environment()

            # Import here to avoid circular imports
            from hydra.tickets.ticket_executor import execute_single_ticket

            # Override environment for mock execution
            original_provider = os.environ.get('LLM_PROVIDER')
            os.environ['LLM_PROVIDER'] = 'mock'

            try:
                # Measure provider response time
                provider_start = time.time()

                # Measure total execution time
                execution_start = time.time()

                # Execute single ticket
                success = execute_single_ticket(
                    tickets_path,
                    '001',
                    skip_preflight=True,
                    allow_system_modifications=True
                )

                execution_time = time.time() - execution_start
                provider_response_time = time.time() - provider_start

                if success:
                    execution_times.append(execution_time)
                    provider_response_times.append(provider_response_time)
                    logger.info(f"Iteration {iteration + 1}: {execution_time:.2f}s")
                else:
                    logger.warning(f"Iteration {iteration + 1}: Failed")

            except Exception as e:
                logger.error(f"Iteration {iteration + 1} failed: {e}")
            finally:
                # Restore original provider
                if original_provider:
                    os.environ['LLM_PROVIDER'] = original_provider
                elif 'LLM_PROVIDER' in os.environ:
                    del os.environ['LLM_PROVIDER']

        # Calculate statistics
        if execution_times:
            return {
                'mean_execution_time': statistics.mean(execution_times),
                'min_execution_time': min(execution_times),
                'max_execution_time': max(execution_times),
                'std_execution_time': statistics.stdev(execution_times) if len(execution_times) > 1 else 0,
                'mean_provider_response': statistics.mean(provider_response_times),
                'success_rate': len(execution_times) / self.iterations,
            }
        else:
            return {
                'mean_execution_time': float('inf'),
                'min_execution_time': float('inf'),
                'max_execution_time': float('inf'),
                'std_execution_time': 0,
                'mean_provider_response': float('inf'),
                'success_rate': 0,
            }

    async def benchmark_parallel_ticket_execution(self) -> Dict[str, float]:
        """Benchmark parallel ticket execution performance."""
        logger.info("Running parallel ticket execution benchmark...")

        parallel_times = []
        sequential_times = []

        for iteration in range(self.iterations):
            # Create fresh test environment
            test_dir, tickets_path = self.create_test_environment()

            # Import here to avoid circular imports
            from hydra.tickets.ticket_executor import (
                execute_single_ticket,
                run_all_tickets,
            )

            # Override environment for mock execution
            original_provider = os.environ.get('LLM_PROVIDER')
            os.environ['LLM_PROVIDER'] = 'mock'

            try:
                # Measure sequential execution
                sequential_start = time.time()
                for i in range(1, min(4, self.test_tickets_count) + 1):  # Test with 3 tickets
                    ticket_id = str(i).zfill(3)
                    execute_single_ticket(
                        tickets_path,
                        ticket_id,
                        skip_preflight=True,
                        allow_system_modifications=True
                    )
                sequential_time = time.time() - sequential_start
                sequential_times.append(sequential_time)

                # Reset test environment
                test_dir, tickets_path = self.create_test_environment()

                # Measure parallel execution
                parallel_start = time.time()
                run_all_tickets(
                    tickets_path,
                    max_parallel=3,
                    skip_preflight=True
                )
                parallel_time = time.time() - parallel_start
                parallel_times.append(parallel_time)

                logger.info(f"Iteration {iteration + 1}: Sequential={sequential_time:.2f}s, Parallel={parallel_time:.2f}s")

            except Exception as e:
                logger.error(f"Iteration {iteration + 1} failed: {e}")
            finally:
                # Restore original provider
                if original_provider:
                    os.environ['LLM_PROVIDER'] = original_provider
                elif 'LLM_PROVIDER' in os.environ:
                    del os.environ['LLM_PROVIDER']

        # Calculate statistics
        if parallel_times and sequential_times:
            mean_parallel = statistics.mean(parallel_times)
            mean_sequential = statistics.mean(sequential_times)
            speedup = mean_sequential / mean_parallel if mean_parallel > 0 else 0
            improvement = ((mean_sequential - mean_parallel) / mean_sequential) * 100 if mean_sequential > 0 else 0

            return {
                'mean_parallel_time': mean_parallel,
                'mean_sequential_time': mean_sequential,
                'speedup_factor': speedup,
                'improvement_percent': improvement,
                'parallel_std': statistics.stdev(parallel_times) if len(parallel_times) > 1 else 0,
                'sequential_std': statistics.stdev(sequential_times) if len(sequential_times) > 1 else 0,
            }
        else:
            return {
                'mean_parallel_time': float('inf'),
                'mean_sequential_time': float('inf'),
                'speedup_factor': 0,
                'improvement_percent': 0,
                'parallel_std': 0,
                'sequential_std': 0,
            }

    async def benchmark_provider_response_times(self) -> Dict[str, Dict[str, float]]:
        """Benchmark different provider response times."""
        logger.info("Running provider response time benchmark...")

        providers = ['mock', 'claude_tmux']  # Test available providers
        provider_results = {}

        for provider in providers:
            logger.info(f"Benchmarking {provider} provider...")
            response_times = []

            # Override environment
            original_provider = os.environ.get('LLM_PROVIDER')
            os.environ['LLM_PROVIDER'] = provider

            try:
                from hydra.providers.provider_factory import (
                    create_provider_from_environment,
                )

                for iteration in range(self.iterations):
                    try:
                        start_time = time.time()

                        # Create provider instance
                        provider_instance = create_provider_from_environment()

                        # Test simple generation
                        result = provider_instance.generate(
                            "Create a simple Python function that returns 'Hello World'",
                            model="fast"
                        )

                        response_time = time.time() - start_time
                        response_times.append(response_time)

                        logger.info(f"{provider} iteration {iteration + 1}: {response_time:.2f}s")

                    except Exception as e:
                        logger.warning(f"{provider} iteration {iteration + 1} failed: {e}")

                if response_times:
                    provider_results[provider] = {
                        'mean_response_time': statistics.mean(response_times),
                        'min_response_time': min(response_times),
                        'max_response_time': max(response_times),
                        'std_response_time': statistics.stdev(response_times) if len(response_times) > 1 else 0,
                        'success_rate': len(response_times) / self.iterations,
                    }
                else:
                    provider_results[provider] = {
                        'mean_response_time': float('inf'),
                        'min_response_time': float('inf'),
                        'max_response_time': float('inf'),
                        'std_response_time': 0,
                        'success_rate': 0,
                    }

            except ImportError as e:
                logger.warning(f"Could not test {provider} provider: {e}")
                provider_results[provider] = {'error': str(e)}
            finally:
                # Restore original provider
                if original_provider:
                    os.environ['LLM_PROVIDER'] = original_provider
                elif 'LLM_PROVIDER' in os.environ:
                    del os.environ['LLM_PROVIDER']

        return provider_results

    async def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """Run all ticket execution benchmarks."""
        logger.info("Starting comprehensive ticket execution benchmark...")

        try:
            # Run individual benchmarks
            single_ticket_results = await self.benchmark_single_ticket_execution()
            parallel_ticket_results = await self.benchmark_parallel_ticket_execution()
            provider_response_results = await self.benchmark_provider_response_times()

            # Check baseline compliance
            single_baseline_met = single_ticket_results['mean_execution_time'] <= self.baselines['single_ticket_max']
            parallel_baseline_met = parallel_ticket_results['speedup_factor'] >= self.baselines['parallel_speedup_min']

            # Calculate overall performance score
            performance_score = 0
            if single_baseline_met:
                performance_score += 40
            if parallel_baseline_met:
                performance_score += 40
            if single_ticket_results['success_rate'] >= 0.8:
                performance_score += 20

            # Compile comprehensive report
            report = {
                'summary': {
                    'performance_score': performance_score,
                    'baseline_compliance': {
                        'single_ticket_execution': single_baseline_met,
                        'parallel_execution': parallel_baseline_met,
                        'overall_passed': single_baseline_met and parallel_baseline_met
                    },
                    'iterations': self.iterations,
                    'test_tickets_count': self.test_tickets_count,
                    'timestamp': time.time()
                },
                'single_ticket_execution': single_ticket_results,
                'parallel_ticket_execution': parallel_ticket_results,
                'provider_response_times': provider_response_results,
                'baselines': self.baselines,
                'recommendations': self._generate_recommendations(
                    single_ticket_results, parallel_ticket_results, provider_response_results
                )
            }

            return report

        finally:
            # Clean up temporary directories
            self.cleanup_temp_dirs()

    def _generate_recommendations(
        self,
        single_results: Dict[str, float],
        parallel_results: Dict[str, float],
        provider_results: Dict[str, Dict[str, float]]
    ) -> List[str]:
        """Generate performance recommendations based on benchmark results."""
        recommendations = []

        # Single ticket performance
        if single_results['mean_execution_time'] > self.baselines['single_ticket_max']:
            recommendations.append(
                f"⚠️ Single ticket execution is slower than baseline "
                f"({single_results['mean_execution_time']:.1f}s vs {self.baselines['single_ticket_max']}s). "
                f"Consider optimizing provider initialization and file I/O operations."
            )
        else:
            recommendations.append(
                f"✅ Single ticket execution meets baseline performance "
                f"({single_results['mean_execution_time']:.1f}s)."
            )

        # Parallel execution performance
        if parallel_results['speedup_factor'] < self.baselines['parallel_speedup_min']:
            recommendations.append(
                f"⚠️ Parallel execution speedup is below baseline "
                f"({parallel_results['speedup_factor']:.1f}x vs {self.baselines['parallel_speedup_min']}x). "
                f"Consider increasing parallelism or optimizing task distribution."
            )
        else:
            recommendations.append(
                f"✅ Parallel execution achieves good speedup "
                f"({parallel_results['speedup_factor']:.1f}x, {parallel_results['improvement_percent']:.1f}% improvement)."
            )

        # Provider performance
        for provider, results in provider_results.items():
            if 'error' not in results:
                response_time = results['mean_response_time']
                if response_time > self.baselines['provider_response_max']:
                    recommendations.append(
                        f"⚠️ {provider} provider response time is high "
                        f"({response_time:.1f}s). Consider connection pooling or caching."
                    )
                else:
                    recommendations.append(
                        f"✅ {provider} provider has good response time ({response_time:.1f}s)."
                    )

        # Success rate recommendations
        if single_results['success_rate'] < 1.0:
            recommendations.append(
                f"⚠️ Single ticket execution success rate is {single_results['success_rate']:.1%}. "
                f"Investigate and fix execution failures."
            )

        # General recommendations
        recommendations.append("💡 Monitor these metrics in production to track performance regressions.")
        recommendations.append("💡 Consider implementing performance alerting for key metrics.")

        return recommendations

    def save_report(self, report: Dict[str, Any], filename: str = "ticket_execution_benchmark.json"):
        """Save benchmark report to file."""
        benchmark_dir = Path(__file__).parent
        report_path = benchmark_dir / filename

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Benchmark report saved to {report_path}")
        return str(report_path)

    def print_report(self, report: Dict[str, Any]):
        """Print formatted benchmark report."""
        print("\n" + "="*80)
        print("TICKET EXECUTION PERFORMANCE BENCHMARK REPORT")
        print("="*80)

        summary = report['summary']
        print(f"\nPerformance Score: {summary['performance_score']}/100")
        print(f"Baseline Compliance: {'✅ PASSED' if summary['baseline_compliance']['overall_passed'] else '❌ FAILED'}")
        print(f"Iterations: {summary['iterations']}")
        print(f"Test Tickets: {summary['test_tickets_count']}")

        # Single ticket results
        print("\n" + "-"*60)
        print("SINGLE TICKET EXECUTION:")
        print("-"*60)
        single = report['single_ticket_execution']
        print(f"Mean Execution Time: {single['mean_execution_time']:.2f}s")
        print(f"Min/Max Time: {single['min_execution_time']:.2f}s / {single['max_execution_time']:.2f}s")
        print(f"Standard Deviation: {single['std_execution_time']:.2f}s")
        print(f"Provider Response Time: {single['mean_provider_response']:.2f}s")
        print(f"Success Rate: {single['success_rate']:.1%}")

        # Parallel execution results
        print("\n" + "-"*60)
        print("PARALLEL TICKET EXECUTION:")
        print("-"*60)
        parallel = report['parallel_ticket_execution']
        print(f"Parallel Time: {parallel['mean_parallel_time']:.2f}s")
        print(f"Sequential Time: {parallel['mean_sequential_time']:.2f}s")
        print(f"Speedup Factor: {parallel['speedup_factor']:.2f}x")
        print(f"Improvement: {parallel['improvement_percent']:.1f}%")

        # Provider response times
        print("\n" + "-"*60)
        print("PROVIDER RESPONSE TIMES:")
        print("-"*60)
        for provider, results in report['provider_response_times'].items():
            if 'error' not in results:
                print(f"{provider.upper()}:")
                print(f"  Mean Response: {results['mean_response_time']:.2f}s")
                print(f"  Min/Max: {results['min_response_time']:.2f}s / {results['max_response_time']:.2f}s")
                print(f"  Success Rate: {results['success_rate']:.1%}")
            else:
                print(f"{provider.upper()}: Error - {results['error']}")

        # Baselines
        print("\n" + "-"*60)
        print("PERFORMANCE BASELINES:")
        print("-"*60)
        baselines = report['baselines']
        print(f"Single Ticket Max Time: {baselines['single_ticket_max']}s")
        print(f"Parallel Speedup Min: {baselines['parallel_speedup_min']}x")
        print(f"Provider Response Max: {baselines['provider_response_max']}s")

        # Recommendations
        print("\n" + "-"*60)
        print("RECOMMENDATIONS:")
        print("-"*60)
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"{i}. {rec}")

        print("\n" + "="*80)


async def main():
    """Run the ticket execution benchmark suite."""
    print("Starting ticket execution performance benchmarks...")
    print("This will create temporary test environments and may take several minutes.\n")

    benchmark = TicketExecutionBenchmark(iterations=3, test_tickets_count=6)

    try:
        # Run comprehensive benchmark
        report = await benchmark.run_comprehensive_benchmark()

        # Print and save report
        benchmark.print_report(report)
        report_path = benchmark.save_report(report)

        # Return success based on baseline compliance
        return report['summary']['baseline_compliance']['overall_passed']

    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        return False
    finally:
        # Ensure cleanup
        benchmark.cleanup_temp_dirs()


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
