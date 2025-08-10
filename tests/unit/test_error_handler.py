"""
Unit tests for error recovery system.
"""

import asyncio
import json
import subprocess
import tempfile
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from hydra.recovery.error_handler import (
    ErrorRecoveryManager,
    ErrorType,
    ErrorContext,
    RecoveryResult,
    CircuitBreaker,
    CircuitState,
    RetryStrategy,
    FileRollbackStrategy,
    ProcessRecoveryStrategy
)


class TestErrorRecoveryManager:
    """Test the main error recovery manager."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def recovery_manager(self, temp_dir):
        """Create error recovery manager for testing."""
        return ErrorRecoveryManager(log_dir=temp_dir / "logs")
    
    def test_error_classification(self, recovery_manager):
        """Test error classification logic."""
        connection_error = ConnectionError("Connection failed")
        assert recovery_manager.classify_error(connection_error, "network_op") == ErrorType.TRANSIENT_NETWORK
        
        timeout_error = TimeoutError("Request timeout")
        assert recovery_manager.classify_error(timeout_error, "provider_call") == ErrorType.PROVIDER_TIMEOUT
        
        permission_error = PermissionError("Permission denied")
        assert recovery_manager.classify_error(permission_error, "file_write") == ErrorType.PERMISSION
        
        io_error = IOError("File not found")
        assert recovery_manager.classify_error(io_error, "file_read") == ErrorType.FILE_SYSTEM
        
        memory_error = MemoryError("Out of memory")
        assert recovery_manager.classify_error(memory_error, "large_operation") == ErrorType.RESOURCE_EXHAUSTION
        
        generic_error = ValueError("Invalid value")
        assert recovery_manager.classify_error(generic_error, "data_processing") == ErrorType.UNKNOWN
    
    @pytest.mark.asyncio
    async def test_handle_error_with_retry(self, recovery_manager):
        """Test error handling with retry strategy."""
        error = ConnectionError("Temporary connection issue")
        
        result = await recovery_manager.handle_error(error, "network_operation")
        
        assert result.success
        assert result.strategy_used == "retry_exponential_backoff"
        assert len(recovery_manager.error_history) == 1
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_functionality(self, recovery_manager):
        """Test circuit breaker prevents repeated failures."""
        error = Exception("Persistent error")
        operation = "failing_operation"
        
        for _ in range(6):
            await recovery_manager.handle_error(error, operation)
        
        circuit_breaker = recovery_manager.get_circuit_breaker(operation)
        assert circuit_breaker.state == CircuitState.OPEN
        assert not circuit_breaker.can_execute()
    
    @pytest.mark.asyncio
    async def test_checkpoint_creation(self, recovery_manager, temp_dir):
        """Test checkpoint creation for file operations."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("original content")
        
        operation_id = "test_operation"
        await recovery_manager.create_checkpoint(operation_id, [test_file])
        
        backup_file = recovery_manager.log_dir.parent / "backups" / f"{operation_id}.backup"
        assert backup_file.exists()
        
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
        
        assert str(test_file) in backup_data["files"]
        assert backup_data["files"][str(test_file)]["content"] == "original content"
    
    def test_error_statistics(self, recovery_manager):
        """Test error statistics collection."""
        stats = recovery_manager.get_error_statistics()
        assert stats["total_errors"] == 0
        
        error_context = ErrorContext(
            error=ConnectionError("test"),
            error_type=ErrorType.TRANSIENT_NETWORK,
            operation="test_op",
            timestamp=datetime.now(),
            recovery_attempted=True
        )
        
        recovery_manager.error_history.append(error_context)
        
        stats = recovery_manager.get_error_statistics()
        assert stats["total_errors"] == 1
        assert stats["error_types"]["transient_network"] == 1
        assert stats["recovery_rate"] == 1.0


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker for testing."""
        return CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    
    def test_initial_state(self, circuit_breaker):
        """Test circuit breaker initial state."""
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.can_execute()
        assert circuit_breaker.failure_count == 0
    
    def test_failure_accumulation(self, circuit_breaker):
        """Test failure count accumulation."""
        for i in range(2):
            circuit_breaker.record_failure()
            assert circuit_breaker.state == CircuitState.CLOSED
            assert circuit_breaker.failure_count == i + 1
        
        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.OPEN
        assert not circuit_breaker.can_execute()
    
    def test_recovery_timeout(self, circuit_breaker):
        """Test circuit breaker recovery after timeout."""
        for _ in range(3):
            circuit_breaker.record_failure()
        
        assert circuit_breaker.state == CircuitState.OPEN
        assert not circuit_breaker.can_execute()
        
        import time
        time.sleep(1.1)
        
        assert circuit_breaker.can_execute()
        
        circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0


class TestRetryStrategy:
    """Test retry strategy implementation."""
    
    @pytest.fixture
    def retry_strategy(self):
        """Create retry strategy for testing."""
        return RetryStrategy(max_retries=3, base_delay=0.1, max_delay=1.0)
    
    def test_can_recover_conditions(self, retry_strategy):
        """Test retry strategy recovery conditions."""
        retryable_context = ErrorContext(
            error=ConnectionError("test"),
            error_type=ErrorType.TRANSIENT_NETWORK,
            operation="test_op",
            timestamp=datetime.now(),
            retry_count=0
        )
        
        assert retry_strategy.can_recover(retryable_context)
        
        non_retryable_context = ErrorContext(
            error=PermissionError("test"),
            error_type=ErrorType.PERMISSION,
            operation="test_op",
            timestamp=datetime.now(),
            retry_count=0
        )
        
        assert not retry_strategy.can_recover(non_retryable_context)
        
        max_retries_context = ErrorContext(
            error=ConnectionError("test"),
            error_type=ErrorType.TRANSIENT_NETWORK,
            operation="test_op",
            timestamp=datetime.now(),
            retry_count=3
        )
        
        assert not retry_strategy.can_recover(max_retries_context)
    
    @pytest.mark.asyncio
    async def test_retry_execution(self, retry_strategy):
        """Test retry strategy execution."""
        error_context = ErrorContext(
            error=ConnectionError("test"),
            error_type=ErrorType.TRANSIENT_NETWORK,
            operation="test_op",
            timestamp=datetime.now(),
            retry_count=0
        )
        
        start_time = asyncio.get_event_loop().time()
        result = await retry_strategy.recover(error_context)
        end_time = asyncio.get_event_loop().time()
        
        assert result.success
        assert result.strategy_used == "retry_exponential_backoff"
        assert end_time - start_time >= 0.1
        assert error_context.retry_count == 1


class TestFileRollbackStrategy:
    """Test file rollback strategy."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def rollback_strategy(self, temp_dir):
        """Create file rollback strategy for testing."""
        return FileRollbackStrategy(backup_dir=temp_dir / "backups")
    
    def test_can_recover_conditions(self, rollback_strategy):
        """Test rollback strategy recovery conditions."""
        file_system_context = ErrorContext(
            error=IOError("test"),
            error_type=ErrorType.FILE_SYSTEM,
            operation="file_write",
            timestamp=datetime.now()
        )
        
        assert rollback_strategy.can_recover(file_system_context)
        
        network_context = ErrorContext(
            error=ConnectionError("test"),
            error_type=ErrorType.TRANSIENT_NETWORK,
            operation="network_op",
            timestamp=datetime.now()
        )
        
        assert not rollback_strategy.can_recover(network_context)
    
    @pytest.mark.asyncio
    async def test_rollback_execution(self, rollback_strategy, temp_dir):
        """Test file rollback execution."""
        operation_id = "test_rollback"
        backup_path = rollback_strategy.backup_dir / f"{operation_id}.backup"
        rollback_strategy.backup_dir.mkdir(parents=True, exist_ok=True)
        
        test_file = temp_dir / "test.txt"
        test_file.write_text("modified content")
        
        backup_data = {
            "operation_id": operation_id,
            "files": {
                str(test_file): {
                    "action": "modified",
                    "content": "original content"
                }
            }
        }
        
        with open(backup_path, 'w') as f:
            json.dump(backup_data, f)
        
        error_context = ErrorContext(
            error=IOError("write failed"),
            error_type=ErrorType.FILE_SYSTEM,
            operation="file_write",
            timestamp=datetime.now(),
            metadata={"operation_id": operation_id}
        )
        
        result = await rollback_strategy.recover(error_context)
        
        assert result.success
        assert result.rollback_performed
        assert result.strategy_used == "file_rollback"
        assert test_file.read_text() == "original content"
    
    @pytest.mark.asyncio
    async def test_rollback_no_backup(self, rollback_strategy):
        """Test rollback when no backup exists."""
        error_context = ErrorContext(
            error=IOError("write failed"),
            error_type=ErrorType.FILE_SYSTEM,
            operation="file_write",
            timestamp=datetime.now(),
            metadata={"operation_id": "nonexistent"}
        )
        
        result = await rollback_strategy.recover(error_context)
        
        assert not result.success
        assert isinstance(result.error, FileNotFoundError)


