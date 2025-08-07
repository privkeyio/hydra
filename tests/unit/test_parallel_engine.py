import threading
import time
import unittest
from unittest.mock import Mock, patch

from hydra.workflows.parallel_engine import (
    ParallelExecutionEngine, Task, TaskStatus, ResourcePool,
    ThreadSafeTaskQueue, DeadlockDetector, AgentResource,
    ResourceState, ExecutionMetrics
)


class TestThreadSafeTaskQueue(unittest.TestCase):
    
    def setUp(self):
        self.queue = ThreadSafeTaskQueue()
    
    def test_put_and_get(self):
        task = Task(id="1", name="test", func=lambda: None)
        self.queue.put(task)
        
        self.assertEqual(self.queue.size(), 1)
        retrieved = self.queue.get(set())
        self.assertEqual(retrieved.id, "1")
        self.assertEqual(self.queue.size(), 0)
    
    def test_dependency_filtering(self):
        task1 = Task(id="1", name="task1", func=lambda: None, dependencies={"0"})
        task2 = Task(id="2", name="task2", func=lambda: None, dependencies=set())
        
        self.queue.put(task1)
        self.queue.put(task2)
        
        result = self.queue.get(set())
        self.assertEqual(result.id, "2")
        
        result = self.queue.get({"0"})
        self.assertEqual(result.id, "1")
    
    def test_blocking_get_timeout(self):
        start = time.time()
        result = self.queue.get_blocking(set(), timeout=0.1)
        elapsed = time.time() - start
        
        self.assertIsNone(result)
        self.assertAlmostEqual(elapsed, 0.1, delta=0.05)
    
    def test_remove(self):
        task = Task(id="1", name="test", func=lambda: None)
        self.queue.put(task)
        
        removed = self.queue.remove("1")
        self.assertTrue(removed)
        self.assertEqual(self.queue.size(), 0)
        
        removed = self.queue.remove("nonexistent")
        self.assertFalse(removed)
    
    def test_concurrent_access(self):
        def producer():
            for i in range(10):
                task = Task(id=str(i), name=f"task{i}", func=lambda: None)
                self.queue.put(task)
                time.sleep(0.001)
        
        def consumer():
            results = []
            for _ in range(10):
                task = self.queue.get_blocking(set(), timeout=1)
                if task:
                    results.append(task.id)
            return results
        
        producer_thread = threading.Thread(target=producer)
        consumer_thread = threading.Thread(target=consumer)
        
        producer_thread.start()
        consumer_thread.start()
        
        producer_thread.join()
        consumer_thread.join()
        
        self.assertEqual(self.queue.size(), 0)


class TestResourcePool(unittest.TestCase):
    
    def setUp(self):
        self.pool = ResourcePool(max_agents=3)
    
    def test_acquire_and_release(self):
        agent = self.pool.acquire()
        self.assertIsNotNone(agent)
        self.assertEqual(agent.state, ResourceState.BUSY)
        
        stats = self.pool.get_stats()
        self.assertEqual(stats["busy"], 1)
        self.assertEqual(stats["available"], 0)
        
        self.pool.release(agent)
        self.assertEqual(agent.state, ResourceState.AVAILABLE)
        
        stats = self.pool.get_stats()
        self.assertEqual(stats["busy"], 0)
        self.assertEqual(stats["available"], 1)
    
    def test_max_agents_limit(self):
        agents = []
        for _ in range(3):
            agent = self.pool.acquire()
            self.assertIsNotNone(agent)
            agents.append(agent)
        
        agent = self.pool.acquire(timeout=0.1)
        self.assertIsNone(agent)
        
        self.pool.release(agents[0])
        agent = self.pool.acquire(timeout=0.1)
        self.assertIsNotNone(agent)
    
    def test_terminate_idle(self):
        agent = self.pool.acquire()
        agent.last_used = time.time() - 400
        self.pool.release(agent)
        
        self.pool.terminate_idle(idle_timeout=300)
        
        stats = self.pool.get_stats()
        self.assertEqual(stats["available"], 0)
        self.assertEqual(stats["total_agents"], 0)
    
    def test_concurrent_acquire_release(self):
        def worker():
            for _ in range(5):
                agent = self.pool.acquire(timeout=1)
                if agent:
                    time.sleep(0.01)
                    self.pool.release(agent)
        
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        stats = self.pool.get_stats()
        self.assertEqual(stats["busy"], 0)


