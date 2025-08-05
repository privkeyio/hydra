"""FastAPI service layer for Hydra REST API."""

import asyncio
import csv
import hashlib
import json
import time
import uuid
from datetime import datetime
from enum import Enum
from io import StringIO
from typing import Annotated, Any, Dict, List, Optional, Set

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from hydra.agents.base import CodeAgent
from hydra.api.auth import AuthMiddleware, get_current_api_key
from hydra.api.tenant import (
    TenantIsolationMiddleware,
    check_tenant_quota,
    get_current_tenant,
    get_tenant_usage_stats,
)
from hydra.billing import get_billing_service
from hydra.cache import get_cache
from hydra.config import get_config
from hydra.models.db import APIKey, Tenant, Usage, get_db
from hydra.monitoring import monitoring, timed_operation
from hydra.performance import (
    cleanup_performance_resources,
    initialize_performance_optimizations,
    streaming_handler,
)
from hydra.security import (
    SecurityHeaders,
    audit_logger,
    input_sanitizer,
    request_signer,
)
from hydra.workers.tasks import execute_workflow_tenant, generate_code_tenant
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


class CacheInvalidateRequest(BaseModel):
    cache_type: str = Field(
        ..., description="Cache type: 'code', 'task', 'api', or 'all'"
    )
    key: Optional[str] = Field(
        None, description="Specific key to invalidate (optional)"
    )


class CacheInvalidateResponse(BaseModel):
    success: bool
    keys_deleted: int
    message: str


class CacheStatsResponse(BaseModel):
    memory_used: str


class UsageReportResponse(BaseModel):
    api_key: str
    period: str
    total_requests: int
    total_tokens: int
    total_cost: float
    endpoint_breakdown: Dict[str, Dict[str, Any]]


class UsageLimitsResponse(BaseModel):
    current_cost: float
    monthly_limit: Optional[float]
    alerts: List[Dict[str, str]]


