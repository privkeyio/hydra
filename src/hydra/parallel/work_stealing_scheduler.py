"""Work Stealing Scheduler for Hydra.

Dynamic load balancing through work stealing for optimal resource usage.
Redistributes tasks from busy to idle workers automatically.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple

logger = logging.getLogger(__name__)


class StealingPolicy(Enum):
    """Policies for work stealing behavior."""

    AGGRESSIVE = "aggressive"  # Steal as much as possible
    CONSERVATIVE = "conservative"  # Only steal when significant imbalance
    BALANCED = "balanced"  # Default balanced approach


@dataclass
class WorkerMetrics:
    """Metrics for a worker's efficiency and load."""

    worker_id: str
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_execution_time: float = 0.0
    last_activity: float = field(default_factory=time.time)
    tasks_stolen_from: int = 0
    tasks_stolen_to: int = 0
    average_task_time: float = 0.0
    efficiency_score: float = 1.0


@dataclass
class Task:
    """Task representation for work stealing."""

    task_id: str
    priority: int = 0
    estimated_duration: float = 0.0
    dependencies: List[str] = field(default_factory=list)
    callback: Optional[Callable] = None
    created_at: float = field(default_factory=time.time)
    assigned_at: Optional[float] = None
    completed_at: Optional[float] = None


class TaskExecutor(Protocol):
    """Protocol for task execution."""

    def execute_task(self, task: Task) -> bool:
        """Execute a task and return success status."""
        ...


