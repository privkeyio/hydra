"""Celery tasks for distributed processing."""

import uuid
from datetime import datetime
from typing import Optional

from celery import Task, current_task
from celery.exceptions import Reject

from hydra.agents.base import CodeAgent
from hydra.api.tenant import check_tenant_quota, update_tenant_usage
from hydra.config import get_config
from hydra.workers.celery_app import app, get_tenant_queue_name, register_tenant_queue
from hydra.workers.websocket import send_progress_update
from hydra.workflows.engine import execute_workflow as run_workflow


class HydraTask(Task):
    """Base task class with progress tracking."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Send task to dead letter queue on failure."""
        if self.request.retries >= self.max_retries:
            app.send_task(
                "hydra.workers.tasks.dead_letter_handler",
                args=[task_id, str(exc), args, kwargs],
                queue="dead_letter"
            )


@app.task(bind=True, base=HydraTask, name="hydra.workers.tasks.generate_code")
def generate_code(
    self,
    prompt: str,
    language: Optional[str] = None,
    max_tokens: int = 4000,
    task_id: Optional[str] = None
) -> dict:
    """Generate code using a single agent."""
    if not task_id:
        task_id = str(uuid.uuid4())

    try:
        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 10, "task_id": task_id}
        )
        send_progress_update(task_id, 10, "Initializing code agent")

        config = get_config()
        agent = CodeAgent(config)

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 50, "task_id": task_id}
        )
        send_progress_update(task_id, 50, "Generating code")

        result = agent.generate_code(
            prompt,
            language=language,
            max_tokens=max_tokens
        )

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 100, "task_id": task_id}
        )
        send_progress_update(task_id, 100, "Code generation complete")

        return {
            "task_id": task_id,
            "code": result,
            "completed_at": datetime.utcnow().isoformat()
        }

    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"task_id": task_id, "error": str(exc)}
        )
        send_progress_update(task_id, -1, f"Failed: {str(exc)}")
        raise Reject(str(exc), requeue=False) from exc


@app.task(bind=True, base=HydraTask, name="hydra.workers.tasks.generate_code_priority")
def generate_code_priority(
    self,
    prompt: str,
    language: Optional[str] = None,
    max_tokens: int = 4000,
    task_id: Optional[str] = None
) -> dict:
    """High-priority code generation for paid tiers."""
    return generate_code.apply(
        args=[prompt, language, max_tokens, task_id]
    ).get()


@app.task(bind=True, base=HydraTask, name="hydra.workers.tasks.execute_workflow")
def execute_workflow(
    self,
    task: str,
    num_agents: int = 3,
    max_iterations: int = 10,
    task_id: Optional[str] = None
) -> dict:
    """Execute a multi-agent workflow."""
    if not task_id:
        task_id = str(uuid.uuid4())

    try:
        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 10, "task_id": task_id}
        )
        send_progress_update(task_id, 10, "Initializing workflow")

        config = get_config()

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 30, "task_id": task_id}
        )
        send_progress_update(task_id, 30, "Starting multi-agent collaboration")

        result = run_workflow(
            task,
            num_agents=num_agents,
            max_iterations=max_iterations,
            config=config
        )

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 100, "task_id": task_id}
        )
        send_progress_update(task_id, 100, "Workflow complete")

        return {
            "task_id": task_id,
            "result": result,
            "completed_at": datetime.utcnow().isoformat()
        }

    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"task_id": task_id, "error": str(exc)}
        )
        send_progress_update(task_id, -1, f"Failed: {str(exc)}")
        raise Reject(str(exc), requeue=False) from exc


@app.task(
    bind=True, base=HydraTask, name="hydra.workers.tasks.execute_workflow_priority"
)
def execute_workflow_priority(
    self,
    task: str,
    num_agents: int = 3,
    max_iterations: int = 10,
    task_id: Optional[str] = None
) -> dict:
    """High-priority workflow execution for paid tiers."""
    return execute_workflow.apply(
        args=[task, num_agents, max_iterations, task_id]
    ).get()