app = FastAPI(
    title="Hydra API",
    description="REST API for Hydra AI agent system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(AuthMiddleware)
app.add_middleware(TenantIsolationMiddleware)
monitoring.instrument_fastapi(app)


@app.on_event("startup")
async def startup_event():
    """Initialize performance optimizations on startup."""
    await initialize_performance_optimizations()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup performance resources on shutdown."""
    await cleanup_performance_resources()

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

    # Apply security headers
    response = SecurityHeaders.apply_headers(response)

    return response

tasks_store: Dict[str, Dict[str, Any]] = {}
admin_websockets: Set[WebSocket] = set()


@timed_operation("code_generation")
async def process_generate_task(task_id: str, request: GenerateRequest, api_key: str):
    """Background task for code generation."""
    try:
        tasks_store[task_id]["status"] = TaskStatus.IN_PROGRESS
        tasks_store[task_id]["progress"] = 10

        await notify_admin_clients("task_update", {
            "task": {
                "id": task_id,
                "status": TaskStatus.IN_PROGRESS,
                "progress": 10,
                "created_at": tasks_store[task_id]["created_at"].isoformat()
            }
        })

        cache = get_cache()

        cached_code = cache.get_code_cache(
            request.prompt,
            language=request.language,
            max_tokens=request.max_tokens
        )

        if cached_code:
            tasks_store[task_id]["status"] = TaskStatus.COMPLETED
            tasks_store[task_id]["progress"] = 100
            tasks_store[task_id]["completed_at"] = datetime.utcnow()
            tasks_store[task_id]["result"] = {"code": cached_code, "cached": True}
            return

        config = get_config()
        agent = CodeAgent(config)

        tasks_store[task_id]["progress"] = 50

        await notify_admin_clients("task_update", {
            "task": {
                "id": task_id,
                "status": TaskStatus.IN_PROGRESS,
                "progress": 50,
                "created_at": tasks_store[task_id]["created_at"].isoformat()
            }
        })

        result = await asyncio.to_thread(
            agent.generate_code,
            request.prompt,
            language=request.language,
            max_tokens=request.max_tokens
        )

        cache.set_code_cache(
            request.prompt,
            result,
            language=request.language,
            max_tokens=request.max_tokens
        )

        tasks_store[task_id]["status"] = TaskStatus.COMPLETED
        tasks_store[task_id]["progress"] = 100
        tasks_store[task_id]["completed_at"] = datetime.utcnow()
        tasks_store[task_id]["result"] = {"code": result, "cached": False}

        cache.set_task_result(task_id, tasks_store[task_id])

        # Track usage for billing
        try:
            from hydra.models.db import get_db
            db = get_db()
            api_key_obj = db.query(APIKey).filter(APIKey.key == api_key).first()
            if api_key_obj:
                billing_service = get_billing_service()
                billing_service.track_usage(
                    api_key_id=api_key_obj.id,
                    endpoint="/generate",
                    prompt=request.prompt,
                    response=result,
                    model=config.llm_provider.model,
                    task_id=task_id
                )
            db.close()
        except Exception as e:
            # Don't fail the task if billing tracking fails
            import logging
            logging.getLogger(__name__).error(f"Billing tracking failed: {e}")

    except Exception as e:
        tasks_store[task_id]["status"] = TaskStatus.FAILED
        tasks_store[task_id]["error"] = str(e)
        tasks_store[task_id]["completed_at"] = datetime.utcnow()


@timed_operation("workflow")
async def process_workflow_task(task_id: str, request: WorkflowRequest, api_key: str):
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

        cache = get_cache()
        cache.set_task_result(task_id, tasks_store[task_id])

        # Track usage for billing
        try:
            from hydra.models.db import get_db
            db = get_db()
            api_key_obj = db.query(APIKey).filter(APIKey.key == api_key).first()
            if api_key_obj:
                billing_service = get_billing_service()
                # Estimate response length for workflows
                response_text = str(result) if result else ""
                billing_service.track_usage(
                    api_key_id=api_key_obj.id,
                    endpoint="/workflow",
                    prompt=request.task,
                    response=response_text,
                    model=config.llm_provider.model,
                    task_id=task_id
                )
            db.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Billing tracking failed: {e}")

    except Exception as e:
        tasks_store[task_id]["status"] = TaskStatus.FAILED
        tasks_store[task_id]["error"] = str(e)
        tasks_store[task_id]["completed_at"] = datetime.utcnow()


@app.post("/generate", response_model=TaskResponse)
async def generate_code(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    req: Request = None
):
    """Generate code using a single agent."""
    # Sanitize input
    is_valid, sanitized = input_sanitizer.sanitize_code_input(request.prompt)
    if not is_valid:
        audit_logger.log_security_event(
            "INPUT_VALIDATION_FAILED",
            "HIGH",
            f"Dangerous input detected: {sanitized}",
            {"user": api_key_info[0], "ip_address": req.client.host}
        )
        raise HTTPException(status_code=400, detail=sanitized)

    request.prompt = sanitized
    task_id = str(uuid.uuid4())

    # Check tenant quota
    if not check_tenant_quota(
        tenant.id, tokens=request.max_tokens, task_id=task_id
    ):
        raise HTTPException(
            status_code=429,
            detail="Tenant quota exceeded"
        )

    # Audit log
    audit_logger.log_operation(
        "CODE_GENERATION",
        api_key_info[0],
        f"task/{task_id}",
        "INITIATED",
        {
            "tenant_id": tenant.id,
            "language": request.language,
            "max_tokens": request.max_tokens,
            "ip_address": req.client.host if req else None
        }
    )

    # Queue tenant-specific task
    generate_code_tenant.apply_async(
        args=[request.prompt, tenant.id],
        kwargs={
            "language": request.language,
            "max_tokens": request.max_tokens,
            "task_id": task_id,
            "is_priority": api_key_info[1]
        },
        task_id=task_id
    )

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Code generation task queued"
    )


@app.post("/generate/stream")
async def generate_code_streaming(
    request: GenerateRequest,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    req: Request = None
):
    """Generate code with streaming response."""
    # Sanitize input
    is_valid, sanitized = input_sanitizer.sanitize_code_input(request.prompt)
    if not is_valid:
        raise HTTPException(status_code=400, detail=sanitized)

    request.prompt = sanitized
    task_id = str(uuid.uuid4())

    # Check tenant quota
    if not check_tenant_quota(
        tenant.id, tokens=request.max_tokens, task_id=task_id
    ):
        raise HTTPException(status_code=429, detail="Tenant quota exceeded")

    config = get_config()
    provider = config.llm_provider.name

    # Create streaming request
    llm_request = {
        "messages": [{"role": "user", "content": request.prompt}],
        "max_tokens": request.max_tokens,
        "temperature": 0.2,
        "stream": True
    }

    # Start streaming
    asyncio.create_task(
        streaming_handler.stream_llm_response(provider, llm_request, task_id)
    )

    async def stream_generator():
        queue = await streaming_handler.create_stream(task_id)
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield f"data: {chunk}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream"
    )


@app.post("/workflow", response_model=TaskResponse)
async def execute_workflow_endpoint(
    request: WorkflowRequest,
    background_tasks: BackgroundTasks,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    req: Request = None
):
    """Execute a multi-agent workflow."""
    # Sanitize input
    is_valid, sanitized = input_sanitizer.sanitize_code_input(request.task)
    if not is_valid:
        audit_logger.log_security_event(
            "INPUT_VALIDATION_FAILED",
            "HIGH",
            f"Dangerous workflow input: {sanitized}",
            {"user": api_key_info[0], "ip_address": req.client.host}
        )
        raise HTTPException(status_code=400, detail=sanitized)

    request.task = sanitized
    task_id = str(uuid.uuid4())

    # Estimate tokens for workflow
    estimated_tokens = request.agents * request.max_iterations * 1000

    # Check tenant quota
    if not check_tenant_quota(
        tenant.id, tokens=estimated_tokens, task_id=task_id
    ):
        raise HTTPException(
            status_code=429,
            detail="Tenant quota exceeded"
        )

    # Audit log
    audit_logger.log_operation(
        "WORKFLOW_EXECUTION",
        api_key_info[0],
        f"task/{task_id}",
        "INITIATED",
        {
            "tenant_id": tenant.id,
            "agents": request.agents,
            "max_iterations": request.max_iterations,
            "ip_address": req.client.host if req else None
        }
    )

    # Queue tenant-specific task
    execute_workflow_tenant.apply_async(
        args=[request.task, tenant.id],
        kwargs={
            "num_agents": request.agents,
            "max_iterations": request.max_iterations,
            "task_id": task_id,
            "is_priority": api_key_info[1]
        },
        task_id=task_id
    )

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Workflow execution task queued"
    )


@app.get("/status/{task_id}", response_model=StatusResponse)
async def get_task_status(
    task_id: str, api_key_info: Annotated[tuple, Depends(get_current_api_key)]
):
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


@app.post("/cache/invalidate", response_model=CacheInvalidateResponse)
async def invalidate_cache(
    request: CacheInvalidateRequest,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)]
):
    """Invalidate cache entries."""
    cache = get_cache()

    try:
        if request.cache_type == "all":
            keys_deleted = (
                cache.invalidate_code_cache() +
                cache.invalidate_task_cache() +
                cache.invalidate_api_cache()
            )
            message = "All cache entries invalidated"
        elif request.cache_type == "code":
            keys_deleted = cache.invalidate_code_cache()
            message = "Code cache invalidated"
        elif request.cache_type == "task":
            if request.key:
                keys_deleted = cache.invalidate_task_cache(request.key)
                message = f"Task cache for {request.key} invalidated"
            else:
                keys_deleted = cache.invalidate_task_cache()
                message = "All task cache invalidated"
        elif request.cache_type == "api":
            if request.key:
                keys_deleted = cache.invalidate_api_cache(request.key)
                message = f"API cache for {request.key} invalidated"
            else:
                keys_deleted = cache.invalidate_api_cache()
                message = "All API cache invalidated"
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid cache_type. Must be 'code', 'task', 'api', or 'all'"
            )

        return CacheInvalidateResponse(
            success=True,
            keys_deleted=keys_deleted,
            message=message
        )
    except Exception as e:
        return CacheInvalidateResponse(
            success=False,
            keys_deleted=0,
            message=f"Cache invalidation failed: {str(e)}"
        )


@app.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats(api_key_info: Annotated[tuple, Depends(get_current_api_key)]):
    """Get cache statistics."""
    cache = get_cache()
    stats = cache.get_cache_stats()

    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])

    return CacheStatsResponse(**stats)


class SignatureRequest(BaseModel):
    method: str = Field(..., description="HTTP method")
    path: str = Field(..., description="Request path")
    body: str = Field("", description="Request body")
    timestamp: int = Field(..., description="Unix timestamp")


class SignatureResponse(BaseModel):
    signature: str = Field(..., description="HMAC signature")
    timestamp: int = Field(..., description="Unix timestamp used")


@app.post("/security/sign", response_model=SignatureResponse)
async def generate_signature(
    request: SignatureRequest,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)]
):
    """Generate HMAC signature for API requests."""
    signature = request_signer.sign_request(
        request.method,
        request.path,
        request.body,
        request.timestamp
    )

    audit_logger.log_operation(
        "SIGNATURE_GENERATION",
        api_key_info[0],
        request.path,
        "SUCCESS",
        {"method": request.method}
    )

    return SignatureResponse(
        signature=signature,
        timestamp=request.timestamp
    )


class AuditLogQuery(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    operation: Optional[str] = None
    user: Optional[str] = None
    limit: int = Field(100, le=1000)


@app.post("/security/audit-logs")
async def query_audit_logs(
    query: AuditLogQuery,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)]
):
    """Query audit logs (admin only)."""
    # Check if user has admin privileges
    if not api_key_info[1]:  # Not a priority/admin user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # This would normally query from a database
    # For now, return a simple response
    return {
        "logs": [],
        "message": "Audit log querying requires database integration"
    }


@app.get("/admin/metrics/realtime")
async def get_realtime_metrics(
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Get real-time metrics for admin dashboard."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    active_tasks = sum(
        1 for t in tasks_store.values()
        if t["status"] in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
    )
    queue_size = sum(
        1 for t in tasks_store.values()
        if t["status"] == TaskStatus.PENDING
    )

    recent_requests = db.query(Usage).order_by(desc(Usage.timestamp)).limit(100).all()
    error_count = sum(
        1 for t in tasks_store.values()
        if t["status"] == TaskStatus.FAILED
    )

    avg_latency = 0
    if recent_requests:
        latencies = [r.response_time for r in recent_requests if r.response_time]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

    return {
        "request_count": len(recent_requests),
        "error_rate": (error_count / len(tasks_store) * 100) if tasks_store else 0,
        "avg_latency": avg_latency,
        "active_tasks": active_tasks,
        "queue_size": queue_size
    }


@app.get("/admin/metrics/usage")
async def get_usage_metrics(
    start: str,
    end: str,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)],
    api_key: Optional[str] = None
):
    """Get usage metrics with date filtering."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = db.query(Usage).filter(
        Usage.timestamp >= start,
        Usage.timestamp <= end
    )

    if api_key:
        query = query.filter(Usage.api_key_id == api_key)

    results = query.all()

    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "api_key_id": r.api_key_id,
            "endpoint": r.endpoint,
            "tokens_used": r.tokens_used,
            "task_id": r.task_id
        }
        for r in results
    ]


