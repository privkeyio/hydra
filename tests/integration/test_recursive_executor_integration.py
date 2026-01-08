"""Integration tests for recursive executor with real ticket scenarios."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from hydra.workflow.recursive_executor import (
    ExecutionState,
    RecursiveExecutor,
    execute_with_retry,
)


class TestRecursiveExecutorIntegration:
    """Integration tests for recursive executor."""
    
    @pytest.fixture
    def failing_tickets_yaml(self, tmp_path):
        """Create tickets file with intentionally failing tickets."""
        tickets_data = {
            "version": "1.0",
            "project": {
                "name": "Test Project",
                "description": "Testing recursive execution",
                "created_at": datetime.now().isoformat(),
                "path": str(tmp_path)
            },
            "tickets": [
                {
                    "id": "FAIL-001",
                    "title": "Always Failing Ticket",
                    "status": "TODO",
                    "priority": 1,
                    "model": "fast",
                    "description": "This ticket always fails verification",
                    "acceptance_criteria": [
                        "Implement function that returns wrong value",
                        "Write tests that always fail",
                        "Missing required documentation"
                    ],
                    "dependencies": []
                },
                {
                    "id": "FAIL-002",
                    "title": "Flaky Ticket",
                    "status": "TODO",
                    "priority": 2,
                    "model": "fast",
                    "description": "This ticket fails first 2 attempts then succeeds",
                    "acceptance_criteria": [
                        "Implement function with random behavior",
                        "Tests pass only on third attempt"
                    ],
                    "dependencies": []
                },
                {
                    "id": "TIMEOUT-001",
                    "title": "Timeout Ticket",
                    "status": "TODO",
                    "priority": 3,
                    "model": "fast",
                    "description": "This ticket times out",
                    "acceptance_criteria": [
                        "Implement infinite loop",
                        "Never completes execution"
                    ],
                    "dependencies": []
                },
                {
                    "id": "SUCCESS-001",
                    "title": "Always Succeeding Ticket",
                    "status": "TODO",
                    "priority": 4,
                    "model": "fast",
                    "description": "This ticket always succeeds",
                    "acceptance_criteria": [
                        "Implement correct function",
                        "All tests pass",
                        "Documentation complete"
                    ],
                    "dependencies": []
                }
            ]
        }
        
        tickets_file = tmp_path / "failing_tickets.yaml"
        with open(tickets_file, 'w') as f:
            yaml.dump(tickets_data, f)
        
        return tickets_file
    
    @pytest.fixture
    def mock_ticket_executor(self):
        """Mock ticket executor with configurable behavior."""
        class MockExecutor:
            def __init__(self):
                self.call_count = {}
                self.behaviors = {}
            
            def set_behavior(self, ticket_id, behavior):
                """Set execution behavior for ticket."""
                self.behaviors[ticket_id] = behavior
                self.call_count[ticket_id] = 0
            
            def execute(self, tickets_file, ticket_id, provider=None):
                """Execute ticket with configured behavior."""
                self.call_count[ticket_id] = self.call_count.get(ticket_id, 0) + 1
                behavior = self.behaviors.get(ticket_id, "success")
                
                if behavior == "always_fail":
                    return {"success": False, "error": "Always fails"}
                elif behavior == "flaky":
                    # Succeed on third attempt
                    if self.call_count[ticket_id] >= 3:
                        return {"success": True}
                    return {"success": False, "error": f"Attempt {self.call_count[ticket_id]} failed"}
                elif behavior == "timeout":
                    raise TimeoutError("Execution timeout")
                else:
                    return {"success": True}
        
        return MockExecutor()
    
    @pytest.fixture
    def mock_verification_engine(self):
        """Mock verification engine with configurable results."""
        class MockVerifier:
            def __init__(self):
                self.call_count = {}
                self.results = {}
            
            def set_result(self, ticket_id, result):
                """Set verification result for ticket."""
                self.results[ticket_id] = result
                self.call_count[ticket_id] = 0
            
            def verify_ticket(self, ticket_id, ticket_data, **kwargs):
                """Verify ticket with configured result."""
                self.call_count[ticket_id] = self.call_count.get(ticket_id, 0) + 1
                
                if ticket_id in self.results:
                    result = self.results[ticket_id]
                    if callable(result):
                        return result(self.call_count[ticket_id])
                    return result
                
                return {"passed": True}
        
        return MockVerifier()
    
    @pytest.mark.asyncio
    async def test_always_failing_ticket(self, failing_tickets_yaml, mock_ticket_executor, tmp_path):
        """Test ticket that always fails reaches max retries."""
        executor = RecursiveExecutor(
            max_retries=3,
            base_backoff=0.01,
            workspace_dir=tmp_path / "workspace"
        )
        
        # Configure mock to always fail
        mock_ticket_executor.set_behavior("FAIL-001", "always_fail")
        
        with patch('hydra.workflow.recursive_executor.execute_single_ticket', mock_ticket_executor.execute):
            success, history = await executor.execute_with_retry(
                str(failing_tickets_yaml),
                "FAIL-001"
            )
            
            assert not success
            assert len(history.attempts) == 4  # 3 retries + circuit broken
            assert history.attempts[-1].state == ExecutionState.CIRCUIT_BROKEN
            assert history.consecutive_failures == 4
            assert mock_ticket_executor.call_count["FAIL-001"] == 3
    
    @pytest.mark.asyncio
    async def test_flaky_ticket_succeeds_on_retry(self, failing_tickets_yaml, mock_ticket_executor, tmp_path):
        """Test flaky ticket that succeeds after retries."""
        executor = RecursiveExecutor(
            max_retries=3,
            base_backoff=0.01,
            workspace_dir=tmp_path / "workspace"
        )
        
        # Configure mock to be flaky
        mock_ticket_executor.set_behavior("FAIL-002", "flaky")
        
        with patch('hydra.workflow.recursive_executor.execute_single_ticket', mock_ticket_executor.execute):
            success, history = await executor.execute_with_retry(
                str(failing_tickets_yaml),
                "FAIL-002"
            )
            
            assert success
            assert len(history.attempts) == 3  # Failed twice, succeeded on third
            assert history.attempts[0].state == ExecutionState.FAILED
            assert history.attempts[1].state == ExecutionState.FAILED
            assert history.attempts[2].state == ExecutionState.SUCCESS
            assert history.total_success == 1
            assert mock_ticket_executor.call_count["FAIL-002"] == 3
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, failing_tickets_yaml, mock_ticket_executor, tmp_path):
        """Test handling of timeout errors."""
        executor = RecursiveExecutor(
            max_retries=2,
            base_backoff=0.01,
            workspace_dir=tmp_path / "workspace"
        )
        
        # Configure mock to timeout
        mock_ticket_executor.set_behavior("TIMEOUT-001", "timeout")
        
        with patch('hydra.workflow.recursive_executor.execute_single_ticket', mock_ticket_executor.execute):
            success, history = await executor.execute_with_retry(
                str(failing_tickets_yaml),
                "TIMEOUT-001"
            )
            
            assert not success
            # Should have tried twice before giving up
            assert mock_ticket_executor.call_count["TIMEOUT-001"] == 2
            assert all("timeout" in str(a.failure_reason).lower() 
                      for a in history.attempts if a.failure_reason)
    
    @pytest.mark.asyncio
    async def test_successful_ticket_no_retry(self, failing_tickets_yaml, mock_ticket_executor, tmp_path):
        """Test successful ticket doesn't retry."""
        executor = RecursiveExecutor(
            max_retries=3,
            base_backoff=0.01,
            workspace_dir=tmp_path / "workspace"
        )
        
        # Configure mock to succeed
        mock_ticket_executor.set_behavior("SUCCESS-001", "success")
        
        with patch('hydra.workflow.recursive_executor.execute_single_ticket', mock_ticket_executor.execute):
            success, history = await executor.execute_with_retry(
                str(failing_tickets_yaml),
                "SUCCESS-001"
            )
            
            assert success
            assert len(history.attempts) == 1
            assert history.attempts[0].state == ExecutionState.SUCCESS
            assert mock_ticket_executor.call_count["SUCCESS-001"] == 1
    
    @pytest.mark.asyncio
    async def test_verification_failure_triggers_retry(self, failing_tickets_yaml, mock_verification_engine, tmp_path):
        """Test verification failure triggers retry."""
        executor = RecursiveExecutor(
            max_retries=3,
            base_backoff=0.01,
            workspace_dir=tmp_path / "workspace"
        )
        
        # Configure verification to fail first time, pass second
        def verification_result(call_count):
            if call_count == 1:
                return {
                    "passed": False,
                    "reason": "Tests failed",
                    "failures": {"test_function": "AssertionError"}
                }
            return {"passed": True}
        
        mock_verification_engine.set_result("SUCCESS-001", verification_result)
        
        with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
            mock_exec.return_value = {"success": True}
            
            with patch('hydra.workflow.recursive_executor.VerificationEngine') as mock_verifier_class:
                mock_verifier_class.return_value.verify_ticket = mock_verification_engine.verify_ticket
                
                success, history = await executor.execute_with_retry(
                    str(failing_tickets_yaml),
                    "SUCCESS-001",
                    verification_config={"strict": True}
                )
                
                assert success
                assert len(history.attempts) == 2
                assert history.attempts[0].state == ExecutionState.FAILED
                assert history.attempts[0].failure_reason == "Tests failed"
                assert history.attempts[1].state == ExecutionState.SUCCESS
    
    @pytest.mark.asyncio
    async def test_state_preservation_across_retries(self, failing_tickets_yaml, tmp_path):
        """Test state preservation between retry attempts."""
        workspace_dir = tmp_path / "workspace"
        executor = RecursiveExecutor(
            max_retries=2,
            base_backoff=0.01,
            workspace_dir=workspace_dir
        )
        
        attempt_states = []
        
        def mock_execute(tickets_file, ticket_id, provider=None):
            """Track state loading across attempts."""
            state = executor.load_workspace_state(ticket_id)
            attempt_states.append(state)
            
            if len(attempt_states) == 1:
                # First attempt fails
                return {"success": False}
            else:
                # Second attempt succeeds
                return {"success": True}
        
        with patch('hydra.workflow.recursive_executor.execute_single_ticket', mock_execute):
            success, history = await executor.execute_with_retry(
                str(failing_tickets_yaml),
                "FAIL-001"
            )
            
            assert success
            assert len(attempt_states) == 2
            # First attempt should have no state
            assert attempt_states[0] is None
            # Second attempt should have failure state
            assert attempt_states[1] is not None
            assert attempt_states[1]["status"] == "failed"
            assert attempt_states[1]["attempt"] == 1
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_execution(self, failing_tickets_yaml, tmp_path):
        """Test circuit breaker prevents repeated failures."""
        executor = RecursiveExecutor(
            max_retries=5,
            base_backoff=0.01,
            workspace_dir=tmp_path / "workspace"
        )
        
        # Run first execution that will fail
        with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
            mock_exec.return_value = {"success": False}
            
            success1, history1 = await executor.execute_with_retry(
                str(failing_tickets_yaml),
                "FAIL-001"
            )
            
            assert not success1
            first_call_count = mock_exec.call_count
        
        # Try again - circuit breaker should be open
        with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
            success2, history2 = await executor.execute_with_retry(
                str(failing_tickets_yaml),
                "FAIL-001"
            )
            
            assert not success2
            # Should not have attempted execution
            assert mock_exec.call_count == 0
    
    @pytest.mark.asyncio
    async def test_learning_from_failures(self, failing_tickets_yaml, tmp_path):
        """Test learning system extracts patterns from failures."""
        executor = RecursiveExecutor(
            max_retries=3,
            base_backoff=0.01,
            workspace_dir=tmp_path / "workspace",
            enable_learning=True
        )
        
        failure_reasons = [
            "ImportError: cannot import module 'foo'",
            "Test test_function failed with AssertionError",
            "ImportError: cannot import module 'bar'"
        ]
        
        call_count = 0
        
        def mock_execute(tickets_file, ticket_id, provider=None):
            nonlocal call_count
            if call_count < len(failure_reasons):
                reason = failure_reasons[call_count]
                call_count += 1
                return {"success": False, "error": reason}
            return {"success": True}
        
        with patch('hydra.workflow.recursive_executor.execute_single_ticket', mock_execute):
            with patch('hydra.workflow.recursive_executor.VerificationEngine') as mock_verifier:
                # Make verification fail with our reasons
                def verify_side_effect(*args, **kwargs):
                    if call_count <= len(failure_reasons):
                        return {
                            "passed": False,
                            "reason": failure_reasons[call_count - 1] if call_count > 0 else "Initial failure"
                        }
                    return {"passed": True}
                
                mock_verifier.return_value.verify_ticket.side_effect = verify_side_effect
                
                success, history = await executor.execute_with_retry(
                    str(failing_tickets_yaml),
                    "FAIL-001",
                    verification_config={"strict": True}
                )
                
                # Check learned patterns
                assert len(history.learned_patterns) > 0
                patterns = history.learned_patterns[-1]["patterns"]
                assert "import_errors" in patterns["common_failures"]
                assert "test_failures" in patterns["common_failures"]
                assert len(patterns["suggestions"]) > 0
    
    def test_synchronous_execution_with_retries(self, failing_tickets_yaml, tmp_path):
        """Test synchronous wrapper handles retries correctly."""
        call_count = 0
        
        def mock_execute(tickets_file, ticket_id, provider=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return {"success": False}
            return {"success": True}
        
        with patch('hydra.workflow.recursive_executor.execute_single_ticket', mock_execute):
            success, result = execute_with_retry(
                str(failing_tickets_yaml),
                "FAIL-001",
                max_retries=3
            )
            
            assert success
            assert result["success"]
            assert result["attempts"] == 2
            assert "metrics" in result
            assert result["metrics"]["total_executions"] == 1
    
    @pytest.mark.asyncio
    async def test_metrics_tracking_across_executions(self, failing_tickets_yaml, tmp_path):
        """Test metrics are tracked across multiple executions."""
        executor = RecursiveExecutor(
            max_retries=2,
            base_backoff=0.01,
            workspace_dir=tmp_path / "workspace",
            enable_metrics=True
        )
        
        # Execute multiple tickets with different outcomes
        with patch('hydra.workflow.recursive_executor.execute_single_ticket') as mock_exec:
            # First ticket succeeds immediately
            mock_exec.return_value = {"success": True}
            await executor.execute_with_retry(str(failing_tickets_yaml), "SUCCESS-001")
            
            # Second ticket fails then succeeds
            mock_exec.side_effect = [{"success": False}, {"success": True}]
            await executor.execute_with_retry(str(failing_tickets_yaml), "FAIL-002")
            
            # Third ticket always fails
            mock_exec.side_effect = [{"success": False}] * 2
            await executor.execute_with_retry(str(failing_tickets_yaml), "FAIL-001")
        
        metrics = executor.get_metrics()
        
        assert metrics["total_executions"] == 3
        assert metrics["successful_retries"] == 1  # FAIL-002 succeeded on retry
        assert metrics["failed_retries"] == 1  # FAIL-001 failed all retries
        assert metrics["average_retry_count"] > 1  # Should be around 1.67
        assert 0 < metrics["success_rate"] < 100  # Some succeeded, some failed