@app.task(name="hydra.workers.tasks.dead_letter_handler")
def dead_letter_handler(task_id: str, error: str, args: list, kwargs: dict):
    """Handle failed tasks in dead letter queue."""
    import logging
    logger = logging.getLogger(__name__)

    logger.error(
        f"Task {task_id} failed permanently: {error}",
        extra={
            "task_id": task_id,
            "args": args,
            "kwargs": kwargs,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

    # TODO: Store in database for analysis
    # TODO: Send alerts for critical failures


@app.task(bind=True, base=HydraTask, name="hydra.workers.tasks.generate_code_tenant")
def generate_code_tenant(
    self,
    prompt: str,
    tenant_id: str,
    language: Optional[str] = None,
    max_tokens: int = 4000,
    task_id: Optional[str] = None,
    is_priority: bool = False
) -> dict:
    """Tenant-specific code generation with isolation."""
    if not task_id:
        task_id = str(uuid.uuid4())

    # Check tenant quota
    if not check_tenant_quota(tenant_id, tokens=max_tokens, task_id=task_id):
        raise Reject("Tenant quota exceeded", requeue=False)

    try:
        # Route to tenant-specific queue
        get_tenant_queue_name(tenant_id, is_priority)
        register_tenant_queue(tenant_id, is_priority)

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 10, "task_id": task_id, "tenant_id": tenant_id}
        )
        send_progress_update(task_id, 10, "Initializing code agent")

        config = get_config()
        agent = CodeAgent(config)

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 50, "task_id": task_id, "tenant_id": tenant_id}
        )
        send_progress_update(task_id, 50, "Generating code")

        result = agent.generate_code(
            prompt,
            language=language,
            max_tokens=max_tokens
        )

        # Update tenant usage
        update_tenant_usage(
            tenant_id, tokens=max_tokens, task_id=task_id, completed=True
        )

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 100, "task_id": task_id, "tenant_id": tenant_id}
        )
        send_progress_update(task_id, 100, "Code generation complete")

        return {
            "task_id": task_id,
            "tenant_id": tenant_id,
            "code": result,
            "completed_at": datetime.utcnow().isoformat()
        }

    except Exception as exc:
        update_tenant_usage(tenant_id, task_id=task_id, completed=True)
        current_task.update_state(
            state="FAILURE",
            meta={"task_id": task_id, "tenant_id": tenant_id, "error": str(exc)}
        )
        send_progress_update(task_id, -1, f"Failed: {str(exc)}")
        raise Reject(str(exc), requeue=False) from exc


@app.task(bind=True, base=HydraTask, name="hydra.workers.tasks.execute_workflow_tenant")
def execute_workflow_tenant(
    self,
    task: str,
    tenant_id: str,
    num_agents: int = 3,
    max_iterations: int = 10,
    task_id: Optional[str] = None,
    is_priority: bool = False
) -> dict:
    """Tenant-specific workflow execution with isolation."""
    if not task_id:
        task_id = str(uuid.uuid4())

    # Estimate tokens for workflow
    estimated_tokens = num_agents * max_iterations * 1000

    # Check tenant quota
    if not check_tenant_quota(tenant_id, tokens=estimated_tokens, task_id=task_id):
        raise Reject("Tenant quota exceeded", requeue=False)

    try:
        # Route to tenant-specific queue
        get_tenant_queue_name(tenant_id, is_priority)
        register_tenant_queue(tenant_id, is_priority)

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 10, "task_id": task_id, "tenant_id": tenant_id}
        )
        send_progress_update(task_id, 10, "Initializing workflow")

        config = get_config()

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 30, "task_id": task_id, "tenant_id": tenant_id}
        )
        send_progress_update(task_id, 30, "Starting multi-agent collaboration")

        result = run_workflow(
            task,
            num_agents=num_agents,
            max_iterations=max_iterations,
            config=config
        )

        # Update tenant usage with actual tokens
        update_tenant_usage(
            tenant_id, tokens=estimated_tokens, task_id=task_id, completed=True
        )

        current_task.update_state(
            state="PROGRESS",
            meta={"progress": 100, "task_id": task_id, "tenant_id": tenant_id}
        )
        send_progress_update(task_id, 100, "Workflow complete")

        return {
            "task_id": task_id,
            "tenant_id": tenant_id,
            "result": result,
            "completed_at": datetime.utcnow().isoformat()
        }

    except Exception as exc:
        update_tenant_usage(tenant_id, task_id=task_id, completed=True)
        current_task.update_state(
            state="FAILURE",
            meta={"task_id": task_id, "tenant_id": tenant_id, "error": str(exc)}
        )
        send_progress_update(task_id, -1, f"Failed: {str(exc)}")
        raise Reject(str(exc), requeue=False) from exc
