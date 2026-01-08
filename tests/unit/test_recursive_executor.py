"""Unit tests for recursive executor with intelligent loop protection."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra.workflow.recursive_executor import (
    CircuitBreaker,
    ExecutionAttempt,
    ExecutionHistory,
    ExecutionState,
    RecursiveExecutor,
    execute_with_retry,
)


class TestExecutionAttempt:
    """Test ExecutionAttempt dataclass."""
    
    def test_attempt_creation(self):
        """Test creating execution attempt."""
        attempt = ExecutionAttempt(
            attempt_number=1,
            start_time=datetime.now()
        )
        assert attempt.attempt_number == 1
        assert attempt.state == ExecutionState.PENDING
        assert attempt.end_time is None
        assert attempt.failure_reason is None
    
    def test_attempt_completion(self):
        """Test completing execution attempt."""
        attempt = ExecutionAttempt(
            attempt_number=1,
            start_time=datetime.now()
        )
        
        attempt.complete(
            ExecutionState.SUCCESS,
            verification_result={"passed": True}
        )
        
        assert attempt.state == ExecutionState.SUCCESS
        assert attempt.end_time is not None
        assert attempt.duration_seconds > 0
        assert attempt.verification_result == {"passed": True}
    
    def test_failed_attempt(self):
        """Test failed execution attempt."""
        attempt = ExecutionAttempt(
            attempt_number=2,
            start_time=datetime.now()
        )
        
        attempt.complete(
            ExecutionState.FAILED,
            failure_reason="Test failed",
            verification_result={"passed": False, "reason": "Test failed"}
        )
        
        assert attempt.state == ExecutionState.FAILED
        assert attempt.failure_reason == "Test failed"
        assert not attempt.verification_result["passed"]


class TestExecutionHistory:
    """Test ExecutionHistory tracking."""
    
    def test_history_creation(self):
        """Test creating execution history."""
        history = ExecutionHistory(ticket_id="TEST-001")
        assert history.ticket_id == "TEST-001"
        assert len(history.attempts) == 0
        assert history.consecutive_failures == 0
        assert history.total_success == 0
        assert history.total_failures == 0
    
    def test_add_successful_attempt(self):
        """Test adding successful attempt."""
        history = ExecutionHistory(ticket_id="TEST-001")
        
        attempt = ExecutionAttempt(1, datetime.now())
        attempt.complete(ExecutionState.SUCCESS)
        history.add_attempt(attempt)
        
        assert len(history.attempts) == 1
        assert history.total_success == 1
        assert history.total_failures == 0
        assert history.consecutive_failures == 0
    
    def test_add_failed_attempts(self):
        """Test adding failed attempts."""
        history = ExecutionHistory(ticket_id="TEST-001")
        
        # Add two failures
        for i in range(2):
            attempt = ExecutionAttempt(i + 1, datetime.now())
            attempt.complete(ExecutionState.FAILED, f"Failure {i + 1}")
            history.add_attempt(attempt)
        
        assert len(history.attempts) == 2
        assert history.total_failures == 2
        assert history.consecutive_failures == 2
        assert history.total_success == 0
        
        # Add success - should reset consecutive failures
        success_attempt = ExecutionAttempt(3, datetime.now())
        success_attempt.complete(ExecutionState.SUCCESS)
        history.add_attempt(success_attempt)
        
        assert history.consecutive_failures == 0
        assert history.total_success == 1
    
    def test_get_failure_patterns(self):
        """Test extracting failure patterns."""
        history = ExecutionHistory(ticket_id="TEST-001")
        
        patterns = ["Test failure", "Import error", "Syntax error"]
        for i, pattern in enumerate(patterns):
            attempt = ExecutionAttempt(i + 1, datetime.now())
            attempt.complete(ExecutionState.FAILED, pattern)
            history.add_attempt(attempt)
        
        extracted = history.get_failure_patterns()
        assert extracted == patterns
    
    def test_get_last_failure_context(self):
        """Test getting last failure context."""
        history = ExecutionHistory(ticket_id="TEST-001")
        
        # Add attempt with context
        attempt1 = ExecutionAttempt(1, datetime.now())
        attempt1.failure_context = {"error": "first"}
        history.add_attempt(attempt1)
        
        # Add another with different context
        attempt2 = ExecutionAttempt(2, datetime.now())
        attempt2.failure_context = {"error": "second"}
        history.add_attempt(attempt2)
        
        # Last context should be from attempt2
        context = history.get_last_failure_context()
        assert context == {"error": "second"}


class TestCircuitBreaker:
    """Test CircuitBreaker pattern."""
    
    def test_circuit_breaker_creation(self):
        """Test creating circuit breaker."""
        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.failure_threshold == 3
        assert breaker.failure_count == 0
        assert not breaker.is_open
        assert breaker.can_execute()
    
    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit breaker opens after threshold."""
        breaker = CircuitBreaker(failure_threshold=3)
        
        # Record failures up to threshold
        for _ in range(3):
            breaker.record_failure()
        
        assert breaker.is_open
        assert not breaker.can_execute()
        assert breaker.failure_count == 3
    
    def test_circuit_breaker_resets_on_success(self):
        """Test circuit breaker resets on success."""
        breaker = CircuitBreaker(failure_threshold=2)
        
        # Record one failure
        breaker.record_failure()
        assert not breaker.is_open
        
        # Record success - should reset
        breaker.record_success()
        assert breaker.failure_count == 0
        assert not breaker.is_open
        assert breaker.can_execute()
    
    def test_circuit_breaker_timeout_reset(self):
        """Test circuit breaker resets after timeout."""
        breaker = CircuitBreaker(failure_threshold=1, reset_timeout=0.1)
        
        # Open the breaker
        breaker.record_failure()
        assert breaker.is_open
        assert not breaker.can_execute()
        
        # Wait for timeout
        import time
        time.sleep(0.2)
        
        # Should be able to execute again
        assert breaker.can_execute()