class TestDeadlockDetector(unittest.TestCase):
    
    def setUp(self):
        self.detector = DeadlockDetector()
    
    def test_no_cycle(self):
        self.detector.add_task("A", {"B"})
        self.detector.add_task("B", {"C"})
        self.detector.add_task("C", set())
        
        cycle = self.detector.detect_cycle()
        self.assertIsNone(cycle)
    
    def test_detect_cycle(self):
        self.detector.add_task("A", {"B"})
        self.detector.add_task("B", {"C"})
        self.detector.add_task("C", {"A"})
        
        cycle = self.detector.detect_cycle()
        self.assertIsNotNone(cycle)
        self.assertIn("A", cycle)
        self.assertIn("B", cycle)
        self.assertIn("C", cycle)
    
    def test_remove_task(self):
        self.detector.add_task("A", {"B"})
        self.detector.add_task("B", {"C"})
        self.detector.add_task("C", {"A"})
        
        self.detector.remove_task("C")
        
        cycle = self.detector.detect_cycle()
        self.assertIsNone(cycle)
    
    def test_find_resolvable(self):
        self.detector.add_task("A", set())
        self.detector.add_task("B", {"A"})
        self.detector.add_task("C", {"A", "B"})
        
        resolvable = self.detector.find_resolvable_tasks(set())
        self.assertEqual(resolvable, {"A"})
        
        resolvable = self.detector.find_resolvable_tasks({"A"})
        self.assertEqual(resolvable, {"A", "B"})
        
        resolvable = self.detector.find_resolvable_tasks({"A", "B"})
        self.assertEqual(resolvable, {"A", "B", "C"})


