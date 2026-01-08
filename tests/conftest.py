"""Global test configuration and fixtures."""

import os
import tempfile
import threading
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Automatically setup proper test environment for all tests."""
    # Ensure TESTING environment is always set
    with patch.dict(os.environ, {
        "TESTING": "1",
        "LLM_PROVIDER": "mock",
        "REDIS_URL": "redis://localhost:6379/0",
        "DATABASE_URL": "sqlite:///test.db",
        "CI": "true"
    }):
        yield


@pytest.fixture(autouse=True)
def limit_thread_pool():
    """Limit thread pool size to prevent exhaustion in tests."""
    import concurrent.futures
    
    # Patch ThreadPoolExecutor to use smaller pool
    original_executor = concurrent.futures.ThreadPoolExecutor
    
    def limited_executor(*args, **kwargs):
        kwargs.setdefault('max_workers', 2)
        return original_executor(*args, **kwargs)
    
    with patch('concurrent.futures.ThreadPoolExecutor', limited_executor):
        yield


@pytest.fixture(autouse=True)
def clean_temp_directories():
    """Clean up temporary directories after each test."""
    yield
    # Clean up any lingering temp files
    import tempfile
    import shutil
    import glob
    
    # Clean up temp directories that might be left behind
    temp_patterns = [
        '/tmp/tmp*',
        '/tmp/hydra*',
        '/tmp/test*'
    ]
    
    for pattern in temp_patterns:
        for path in glob.glob(pattern):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.isfile(path):
                    os.unlink(path)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors


@pytest.fixture
def isolated_tempdir():
    """Provide an isolated temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(autouse=True)
def limit_async_tasks():
    """Limit asyncio tasks to prevent resource exhaustion."""
    import asyncio
    
    # Set a reasonable task limit
    try:
        loop = asyncio.get_running_loop()
        # Limit concurrent tasks
        semaphore = asyncio.Semaphore(10)
        
        original_create_task = loop.create_task
        
        async def limited_create_task(coro, **kwargs):
            async with semaphore:
                return await original_create_task(coro, **kwargs)
        
        loop.create_task = limited_create_task
        yield
        loop.create_task = original_create_task
    except RuntimeError:
        # No event loop running
        yield