class WorkStealingScheduler:
    """Dynamic work stealing scheduler for load balancing."""

    def __init__(
        self,
        num_workers: int = 3,
        stealing_policy: StealingPolicy = StealingPolicy.BALANCED,
        rebalance_interval: float = 10.0,
        efficiency_threshold: float = 0.7
    ):
        self.num_workers = num_workers
        self.stealing_policy = stealing_policy
        self.rebalance_interval = rebalance_interval
        self.efficiency_threshold = efficiency_threshold

        # Worker management
        self.worker_queues: Dict[str, deque[Task]] = {}
        self.worker_locks: Dict[str, threading.Lock] = {}
        self.worker_metrics: Dict[str, WorkerMetrics] = {}

        # Global state
        self.running = False
        self.rebalance_thread: Optional[threading.Thread] = None
        self.global_lock = threading.RLock()
        self.completed_tasks: Set[str] = set()
        self.failed_tasks: Set[str] = set()

        # Configuration
        self.steal_threshold_ratio = self._get_steal_threshold()
        self.max_steal_count = max(1, num_workers // 2)

        self._initialize_workers()

    def _get_steal_threshold(self) -> float:
        """Get stealing threshold based on policy."""
        thresholds = {
            StealingPolicy.AGGRESSIVE: 1.5,
            StealingPolicy.CONSERVATIVE: 3.0,
            StealingPolicy.BALANCED: 2.0
        }
        return thresholds[self.stealing_policy]

    def _initialize_workers(self):
        """Initialize worker queues and metrics."""
        for i in range(self.num_workers):
            worker_id = f"worker_{i}"
            self.worker_queues[worker_id] = deque()
            self.worker_locks[worker_id] = threading.Lock()
            self.worker_metrics[worker_id] = WorkerMetrics(worker_id=worker_id)

        logger.info(f"Initialized {self.num_workers} workers for work stealing")

    def start(self):
        """Start the scheduler and rebalancing thread."""
        if self.running:
            return

        self.running = True
        try:
            self.rebalance_thread = threading.Thread(
                target=self._rebalance_loop,
                daemon=True,
                name="WorkStealingRebalancer"
            )
            self.rebalance_thread.start()
            logger.info("Work stealing scheduler started")
        except RuntimeError as e:
            # Handle thread creation failures gracefully (e.g., in test environments)
            logger.warning(f"Failed to start rebalance thread: {e}")
            self.rebalance_thread = None
            self.running = False  # Set running to False if thread creation fails

    def stop(self):
        """Stop the scheduler and cleanup resources."""
        self.running = False
        if self.rebalance_thread and self.rebalance_thread.is_alive():
            self.rebalance_thread.join(timeout=5.0)
        logger.info("Work stealing scheduler stopped")

    def submit_task(self, task: Task) -> bool:
        """Submit a task to the least loaded worker."""
        if not self.running:
            logger.error("Scheduler not running")
            return False

        target_worker = self._find_least_loaded_worker()
        if not target_worker:
            logger.error("No available workers")
            return False

        with self.worker_locks[target_worker]:
            self.worker_queues[target_worker].append(task)

        logger.debug(f"Task {task.task_id} assigned to {target_worker}")
        return True

    def get_task(self, worker_id: str) -> Optional[Task]:
        """Get next task for a worker, possibly stealing from others."""
        # First try own queue
        with self.worker_locks[worker_id]:
            if self.worker_queues[worker_id]:
                task = self.worker_queues[worker_id].popleft()
                task.assigned_at = time.time()
                self.worker_metrics[worker_id].active_tasks += 1
                self.worker_metrics[worker_id].last_activity = time.time()
                return task

        # Try to steal from other workers
        stolen_task = self._attempt_steal(worker_id)
        if stolen_task:
            stolen_task.assigned_at = time.time()
            self.worker_metrics[worker_id].active_tasks += 1
            self.worker_metrics[worker_id].last_activity = time.time()
            self.worker_metrics[worker_id].tasks_stolen_to += 1

        return stolen_task

    def complete_task(self, worker_id: str, task: Task, success: bool):
        """Mark a task as completed and update metrics."""
        current_time = time.time()
        task.completed_at = current_time

        with self.global_lock:
            metrics = self.worker_metrics[worker_id]
            metrics.active_tasks = max(0, metrics.active_tasks - 1)
            metrics.last_activity = current_time

            if success:
                metrics.completed_tasks += 1
                self.completed_tasks.add(task.task_id)
            else:
                metrics.failed_tasks += 1
                self.failed_tasks.add(task.task_id)

            # Update execution time and efficiency
            if task.assigned_at:
                execution_time = current_time - task.assigned_at
                metrics.total_execution_time += execution_time

                total_tasks = metrics.completed_tasks + metrics.failed_tasks
                if total_tasks > 0:
                    avg_time = metrics.total_execution_time / total_tasks
                    metrics.average_task_time = avg_time
                    # Simple efficiency based on success rate and speed
                    success_rate = metrics.completed_tasks / total_tasks
                    # Assume 60s is baseline for speed factor
                    speed_factor = min(1.0, 60.0 / max(avg_time, 1.0))
                    metrics.efficiency_score = success_rate * speed_factor

    def _find_least_loaded_worker(self) -> Optional[str]:
        """Find the worker with the least load."""
        min_load = float('inf')
        target_worker = None

        for worker_id, metrics in self.worker_metrics.items():
            # Load based on active tasks + queue size
            with self.worker_locks[worker_id]:
                queue_size = len(self.worker_queues[worker_id])
            load = metrics.active_tasks + queue_size

            if load < min_load:
                min_load = load
                target_worker = worker_id

        return target_worker

    def _attempt_steal(self, stealing_worker_id: str) -> Optional[Task]:
        """Attempt to steal work from other workers."""
        candidate_victims = self._find_steal_candidates(stealing_worker_id)

        for victim_worker_id in candidate_victims:
            with self.worker_locks[victim_worker_id]:
                queue = self.worker_queues[victim_worker_id]
                if len(queue) > 1:  # Only steal if victim has more than 1 task
                    # Steal from the end (LIFO for better cache locality)
                    stolen_task = queue.pop()
                    self.worker_metrics[victim_worker_id].tasks_stolen_from += 1
                    logger.debug(
                        f"Worker {stealing_worker_id} stole task {stolen_task.task_id} "
                        f"from {victim_worker_id}"
                    )
                    return stolen_task

        return None

    def _find_steal_candidates(self, stealing_worker_id: str) -> List[str]:
        """Find workers that are candidates for stealing from."""
        candidates = []
        stealing_metrics = self.worker_metrics[stealing_worker_id]

        for worker_id, metrics in self.worker_metrics.items():
            if worker_id == stealing_worker_id:
                continue

            with self.worker_locks[worker_id]:
                queue_size = len(self.worker_queues[worker_id])

            total_load = metrics.active_tasks + queue_size
            stealing_queue = self.worker_queues[stealing_worker_id]
            stealing_load = stealing_metrics.active_tasks + len(stealing_queue)

            # Check if imbalance meets threshold
            if total_load > stealing_load * self.steal_threshold_ratio:
                # Weight by efficiency and load
                weight = total_load * (2.0 - metrics.efficiency_score)
                candidates.append((worker_id, weight))

        # Sort by weight (higher weight = better candidate)
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [worker_id for worker_id, _ in candidates[:self.max_steal_count]]

    def _rebalance_loop(self):
        """Run periodic rebalancing of work."""
        logger.info(f"Starting rebalance loop (interval: {self.rebalance_interval}s)")

        while self.running:
            try:
                time.sleep(self.rebalance_interval)
                if self.running:  # Check again after sleep
                    self._perform_rebalancing()
            except Exception as e:
                logger.error(f"Error in rebalance loop: {e}")

    def _perform_rebalancing(self):
        """Perform active rebalancing of work."""
        with self.global_lock:
            imbalances = self._detect_imbalances()

            if not imbalances:
                logger.debug("No significant imbalances detected")
                return

            logger.info(f"Detected {len(imbalances)} load imbalances, rebalancing...")

            rebalanced_count = 0
            for overloaded_worker, underloaded_workers in imbalances:
                moved = self._move_tasks(overloaded_worker, underloaded_workers)
                rebalanced_count += moved

            if rebalanced_count > 0:
                logger.info(f"Rebalanced {rebalanced_count} tasks")
                self._log_worker_status()

    def _detect_imbalances(self) -> List[Tuple[str, List[str]]]:
        """Detect load imbalances between workers."""
        loads = {}

        # Calculate current load for each worker
        for worker_id, metrics in self.worker_metrics.items():
            with self.worker_locks[worker_id]:
                queue_size = len(self.worker_queues[worker_id])
            loads[worker_id] = metrics.active_tasks + queue_size

        if not loads:
            return []

        avg_load = sum(loads.values()) / len(loads)
        imbalance_threshold = avg_load * 0.5  # 50% deviation from average

        overloaded = [
            worker_id for worker_id, load in loads.items()
            if load > avg_load + imbalance_threshold
        ]

        underloaded = [
            worker_id for worker_id, load in loads.items()
            if load < avg_load - imbalance_threshold
        ]

        imbalances = []
        for overloaded_worker in overloaded:
            available_targets = [
                w for w in underloaded
                if loads[w] < loads[overloaded_worker] * 0.8
            ]
            if available_targets:
                imbalances.append((overloaded_worker, available_targets))

        return imbalances

    def _move_tasks(self, from_worker: str, to_workers: List[str]) -> int:
        """Move tasks from overloaded to underloaded workers."""
        if not to_workers:
            return 0

        moved_count = 0

        with self.worker_locks[from_worker]:
            from_queue = self.worker_queues[from_worker]
            # Move up to half of the excess tasks
            max_moves = max(1, len(from_queue) // 2)

            tasks_to_move = []
            while moved_count < max_moves and len(from_queue) > 1:
                tasks_to_move.append(from_queue.pop())  # Take from end
                moved_count += 1

        # Distribute tasks among target workers
        for i, task_to_move in enumerate(tasks_to_move):
            target_worker = to_workers[i % len(to_workers)]

            with self.worker_locks[target_worker]:
                self.worker_queues[target_worker].append(task_to_move)

            logger.debug(
                f"Moved task {task_to_move.task_id} from {from_worker} "
                f"to {target_worker}"
            )

        return moved_count

    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive scheduler metrics."""
        with self.global_lock:
            total_completed = sum(m.completed_tasks for m in self.worker_metrics.values())
            total_failed = sum(m.failed_tasks for m in self.worker_metrics.values())
            total_active = sum(m.active_tasks for m in self.worker_metrics.values())

            queue_sizes = {}
            for worker_id in self.worker_queues:
                with self.worker_locks[worker_id]:
                    queue_sizes[worker_id] = len(self.worker_queues[worker_id])

            return {
                "total_workers": self.num_workers,
                "stealing_policy": self.stealing_policy.value,
                "rebalance_interval": self.rebalance_interval,
                "total_completed": total_completed,
                "total_failed": total_failed,
                "total_active": total_active,
                "success_rate": (
                    total_completed / max(total_completed + total_failed, 1) * 100
                ),
                "worker_metrics": {
                    worker_id: {
                        "active_tasks": metrics.active_tasks,
                        "completed_tasks": metrics.completed_tasks,
                        "failed_tasks": metrics.failed_tasks,
                        "queue_size": queue_sizes[worker_id],
                        "efficiency_score": metrics.efficiency_score,
                        "average_task_time": metrics.average_task_time,
                        "tasks_stolen_from": metrics.tasks_stolen_from,
                        "tasks_stolen_to": metrics.tasks_stolen_to
                    }
                    for worker_id, metrics in self.worker_metrics.items()
                }
            }

    def _log_worker_status(self):
        """Log current worker status for debugging."""
        for worker_id, metrics in self.worker_metrics.items():
            with self.worker_locks[worker_id]:
                queue_size = len(self.worker_queues[worker_id])

            logger.debug(
                f"Worker {worker_id}: active={metrics.active_tasks}, "
                f"queue={queue_size}, completed={metrics.completed_tasks}, "
                f"efficiency={metrics.efficiency_score:.2f}"
            )

    def get_worker_efficiency(self, worker_id: str) -> float:
        """Get efficiency score for a specific worker."""
        if worker_id in self.worker_metrics:
            return self.worker_metrics[worker_id].efficiency_score
        return 0.0

    def configure_stealing_policy(
        self,
        policy: StealingPolicy,
        custom_threshold: Optional[float] = None
    ):
        """Configure work stealing policy at runtime."""
        self.stealing_policy = policy
        if custom_threshold:
            self.steal_threshold_ratio = custom_threshold
        else:
            self.steal_threshold_ratio = self._get_steal_threshold()

        logger.info(
            f"Updated stealing policy to {policy.value} "
            f"(threshold: {self.steal_threshold_ratio})"
        )

    def get_load_distribution(self) -> Dict[str, float]:
        """Get current load distribution across workers."""
        distribution = {}
        total_load = 0

        for worker_id, metrics in self.worker_metrics.items():
            with self.worker_locks[worker_id]:
                queue_size = len(self.worker_queues[worker_id])
            load = metrics.active_tasks + queue_size
            distribution[worker_id] = load
            total_load += load

        # Normalize to percentages
        if total_load > 0:
            distribution = {
                worker_id: (load / total_load) * 100
                for worker_id, load in distribution.items()
            }

        return distribution

    def force_rebalance(self):
        """Force immediate rebalancing."""
        logger.info("Forcing immediate rebalance")
        self._perform_rebalancing()
