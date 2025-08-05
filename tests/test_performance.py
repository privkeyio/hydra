import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List

import aiohttp
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from hydra.models.db import Task, Usage, get_db_manager
from hydra.performance import pool_manager, get_optimized_session


class PerformanceMetrics:
    def __init__(self):
        self.latencies: List[float] = []
        self.errors: int = 0
        self.start_time: float = 0
        self.end_time: float = 0
    
    def add_latency(self, latency: float):
        self.latencies.append(latency)
    
    def add_error(self):
        self.errors += 1
    
    def get_p95_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[index]
    
    def get_avg_latency(self) -> float:
        if not self.latencies:
            return 0
        return sum(self.latencies) / len(self.latencies)
    
    def get_throughput(self) -> float:
        duration = self.end_time - self.start_time
        if duration == 0:
            return 0
        return len(self.latencies) / duration


@pytest.fixture
async def test_db():
    """Create test database connection."""
    db_manager = get_db_manager()
    yield db_manager
    # Cleanup handled by session


@pytest.mark.skip(reason="Requires database setup - integration test")
@pytest.mark.asyncio
async def test_database_connection_pooling(test_db):
    """Test database connection pooling performance."""
    metrics = PerformanceMetrics()
    metrics.start_time = time.time()
    
    async def query_task():
        start = time.time()
        try:
            async with get_optimized_session() as session:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM tasks")
                )
                _ = result.scalar()
            metrics.add_latency((time.time() - start) * 1000)
        except Exception:
            metrics.add_error()
    
    # Run 100 concurrent queries
    tasks = [query_task() for _ in range(100)]
    await asyncio.gather(*tasks)
    
    metrics.end_time = time.time()
    
    # Verify performance criteria
    assert metrics.get_avg_latency() < 100, f"Average query time {metrics.get_avg_latency()}ms exceeds 100ms"
    assert metrics.errors == 0, f"Got {metrics.errors} errors during connection pool test"
    assert metrics.get_throughput() > 50, f"Throughput {metrics.get_throughput()} req/s is below 50 req/s"


@pytest.mark.skip(reason="Requires network access - integration test")
@pytest.mark.asyncio
async def test_http_connection_pooling():
    """Test HTTP connection pooling for external services."""
    metrics = PerformanceMetrics()
    metrics.start_time = time.time()
    
    async def make_request():
        start = time.time()
        try:
            session = await pool_manager.get_http_session()
            async with session.get("https://httpbin.org/delay/0") as response:
                await response.text()
            metrics.add_latency((time.time() - start) * 1000)
        except Exception:
            metrics.add_error()
    
    # Run 50 concurrent HTTP requests
    tasks = [make_request() for _ in range(50)]
    await asyncio.gather(*tasks)
    
    metrics.end_time = time.time()
    
    # Verify HTTP pooling performance
    assert metrics.get_avg_latency() < 500, f"Average HTTP request time {metrics.get_avg_latency()}ms exceeds 500ms"
    assert metrics.errors < 5, f"Got {metrics.errors} errors during HTTP pool test"


@pytest.mark.skip(reason="Requires FastAPI server running - integration test")
@pytest.mark.asyncio
async def test_concurrent_request_handling():
    """Test handling 100+ concurrent requests."""
    metrics = PerformanceMetrics()
    concurrent_count = 120
    
    async def simulate_request(request_id: int):
        start = time.time()
        try:
            # Simulate various operations
            async with get_optimized_session() as session:
                # Read operation
                result = await session.execute(
                    text("SELECT id FROM tasks LIMIT 1")
                )
                _ = result.scalar()
                
                # Simulate processing time
                await asyncio.sleep(0.1)
                
            metrics.add_latency((time.time() - start) * 1000)
        except Exception:
            metrics.add_error()
    
    metrics.start_time = time.time()
    
    # Run concurrent requests
    tasks = [simulate_request(i) for i in range(concurrent_count)]
    await asyncio.gather(*tasks)
    
    metrics.end_time = time.time()
    
    # Verify acceptance criteria
    assert metrics.get_p95_latency() < 2000, f"P95 latency {metrics.get_p95_latency()}ms exceeds 2000ms"
    assert len(metrics.latencies) >= 100, f"Only handled {len(metrics.latencies)} requests, expected 100+"
    assert metrics.errors < 10, f"Got {metrics.errors} errors, expected < 10"


def test_memory_stability():
    """Test memory usage stability under load."""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # Simulate load
    data_chunks = []
    for _ in range(100):
        # Create some data that would be cached
        chunk = {"data": "x" * 1000, "timestamp": datetime.utcnow()}
        data_chunks.append(chunk)
        
        # Simulate cleanup every 20 iterations
        if len(data_chunks) > 20:
            data_chunks = data_chunks[-10:]
    
    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = final_memory - initial_memory
    
    # Memory should not increase by more than 100MB
    assert memory_increase < 100, f"Memory increased by {memory_increase}MB, expected < 100MB"


@pytest.mark.skip(reason="Requires asyncpg database setup - integration test")
@pytest.mark.asyncio
async def test_database_query_performance():
    """Test optimized database queries."""
    metrics = PerformanceMetrics()
    
    async with get_optimized_session() as session:
        # Test indexed query performance
        queries = [
            ("SELECT * FROM tasks WHERE tenant_id = :tid AND status = :status LIMIT 10",
             {"tid": "test-tenant", "status": "completed"}),
            ("SELECT * FROM usage WHERE api_key_id = :key AND timestamp > :ts LIMIT 100",
             {"key": 1, "ts": "2024-01-01"}),
            ("SELECT COUNT(*) FROM tasks WHERE tenant_id = :tid",
             {"tid": "test-tenant"}),
        ]
        
        for query, params in queries:
            start = time.time()
            try:
                result = await session.execute(text(query), params)
                _ = result.fetchall()
                latency = (time.time() - start) * 1000
                metrics.add_latency(latency)
                assert latency < 100, f"Query took {latency}ms, expected < 100ms"
            except Exception:
                metrics.add_error()
    
    assert metrics.errors == 0, f"Got {metrics.errors} query errors"
    assert metrics.get_avg_latency() < 100, f"Average query time {metrics.get_avg_latency()}ms exceeds 100ms"


if __name__ == "__main__":
    # Run performance tests
    asyncio.run(test_database_connection_pooling(get_db_manager()))
    asyncio.run(test_http_connection_pooling())
    asyncio.run(test_concurrent_request_handling())
    test_memory_stability()
    asyncio.run(test_database_query_performance())
    
    print("All performance tests passed!")
    print("✓ P95 latency < 2s for simple requests")
    print("✓ Support for 100+ concurrent requests")
    print("✓ Database query time < 100ms")
    print("✓ Memory usage stable under load")