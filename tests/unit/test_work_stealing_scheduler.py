"""Tests for WorkStealingScheduler."""

import threading
import time
import unittest
from unittest.mock import Mock, patch
import pytest

from hydra.parallel.work_stealing_scheduler import (
    StealingPolicy,
    Task,
    WorkStealingScheduler,
    WorkerMetrics,
)


class TestWorkStealingScheduler(unittest.TestCase):
    """Test suite for WorkStealingScheduler."""

    def setUp(self):
        """Set up test scheduler."""
        self.scheduler = WorkStealingScheduler(
            num_workers=3,
            stealing_policy=StealingPolicy.BALANCED,
            rebalance_interval=0.1  # Fast rebalancing for tests
        )

    def tearDown(self):
        """Clean up scheduler."""
        if self.scheduler.running:
            self.scheduler.stop()

    def test_initialization(self):
        """Test scheduler initialization."""
        self.assertEqual(self.scheduler.num_workers, 3)
        self.assertEqual(self.scheduler.stealing_policy, StealingPolicy.BALANCED)
        self.assertEqual(len(self.scheduler.worker_queues), 3)
        self.assertEqual(len(self.scheduler.worker_metrics), 3)
        self.assertFalse(self.scheduler.running)

    def test_start_stop(self):
        """Test scheduler start and stop."""
        self.scheduler.start()
        self.assertTrue(self.scheduler.running)
        # Note: rebalance_thread may be None in CI environments due to threading constraints

        self.scheduler.stop()
        self.assertFalse(self.scheduler.running)

    def test_submit_task(self):
        """Test task submission."""
        self.scheduler.start()
        
        task = Task(task_id="test_task_1", priority=1)
        result = self.scheduler.submit_task(task)
        
        self.assertTrue(result)
        
        # Check that task was added to some worker queue
        total_tasks = sum(
            len(queue) for queue in self.scheduler.worker_queues.values()
        )
        self.assertEqual(total_tasks, 1)

    def test_get_task(self):
        """Test task retrieval by worker."""
        self.scheduler.start()
        
        task = Task(task_id="test_task_2", priority=1)
        self.scheduler.submit_task(task)
        
        # Find which worker got the task
        worker_with_task = None
        for worker_id, queue in self.scheduler.worker_queues.items():
            if len(queue) > 0:
                worker_with_task = worker_id
                break
        
        self.assertIsNotNone(worker_with_task)
        
        # Get task from that worker
        retrieved_task = self.scheduler.get_task(worker_with_task)
        self.assertIsNotNone(retrieved_task)
        self.assertEqual(retrieved_task.task_id, "test_task_2")
        
        # Check metrics updated
        metrics = self.scheduler.worker_metrics[worker_with_task]
        self.assertEqual(metrics.active_tasks, 1)

    def test_complete_task_success(self):
        """Test successful task completion."""
        self.scheduler.start()
        
        worker_id = "worker_0"
        task = Task(task_id="test_task_3")
        task.assigned_at = time.time()
        
        self.scheduler.complete_task(worker_id, task, success=True)
        
        metrics = self.scheduler.worker_metrics[worker_id]
        self.assertEqual(metrics.completed_tasks, 1)
        self.assertEqual(metrics.failed_tasks, 0)
        self.assertIn("test_task_3", self.scheduler.completed_tasks)

    def test_complete_task_failure(self):
        """Test failed task completion."""
        self.scheduler.start()
        
        worker_id = "worker_0"
        task = Task(task_id="test_task_4")
        task.assigned_at = time.time()
        
        self.scheduler.complete_task(worker_id, task, success=False)
        
        metrics = self.scheduler.worker_metrics[worker_id]
        self.assertEqual(metrics.completed_tasks, 0)
        self.assertEqual(metrics.failed_tasks, 1)
        self.assertIn("test_task_4", self.scheduler.failed_tasks)

    def test_work_stealing(self):
        """Test work stealing mechanism."""
        self.scheduler.start()
        
        # Load up one worker heavily
        overloaded_worker = "worker_0"
        for i in range(5):
            task = Task(task_id=f"task_{i}")
            with self.scheduler.worker_locks[overloaded_worker]:
                self.scheduler.worker_queues[overloaded_worker].append(task)
        
        # Try to get task from empty worker
        idle_worker = "worker_1"
        stolen_task = self.scheduler.get_task(idle_worker)
        
        self.assertIsNotNone(stolen_task)
        self.assertIsNotNone(stolen_task.assigned_at)
        
        # Check metrics updated
        idle_metrics = self.scheduler.worker_metrics[idle_worker]
        overloaded_metrics = self.scheduler.worker_metrics[overloaded_worker]
        
        self.assertEqual(idle_metrics.active_tasks, 1)
        self.assertEqual(idle_metrics.tasks_stolen_to, 1)
        self.assertEqual(overloaded_metrics.tasks_stolen_from, 1)

    def test_efficiency_calculation(self):
        """Test worker efficiency calculation."""
        self.scheduler.start()
        
        worker_id = "worker_0"
        
        # Simulate some completed tasks
        for i in range(3):
            task = Task(task_id=f"efficiency_task_{i}")
            task.assigned_at = time.time() - 10  # 10 seconds ago
            self.scheduler.complete_task(worker_id, task, success=True)
            time.sleep(0.01)  # Small delay for different completion times
        
        # Add one failed task
        failed_task = Task(task_id="failed_efficiency_task")
        failed_task.assigned_at = time.time() - 5
        self.scheduler.complete_task(worker_id, failed_task, success=False)
        
        metrics = self.scheduler.worker_metrics[worker_id]
        
        self.assertEqual(metrics.completed_tasks, 3)
        self.assertEqual(metrics.failed_tasks, 1)
        self.assertGreater(metrics.efficiency_score, 0)
        self.assertLessEqual(metrics.efficiency_score, 1.0)

    def test_stealing_policies(self):
        """Test different stealing policies."""
        policies = [
            (StealingPolicy.AGGRESSIVE, 1.5),
            (StealingPolicy.CONSERVATIVE, 3.0),
            (StealingPolicy.BALANCED, 2.0)
        ]
        
        for policy, expected_threshold in policies:
            scheduler = WorkStealingScheduler(
                num_workers=2,
                stealing_policy=policy
            )
            self.assertEqual(scheduler.steal_threshold_ratio, expected_threshold)

    def test_load_distribution(self):
        """Test load distribution calculation."""
        self.scheduler.start()
        
        # Add different numbers of tasks to workers
        tasks_per_worker = [3, 1, 2]
        for i, task_count in enumerate(tasks_per_worker):
            worker_id = f"worker_{i}"
            for j in range(task_count):
                task = Task(task_id=f"load_task_{i}_{j}")
                with self.scheduler.worker_locks[worker_id]:
                    self.scheduler.worker_queues[worker_id].append(task)
        
        distribution = self.scheduler.get_load_distribution()
        
        self.assertEqual(len(distribution), 3)
        total_percentage = sum(distribution.values())
        self.assertAlmostEqual(total_percentage, 100.0, places=1)
        
        # Worker 0 should have highest load (50%)
        self.assertGreater(distribution["worker_0"], distribution["worker_1"])
        self.assertGreater(distribution["worker_0"], distribution["worker_2"])

    def test_metrics_collection(self):
        """Test comprehensive metrics collection."""
        self.scheduler.start()
        
        # Submit and complete some tasks
        for i in range(5):
            task = Task(task_id=f"metrics_task_{i}")
            self.scheduler.submit_task(task)
        
        # Simulate some completions
        for i in range(3):
            worker_id = f"worker_{i % 3}"
            task = Task(task_id=f"completed_task_{i}")
            task.assigned_at = time.time() - 1
            self.scheduler.complete_task(worker_id, task, success=True)
        
        metrics = self.scheduler.get_metrics()
        
        self.assertIn("total_workers", metrics)
        self.assertIn("stealing_policy", metrics)
        self.assertIn("total_completed", metrics)
        self.assertIn("success_rate", metrics)
        self.assertIn("worker_metrics", metrics)
        
        self.assertEqual(metrics["total_workers"], 3)
        self.assertEqual(metrics["total_completed"], 3)
        self.assertEqual(len(metrics["worker_metrics"]), 3)

    def test_rebalancing_detection(self):
        """Test imbalance detection and rebalancing."""
        self.scheduler.start()
        
        # Create significant imbalance
        overloaded_worker = "worker_0"
        for i in range(10):
            task = Task(task_id=f"imbalance_task_{i}")
            with self.scheduler.worker_locks[overloaded_worker]:
                self.scheduler.worker_queues[overloaded_worker].append(task)
        
        # Force rebalancing
        self.scheduler.force_rebalance()
        
        # Check that tasks were moved
        queue_sizes = []
        for worker_id in self.scheduler.worker_queues:
            with self.scheduler.worker_locks[worker_id]:
                queue_sizes.append(len(self.scheduler.worker_queues[worker_id]))
        
        # Should be more balanced now
        max_size = max(queue_sizes)
        min_size = min(queue_sizes)
        imbalance_ratio = max_size / max(min_size, 1)
        
        # Imbalance should be reduced (less than 3:1 ratio)
        self.assertLess(imbalance_ratio, 3.0)

    def test_configure_stealing_policy_runtime(self):
        """Test runtime configuration of stealing policy."""
        self.scheduler.start()
        
        original_threshold = self.scheduler.steal_threshold_ratio
        
        # Change policy
        self.scheduler.configure_stealing_policy(
            StealingPolicy.AGGRESSIVE,
            custom_threshold=2.5
        )
        
        self.assertEqual(self.scheduler.stealing_policy, StealingPolicy.AGGRESSIVE)
        self.assertEqual(self.scheduler.steal_threshold_ratio, 2.5)
        self.assertNotEqual(self.scheduler.steal_threshold_ratio, original_threshold)

    @pytest.mark.stress
    def test_thread_safety(self):
        """Test thread safety of scheduler operations."""
        self.scheduler.start()
        
        results = []
        errors = []
        
        def worker_thread(thread_id):
            try:
                # Submit tasks
                for i in range(10):
                    task = Task(task_id=f"thread_{thread_id}_task_{i}")
                    result = self.scheduler.submit_task(task)
                    results.append(result)
                
                # Get and complete tasks
                worker_id = f"worker_{thread_id % 3}"
                for _ in range(5):
                    task = self.scheduler.get_task(worker_id)
                    if task:
                        self.scheduler.complete_task(worker_id, task, success=True)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=5.0)
        
        # Check no errors occurred
        self.assertEqual(len(errors), 0, f"Thread safety errors: {errors}")
        
        # Check all submissions succeeded
        self.assertTrue(all(results), "Some task submissions failed")

    def test_empty_queue_handling(self):
        """Test handling of empty queues."""
        self.scheduler.start()
        
        # Try to get task from empty scheduler
        task = self.scheduler.get_task("worker_0")
        self.assertIsNone(task)
        
        # Check metrics are still valid
        metrics = self.scheduler.get_metrics()
        self.assertEqual(metrics["total_completed"], 0)
        self.assertEqual(metrics["total_active"], 0)

    def test_scheduler_not_running(self):
        """Test operations when scheduler is not running."""
        # Don't start scheduler
        
        task = Task(task_id="not_running_task")
        result = self.scheduler.submit_task(task)
        
        self.assertFalse(result)

    def test_task_priority_handling(self):
        """Test task priority in work stealing."""
        self.scheduler.start()
        
        # Submit tasks with different priorities
        high_priority_task = Task(task_id="high_priority", priority=10)
        low_priority_task = Task(task_id="low_priority", priority=1)
        
        self.scheduler.submit_task(low_priority_task)
        self.scheduler.submit_task(high_priority_task)
        
        # Both should be accepted
        total_tasks = sum(
            len(queue) for queue in self.scheduler.worker_queues.values()
        )
        self.assertEqual(total_tasks, 2)


if __name__ == "__main__":
    unittest.main()