@app.get("/admin/tasks/queue")
async def get_task_queue(
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Get current task queue status."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    tasks = []
    for task_id, task_data in tasks_store.items():
        tasks.append({
            "id": task_id,
            "status": task_data["status"],
            "created_at": task_data["created_at"].isoformat(),
            "completed_at": (
                task_data["completed_at"].isoformat()
                if task_data["completed_at"] else None
            ),
            "agent_count": task_data.get("agent_count", 1),
            "progress": task_data.get("progress", 0)
        })

    return sorted(tasks, key=lambda x: x["created_at"], reverse=True)[:50]


@app.get("/admin/api-keys")
async def list_api_keys(
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """List all API keys."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    keys = db.query(APIKey).all()
    return [
        {
            "key": k.key,
            "name": k.name,
            "created_at": k.created_at.isoformat(),
            "is_active": k.is_active,
            "rate_limit": k.rate_limit
        }
        for k in keys
    ]


@app.post("/admin/api-keys")
async def create_api_key(
    data: dict,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Create new API key."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    if "tenant_id" not in data:
        raise HTTPException(status_code=400, detail="tenant_id is required")

    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == data["tenant_id"]).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    key = "sk-" + hashlib.sha256(
        f"{data['name']}-{datetime.utcnow()}".encode()
    ).hexdigest()[:32]

    api_key = APIKey(
        key=key,
        name=data["name"],
        tenant_id=data["tenant_id"],
        rate_limit=data.get("rate_limit", 1000)
    )

    db.add(api_key)
    db.commit()

    audit_logger.log_operation(
        "API_KEY_CREATED",
        api_key_info[0],
        key,
        "SUCCESS",
        {"name": data["name"], "tenant_id": data["tenant_id"]}
    )

    return {"key": key, "name": data["name"], "tenant_id": data["tenant_id"]}


@app.put("/admin/api-keys/{key}")
async def update_api_key(
    key: str,
    data: dict,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Update API key."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    api_key = db.query(APIKey).filter(APIKey.key == key).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    if "name" in data:
        api_key.name = data["name"]
    if "is_active" in data:
        api_key.is_active = data["is_active"]
    if "rate_limit" in data:
        api_key.rate_limit = data["rate_limit"]

    db.commit()

    audit_logger.log_operation(
        "API_KEY_UPDATED",
        api_key_info[0],
        key,
        "SUCCESS",
        data
    )

    return {"success": True}


@app.delete("/admin/api-keys/{key}")
async def delete_api_key(
    key: str,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Delete API key."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    api_key = db.query(APIKey).filter(APIKey.key == key).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    db.delete(api_key)
    db.commit()

    audit_logger.log_operation(
        "API_KEY_DELETED",
        api_key_info[0],
        key,
        "SUCCESS",
        {"name": api_key.name}
    )

    return {"success": True}


@app.get("/admin/export/usage")
async def export_usage_data(
    start: str,
    end: str,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Export usage data as CSV."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    usage_data = db.query(Usage).filter(
        Usage.timestamp >= start,
        Usage.timestamp <= end
    ).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp", "API Key", "Endpoint",
        "Tokens Used", "Task ID", "Response Time"
    ])

    for u in usage_data:
        writer.writerow([
            u.timestamp.isoformat(),
            u.api_key_id,
            u.endpoint,
            u.tokens_used,
            u.task_id or "",
            u.response_time or ""
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=usage_{start}_to_{end}.csv"
            )
        }
    )


async def notify_admin_clients(message_type: str, data: dict):
    """Send notification to all connected admin WebSocket clients."""
    message = json.dumps({"type": message_type, **data})
    dead_clients = set()

    for ws in admin_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            dead_clients.add(ws)

    admin_websockets.difference_update(dead_clients)


@app.websocket("/ws/admin")
async def admin_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for admin dashboard real-time updates."""
    await websocket.accept()
    admin_websockets.add(websocket)

    try:
        # Send initial metrics
        metrics = {
            "request_count": len(tasks_store),
            "error_rate": 0,
            "avg_latency": 0,
            "active_tasks": sum(
                1 for t in tasks_store.values()
                if t["status"] in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
            ),
            "queue_size": sum(
                1 for t in tasks_store.values()
                if t["status"] == TaskStatus.PENDING
            )
        }
        await websocket.send_text(json.dumps({"type": "metrics", "metrics": metrics}))

        # Keep connection alive
        while True:
            # Send periodic metrics updates
            await asyncio.sleep(5)
            metrics = {
                "request_count": len(tasks_store),
                "error_rate": (
                    sum(1 for t in tasks_store.values()
                        if t["status"] == TaskStatus.FAILED)
                    / max(len(tasks_store), 1) * 100
                ),
                "avg_latency": 0,
                "active_tasks": sum(
                    1 for t in tasks_store.values()
                    if t["status"] in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
                ),
                "queue_size": sum(
                    1 for t in tasks_store.values()
                    if t["status"] == TaskStatus.PENDING
                )
            }
            await websocket.send_text(
                json.dumps({"type": "metrics", "metrics": metrics})
            )

    except WebSocketDisconnect:
        admin_websockets.discard(websocket)
    except Exception:
        admin_websockets.discard(websocket)


@app.get("/billing/usage", response_model=List[Dict])
async def get_usage_history(
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get usage history for the current API key."""
    billing_service = get_billing_service()

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    usage_records = billing_service.get_usage_for_api_key(
        api_key_info[0], start_dt, end_dt
    )

    return usage_records


@app.get("/billing/report/{year}/{month}", response_model=UsageReportResponse)
async def get_monthly_report(
    year: int,
    month: int,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Get monthly usage report for the current API key."""
    billing_service = get_billing_service()

    report = billing_service.get_monthly_report(api_key_info[0], year, month)

    return UsageReportResponse(**report)


@app.get("/billing/limits", response_model=UsageLimitsResponse)
async def get_usage_limits(
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)],
    monthly_limit: Optional[float] = None
):
    """Check usage limits and get alerts."""
    from decimal import Decimal

    billing_service = get_billing_service()

    limit_decimal = Decimal(str(monthly_limit)) if monthly_limit else None
    limits_info = billing_service.check_usage_limits(api_key_info[0], limit_decimal)

    return UsageLimitsResponse(**limits_info)


@app.get("/admin/billing/export/{api_key}")
async def export_usage_csv(
    api_key: str,
    year: int,
    month: int,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Export usage data as CSV for admin users."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    billing_service = get_billing_service()
    report = billing_service.get_monthly_report(api_key, year, month)

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Timestamp", "Endpoint", "Tokens Used", "Estimated Cost", "Task ID"
    ])

    for record in report["usage_records"]:
        writer.writerow([
            record["timestamp"],
            record["endpoint"],
            record["tokens_used"],
            record["estimated_cost"],
            record["task_id"] or ""
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=usage_{api_key}_{year}_{month}.csv"
            )
        }
    )


