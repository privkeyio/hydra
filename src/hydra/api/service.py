"""FastAPI service layer for Hydra REST API."""

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from hydra.agents.base import CodeAgent
from hydra.config import get_config
from hydra.workflows.engine import execute_workflow


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
    description="REST API for Hydra AI agent system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

tasks_store: Dict[str, Dict[str, Any]] = {}


async def process_generate_task(task_id: str, request: GenerateRequest):
    """Background task for code generation."""
    try:
        tasks_store[task_id]["status"] = TaskStatus.IN_PROGRESS
        tasks_store[task_id]["progress"] = 10

        config = get_config()
        agent = CodeAgent(config)

        tasks_store[task_id]["progress"] = 50

        result = await asyncio.to_thread(
            agent.generate_code,
            request.prompt,
            language=request.language,
            max_tokens=request.max_tokens
        )

        tasks_store[task_id]["status"] = TaskStatus.COMPLETED
        tasks_store[task_id]["progress"] = 100
        tasks_store[task_id]["completed_at"] = datetime.utcnow()
        tasks_store[task_id]["result"] = {"code": result}

    except Exception as e:
        tasks_store[task_id]["status"] = TaskStatus.FAILED
        tasks_store[task_id]["error"] = str(e)
        tasks_store[task_id]["completed_at"] = datetime.utcnow()


async def process_workflow_task(task_id: str, request: WorkflowRequest):
    """Background task for workflow execution."""
    try:
        tasks_store[task_id]["status"] = TaskStatus.IN_PROGRESS
        tasks_store[task_id]["progress"] = 10

        config = get_config()

        tasks_store[task_id]["progress"] = 30

        result = await asyncio.to_thread(
            execute_workflow,
            request.task,
            num_agents=request.agents,
            max_iterations=request.max_iterations,
            config=config
        )

        tasks_store[task_id]["status"] = TaskStatus.COMPLETED
        tasks_store[task_id]["progress"] = 100
        tasks_store[task_id]["completed_at"] = datetime.utcnow()
        tasks_store[task_id]["result"] = result

    except Exception as e:
        tasks_store[task_id]["status"] = TaskStatus.FAILED
        tasks_store[task_id]["error"] = str(e)
        tasks_store[task_id]["completed_at"] = datetime.utcnow()


@app.post("/generate", response_model=TaskResponse)
async def generate_code(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Generate code using a single agent."""
    task_id = str(uuid.uuid4())

    tasks_store[task_id] = {
        "status": TaskStatus.PENDING,
        "progress": 0,
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "result": None,
        "error": None
    }

    background_tasks.add_task(process_generate_task, task_id, request)

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Code generation task queued"
    )


@app.post("/workflow", response_model=TaskResponse)
async def execute_workflow_endpoint(
    request: WorkflowRequest, background_tasks: BackgroundTasks
):
    """Execute a multi-agent workflow."""
    task_id = str(uuid.uuid4())

    tasks_store[task_id] = {
        "status": TaskStatus.PENDING,
        "progress": 0,
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "result": None,
        "error": None
    }

    background_tasks.add_task(process_workflow_task, task_id, request)

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Workflow execution task queued"
    )


@app.get("/status/{task_id}", response_model=StatusResponse)
async def get_task_status(task_id: str):
    """Get the status of a specific task."""
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = tasks_store[task_id]

    return StatusResponse(
        task_id=task_id,
        status=task_data["status"],
        progress=task_data["progress"],
        created_at=task_data["created_at"],
        completed_at=task_data.get("completed_at"),
        result=task_data.get("result"),
        error=task_data.get("error")
    )


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
