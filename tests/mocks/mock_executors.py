"""Mock executors for testing parallel execution and workflows."""

import time
import threading
from typing import Any, Dict, List, Optional, Callable
from concurrent.futures import Future
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass
class MockTaskResult:
    """Result of a mock task execution."""
    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    

class MockExecutor:
    """Mock executor for testing task execution."""
    
    def __init__(self, max_workers: int = 4, error_rate: float = 0.0):
        self.max_workers = max_workers
        self.error_rate = error_rate
        self.task_counter = 0
        self.submitted_tasks = []
        self.completed_tasks = []
        self.failed_tasks = []
        self.running_tasks = {}
        self._lock = threading.Lock()
        
    def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> str:
        """Submit a task for execution."""
        with self._lock:
            self.task_counter += 1
            full_task_id = f"{task_id}-{self.task_counter}"
            
            task_info = {
                "task_id": full_task_id,
                "func": func,
                "args": args,
                "kwargs": kwargs,
                "submitted_at": time.time()
            }
            
            self.submitted_tasks.append(task_info)
            self.running_tasks[full_task_id] = task_info
            
            # Simulate async execution
            threading.Thread(
                target=self._execute_task,
                args=(task_info,),
                daemon=True
            ).start()
            
            return full_task_id
    
    def _execute_task(self, task_info: Dict[str, Any]):
        """Execute a task (simulated)."""
        task_id = task_info["task_id"]
        func = task_info["func"]
        args = task_info["args"]
        kwargs = task_info["kwargs"]
        
        start_time = time.time()
        
        try:
            # Simulate some execution time
            time.sleep(0.1 + (hash(task_id) % 100) / 1000)
            
            # Simulate random failures
            import random
            if random.random() < self.error_rate:
                raise Exception(f"Mock execution failure for task {task_id}")
            
            # Execute the function
            if callable(func):
                result = func(*args, **kwargs)
            else:
                result = f"Mock result for {task_id}"
            
            execution_time = time.time() - start_time
            
            task_result = MockTaskResult(
                task_id=task_id,
                success=True,
                result=result,
                execution_time=execution_time
            )
            
            with self._lock:
                self.completed_tasks.append(task_result)
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
                    
        except Exception as e:
            execution_time = time.time() - start_time
            
            task_result = MockTaskResult(
                task_id=task_id,
                success=False,
                error=str(e),
                execution_time=execution_time
            )
            
            with self._lock:
                self.failed_tasks.append(task_result)
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
    
    def get_task_status(self, task_id: str) -> Optional[str]:
        """Get the status of a task."""
        with self._lock:
            if task_id in self.running_tasks:
                return "running"
            
            for task in self.completed_tasks:
                if task.task_id == task_id:
                    return "completed"
            
            for task in self.failed_tasks:
                if task.task_id == task_id:
                    return "failed"
            
            return None
    
    def get_task_result(self, task_id: str) -> Optional[MockTaskResult]:
        """Get the result of a completed task."""
        with self._lock:
            for task in self.completed_tasks:
                if task.task_id == task_id:
                    return task
            
            for task in self.failed_tasks:
                if task.task_id == task_id:
                    return task
            
            return None
    
    def wait_for_completion(self, timeout: float = 10.0) -> bool:
        """Wait for all tasks to complete."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._lock:
                if not self.running_tasks:
                    return True
            time.sleep(0.1)
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get executor statistics."""
        with self._lock:
            return {
                "submitted": len(self.submitted_tasks),
                "running": len(self.running_tasks),
                "completed": len(self.completed_tasks),
                "failed": len(self.failed_tasks),
                "success_rate": len(self.completed_tasks) / max(1, self.task_counter)
            }


class MockParallelEngine:
    """Mock parallel execution engine for testing complex workflows."""
    
    def __init__(self, max_workers: int = 4, max_parallel: int = 2):
        self.max_workers = max_workers
        self.max_parallel = max_parallel
        self.executors = [MockExecutor(max_workers) for _ in range(max_parallel)]
        self.current_executor = 0
        self.workflow_results = {}
        self._lock = threading.Lock()
        
    def execute_workflow(self, workflow_id: str, tasks: List[Dict[str, Any]]) -> str:
        """Execute a workflow with multiple tasks."""
        with self._lock:
            workflow_info = {
                "workflow_id": workflow_id,
                "tasks": tasks,
                "submitted_at": time.time(),
                "task_ids": []
            }
            
            # Submit tasks to different executors
            for i, task in enumerate(tasks):
                executor_idx = i % len(self.executors)
                executor = self.executors[executor_idx]
                
                task_id = executor.submit_task(
                    f"{workflow_id}-task-{i}",
                    task.get("func", lambda: "mock_result"),
                    *task.get("args", []),
                    **task.get("kwargs", {})
                )
                
                workflow_info["task_ids"].append(task_id)
            
            self.workflow_results[workflow_id] = workflow_info
            return workflow_id
    
    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get the status of a workflow."""
        if workflow_id not in self.workflow_results:
            return {"error": "Workflow not found"}
        
        workflow = self.workflow_results[workflow_id]
        task_statuses = {}
        
        for executor in self.executors:
            for task_id in workflow["task_ids"]:
                status = executor.get_task_status(task_id)
                if status:
                    task_statuses[task_id] = status
        
        completed = sum(1 for s in task_statuses.values() if s == "completed")
        failed = sum(1 for s in task_statuses.values() if s == "failed")
        running = sum(1 for s in task_statuses.values() if s == "running")
        
        return {
            "workflow_id": workflow_id,
            "total_tasks": len(workflow["task_ids"]),
            "completed": completed,
            "failed": failed,
            "running": running,
            "task_statuses": task_statuses
        }
    
    def wait_for_workflow(self, workflow_id: str, timeout: float = 30.0) -> bool:
        """Wait for a workflow to complete."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_workflow_status(workflow_id)
            if status.get("running", 0) == 0:
                return True
            time.sleep(0.5)
        
        return False
    
    def get_engine_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        total_stats = {
            "submitted": 0,
            "running": 0,
            "completed": 0,
            "failed": 0
        }
        
        executor_stats = []
        for i, executor in enumerate(self.executors):
            stats = executor.get_stats()
            executor_stats.append({"executor_id": i, **stats})
            
            for key in total_stats:
                if key in stats:
                    total_stats[key] += stats[key]
        
        return {
            "total": total_stats,
            "executors": executor_stats,
            "workflows": len(self.workflow_results)
        }