class TenantRequest(BaseModel):
    id: str = Field(..., description="Unique tenant identifier")
    name: str = Field(..., description="Tenant name")
    max_requests_per_minute: Optional[int] = Field(
        60, description="Max requests per minute"
    )
    max_tokens_per_month: Optional[int] = Field(
        1000000, description="Max tokens per month"
    )
    max_concurrent_tasks: Optional[int] = Field(
        10, description="Max concurrent tasks"
    )


class TenantResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    is_active: bool
    max_requests_per_minute: int
    max_tokens_per_month: int
    max_concurrent_tasks: int


class TenantUsageResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    current_month_tokens: int
    max_tokens_per_month: int
    active_tasks: int
    max_concurrent_tasks: int
    tasks_this_month: int
    requests_per_minute_limit: int


@app.post("/admin/tenants", response_model=TenantResponse)
async def create_tenant(
    request: TenantRequest,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Create a new tenant (admin only)."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Check if tenant already exists
    existing = db.query(Tenant).filter(Tenant.id == request.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tenant ID already exists")

    tenant = Tenant(
        id=request.id,
        name=request.name,
        max_requests_per_minute=request.max_requests_per_minute,
        max_tokens_per_month=request.max_tokens_per_month,
        max_concurrent_tasks=request.max_concurrent_tasks
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    audit_logger.log_operation(
        "TENANT_CREATED",
        api_key_info[0],
        tenant.id,
        "SUCCESS",
        {"name": request.name}
    )

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        created_at=tenant.created_at,
        is_active=tenant.is_active,
        max_requests_per_minute=tenant.max_requests_per_minute,
        max_tokens_per_month=tenant.max_tokens_per_month,
        max_concurrent_tasks=tenant.max_concurrent_tasks
    )


@app.get("/admin/tenants", response_model=List[TenantResponse])
async def list_tenants(
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """List all tenants (admin only)."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    tenants = db.query(Tenant).all()

    return [
        TenantResponse(
            id=t.id,
            name=t.name,
            created_at=t.created_at,
            is_active=t.is_active,
            max_requests_per_minute=t.max_requests_per_minute,
            max_tokens_per_month=t.max_tokens_per_month,
            max_concurrent_tasks=t.max_concurrent_tasks
        )
        for t in tenants
    ]


@app.get("/admin/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Get tenant details (admin only)."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        created_at=tenant.created_at,
        is_active=tenant.is_active,
        max_requests_per_minute=tenant.max_requests_per_minute,
        max_tokens_per_month=tenant.max_tokens_per_month,
        max_concurrent_tasks=tenant.max_concurrent_tasks
    )


@app.put("/admin/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    data: dict,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Update tenant configuration (admin only)."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if "name" in data:
        tenant.name = data["name"]
    if "is_active" in data:
        tenant.is_active = data["is_active"]
    if "max_requests_per_minute" in data:
        tenant.max_requests_per_minute = data["max_requests_per_minute"]
    if "max_tokens_per_month" in data:
        tenant.max_tokens_per_month = data["max_tokens_per_month"]
    if "max_concurrent_tasks" in data:
        tenant.max_concurrent_tasks = data["max_concurrent_tasks"]

    db.commit()
    db.refresh(tenant)

    audit_logger.log_operation(
        "TENANT_UPDATED",
        api_key_info[0],
        tenant_id,
        "SUCCESS",
        data
    )

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        created_at=tenant.created_at,
        is_active=tenant.is_active,
        max_requests_per_minute=tenant.max_requests_per_minute,
        max_tokens_per_month=tenant.max_tokens_per_month,
        max_concurrent_tasks=tenant.max_concurrent_tasks
    )


@app.get("/admin/tenants/{tenant_id}/usage", response_model=TenantUsageResponse)
async def get_tenant_usage(
    tenant_id: str,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Get tenant usage statistics (admin only)."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    stats = get_tenant_usage_stats(tenant_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantUsageResponse(**stats)


@app.delete("/admin/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    api_key_info: Annotated[tuple, Depends(get_current_api_key)],
    db: Annotated[Session, Depends(get_db)]
):
    """Delete tenant (admin only)."""
    if not api_key_info[1]:
        raise HTTPException(status_code=403, detail="Admin access required")

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Check if tenant has any active resources
    active_keys = db.query(APIKey).filter(APIKey.tenant_id == tenant_id).count()
    if active_keys > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete tenant with {active_keys} active API keys"
        )

    db.delete(tenant)
    db.commit()

    audit_logger.log_operation(
        "TENANT_DELETED",
        api_key_info[0],
        tenant_id,
        "SUCCESS",
        {"name": tenant.name}
    )

    return {"success": True}


@app.get("/tenant/usage", response_model=TenantUsageResponse)
async def get_current_tenant_usage(
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Get current tenant's usage statistics."""
    stats = get_tenant_usage_stats(tenant.id)
    return TenantUsageResponse(**stats)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
