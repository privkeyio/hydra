import random
import threading
import time
import unittest
from concurrent.futures import as_completed

from hydra.workflows.parallel_engine import ParallelExecutionEngine


class TestParallelEngineStress(unittest.TestCase):
    
    def test_high_concurrency(self):
        engine = ParallelExecutionEngine(
            max_workers=20,
            max_agents=20
        )
        
        results = {}
        lock = threading.Lock()
        
        def worker_task(task_id, delay):
            time.sleep(delay)
            with lock:
                results[task_id] = threading.current_thread().ident
            return task_id
        
        task_ids = []
        for i in range(100):
            delay = random.uniform(0.001, 0.01)
            task_id = engine.submit_task(
                name=f"stress_task_{i}",
                func=worker_task,
                args=(i, delay)
            )
            task_ids.append(task_id)
        
        success = engine.wait_for_completion(timeout=10)
        self.assertTrue(success)
        
        self.assertEqual(len(results), 100)
        
        unique_threads = len(set(results.values()))
        self.assertGreater(unique_threads, 1)
        
        metrics = engine.get_metrics()
        self.assertEqual(metrics.tasks_completed, 100)
        self.assertEqual(metrics.tasks_failed, 0)
        self.assertGreater(metrics.peak_concurrency, 10)
        
        engine.shutdown()
    
    def test_complex_dependency_graph(self):
        engine = ParallelExecutionEngine(
            max_workers=10,
            max_agents=10
        )
        
        execution_order = []
        lock = threading.Lock()
        
        def task_func(name):
            with lock:
                execution_order.append(name)
            return name
        
        task_map = {}
        
        for layer in range(5):
            for node in range(4):
                task_name = f"L{layer}_N{node}"
                dependencies = set()
                
                if layer > 0:
                    for prev_node in range(4):
                        prev_name = f"L{layer-1}_N{prev_node}"
                        dependencies.add(task_map[prev_name])
                
                task_id = engine.submit_task(
                    name=task_name,
                    func=task_func,
                    args=(task_name,),
                    dependencies=dependencies
                )
                task_map[task_name] = task_id
        
        success = engine.wait_for_completion(timeout=10)
        self.assertTrue(success)
        
        self.assertEqual(len(execution_order), 20)
        
        for i, task_name in enumerate(execution_order):
            layer = int(task_name[1])
            for j in range(i):
                prev_layer = int(execution_order[j][1])
                self.assertLessEqual(prev_layer, layer)
        
        metrics = engine.get_metrics()
        self.assertEqual(metrics.tasks_completed, 20)
        
        engine.shutdown()
    
    def test_mixed_workload(self):
        engine = ParallelExecutionEngine(
            max_workers=15,
            max_agents=15
        )
        
        success_count = {"count": 0}
        failure_count = {"count": 0}
        timeout_count = {"count": 0}
        lock = threading.Lock()
        
        def cpu_intensive_task(n):
            result = sum(i ** 2 for i in range(n))
            with lock:
                success_count["count"] += 1
            return result
        
        def io_task(delay):
            time.sleep(delay)
            with lock:
                success_count["count"] += 1
            return "io_complete"
        
        def failing_task():
            with lock:
                failure_count["count"] += 1
            raise Exception("Expected failure")
        
        def timeout_task():
            time.sleep(5)
            with lock:
                timeout_count["count"] += 1
            return "should_timeout"
        
        task_ids = []
        
        for i in range(20):
            task_id = engine.submit_task(
                name=f"cpu_{i}",
                func=cpu_intensive_task,
                args=(1000,)
            )
            task_ids.append(task_id)
        
        for i in range(20):
            task_id = engine.submit_task(
                name=f"io_{i}",
                func=io_task,
                args=(random.uniform(0.01, 0.05),)
            )
            task_ids.append(task_id)
        
        for i in range(5):
            task_id = engine.submit_task(
                name=f"fail_{i}",
                func=failing_task
            )
            task_ids.append(task_id)
        
        for i in range(5):
            task_id = engine.submit_task(
                name=f"timeout_{i}",
                func=timeout_task,
                timeout=0.1
            )
            task_ids.append(task_id)
        
        success = engine.wait_for_completion(timeout=15)
        self.assertTrue(success)
        
        self.assertEqual(success_count["count"], 40)
        self.assertGreater(failure_count["count"], 0)
        
        metrics = engine.get_metrics()
        self.assertEqual(metrics.tasks_completed, 40)
        self.assertEqual(metrics.tasks_failed, 10)
        self.assertGreater(metrics.tasks_retried, 0)
        
        engine.shutdown()
    
    def test_rapid_submission_and_cancellation(self):
        engine = ParallelExecutionEngine(
            max_workers=10,
            max_agents=10
        )
        
        def task_func():
            time.sleep(0.1)
            return "completed"
        
        submitted_tasks = []
        cancelled_tasks = []
        
        for i in range(50):
            task_id = engine.submit_task(
                name=f"rapid_{i}",
                func=task_func
            )
            submitted_tasks.append(task_id)
            
            if random.random() < 0.3:
                if engine.cancel_task(task_id):
                    cancelled_tasks.append(task_id)
        
        success = engine.wait_for_completion(timeout=10)
        self.assertTrue(success)
        
        metrics = engine.get_metrics()
        self.assertEqual(
            metrics.tasks_completed + metrics.tasks_cancelled,
            50
        )
        self.assertEqual(metrics.tasks_cancelled, len(cancelled_tasks))
        
        engine.shutdown()
    
    def test_resource_exhaustion_recovery(self):
        engine = ParallelExecutionEngine(
            max_workers=5,
            max_agents=5
        )
        
        def memory_intensive_task():
            data = [random.random() for _ in range(100000)]
            result = sum(data)
            time.sleep(0.01)
            return result
        
        task_ids = []
        
        for batch in range(3):
            batch_ids = []
            for i in range(20):
                task_id = engine.submit_task(
                    name=f"memory_batch{batch}_task{i}",
                    func=memory_intensive_task
                )
                batch_ids.append(task_id)
            
            task_ids.extend(batch_ids)
            
            if batch < 2:
                time.sleep(0.5)
        
        success = engine.wait_for_completion(timeout=20)
        self.assertTrue(success)
        
        metrics = engine.get_metrics()
        self.assertEqual(metrics.tasks_completed, 60)
        self.assertLessEqual(metrics.peak_concurrency, 5)
        
        engine.shutdown()
    
    def test_cascading_failures(self):
        engine = ParallelExecutionEngine(
            max_workers=10,
            max_agents=10
        )
        
        def parent_task():
            return "parent_complete"
        
        def child_task(should_fail):
            if should_fail:
                raise Exception("Child task failed")
            return "child_complete"
        
        parent_id = engine.submit_task(
            name="parent",
            func=parent_task
        )
        
        child_ids = []
        for i in range(10):
            should_fail = i % 3 == 0
            child_id = engine.submit_task(
                name=f"child_{i}",
                func=child_task,
                args=(should_fail,),
                dependencies={parent_id}
            )
            child_ids.append(child_id)
        
        grandchild_ids = []
        for i, child_id in enumerate(child_ids):
            if i % 3 != 0:
                grandchild_id = engine.submit_task(
                    name=f"grandchild_{i}",
                    func=lambda: "grandchild_complete",
                    dependencies={child_id}
                )
                grandchild_ids.append(grandchild_id)
        
        success = engine.wait_for_completion(timeout=10)
        self.assertTrue(success)
        
        metrics = engine.get_metrics()
        self.assertGreater(metrics.tasks_completed, 10)
        self.assertGreater(metrics.tasks_failed, 0)
        
        engine.shutdown()
    
    def test_dynamic_priority_adjustment(self):
        engine = ParallelExecutionEngine(
            max_workers=5,
            max_agents=5
        )
        
        execution_times = {}
        lock = threading.Lock()
        
        def priority_task(task_name):
            with lock:
                execution_times[task_name] = time.time()
            time.sleep(0.01)
            return task_name
        
        task_ids = []
        
        for priority in [0, 1, 2]:
            for i in range(10):
                task_name = f"P{priority}_T{i}"
                task_id = engine.submit_task(
                    name=task_name,
                    func=priority_task,
                    args=(task_name,),
                    priority=priority
                )
                task_ids.append(task_id)
        
        success = engine.wait_for_completion(timeout=10)
        self.assertTrue(success)
        
        priority_0_times = [
            execution_times[f"P0_T{i}"] 
            for i in range(10)
        ]
        priority_2_times = [
            execution_times[f"P2_T{i}"] 
            for i in range(10)
        ]
        
        avg_p0 = sum(priority_0_times) / len(priority_0_times)
        avg_p2 = sum(priority_2_times) / len(priority_2_times)
        
        metrics = engine.get_metrics()
        self.assertEqual(metrics.tasks_completed, 30)
        
        engine.shutdown()


if __name__ == '__main__':
    unittest.main()