"""Parallel execution performance benchmarks."""

import time
from typing import Any, Dict

from tests.mocks import MockExecutor, MockParallelEngine

from .benchmark_runner import BenchmarkRunner


class ParallelExecutionBenchmark:
    """Benchmark parallel execution systems."""

    def __init__(self):
        self.runner = BenchmarkRunner(warmup_iterations=2)

    def benchmark_task_submission(self, iterations: int = 100) -> Dict[str, Any]:
        """Benchmark task submission overhead."""
        executor = MockExecutor(max_workers=4)
        results = {}

        def submit_single_task():
            def dummy_task():
                return "result"

            task_id = executor.submit_task("test", dummy_task)
            return task_id

        result = self.runner.run_benchmark(
            name="task_submission", func=submit_single_task, iterations=iterations
        )
        results["single_submission"] = result

        # Batch submission
        def submit_batch_tasks():
            task_ids = []
            for i in range(10):
                task_id = executor.submit_task(f"batch_{i}", lambda: f"result_{i}")
                task_ids.append(task_id)
            return task_ids

        result = self.runner.run_benchmark(
            name="batch_submission",
            func=submit_batch_tasks,
            iterations=iterations // 10,  # Fewer iterations since each does 10 tasks
        )
        results["batch_submission"] = result

        return results

    def benchmark_task_execution(self, iterations: int = 50) -> Dict[str, Any]:
        """Benchmark task execution performance."""
        results = {}

        # Different task complexities
        def simple_task():
            return sum(range(100))

        def medium_task():
            return sum(i * i for i in range(1000))

        def complex_task():
            import time

            time.sleep(0.01)  # 10ms simulated work
            return sum(i * i * i for i in range(100))

        task_types = {
            "simple": simple_task,
            "medium": medium_task,
            "complex": complex_task,
        }

        for task_name, task_func in task_types.items():
            executor = MockExecutor(max_workers=4, error_rate=0.0)

            def execute_and_wait():
                task_id = executor.submit_task(f"perf_{task_name}", task_func)
                # Wait for completion
                start_time = time.time()
                while time.time() - start_time < 5:  # 5 second timeout
                    status = executor.get_task_status(task_id)
                    if status in ["completed", "failed"]:
                        break
                    time.sleep(0.01)
                return executor.get_task_result(task_id)

            result = self.runner.run_benchmark(
                name=f"execution_{task_name}",
                func=execute_and_wait,
                iterations=iterations,
            )
            results[f"execution_{task_name}"] = result

        return results

    def benchmark_concurrent_execution(self, iterations: int = 20) -> Dict[str, Any]:
        """Benchmark concurrent task execution."""
        results = {}

        # Test different concurrency levels
        concurrency_levels = [1, 2, 4, 8, 16]

        for concurrency in concurrency_levels:
            executor = MockExecutor(max_workers=max(4, concurrency))

            def concurrent_execution():
                task_ids = []

                # Submit concurrent tasks
                for i in range(concurrency):
                    task_id = executor.submit_task(
                        f"concurrent_{i}",
                        lambda x=i: sum(range(x * 100, (x + 1) * 100)),
                    )
                    task_ids.append(task_id)

                # Wait for all to complete
                completed = 0
                start_time = time.time()
                while completed < len(task_ids) and time.time() - start_time < 10:
                    completed = 0
                    for task_id in task_ids:
                        status = executor.get_task_status(task_id)
                        if status in ["completed", "failed"]:
                            completed += 1
                    time.sleep(0.01)

                return completed == len(task_ids)

            result = self.runner.run_benchmark(
                name=f"concurrency_{concurrency}",
                func=concurrent_execution,
                iterations=iterations,
            )
            results[f"concurrency_{concurrency}"] = result

        return results

    def benchmark_workflow_execution(self, iterations: int = 30) -> Dict[str, Any]:
        """Benchmark workflow execution performance."""
        engine = MockParallelEngine(max_workers=4, max_parallel=2)
        results = {}

        # Different workflow sizes
        workflow_sizes = [5, 10, 20, 50]

        for size in workflow_sizes:

            def execute_workflow():
                tasks = []
                for i in range(size):
                    tasks.append(
                        {
                            "func": lambda x=i: f"task_{x}_result",
                            "args": [],
                            "kwargs": {},
                        }
                    )

                workflow_id = engine.execute_workflow(f"perf_workflow_{size}", tasks)

                # Wait for completion
                success = engine.wait_for_workflow(workflow_id, timeout=15.0)
                return success

            result = self.runner.run_benchmark(
                name=f"workflow_size_{size}",
                func=execute_workflow,
                iterations=iterations,
            )
            results[f"workflow_size_{size}"] = result

        return results

    def benchmark_error_recovery(self, iterations: int = 50) -> Dict[str, Any]:
        """Benchmark error recovery performance."""
        results = {}

        # Different error rates
        error_rates = [0.1, 0.3, 0.5, 0.7]

        for error_rate in error_rates:
            executor = MockExecutor(max_workers=4, error_rate=error_rate)

            def execute_with_errors():
                task_id = executor.submit_task("error_test", lambda: "success_result")

                # Wait for completion
                start_time = time.time()
                while time.time() - start_time < 3:
                    status = executor.get_task_status(task_id)
                    if status in ["completed", "failed"]:
                        break
                    time.sleep(0.01)

                return executor.get_task_result(task_id)

            result = self.runner.run_benchmark(
                name=f"error_rate_{error_rate}",
                func=execute_with_errors,
                iterations=iterations,
            )
            results[f"error_rate_{error_rate}"] = result

        return results

    def benchmark_resource_utilization(self, iterations: int = 20) -> Dict[str, Any]:
        """Benchmark resource utilization efficiency."""
        results = {}

        # Test with different worker pool sizes
        worker_counts = [1, 2, 4, 8]

        for worker_count in worker_counts:
            executor = MockExecutor(max_workers=worker_count)

            def resource_intensive():
                # Submit more tasks than workers to test queuing
                task_count = worker_count * 3
                task_ids = []

                for i in range(task_count):
                    task_id = executor.submit_task(
                        f"resource_{i}", lambda x=i: sum(range(x * 500, (x + 1) * 500))
                    )
                    task_ids.append(task_id)

                # Wait for all tasks
                completed = 0
                start_time = time.time()
                while completed < len(task_ids) and time.time() - start_time < 15:
                    completed = 0
                    for task_id in task_ids:
                        status = executor.get_task_status(task_id)
                        if status in ["completed", "failed"]:
                            completed += 1
                    time.sleep(0.01)

                stats = executor.get_stats()
                return stats

            result = self.runner.run_benchmark(
                name=f"workers_{worker_count}",
                func=resource_intensive,
                iterations=iterations,
            )
            results[f"workers_{worker_count}"] = result

        return results

    def benchmark_throughput_scaling(self, iterations: int = 15) -> Dict[str, Any]:
        """Benchmark throughput scaling with load."""
        results = {}

        # Test with increasing load
        load_levels = [10, 50, 100, 200, 500]

        for load in load_levels:
            executor = MockExecutor(max_workers=8)

            def throughput_test():
                task_ids = []
                start_time = time.time()

                # Submit all tasks
                for i in range(load):
                    task_id = executor.submit_task(f"throughput_{i}", lambda x=i: x * 2)
                    task_ids.append(task_id)

                # Wait for all to complete
                completed = 0
                while completed < len(task_ids) and time.time() - start_time < 30:
                    completed = 0
                    for task_id in task_ids:
                        status = executor.get_task_status(task_id)
                        if status in ["completed", "failed"]:
                            completed += 1
                    time.sleep(0.01)

                total_time = time.time() - start_time
                throughput = completed / total_time if total_time > 0 else 0
                return throughput

            result = self.runner.run_benchmark(
                name=f"load_{load}", func=throughput_test, iterations=iterations
            )
            results[f"load_{load}"] = result

        return results

    def run_all_benchmarks(self, iterations: int = 30) -> Dict[str, Any]:
        """Run all parallel execution benchmarks."""
        all_results = {}

        print("Running task submission benchmark...")
        all_results["task_submission"] = self.benchmark_task_submission(iterations)

        print("Running task execution benchmark...")
        all_results["task_execution"] = self.benchmark_task_execution(iterations)

        print("Running concurrent execution benchmark...")
        all_results["concurrent_execution"] = self.benchmark_concurrent_execution(
            iterations
        )

        print("Running workflow execution benchmark...")
        all_results["workflow_execution"] = self.benchmark_workflow_execution(
            iterations
        )

        print("Running error recovery benchmark...")
        all_results["error_recovery"] = self.benchmark_error_recovery(iterations)

        print("Running resource utilization benchmark...")
        all_results["resource_utilization"] = self.benchmark_resource_utilization(
            iterations
        )

        print("Running throughput scaling benchmark...")
        all_results["throughput_scaling"] = self.benchmark_throughput_scaling(
            iterations
        )

        return all_results

    def get_summary(self) -> Dict[str, Any]:
        """Get benchmark summary."""
        return self.runner.get_summary()

    def save_results(self, filename: str):
        """Save benchmark results."""
        self.runner.save_results(filename)
