import asyncio
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    min_size: int = 5
    max_size: int = 20
    timeout: float = 30.0
    recycle: int = 3600
    pre_ping: bool = True


class ConnectionPoolManager:
    def __init__(self):
        self._pools: Dict[str, Any] = {}
        self._pool_configs: Dict[str, PoolConfig] = {
            "database": PoolConfig(min_size=10, max_size=50),
            "redis": PoolConfig(min_size=5, max_size=20),
            "http": PoolConfig(min_size=10, max_size=100),
        }
        self._executor = ThreadPoolExecutor(max_workers=20)
        
    async def get_database_pool(self, database_url: Optional[str] = None):
        if "database" not in self._pools:
            config = self._pool_configs["database"]
            url = database_url or os.getenv("DATABASE_URL", "postgresql+asyncpg://hydra:hydra@localhost/hydra")
            
            self._pools["database"] = create_async_engine(
                url,
                poolclass=QueuePool,
                pool_size=config.min_size,
                max_overflow=config.max_size - config.min_size,
                pool_timeout=config.timeout,
                pool_recycle=config.recycle,
                pool_pre_ping=config.pre_ping,
                echo=False,
            )
        return self._pools["database"]
    
    async def get_http_session(self) -> aiohttp.ClientSession:
        if "http" not in self._pools:
            config = self._pool_configs["http"]
            connector = aiohttp.TCPConnector(
                limit=config.max_size,
                limit_per_host=30,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            self._pools["http"] = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )
        return self._pools["http"]
    
    async def close_all(self):
        for name, pool in self._pools.items():
            if hasattr(pool, "dispose"):
                await pool.dispose()
            elif hasattr(pool, "close"):
                await pool.close()
        self._pools.clear()
        self._executor.shutdown(wait=True)


pool_manager = ConnectionPoolManager()


class RequestBatcher:
    def __init__(self, batch_size: int = 10, batch_timeout: float = 0.1):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self._queues: Dict[str, asyncio.Queue] = defaultdict(lambda: asyncio.Queue())
        self._batch_tasks: Dict[str, asyncio.Task] = {}
        
    async def add_request(self, provider: str, request: Dict[str, Any]) -> Any:
        queue = self._queues[provider]
        future = asyncio.Future()
        await queue.put((request, future))
        
        if provider not in self._batch_tasks or self._batch_tasks[provider].done():
            self._batch_tasks[provider] = asyncio.create_task(self._process_batch(provider))
            
        return await future
    
    async def _process_batch(self, provider: str):
        queue = self._queues[provider]
        batch = []
        start_time = time.time()
        
        while len(batch) < self.batch_size and (time.time() - start_time) < self.batch_timeout:
            try:
                timeout = self.batch_timeout - (time.time() - start_time)
                request, future = await asyncio.wait_for(queue.get(), timeout=max(0.01, timeout))
                batch.append((request, future))
            except asyncio.TimeoutError:
                break
                
        if batch:
            await self._execute_batch(provider, batch)
    
    async def _execute_batch(self, provider: str, batch: List[Tuple[Dict, asyncio.Future]]):
        try:
            requests = [req for req, _ in batch]
            results = await self._call_provider_batch(provider, requests)
            
            for (_, future), result in zip(batch, results):
                if isinstance(result, Exception):
                    future.set_exception(result)
                else:
                    future.set_result(result)
        except Exception as e:
            for _, future in batch:
                future.set_exception(e)
    
    async def _call_provider_batch(self, provider: str, requests: List[Dict]) -> List[Any]:
        session = await pool_manager.get_http_session()
        
        if provider == "openai":
            url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"
            headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}
        elif provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                "anthropic-version": "2023-06-01"
            }
        else:
            url = os.getenv("VENICE_BASE_URL", "https://api.venice.ai/api/v1") + "/chat/completions"
            headers = {"Authorization": f"Bearer {os.getenv('VENICE_API_KEY')}"}
        
        tasks = []
        for request in requests:
            task = session.post(url, json=request, headers=headers)
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        
        for response in responses:
            if isinstance(response, Exception):
                results.append(response)
            else:
                try:
                    data = await response.json()
                    results.append(data)
                except Exception as e:
                    results.append(e)
                    
        return results


