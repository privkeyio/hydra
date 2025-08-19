"""Comprehensive benchmark runner for CI integration.

This script runs all performance benchmarks and generates artifacts suitable
for CI/CD pipeline integration and performance tracking over time.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.async_performance_benchmark import (
    PerformanceBenchmark as AsyncBenchmark,
)
from benchmarks.performance_benchmarks import PerformanceBenchmark
from benchmarks.provider_response_benchmark import ProviderResponseBenchmark
from benchmarks.ticket_execution_benchmark import TicketExecutionBenchmark

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ComprehensiveBenchmarkRunner:
    """Runner for all performance benchmarks with CI integration."""

    def __init__(self, output_dir: str = "benchmark_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results = {}

        # CI environment settings
        self.is_ci = os.environ.get('CI') == 'true'
        self.iterations = 2 if self.is_ci else 5  # Fewer iterations in CI for speed

    async def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all benchmark suites and compile comprehensive report."""
        logger.info("Starting comprehensive benchmark suite...")
        start_time = time.time()

        benchmark_results = {}
        errors = {}

        # 1. Performance optimizations benchmark
        try:
            logger.info("Running performance optimizations benchmark...")
            perf_benchmark = PerformanceBenchmark(iterations=self.iterations, warmup=2)
            perf_results = await perf_benchmark.run_all_benchmarks()
            benchmark_results['performance_optimizations'] = perf_results

            # Save individual report
            perf_path = self.output_dir / "performance_optimizations.json"
            perf_benchmark.export_results(str(perf_path))

        except Exception as e:
            logger.error(f"Performance optimizations benchmark failed: {e}")
            errors['performance_optimizations'] = str(e)

        # 2. Async vs sync performance benchmark
        try:
            logger.info("Running async vs sync benchmark...")
            async_benchmark = AsyncBenchmark(iterations=self.iterations)
            async_results = await async_benchmark.run_all_benchmarks()
            benchmark_results['async_performance'] = async_results

            # Save individual report
            async_path = self.output_dir / "async_performance.json"
            async_benchmark.save_report(async_results, str(async_path))

        except Exception as e:
            logger.error(f"Async performance benchmark failed: {e}")
            errors['async_performance'] = str(e)

        # 3. Ticket execution benchmark
        try:
            logger.info("Running ticket execution benchmark...")
            ticket_benchmark = TicketExecutionBenchmark(
                iterations=self.iterations,
                test_tickets_count=4  # Reduced for CI
            )
            ticket_results = await ticket_benchmark.run_comprehensive_benchmark()
            benchmark_results['ticket_execution'] = ticket_results

            # Save individual report
            ticket_path = self.output_dir / "ticket_execution.json"
            ticket_benchmark.save_report(ticket_results, str(ticket_path))

        except Exception as e:
            logger.error(f"Ticket execution benchmark failed: {e}")
            errors['ticket_execution'] = str(e)

        # 4. Provider response time benchmark
        try:
            logger.info("Running provider response benchmark...")
            provider_benchmark = ProviderResponseBenchmark(
                iterations=self.iterations,
                concurrent_requests=3
            )
            provider_results = await provider_benchmark.run_comprehensive_provider_benchmark()
            benchmark_results['provider_response'] = provider_results

            # Save individual report
            provider_path = self.output_dir / "provider_response.json"
            provider_benchmark.save_report(provider_results, str(provider_path))

        except Exception as e:
            logger.error(f"Provider response benchmark failed: {e}")
            errors['provider_response'] = str(e)

        total_time = time.time() - start_time

        # Compile comprehensive summary
        summary = self._compile_summary(benchmark_results, errors, total_time)

        # Save comprehensive report
        comprehensive_path = self.output_dir / "comprehensive_benchmark_report.json"
        with open(comprehensive_path, 'w') as f:
            json.dump(summary, f, indent=2)

        # Generate markdown summary for GitHub
        self._generate_markdown_summary(summary)

        logger.info(f"Benchmark suite completed in {total_time:.1f}s")
        return summary

    def _compile_summary(self, results: Dict[str, Any], errors: Dict[str, str], total_time: float) -> Dict[str, Any]:
        """Compile comprehensive benchmark summary."""
        # Extract key metrics from each benchmark
        summary_metrics = {}
        overall_pass = True

        # Performance optimizations
        if 'performance_optimizations' in results:
            perf_data = results['performance_optimizations']
            # Calculate average improvement across optimizations
            improvements = []
            for name, result in perf_data.items():
                if hasattr(result, 'improvement') and result.improvement:
                    improvements.append(result.improvement)

            avg_improvement = sum(improvements) / len(improvements) if improvements else 0
            summary_metrics['performance_optimizations'] = {
                'average_improvement': avg_improvement,
                'optimizations_tested': len(perf_data),
                'passed': avg_improvement > 10  # 10% improvement threshold
            }
            overall_pass &= summary_metrics['performance_optimizations']['passed']

        # Async performance
        if 'async_performance' in results:
            async_data = results['async_performance']
            goal_met = async_data.get('summary', {}).get('goal_met', False)
            avg_improvement = async_data.get('summary', {}).get('average_improvement', '0%')

            summary_metrics['async_performance'] = {
                'goal_met': goal_met,
                'average_improvement': avg_improvement,
                'benchmarks_run': async_data.get('summary', {}).get('total_benchmarks', 0),
                'passed': goal_met
            }
            overall_pass &= goal_met

        # Ticket execution
        if 'ticket_execution' in results:
            ticket_data = results['ticket_execution']
            baseline_passed = ticket_data.get('summary', {}).get('baseline_compliance', {}).get('overall_passed', False)
            performance_score = ticket_data.get('summary', {}).get('performance_score', 0)

            summary_metrics['ticket_execution'] = {
                'baseline_compliance': baseline_passed,
                'performance_score': performance_score,
                'passed': baseline_passed and performance_score >= 80
            }
            overall_pass &= summary_metrics['ticket_execution']['passed']

        # Provider response
        if 'provider_response' in results:
            provider_data = results['provider_response']
            providers_tested = provider_data.get('summary', {}).get('providers_tested', [])
            baseline_compliance = provider_data.get('baseline_compliance', {})

            passed_providers = sum(1 for comp in baseline_compliance.values()
                                   if isinstance(comp, dict) and comp.get('overall', False))

            summary_metrics['provider_response'] = {
                'providers_tested': len(providers_tested),
                'providers_passed': passed_providers,
                'passed': passed_providers > 0
            }
            overall_pass &= summary_metrics['provider_response']['passed']

        # Create comprehensive summary
        summary = {
            'meta': {
                'timestamp': time.time(),
                'total_execution_time': total_time,
                'environment': 'CI' if self.is_ci else 'local',
                'iterations': self.iterations,
                'git_commit': os.environ.get('GITHUB_SHA', 'unknown'),
                'git_branch': os.environ.get('GITHUB_REF_NAME', 'unknown')
            },
            'overall': {
                'passed': overall_pass,
                'benchmarks_run': len(results),
                'benchmarks_failed': len(errors),
                'success_rate': len(results) / (len(results) + len(errors)) if (len(results) + len(errors)) > 0 else 0
            },
            'metrics': summary_metrics,
            'detailed_results': results,
            'errors': errors,
            'baselines': {
                'single_ticket_max_time': 60.0,
                'parallel_speedup_min': 2.0,
                'async_improvement_target': 30.0,
                'provider_response_max': 10.0
            }
        }

        return summary

    def _generate_markdown_summary(self, summary: Dict[str, Any]):
        """Generate markdown summary for GitHub Actions."""
        markdown_path = self.output_dir / "benchmark_summary.md"

        overall_status = "✅ PASSED" if summary['overall']['passed'] else "❌ FAILED"

        markdown_content = f"""# Performance Benchmark Report

## Overall Status: {overall_status}

### Summary
- **Total Execution Time**: {summary['meta']['total_execution_time']:.1f}s
- **Environment**: {summary['meta']['environment']}
- **Benchmarks Run**: {summary['overall']['benchmarks_run']}
- **Success Rate**: {summary['overall']['success_rate']:.1%}

### Key Metrics

"""

        # Add metrics for each benchmark
        for benchmark_name, metrics in summary['metrics'].items():
            status = "✅" if metrics.get('passed', False) else "❌"
            markdown_content += f"#### {benchmark_name.replace('_', ' ').title()} {status}\n"

            if benchmark_name == 'performance_optimizations':
                markdown_content += f"- Average Improvement: {metrics['average_improvement']:.1f}%\n"
                markdown_content += f"- Optimizations Tested: {metrics['optimizations_tested']}\n"

            elif benchmark_name == 'async_performance':
                markdown_content += f"- Goal Met: {'Yes' if metrics['goal_met'] else 'No'}\n"
                markdown_content += f"- Average Improvement: {metrics['average_improvement']}\n"

            elif benchmark_name == 'ticket_execution':
                markdown_content += f"- Baseline Compliance: {'Yes' if metrics['baseline_compliance'] else 'No'}\n"
                markdown_content += f"- Performance Score: {metrics['performance_score']}/100\n"

            elif benchmark_name == 'provider_response':
                markdown_content += f"- Providers Tested: {metrics['providers_tested']}\n"
                markdown_content += f"- Providers Passed: {metrics['providers_passed']}\n"

            markdown_content += "\n"

        # Add errors if any
        if summary['errors']:
            markdown_content += "### Errors\n"
            for error_name, error_msg in summary['errors'].items():
                markdown_content += f"- **{error_name}**: {error_msg}\n"
            markdown_content += "\n"

        # Add artifact locations
        markdown_content += f"""### Artifacts
- Comprehensive Report: `{self.output_dir}/comprehensive_benchmark_report.json`
- Individual Reports: `{self.output_dir}/*.json`

Generated at: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
"""

        with open(markdown_path, 'w') as f:
            f.write(markdown_content)

        logger.info(f"Markdown summary saved to {markdown_path}")

    def print_summary(self, summary: Dict[str, Any]):
        """Print formatted summary to console."""
        print("\n" + "="*80)
        print("COMPREHENSIVE PERFORMANCE BENCHMARK REPORT")
        print("="*80)

        overall = summary['overall']
        meta = summary['meta']

        print(f"\nOverall Status: {'✅ PASSED' if overall['passed'] else '❌ FAILED'}")
        print(f"Total Execution Time: {meta['total_execution_time']:.1f}s")
        print(f"Environment: {meta['environment']}")
        print(f"Benchmarks Run: {overall['benchmarks_run']}")
        print(f"Benchmarks Failed: {overall['benchmarks_failed']}")
        print(f"Success Rate: {overall['success_rate']:.1%}")

        # Print key metrics
        print("\n" + "-"*60)
        print("KEY METRICS:")
        print("-"*60)

        for benchmark_name, metrics in summary['metrics'].items():
            status = "✅ PASSED" if metrics.get('passed', False) else "❌ FAILED"
            print(f"\n{benchmark_name.replace('_', ' ').title()}: {status}")

            for key, value in metrics.items():
                if key != 'passed':
                    print(f"  {key.replace('_', ' ').title()}: {value}")

        # Print errors
        if summary['errors']:
            print("\n" + "-"*60)
            print("ERRORS:")
            print("-"*60)
            for error_name, error_msg in summary['errors'].items():
                print(f"{error_name}: {error_msg}")

        print("\n" + "="*80)


async def main():
    """Run comprehensive benchmark suite."""
    runner = ComprehensiveBenchmarkRunner("benchmark_results")

    try:
        summary = await runner.run_all_benchmarks()
        runner.print_summary(summary)

        # Return exit code based on overall pass/fail
        return 0 if summary['overall']['passed'] else 1

    except Exception as e:
        logger.error(f"Benchmark runner failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