class TestRecursiveExecutor:
    """Test RecursiveExecutor main functionality."""
    
    def test_executor_creation(self):
        """Test creating recursive executor."""
        executor = RecursiveExecutor(max_retries=4)
        assert executor.max_retries == 4
        assert executor.base_backoff == 1.0
        assert executor.enable_learning
        assert executor.enable_metrics
    
    def test_max_retries_limit(self):
        """Test max retries is capped at 5."""
        executor = RecursiveExecutor(max_retries=10)
        assert executor.max_retries == 5  # Should be capped
    
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff calculation."""
        executor = RecursiveExecutor(base_backoff=2.0)
        
        assert executor.get_exponential_backoff(0) == 2.0  # 2 * 2^0
        assert executor.get_exponential_backoff(1) == 4.0  # 2 * 2^1
        assert executor.get_exponential_backoff(2) == 8.0  # 2 * 2^2
        assert executor.get_exponential_backoff(3) == 16.0  # 2 * 2^3
    
    def test_workspace_state_persistence(self):
        """Test saving and loading workspace state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = RecursiveExecutor(workspace_dir=Path(tmpdir))
            
            # Save state
            state = {"status": "in_progress", "data": {"key": "value"}}
            executor.save_workspace_state("TEST-001", state)
            
            # Load state
            loaded = executor.load_workspace_state("TEST-001")
            assert loaded == state
            
            # Non-existent ticket
            assert executor.load_workspace_state("TEST-999") is None
    
    def test_analyze_failure_patterns(self):
        """Test failure pattern analysis."""
        executor = RecursiveExecutor()
        history = ExecutionHistory(ticket_id="TEST-001")
        
        # Add various failure attempts
        failures = [
            "Test test_function failed",
            "ImportError: cannot import module",
            "Test coverage too low",
            "Timeout exceeded",
            "SyntaxError in file.py"
        ]
        
        for i, failure in enumerate(failures):
            attempt = ExecutionAttempt(i + 1, datetime.now())
            attempt.complete(ExecutionState.FAILED, failure)
            history.add_attempt(attempt)
        
        analysis = executor.analyze_failure_patterns(history)
        
        assert "test_failures" in analysis["common_failures"]
        assert "import_errors" in analysis["common_failures"]
        assert "syntax_errors" in analysis["common_failures"]
        assert "timeouts" in analysis["common_failures"]
        assert len(analysis["suggestions"]) > 0
        assert analysis["risk_level"] == "high"  # Due to consecutive failures
    
    def test_inject_failure_context(self):
        """Test injecting failure context into ticket."""
        executor = RecursiveExecutor()
        history = ExecutionHistory(ticket_id="TEST-001")
        
        # Add failed attempt with context
        attempt = ExecutionAttempt(1, datetime.now())
        attempt.failure_reason = "Test failed"
        attempt.failure_context = {"test": "context"}
        history.add_attempt(attempt)
        
        # Original ticket
        ticket = {"id": "TEST-001", "title": "Test ticket"}
        
        # Inject context
        enhanced = executor.inject_failure_context(ticket, history)
        
        assert "execution_context" in enhanced
        assert enhanced["execution_context"]["retry_attempt"] == 2
        assert "Test failed" in enhanced["execution_context"]["previous_failures"]
        assert enhanced["execution_context"]["last_failure_context"] == {"test": "context"}
    
    def test_successful_execution_first_attempt(self):
        """Test successful execution on first attempt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = RecursiveExecutor(workspace_dir=Path(tmpdir))
            
            # Mock ticket parsing and execution
            with patch('hydra.workflow.recursive_executor.parse_ticket') as mock_parse:
                mock_parse.return_value = {"id": "TEST-001", "title": "Test"}
                
                with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
                    mock_exec.return_value = True
                    
                    result = executor.execute_with_retry(
                        "tickets.yaml",
                        "TEST-001",
                        provider=None
                    )
                    
                    assert result.get("success", False)
    
    def test_retry_after_failure(self):
        """Test retry after initial failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = RecursiveExecutor(
                workspace_dir=Path(tmpdir),
                max_retries=3,
                base_backoff=0.01  # Short backoff for testing
            )
            
            with patch('hydra.workflow.recursive_executor.parse_ticket') as mock_parse:
                mock_parse.return_value = {"id": "TEST-001", "title": "Test"}
                
                with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
                    # Fail first, succeed second
                    mock_exec.side_effect = [False, True]
                    
                    result = executor.execute_with_retry(
                        "tickets.yaml",
                        "TEST-001",
                        provider=None
                    )
                    
                    assert result.get("success", False)
    
    def test_max_retries_exceeded(self):
        """Test max retries exceeded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = RecursiveExecutor(
                workspace_dir=Path(tmpdir),
                max_retries=2,
                base_backoff=0.01
            )
            
            with patch('hydra.workflow.recursive_executor.parse_ticket') as mock_parse:
                mock_parse.return_value = {"id": "TEST-001", "title": "Test"}
                
                with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
                    # Always fail
                    mock_exec.return_value = False
                    
                    with patch.object(executor, '_verify_ticket') as mock_verify:
                        # Make verification fail to simulate max retries 
                        mock_verify.return_value = {"success": False, "score": 0.0}
                        
                        result = executor.execute_with_retry(
                            "tickets.yaml",
                            "TEST-001",
                            provider=None
                        )
                        
                        assert not result.get("success", True)
    
    def test_circuit_breaker_activation(self):
        """Test circuit breaker stops execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = RecursiveExecutor(
                workspace_dir=Path(tmpdir),
                max_retries=5,
                base_backoff=0.01
            )
            
            # Pre-open circuit breaker
            ticket_id = "TEST-001"
            executor.circuit_breakers[ticket_id] = CircuitBreaker(failure_threshold=1)
            executor.circuit_breakers[ticket_id].record_failure()  # Open it
            
            with patch('hydra.workflow.recursive_executor.parse_ticket') as mock_parse:
                mock_parse.return_value = {"id": ticket_id, "title": "Test"}
                
                with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
                    result = executor.execute_with_retry(
                        "tickets.yaml",
                        ticket_id,
                        provider=None
                    )
                    
                    assert not result.get("success", True)
                    # Should not have tried execution due to circuit breaker
                    mock_exec.assert_not_called()
    
    def test_verification_integration(self):
        """Test integration with verification engine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = RecursiveExecutor(
                workspace_dir=Path(tmpdir),
                base_backoff=0.01
            )
            
            with patch('hydra.workflow.recursive_executor.parse_ticket') as mock_parse:
                mock_parse.return_value = {"id": "TEST-001", "title": "Test"}
                
                with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
                    mock_exec.return_value = True
                    
                    result = executor.execute_with_retry(
                        "tickets.yaml",
                        "TEST-001",
                        provider=None
                    )
                    
                    # Should complete successfully in test mode
                    assert result.get("success", False)
    
    def test_metrics_tracking(self):
        """Test metrics tracking functionality."""
        executor = RecursiveExecutor(enable_metrics=True)
        
        # Simulate some executions
        history1 = ExecutionHistory(ticket_id="TEST-001")
        attempt1 = ExecutionAttempt(1, datetime.now())
        attempt1.complete(ExecutionState.SUCCESS)
        history1.add_attempt(attempt1)
        executor._update_metrics(history1)
        
        history2 = ExecutionHistory(ticket_id="TEST-002")
        attempt2 = ExecutionAttempt(1, datetime.now())
        attempt2.complete(ExecutionState.FAILED)
        history2.add_attempt(attempt2)
        attempt3 = ExecutionAttempt(2, datetime.now())
        attempt3.complete(ExecutionState.SUCCESS)
        history2.add_attempt(attempt3)
        history2.total_success = 1
        executor.metrics["total_executions"] = 2
        executor._update_metrics(history2)
        
        metrics = executor.get_metrics()
        assert metrics["total_executions"] == 2
        assert metrics["average_retry_count"] > 1
    
    def test_synchronous_wrapper(self):
        """Test synchronous execution wrapper."""
        import os
        from unittest.mock import patch
        
        # Ensure TEST_MODE is set to avoid threading issues
        with patch.dict(os.environ, {"TESTING": "1"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                with patch('hydra.workflow.recursive_executor.parse_ticket') as mock_parse:
                    mock_parse.return_value = {"id": "TEST-001", "title": "Test"}
                    
                    with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
                        mock_exec.return_value = True
                        
                        success, result = execute_with_retry(
                            "tickets.yaml",
                            "TEST-001",
                            max_retries=2
                        )
                        
                        assert success
                        assert result["success"]
                        assert "metrics" in result
                        assert "history" in result