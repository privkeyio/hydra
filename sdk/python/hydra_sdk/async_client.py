import asyncio
from typing import Dict, Optional

from .async_base_client import AsyncBaseClient
from .models import (
    AuditLogQuery,
    CacheInvalidateRequest,
    CacheInvalidateResponse,
    CacheStatsResponse,
    GenerateRequest,
    HealthResponse,
    SignatureRequest,
    SignatureResponse,
    StatusResponse,
    TaskResponse,
    WorkflowRequest,
)


class HydraAsyncClient(AsyncBaseClient):
    async def generate_code(
        self,
        prompt: str,
        language: Optional[str] = None,
        max_tokens: Optional[int] = 4000,
    ) -> TaskResponse:
        request = GenerateRequest(
            prompt=prompt,
            language=language,
            max_tokens=max_tokens,
        )
        response = await self._make_request("POST", "/generate", request.dict())
        return TaskResponse(**response)

    async def execute_workflow(
        self,
        task: str,
        agents: Optional[int] = 3,
        max_iterations: Optional[int] = 10,
    ) -> TaskResponse:
        request = WorkflowRequest(
            task=task,
            agents=agents,
            max_iterations=max_iterations,
        )
        response = await self._make_request("POST", "/workflow", request.dict())
        return TaskResponse(**response)

    async def get_task_status(self, task_id: str) -> StatusResponse:
        response = await self._make_request("GET", f"/status/{task_id}")
        return StatusResponse(**response)

    async def get_health(self) -> HealthResponse:
        response = await self._make_request("GET", "/health")
        return HealthResponse(**response)

    async def invalidate_cache(
        self,
        cache_type: str,
        key: Optional[str] = None,
    ) -> CacheInvalidateResponse:
        request = CacheInvalidateRequest(cache_type=cache_type, key=key)
        response = await self._make_request("POST", "/cache/invalidate", request.dict())
        return CacheInvalidateResponse(**response)

    async def get_cache_stats(self) -> CacheStatsResponse:
        response = await self._make_request("GET", "/cache/stats")
        return CacheStatsResponse(**response)

    async def generate_signature(
        self,
        method: str,
        path: str,
        body: str = "",
        timestamp: int = None,
    ) -> SignatureResponse:
        if timestamp is None:
            import time
            timestamp = int(time.time())

        request = SignatureRequest(
            method=method,
            path=path,
            body=body,
            timestamp=timestamp,
        )
        response = await self._make_request("POST", "/security/sign", request.dict())
        return SignatureResponse(**response)

    async def query_audit_logs(self, query: AuditLogQuery) -> Dict:
        response = await self._make_request("POST", "/security/audit-logs", query.dict())
        return response

    async def wait_for_completion(
        self,
        task_id: str,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
    ) -> StatusResponse:
        start_time = asyncio.get_event_loop().time()

        while True:
            status = await self.get_task_status(task_id)

            if status.status in ["completed", "failed"]:
                return status

            if timeout and (asyncio.get_event_loop().time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

            await asyncio.sleep(poll_interval)