request_batcher = RequestBatcher()


class StreamingResponseHandler:
    def __init__(self):
        self._active_streams: Dict[str, asyncio.Queue] = {}
        
    async def create_stream(self, task_id: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=100)
        self._active_streams[task_id] = queue
        return queue
    
    async def write_chunk(self, task_id: str, chunk: str):
        if task_id in self._active_streams:
            await self._active_streams[task_id].put(chunk)
    
    async def close_stream(self, task_id: str):
        if task_id in self._active_streams:
            await self._active_streams[task_id].put(None)
            del self._active_streams[task_id]
    
    async def stream_llm_response(self, provider: str, request: Dict, task_id: str):
        queue = await self.create_stream(task_id)
        
        try:
            session = await pool_manager.get_http_session()
            request["stream"] = True
            
            if provider == "openai":
                url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"
                headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                    "anthropic-version": "2023-06-01"
                }
            else:
                url = os.getenv("VENICE_BASE_URL", "https://api.venice.ai/api/v1") + "/chat/completions"
                headers = {"Authorization": f"Bearer {os.getenv('VENICE_API_KEY')}"}
            
            async with session.post(url, json=request, headers=headers) as response:
                async for line in response.content:
                    if line:
                        decoded = line.decode("utf-8").strip()
                        if decoded.startswith("data: ") and decoded != "data: [DONE]":
                            chunk = decoded[6:]
                            await self.write_chunk(task_id, chunk)
                            
        except Exception as e:
            logger.error(f"Streaming error for task {task_id}: {e}")
            await self.write_chunk(task_id, f"ERROR: {str(e)}")
        finally:
            await self.close_stream(task_id)
            
        return queue


streaming_handler = StreamingResponseHandler()


class QueryOptimizer:
    @staticmethod
    async def optimize_task_queries(session: AsyncSession):
        await session.execute(
            text("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_status_tenant_created 
            ON tasks(status, tenant_id, created_at DESC);
            
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_api_key_month 
            ON usage(api_key_id, DATE_TRUNC('month', timestamp));
            
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_cost_tracking 
            ON usage(provider, model, DATE_TRUNC('day', timestamp)) 
            WHERE cost IS NOT NULL;
            """)
        )
        await session.commit()
    
    @staticmethod
    async def get_task_with_usage(session: AsyncSession, task_id: str):
        result = await session.execute(
            select("tasks", "usage").join("usage", isouter=True).where(
                text("tasks.id = :task_id")
            ).params(task_id=task_id).options(
                selectinload("usage_records")
            )
        )
        return result.scalars().first()
    
    @staticmethod
    async def get_tenant_usage_summary(session: AsyncSession, tenant_id: str, month: str):
        result = await session.execute(
            text("""
            SELECT 
                COUNT(DISTINCT t.id) as task_count,
                SUM(u.tokens_used) as total_tokens,
                SUM(u.cost) as total_cost,
                COUNT(DISTINCT DATE(t.created_at)) as active_days
            FROM tasks t
            LEFT JOIN usage u ON t.id = u.task_id
            WHERE t.tenant_id = :tenant_id
                AND DATE_TRUNC('month', t.created_at) = :month
            """).params(tenant_id=tenant_id, month=month)
        )
        return result.fetchone()


@asynccontextmanager
async def get_optimized_session():
    engine = await pool_manager.get_database_pool()
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def initialize_performance_optimizations():
    logger.info("Initializing performance optimizations")
    
    async with get_optimized_session() as session:
        await QueryOptimizer.optimize_task_queries(session)
    
    logger.info("Performance optimizations initialized")


async def cleanup_performance_resources():
    await pool_manager.close_all()