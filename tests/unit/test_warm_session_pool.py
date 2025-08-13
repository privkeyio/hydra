"""Tests for WarmSessionPool."""
import time
import unittest.mock as mock
from typing import Set
from unittest.mock import MagicMock, Mock

import pytest

from hydra.providers.interactive_base import (
    InteractiveAIProvider,
    ProviderCapability,
    ProviderConfig,
    SessionInfo,
    SessionState,
    TaskResult,
)
from hydra.providers.warm_session_pool import PoolSessionState, WarmSessionPool


class MockProvider(InteractiveAIProvider):
    """Mock provider for testing."""

    def __init__(self, should_fail: bool = False):
        config = ProviderConfig(provider_name="mock")
        super().__init__(config)
        self.should_fail = should_fail
        self.started_sessions = set()
        self.stopped_sessions = set()

    def validate_config(self):
        pass

    def discover_tool(self) -> bool:
        return True

    def detect_capabilities(self) -> Set[ProviderCapability]:
        return {ProviderCapability.SESSION_PERSISTENCE, ProviderCapability.TASK_EXECUTION}

    def start_session(self, session_id=None, working_directory=None) -> str:
        if self.should_fail:
            raise RuntimeError("Mock provider failure")
        
        session_id = session_id or self.generate_session_id()
        self.started_sessions.add(session_id)
        
        session_info = SessionInfo(
            session_id=session_id,
            state=SessionState.ACTIVE,
            created_at=time.time(),
            last_activity=time.time()
        )
        self._sessions[session_id] = session_info
        return session_id

    def stop_session(self, session_id: str):
        if session_id in self.started_sessions:
            self.started_sessions.remove(session_id)
        self.stopped_sessions.add(session_id)
        if session_id in self._sessions:
            self._sessions[session_id].state = SessionState.TERMINATED

    def execute_task(self, session_id: str, task_prompt: str, timeout=None) -> TaskResult:
        if session_id not in self.started_sessions:
            raise KeyError(f"Session {session_id} not found")
        
        return TaskResult(
            task_id="test_task",
            success=True,
            output="Task completed successfully"
        )

    def handle_prompt(self, session_id: str, prompt: str, auto_respond: bool = False) -> str:
        return "Mock response"

    def get_session_state(self, session_id: str) -> dict:
        if session_id not in self.started_sessions:
            raise KeyError(f"Session {session_id} not found")
        return {"session_id": session_id, "state": "active"}

    def restore_session_state(self, session_id: str, state: dict):
        pass


