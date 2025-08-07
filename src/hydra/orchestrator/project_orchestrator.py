import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from hydra.agents.base import CodeAgent
from hydra.config import get_config
from hydra.exceptions import ValidationError

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskComplexity(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    CRITICAL = "critical"


class ModelType(Enum):
    SONNET = "sonnet"
    OPUS = "opus"
    AUTO = "auto"


@dataclass
class TaskNode:
    id: str
    name: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    complexity: TaskComplexity = TaskComplexity.MODERATE
    model: ModelType = ModelType.AUTO
    retry_count: int = 2
    timeout: int = 300
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    assigned_agent: Optional[str] = None

    def __hash__(self):
        return hash(self.id)

    @property
    def execution_time(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def can_execute(self, completed_tasks: Set[str]) -> bool:
        return all(dep in completed_tasks for dep in self.dependencies)


@dataclass
class ProjectSpecification:
    name: str
    description: str
    tasks: List[TaskNode]
    max_parallel: int = 4
    global_timeout: int = 3600
    model_preferences: Dict[str, str] = field(default_factory=dict)
    output_directory: Optional[str] = None

    @classmethod
    def from_yaml(cls, yaml_content: str) -> 'ProjectSpecification':
        data = yaml.safe_load(yaml_content)
        return cls.from_dict(data)

    @classmethod
    def from_json(cls, json_content: str) -> 'ProjectSpecification':
        data = json.loads(json_content)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectSpecification':
        tasks = []
        for task_data in data.get('tasks', []):
            task = TaskNode(
                id=task_data.get('id', str(uuid.uuid4())),
                name=task_data['name'],
                description=task_data['description'],
                dependencies=task_data.get('dependencies', []),
                complexity=TaskComplexity(task_data.get('complexity', 'moderate')),
                model=ModelType(task_data.get('model', 'auto')),
                retry_count=task_data.get('retry_count', 2),
                timeout=task_data.get('timeout', 300),
                parameters=task_data.get('parameters', {})
            )
            tasks.append(task)

        return cls(
            name=data['name'],
            description=data['description'],
            tasks=tasks,
            max_parallel=data.get('max_parallel', 4),
            global_timeout=data.get('global_timeout', 3600),
            model_preferences=data.get('model_preferences', {}),
            output_directory=data.get('output_directory')
        )

    def validate(self) -> Tuple[bool, List[str]]:
        errors = []
        task_ids = set()

        for task in self.tasks:
            if task.id in task_ids:
                errors.append(f"Duplicate task ID: {task.id}")
            task_ids.add(task.id)

            for dep in task.dependencies:
                if dep not in task_ids:
                    errors.append(f"Task {task.id} depends on unknown task: {dep}")

        if self._has_cycle():
            errors.append("Circular dependency detected in task graph")

        if self.max_parallel < 1 or self.max_parallel > 10:
            errors.append("max_parallel must be between 1 and 10")

        return len(errors) == 0, errors

    def _has_cycle(self) -> bool:
        visited = set()
        rec_stack = set()

        def visit(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = next((t for t in self.tasks if t.id == task_id), None)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        if visit(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(task_id)
            return False

        for task in self.tasks:
            if task.id not in visited:
                if visit(task.id):
                    return True
        return False

    def get_execution_order(self) -> List[List[TaskNode]]:
        levels = []
        completed = set()
        remaining = set(self.tasks)

        while remaining:
            current_level = []
            for task in remaining:
                if task.can_execute(completed):
                    current_level.append(task)

            if not current_level:
                break

            levels.append(current_level)
            for task in current_level:
                completed.add(task.id)
                remaining.remove(task)

        return levels


class ProjectOrchestrator:
    def __init__(self, specification: ProjectSpecification, config=None):
        self.spec = specification
        self.config = config or get_config()
        self.agents = {}
        self.completed_tasks = set()
        self.failed_tasks = set()
        self.running_tasks = set()
        self.task_queue = deque()
        self.executor = ThreadPoolExecutor(max_workers=specification.max_parallel)
        self.start_time = None
        self.end_time = None
        self.execution_log = []

    def _select_model_for_task(self, task: TaskNode) -> str:
        if task.model != ModelType.AUTO:
            model_map = {
                ModelType.SONNET: "claude-3-5-sonnet-20241022",
                ModelType.OPUS: "claude-3-opus-20240229"
            }
            return model_map.get(task.model, self.config.llm_provider.model)

        complexity_model_map = {
            TaskComplexity.SIMPLE: "claude-3-5-sonnet-20241022",
            TaskComplexity.MODERATE: "claude-3-5-sonnet-20241022",
            TaskComplexity.COMPLEX: "claude-3-opus-20240229",
            TaskComplexity.CRITICAL: "claude-3-opus-20240229"
        }

        return complexity_model_map.get(task.complexity, self.config.llm_provider.model)

    def _analyze_task_complexity(self, task: TaskNode) -> TaskComplexity:
        indicators = {
            'simple': ['create', 'list', 'fetch', 'display', 'format'],
            'moderate': ['implement', 'calculate', 'process', 'transform'],
            'complex': ['architect', 'design', 'optimize', 'refactor', 'integrate'],
            'critical': [
                'security', 'performance', 'scale', 'distribute', 'orchestrate'
            ]
        }

        description_lower = task.description.lower()

        for level, keywords in indicators.items():
            if any(keyword in description_lower for keyword in keywords):
                return TaskComplexity(level)

        if len(task.dependencies) > 3:
            return TaskComplexity.COMPLEX
        elif len(task.dependencies) > 1:
            return TaskComplexity.MODERATE

        return task.complexity

    async def _execute_task(self, task: TaskNode) -> Dict[str, Any]:
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        self.running_tasks.add(task.id)

        agent_id = f"agent_{task.id}_{uuid.uuid4().hex[:8]}"
        task.assigned_agent = agent_id

        self._log_event(f"Starting task {task.id} with agent {agent_id}")

        try:
            model = self._select_model_for_task(task)

            original_model = self.config.llm_provider.model
            self.config.llm_provider.model = model

            agent = CodeAgent(name=agent_id, depth=0, safe_mode=True)
            self.agents[agent_id] = agent

            prompt = self._build_task_prompt(task)

            result = await asyncio.wait_for(
                asyncio.to_thread(agent.complete_task, prompt),
                timeout=task.timeout
            )

            self.config.llm_provider.model = original_model

            task.status = TaskStatus.COMPLETED
            task.result = result
            task.end_time = time.time()
            self.completed_tasks.add(task.id)
            self.running_tasks.discard(task.id)

            self._log_event(f"Completed task {task.id} in {task.execution_time:.2f}s")

            return result

        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"Task timed out after {task.timeout} seconds"
            task.end_time = time.time()
            self.failed_tasks.add(task.id)
            self.running_tasks.discard(task.id)
            self._log_event(f"Task {task.id} timed out")
            raise

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.end_time = time.time()
            self.failed_tasks.add(task.id)
            self.running_tasks.discard(task.id)
            self._log_event(f"Task {task.id} failed: {e}")
            raise

    def _build_task_prompt(self, task: TaskNode) -> str:
        context_parts = [
            f"Project: {self.spec.name}",
            f"Task: {task.name}",
            f"Description: {task.description}"
        ]

        if task.dependencies:
            dep_results = []
            for dep_id in task.dependencies:
                dep_task = next((t for t in self.spec.tasks if t.id == dep_id), None)
                if dep_task and dep_task.result:
                    dep_results.append(f"- {dep_task.name}: Completed")
            if dep_results:
                context_parts.append(
                    "Previous tasks completed:\n" + "\n".join(dep_results)
                )

        if task.parameters:
            context_parts.append(f"Parameters: {json.dumps(task.parameters, indent=2)}")

        return "\n\n".join(context_parts)

    async def execute(self) -> Dict[str, Any]:
        self.start_time = time.time()
        valid, errors = self.spec.validate()

        if not valid:
            raise ValidationError(f"Invalid project specification: {errors}")

        self._log_event(f"Starting project execution: {self.spec.name}")

        execution_levels = self.spec.get_execution_order()

        for level_idx, level_tasks in enumerate(execution_levels):
            self._log_event(
                f"Executing level {level_idx + 1} with {len(level_tasks)} tasks"
            )

            tasks_to_run = []
            for task in level_tasks:
                if task.status == TaskStatus.PENDING:
                    tasks_to_run.append(task)

            if tasks_to_run:
                batch_size = min(len(tasks_to_run), self.spec.max_parallel)
                for i in range(0, len(tasks_to_run), batch_size):
                    batch = tasks_to_run[i:i + batch_size]

                    coroutines = []
                    for task in batch:
                        for attempt in range(task.retry_count + 1):
                            try:
                                coroutines.append(self._execute_task(task))
                                break
                            except Exception:
                                if attempt == task.retry_count:
                                    self._log_event(
                                        f"Task {task.id} failed after "
                                        f"{attempt + 1} attempts"
                                    )
                                else:
                                    self._log_event(
                                        f"Retrying task {task.id} "
                                        f"(attempt {attempt + 2})"
                                    )
                                    await asyncio.sleep(2 ** attempt)

                    if coroutines:
                        await asyncio.gather(*coroutines, return_exceptions=True)

        self.end_time = time.time()

        return self._generate_report()

    def _generate_report(self) -> Dict[str, Any]:
        if self.end_time and self.start_time:
            total_time = self.end_time - self.start_time
        else:
            total_time = 0

        task_results = {}
        for task in self.spec.tasks:
            task_results[task.id] = {
                'name': task.name,
                'status': task.status.value,
                'execution_time': task.execution_time,
                'model_used': self._select_model_for_task(task),
                'result': task.result if task.status == TaskStatus.COMPLETED else None,
                'error': task.error if task.status == TaskStatus.FAILED else None
            }

        return {
            'project': self.spec.name,
            'status': 'completed' if not self.failed_tasks else 'partial',
            'total_execution_time': total_time,
            'tasks_completed': len(self.completed_tasks),
            'tasks_failed': len(self.failed_tasks),
            'task_results': task_results,
            'execution_log': self.execution_log,
            'statistics': {
                'average_task_time': (
                    sum(t.execution_time or 0 for t in self.spec.tasks) /
                    len(self.spec.tasks) if self.spec.tasks else 0
                ),
                'parallelism_achieved': self._calculate_parallelism(),
                'model_distribution': self._get_model_distribution()
            }
        }

    def _calculate_parallelism(self) -> float:
        if not self.execution_log:
            return 0.0

        max_concurrent = 0
        current_concurrent = 0

        for event in self.execution_log:
            if 'Starting task' in event['message']:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            elif 'Completed task' in event['message'] or 'failed' in event['message']:
                current_concurrent = max(0, current_concurrent - 1)

        return max_concurrent

    def _get_model_distribution(self) -> Dict[str, int]:
        distribution = defaultdict(int)
        for task in self.spec.tasks:
            model = self._select_model_for_task(task)
            model_name = 'sonnet' if 'sonnet' in model.lower() else 'opus'
            distribution[model_name] += 1
        return dict(distribution)

    def _log_event(self, message: str):
        event = {
            'timestamp': time.time(),
            'message': message
        }
        self.execution_log.append(event)
        logger.info(message)

    async def visualize_progress(self) -> str:
        lines = []
        lines.append(f"Project: {self.spec.name}")
        lines.append("=" * 60)

        for task in self.spec.tasks:
            status_symbol = {
                TaskStatus.PENDING: "⏳",
                TaskStatus.RUNNING: "🔄",
                TaskStatus.COMPLETED: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.SKIPPED: "⏭️"
            }.get(task.status, "❓")

            if task.dependencies:
                deps = f" (deps: {', '.join(task.dependencies)})"
            else:
                deps = ""
            lines.append(f"{status_symbol} {task.id}: {task.name}{deps}")

            if task.status == TaskStatus.RUNNING and task.assigned_agent:
                lines.append(f"   └─ Agent: {task.assigned_agent}")
            elif task.status == TaskStatus.COMPLETED and task.execution_time:
                lines.append(f"   └─ Time: {task.execution_time:.2f}s")
            elif task.status == TaskStatus.FAILED and task.error:
                lines.append(f"   └─ Error: {task.error[:50]}...")

        lines.append("=" * 60)
        progress = f"Progress: {len(self.completed_tasks)}/{len(self.spec.tasks)} tasks"
        lines.append(progress)

        if self.start_time:
            elapsed = time.time() - self.start_time
            lines.append(f"Elapsed: {elapsed:.2f}s")

        return "\n".join(lines)

    def cleanup(self):
        self.executor.shutdown(wait=True)
        self.agents.clear()