class TestParallelExecutionEngine(unittest.TestCase):
    
    def setUp(self):
        self.engine = ParallelExecutionEngine(
            max_workers=4,
            max_agents=4,
            deadlock_check_interval=0.1
        )
    
    def tearDown(self):
        self.engine.shutdown(wait=False)
    
    def test_simple_task_execution(self):
        result = {"value": None}
        
        def simple_task(val):
            result["value"] = val
            return val * 2
        
        task_id = self.engine.submit_task(
            name="simple",
            func=simple_task,
            args=(5,)
        )
        
        success = self.engine.wait_for_completion(timeout=2)
        self.assertTrue(success)
        
        self.assertEqual(result["value"], 5)
        
        metrics = self.engine.get_metrics()
        self.assertEqual(metrics.tasks_submitted, 1)
        self.assertEqual(metrics.tasks_completed, 1)
        self.assertEqual(metrics.tasks_failed, 0)
    
    def test_task_dependencies(self):
        results = []
        
        def task_func(name):
            results.append(name)
            return name
        
        task_a = self.engine.submit_task(
            name="A",
            func=task_func,
            args=("A",)
        )
        
        task_b = self.engine.submit_task(
            name="B",
            func=task_func,
            args=("B",),
            dependencies={task_a}
        )
        
        task_c = self.engine.submit_task(
            name="C",
            func=task_func,
            args=("C",),
            dependencies={task_a, task_b}
        )
        
        success = self.engine.wait_for_completion(timeout=3)
        self.assertTrue(success)
        
        self.assertEqual(results[0], "A")
        self.assertEqual(results[1], "B")
        self.assertEqual(results[2], "C")
    
    def test_parallel_execution(self):
        start_time = time.time()
        
        def slow_task():
            time.sleep(0.1)
            return True
        
        task_ids = []
        for i in range(4):
            task_id = self.engine.submit_task(
                name=f"task_{i}",
                func=slow_task
            )
            task_ids.append(task_id)
        
        success = self.engine.wait_for_completion(timeout=2)
        self.assertTrue(success)
        
        elapsed = time.time() - start_time
        self.assertLess(elapsed, 0.5)
        
        metrics = self.engine.get_metrics()
        self.assertEqual(metrics.tasks_completed, 4)
        self.assertGreater(metrics.peak_concurrency, 1)
    
    def test_task_timeout(self):
        def long_task():
            time.sleep(2)
            return "completed"
        
        task_id = self.engine.submit_task(
            name="timeout_task",
            func=long_task,
            timeout=0.1
        )
        
        success = self.engine.wait_for_completion(timeout=3)
        self.assertTrue(success)
        
        metrics = self.engine.get_metrics()
        self.assertEqual(metrics.tasks_failed, 1)
    
    def test_task_retry(self):
        attempt_count = {"count": 0}
        
        def failing_task():
            attempt_count["count"] += 1
            if attempt_count["count"] < 3:
                raise Exception("Simulated failure")
            return "success"
        
        task_id = self.engine.submit_task(
            name="retry_task",
            func=failing_task
        )
        
        success = self.engine.wait_for_completion(timeout=3)
        self.assertTrue(success)
        
        self.assertEqual(attempt_count["count"], 3)
        
        metrics = self.engine.get_metrics()
        self.assertEqual(metrics.tasks_completed, 1)
        self.assertEqual(metrics.tasks_retried, 2)
    
    def test_cancel_task(self):
        def slow_task():
            time.sleep(1)
            return "completed"
        
        task_id = self.engine.submit_task(
            name="cancel_task",
            func=slow_task
        )
        
        cancelled = self.engine.cancel_task(task_id)
        self.assertTrue(cancelled)
        
        success = self.engine.wait_for_completion(timeout=0.5)
        self.assertTrue(success)
        
        metrics = self.engine.get_metrics()
        self.assertEqual(metrics.tasks_cancelled, 1)
    
    def test_deadlock_detection(self):
        task_a = self.engine.submit_task(
            name="A",
            func=lambda: None,
            dependencies={"B"}
        )
        
        task_b = self.engine.submit_task(
            name="B",
            func=lambda: None,
            dependencies={"C"}
        )
        
        task_c = self.engine.submit_task(
            name="C",
            func=lambda: None,
            dependencies={"A"}
        )
        
        time.sleep(0.3)
        
        metrics = self.engine.get_metrics()
        self.assertGreater(metrics.deadlocks_detected, 0)
        self.assertGreater(metrics.deadlocks_resolved, 0)
    
    def test_get_task_status(self):
        def task():
            time.sleep(0.1)
            return "done"
        
        task_id = self.engine.submit_task(
            name="status_task",
            func=task
        )
        
        time.sleep(0.05)
        status = self.engine.get_task_status(task_id)
        self.assertIn(status, [TaskStatus.PENDING, TaskStatus.RUNNING])
        
        self.engine.wait_for_completion(timeout=2)
        status = self.engine.get_task_status(task_id)
        self.assertEqual(status, TaskStatus.COMPLETED)
    
    def test_resource_scaling(self):
        initial_stats = self.engine.resource_pool.get_stats()
        
        def task():
            time.sleep(0.05)
            return True
        
        for i in range(10):
            self.engine.submit_task(
                name=f"scale_task_{i}",
                func=task
            )
        
        time.sleep(0.1)
        
        mid_stats = self.engine.resource_pool.get_stats()
        self.assertGreaterEqual(mid_stats["total_agents"], initial_stats["total_agents"])
        
        self.engine.wait_for_completion(timeout=3)
        
        time.sleep(0.2)
        
        metrics = self.engine.get_metrics()
        self.assertGreaterEqual(metrics.agents_created, 0)


if __name__ == '__main__':
    unittest.main()