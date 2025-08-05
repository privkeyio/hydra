"""FastAPI service layer with Celery task queue integration."""

import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from celery.result import AsyncResult
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from hydra.api.auth import AuthMiddleware, get_current_api_key
from hydra.config import get_config
from hydra.monitoring import monitoring, timed_operation
from hydra.workers.celery_app import app as celery_app
from hydra.workers.tasks import (
    execute_workflow,
    execute_workflow_priority,
    generate_code,
    generate_code_priority,
)


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="Code generation prompt")
    language: Optional[str] = Field(None, description="Target programming language")
    max_tokens: Optional[int] = Field(4000, description="Maximum tokens to generate")


class WorkflowRequest(BaseModel):
    task: str = Field(..., description="Multi-agent workflow task description")
    agents: Optional[int] = Field(3, description="Number of agents to use")
    max_iterations: Optional[int] = Field(10, description="Maximum workflow iterations")


class TaskResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    message: str = Field(..., description="Status message")


class StatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = Field(..., description="Progress percentage (0-100)")
    created_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    providers: Dict[str, str]
    version: str = "1.0.0"


app = FastAPI(
    title="Hydra API",
    description="REST API for Hydra AI agent system with Celery task queue",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(AuthMiddleware)
monitoring.instrument_fastapi(app)

@app.middleware("http")
async def monitoring_middleware(request: Request, call_next):
    start_time = time.time()
    correlation_id = request.headers.get("x-correlation-id")
    monitoring.set_correlation_id(correlation_id)

    response = await call_next(request)

    duration = time.time() - start_time
    monitoring.record_request(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
        duration=duration
    )

    response.headers["x-correlation-id"] = monitoring.get_correlation_id()
    return response


def get_task_status(celery_result: AsyncResult) -> TaskStatus:
    """Convert Celery task state to our TaskStatus enum."""
    state_mapping = {
        "PENDING": TaskStatus.PENDING,
        "STARTED": TaskStatus.IN_PROGRESS,
        "PROGRESS": TaskStatus.IN_PROGRESS,
        "SUCCESS": TaskStatus.COMPLETED,
        "FAILURE": TaskStatus.FAILED,
        "RETRY": TaskStatus.IN_PROGRESS,
        "REVOKED": TaskStatus.FAILED
    }
    return state_mapping.get(celery_result.state, TaskStatus.PENDING)


def get_task_progress(celery_result: AsyncResult) -> int:
    """Extract progress from Celery task metadata."""
    if celery_result.state == "PENDING":
        return 0
    elif celery_result.state == "SUCCESS":
        return 100
    elif celery_result.state in ("PROGRESS", "STARTED"):
        meta = celery_result.info
        if isinstance(meta, dict) and "progress" in meta:
            return meta["progress"]
        return 50
    else:
        return 0


@app.post("/generate", response_model=TaskResponse)
@timed_operation("api_generate")
async def generate_code_endpoint(
    request: GenerateRequest,
    api_key_info: tuple = Depends(get_current_api_key)
):
    """Generate code using a single agent."""
    api_key, is_priority = api_key_info

    task_func = generate_code_priority if is_priority else generate_code

    result = task_func.apply_async(
        args=[request.prompt, request.language, request.max_tokens],
        kwargs={"task_id": None}
    )

    return TaskResponse(
        task_id=result.id,
        status=TaskStatus.PENDING,
        message="Code generation task queued"
    )


@app.post("/workflow", response_model=TaskResponse)
@timed_operation("api_workflow")
async def execute_workflow_endpoint(
    request: WorkflowRequest,
    api_key_info: tuple = Depends(get_current_api_key)
):
    """Execute a multi-agent workflow."""
    api_key, is_priority = api_key_info

    task_func = execute_workflow_priority if is_priority else execute_workflow

    result = task_func.apply_async(
        args=[request.task, request.agents, request.max_iterations],
        kwargs={"task_id": None}
    )

    return TaskResponse(
        task_id=result.id,
        status=TaskStatus.PENDING,
        message="Workflow execution task queued"
    )


@app.get("/status/{task_id}", response_model=StatusResponse)
async def get_task_status_endpoint(task_id: str, api_key_info: tuple = Depends(get_current_api_key)):
    """Get the status of a specific task."""
    result = AsyncResult(task_id, app=celery_app)

    if result.state == "PENDING" and result.info is None:
        raise HTTPException(status_code=404, detail="Task not found")

    status = get_task_status(result)
    progress = get_task_progress(result)

    response_data = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "created_at": datetime.utcnow()
    }

    if status == TaskStatus.COMPLETED:
        response_data["completed_at"] = datetime.utcnow()
        response_data["result"] = result.result
    elif status == TaskStatus.FAILED:
        response_data["completed_at"] = datetime.utcnow()
        response_data["error"] = str(result.info)

    return StatusResponse(**response_data)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with provider status."""
    try:
        config = get_config()
        provider_status = {}

        try:
            provider_name = config.llm_provider.name
            provider_status[provider_name] = "available"
        except Exception:
            provider_status["default"] = "unknown"

        celery_status = celery_app.control.inspect()
        active_queues = celery_status.active_queues()
        if active_queues:
            provider_status["celery"] = "healthy"
        else:
            provider_status["celery"] = "no_workers"

        return HealthResponse(
            status="healthy",
            timestamp=datetime.utcnow(),
            providers=provider_status
        )
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.utcnow(),
            providers={"error": str(e)}
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
