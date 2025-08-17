"""Tenant isolation and resource management middleware."""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from hydra.models.db import APIKey, Task, Tenant, get_db

logger = logging.getLogger(__name__)


class TenantResourceTracker:
    """Track resource usage per tenant."""

    def __init__(self):
        self.request_counts: Dict[str, list] = defaultdict(list)
        self.token_usage: Dict[str, int] = defaultdict(int)
        self.concurrent_tasks: Dict[str, set] = defaultdict(set)
        self.usage_reset_time: Dict[str, datetime] = {}

    def check_request_limit(self, tenant_id: str, limit: int) -> bool:
        """Check if tenant has exceeded request limit."""
        now = time.time()
        window = 60  # 1 minute window

        requests = self.request_counts[tenant_id]
        cutoff = now - window
        requests[:] = [t for t in requests if t > cutoff]

        if len(requests) >= limit:
            return False

        requests.append(now)
        return True

    def check_token_limit(
        self, tenant_id: str, tokens: int, monthly_limit: int
    ) -> bool:
        """Check if tenant has exceeded monthly token limit."""
        now = datetime.utcnow()

        if tenant_id not in self.usage_reset_time:
            self.usage_reset_time[tenant_id] = now.replace(
                day=1, hour=0, minute=0, second=0
            )

        if now >= self.usage_reset_time[tenant_id] + timedelta(days=30):
            self.token_usage[tenant_id] = 0
            self.usage_reset_time[tenant_id] = now.replace(
                day=1, hour=0, minute=0, second=0
            )

        if self.token_usage[tenant_id] + tokens > monthly_limit:
            return False

        return True

    def add_token_usage(self, tenant_id: str, tokens: int):
        """Add token usage for tenant."""
        self.token_usage[tenant_id] += tokens

    def check_concurrent_tasks(self, tenant_id: str, task_id: str, limit: int) -> bool:
        """Check if tenant can start a new task."""
        active_tasks = self.concurrent_tasks[tenant_id]

        # Clean up completed tasks periodically
        if len(active_tasks) > limit * 2:
            active_tasks.clear()

        if len(active_tasks) >= limit and task_id not in active_tasks:
            return False

        active_tasks.add(task_id)
        return True

    def complete_task(self, tenant_id: str, task_id: str):
        """Mark task as completed."""
        self.concurrent_tasks[tenant_id].discard(task_id)


resource_tracker = TenantResourceTracker()


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    """Middleware for tenant isolation and resource management."""

    async def dispatch(self, request: Request, call_next):
        """Process request with tenant isolation."""
        path = request.url.path

        # Skip tenant check for health endpoint
        if path == "/health":
            return await call_next(request)

        # Get tenant ID from API key
        if not hasattr(request.state, "api_key"):
            # Auth middleware should have already handled this
            return await call_next(request)

        api_key = request.state.api_key
        db: Session = next(get_db())

        try:
            # Get tenant info from API key
            api_key_obj = (
                db.query(APIKey)
                .filter(APIKey.key == api_key, APIKey.is_active.is_(True))
                .first()
            )

            if not api_key_obj or not api_key_obj.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="API key not associated with a tenant",
                )

            tenant = (
                db.query(Tenant)
                .filter(Tenant.id == api_key_obj.tenant_id, Tenant.is_active.is_(True))
                .first()
            )

            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant not found or inactive",
                )

            # Check request rate limit
            if not resource_tracker.check_request_limit(
                tenant.id, tenant.max_requests_per_minute
            ):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Tenant request limit exceeded: "
                        f"{tenant.max_requests_per_minute}/min"
                    ),
                )

            # Add tenant info to request state
            request.state.tenant_id = tenant.id
            request.state.tenant = tenant

            # Process request
            response = await call_next(request)

            return response

        finally:
            db.close()


async def get_current_tenant(request: Request) -> Tenant:
    """Get current tenant from request state."""
    if not hasattr(request.state, "tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No tenant context available"
        )
    return request.state.tenant


def check_tenant_quota(
    tenant_id: str, tokens: int = 0, task_id: Optional[str] = None
) -> bool:
    """Check if tenant has available quota for operation."""
    db: Session = next(get_db())

    try:
        tenant = (
            db.query(Tenant)
            .filter(Tenant.id == tenant_id, Tenant.is_active.is_(True))
            .first()
        )

        if not tenant:
            return False

        # Check token limit if tokens provided
        if tokens > 0:
            if not resource_tracker.check_token_limit(
                tenant_id, tokens, tenant.max_tokens_per_month
            ):
                return False

        # Check concurrent task limit if task_id provided
        if task_id:
            if not resource_tracker.check_concurrent_tasks(
                tenant_id, task_id, tenant.max_concurrent_tasks
            ):
                return False

        return True

    finally:
        db.close()


def update_tenant_usage(
    tenant_id: str,
    tokens: int = 0,
    task_id: Optional[str] = None,
    completed: bool = False,
):
    """Update tenant resource usage."""
    if tokens > 0:
        resource_tracker.add_token_usage(tenant_id, tokens)

    if task_id and completed:
        resource_tracker.complete_task(tenant_id, task_id)


def get_tenant_usage_stats(tenant_id: str) -> Dict:
    """Get current usage statistics for a tenant."""
    db: Session = next(get_db())

    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return {}

        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0)

        # Get task count for current month
        task_count = (
            db.query(Task)
            .filter(Task.tenant_id == tenant_id, Task.created_at >= month_start)
            .count()
        )

        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "current_month_tokens": resource_tracker.token_usage.get(tenant_id, 0),
            "max_tokens_per_month": tenant.max_tokens_per_month,
            "active_tasks": len(
                resource_tracker.concurrent_tasks.get(tenant_id, set())
            ),
            "max_concurrent_tasks": tenant.max_concurrent_tasks,
            "tasks_this_month": task_count,
            "requests_per_minute_limit": tenant.max_requests_per_minute,
        }

    finally:
        db.close()
