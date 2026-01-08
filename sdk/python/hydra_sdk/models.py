from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


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
    memory_peak: str
    total_keys: int
    connected_clients: int
    cache_hit_rate: float
    uptime_seconds: int


class SignatureRequest(BaseModel):
    method: str = Field(..., description="HTTP method")
    path: str = Field(..., description="Request path")
    body: str = Field("", description="Request body")
    timestamp: int = Field(..., description="Unix timestamp")


class SignatureResponse(BaseModel):
    signature: str = Field(..., description="HMAC signature")
    timestamp: int = Field(..., description="Unix timestamp used")


class AuditLogQuery(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    operation: Optional[str] = None
    user: Optional[str] = None
    limit: int = Field(100, le=1000)
