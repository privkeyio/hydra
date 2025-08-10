"""Hydra Parallel Execution Module."""

from .async_executor import AsyncParallelExecutor
from .batch_executor import BatchConfig, BatchExecutor, BatchGroup
from .executor import ExecutionPlan, ExecutionStatus, ParallelExecutor, TicketNode
from .work_stealing_async_executor import WorkStealingAsyncExecutor
from .work_stealing_scheduler import (
    StealingPolicy,
    Task,
    WorkerMetrics,
    WorkStealingScheduler,
)

# Backwards compatibility alias
SyncParallelExecutor = ParallelExecutor

__all__ = [
    'ParallelExecutor',
    'AsyncParallelExecutor',
    'BatchExecutor',
    'WorkStealingAsyncExecutor',
    'SyncParallelExecutor',
    'ExecutionPlan',
    'TicketNode',
    'ExecutionStatus',
    'BatchConfig',
    'BatchGroup',
    'WorkStealingScheduler',
    'StealingPolicy',
    'Task',
    'WorkerMetrics',
]