class TestProcessRecoveryStrategy:
    """Test process recovery strategy."""
    
    @pytest.fixture
    def process_strategy(self):
        """Create process recovery strategy for testing."""
        return ProcessRecoveryStrategy()
    
    def test_can_recover_conditions(self, process_strategy):
        """Test process recovery conditions."""
        process_context = ErrorContext(
            error=subprocess.CalledProcessError(1, "test"),
            error_type=ErrorType.PROCESS_EXECUTION,
            operation="command_exec",
            timestamp=datetime.now()
        )
        
        assert process_strategy.can_recover(process_context)
        
        network_context = ErrorContext(
            error=ConnectionError("test"),
            error_type=ErrorType.TRANSIENT_NETWORK,
            operation="network_op",
            timestamp=datetime.now()
        )
        
        assert not process_strategy.can_recover(network_context)
    
    @pytest.mark.asyncio
    async def test_process_recovery_execution(self, process_strategy):
        """Test process recovery with cleanup commands."""
        error_context = ErrorContext(
            error=subprocess.CalledProcessError(1, "failed_command"),
            error_type=ErrorType.PROCESS_EXECUTION,
            operation="command_exec",
            timestamp=datetime.now(),
            metadata={
                "cleanup_commands": ["echo 'cleanup performed'"]
            }
        )
        
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b'cleanup performed', b'')
            mock_subprocess.return_value = mock_process
            
            result = await process_strategy.recover(error_context)
            
            assert result.success
            assert result.strategy_used == "process_cleanup"
            mock_subprocess.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_recovery_no_cleanup(self, process_strategy):
        """Test process recovery without cleanup commands."""
        error_context = ErrorContext(
            error=subprocess.CalledProcessError(1, "failed_command"),
            error_type=ErrorType.PROCESS_EXECUTION,
            operation="command_exec",
            timestamp=datetime.now(),
            metadata={}
        )
        
        result = await process_strategy.recover(error_context)
        
        assert result.success
        assert result.strategy_used == "process_cleanup"


@pytest.mark.asyncio
async def test_integration_error_recovery_workflow():
    """Test complete error recovery workflow integration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        recovery_manager = ErrorRecoveryManager(log_dir=temp_dir / "logs")
        
        error = ConnectionError("Network unavailable")
        operation = "critical_network_operation"
        
        result = await recovery_manager.handle_error(error, operation)
        
        assert result.success
        assert len(recovery_manager.error_history) == 1
        
        stats = recovery_manager.get_error_statistics()
        assert stats["total_errors"] == 1
        assert stats["recovery_rate"] == 1.0
        
        error_log = temp_dir / "logs" / f"errors_{datetime.now().strftime('%Y%m%d')}.log"
        assert error_log.exists()
        
        recovery_log = temp_dir / "logs" / f"recovery_{datetime.now().strftime('%Y%m%d')}.log"
        assert recovery_log.exists()