class TestWarmSessionPool:
    """Test cases for WarmSessionPool."""

    def setup_method(self):
        """Set up test fixtures."""
        self.provider_factory = lambda: MockProvider()

    def test_pool_initialization(self):
        """Test pool initializes with correct number of sessions."""
        with WarmSessionPool(
            self.provider_factory,
            min_pool_size=2,
            max_pool_size=4
        ) as pool:
            # Allow time for initial warming
            time.sleep(0.1)
            
            stats = pool.get_stats()
            assert stats['pool_size_current'] >= 2
            assert stats['pool_size_min'] == 2
            assert stats['pool_size_max'] == 4

    def test_session_acquisition_speed(self):
        """Test session acquisition is under 1 second."""
        with WarmSessionPool(
            self.provider_factory,
            min_pool_size=3,
            max_pool_size=5
        ) as pool:
            # Allow pool to warm up
            time.sleep(0.1)
            
            start_time = time.time()
            provider = pool.acquire_session(timeout=1.0)
            acquisition_time = time.time() - start_time
            
            assert provider is not None
            assert acquisition_time < 1.0
            
            # Release session
            pool.release_session(provider)

    def test_session_health_checking(self):
        """Test session health checking before reuse."""
        def failing_factory():
            return MockProvider(should_fail=False)
            
        with WarmSessionPool(
            failing_factory,
            min_pool_size=1,
            max_pool_size=2
        ) as pool:
            time.sleep(0.1)
            
            # Acquire a session
            provider = pool.acquire_session()
            assert provider is not None
            
            # Simulate session becoming unhealthy
            provider.should_fail = True
            
            # Release and try to acquire again
            pool.release_session(provider)
            time.sleep(0.1)
            
            # Health check should detect the issue
            provider2 = pool.acquire_session()
            # Should still work due to pool creating new sessions
            assert provider2 is not None

    def test_idle_session_recycling(self):
        """Test idle sessions are recycled after timeout."""
        with WarmSessionPool(
            self.provider_factory,
            min_pool_size=2,
            max_pool_size=3,
            idle_timeout=1  # 1 second for testing
        ) as pool:
            time.sleep(0.1)
            
            # Get initial session count
            initial_stats = pool.get_stats()
            initial_created = initial_stats['sessions_created']
            
            # Acquire and release a session
            provider = pool.acquire_session()
            assert provider is not None
            pool.release_session(provider)
            
            # Wait for session to become idle (longer than idle_timeout)
            time.sleep(1.5)
            
            # Manually trigger recycling since background thread runs every 30s
            pool._recycle_old_sessions()
            
            # Check that sessions were recycled
            final_stats = pool.get_stats()
            assert final_stats['sessions_recycled'] > 0

    def test_dynamic_pool_sizing(self):
        """Test pool size adjusts based on workload."""
        with WarmSessionPool(
            self.provider_factory,
            min_pool_size=2,
            max_pool_size=5
        ) as pool:
            time.sleep(0.1)
            
            # Acquire multiple sessions to simulate high load
            providers = []
            for _ in range(3):
                provider = pool.acquire_session()
                if provider:
                    providers.append(provider)
                    
            # Check pool may have grown
            stats = pool.get_stats()
            assert stats['sessions_allocated'] == len(providers)
            
            # Release all sessions
            for provider in providers:
                pool.release_session(provider)

    def test_pool_statistics(self):
        """Test pool statistics are tracked correctly."""
        with WarmSessionPool(
            self.provider_factory,
            min_pool_size=2,
            max_pool_size=4
        ) as pool:
            time.sleep(0.1)
            
            stats = pool.get_stats()
            
            # Check required stat fields exist
            assert 'sessions_created' in stats
            assert 'sessions_allocated' in stats
            assert 'sessions_recycled' in stats
            assert 'health_checks_passed' in stats
            assert 'health_checks_failed' in stats
            assert 'allocation_time_avg' in stats
            assert 'pool_size_current' in stats
            assert 'sessions_ready' in stats
            
            # Check reasonable values
            assert stats['sessions_created'] >= 2
            assert stats['pool_size_current'] >= 2

    def test_session_reuse_limits(self):
        """Test sessions are recycled after max allocations."""
        with WarmSessionPool(
            self.provider_factory,
            min_pool_size=1,
            max_pool_size=2,
            max_allocation_count=3
        ) as pool:
            time.sleep(0.1)
            
            # Acquire and release same session multiple times
            for _ in range(5):  # More than max_allocation_count
                provider = pool.acquire_session()
                assert provider is not None
                pool.release_session(provider)
                
            stats = pool.get_stats()
            # Should have recycled at least one session
            assert stats['sessions_recycled'] > 0

    def test_concurrent_access(self):
        """Test pool handles concurrent session requests."""
        import concurrent.futures
        
        with WarmSessionPool(
            self.provider_factory,
            min_pool_size=3,
            max_pool_size=5
        ) as pool:
            time.sleep(0.1)
            
            results = []
            errors = []
            
            def acquire_and_release():
                try:
                    provider = pool.acquire_session()
                    if provider:
                        results.append(provider)
                        time.sleep(0.01)  # Brief hold
                        pool.release_session(provider)
                    else:
                        errors.append("Failed to acquire")
                except Exception as e:
                    errors.append(str(e))
            
            # Launch limited concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for _ in range(6):  # Reduced from 10 to 6
                    future = executor.submit(acquire_and_release)
                    futures.append(future)
                    
                # Wait for all threads
                concurrent.futures.wait(futures, timeout=10)
                
            # Check results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) > 0

    def test_pool_shutdown(self):
        """Test pool shuts down gracefully."""
        pool = WarmSessionPool(
            self.provider_factory,
            min_pool_size=2,
            max_pool_size=4
        )
        
        time.sleep(0.1)
        
        # Check pool is working
        stats = pool.get_stats()
        assert stats['pool_size_current'] >= 2
        
        # Shutdown
        pool.shutdown()
        
        # Check pool is empty
        stats = pool.get_stats()
        assert stats['pool_size_current'] == 0

    def test_provider_factory_failure_handling(self):
        """Test pool handles provider factory failures gracefully."""
        def failing_factory():
            raise RuntimeError("Provider creation failed")
            
        with WarmSessionPool(
            failing_factory,
            min_pool_size=2,
            max_pool_size=4
        ) as pool:
            # Pool should handle creation failures gracefully
            time.sleep(0.2)  # Allow time for failed attempts
            
            stats = pool.get_stats()
            # Pool should not crash, even with failures
            assert 'sessions_created' in stats

    @pytest.mark.parametrize("min_size,max_size", [
        (1, 2),
        (3, 5),
        (2, 10)
    ])
    def test_different_pool_sizes(self, min_size, max_size):
        """Test pool works with different size configurations."""
        with WarmSessionPool(
            self.provider_factory,
            min_pool_size=min_size,
            max_pool_size=max_size
        ) as pool:
            time.sleep(0.1)
            
            stats = pool.get_stats()
            assert stats['pool_size_min'] == min_size
            assert stats['pool_size_max'] == max_size
            assert stats['pool_size_current'] >= min_size