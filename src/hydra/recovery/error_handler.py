"""Comprehensive error recovery system with automatic rollback and retry."""

import asyncio
import json
import logging
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Classification of error types for recovery strategies."""

    TRANSIENT_NETWORK = "transient_network"
    FILE_SYSTEM = "file_system"
    PROCESS_EXECUTION = "process_execution"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    PERMISSION = "permission"
    CONFIGURATION = "configuration"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN = "unknown"


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ErrorContext:
    """Context information about an error."""

    error: Exception
    error_type: ErrorType
    operation: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    recovery_attempted: bool = False


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""

    success: bool
    error: Optional[Exception] = None
    rollback_performed: bool = False
    strategy_used: Optional[str] = None
    execution_time: float = 0.0


class RecoveryStrategy(ABC):
    """Abstract base class for recovery strategies."""

    @abstractmethod
    def can_recover(self, error_context: ErrorContext) -> bool:
        """Determine if this strategy can handle the error."""
        pass

    @abstractmethod
    async def recover(self, error_context: ErrorContext) -> RecoveryResult:
        """Attempt to recover from the error."""
        pass


class RetryStrategy(RecoveryStrategy):
    """Recovery strategy using exponential backoff retry."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0,
                 max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def can_recover(self, error_context: ErrorContext) -> bool:
        return (error_context.retry_count < self.max_retries and
                error_context.error_type in {
                    ErrorType.TRANSIENT_NETWORK,
                    ErrorType.PROVIDER_TIMEOUT,
                    ErrorType.RESOURCE_EXHAUSTION
                })

    async def recover(self, error_context: ErrorContext) -> RecoveryResult:
        start_time = time.time()

        if not self.can_recover(error_context):
            return RecoveryResult(
                success=False,
                error=error_context.error,
                execution_time=time.time() - start_time
            )

        delay = min(self.base_delay * (2 ** error_context.retry_count), self.max_delay)
        logger.info(
            f"Retrying operation '{error_context.operation}' after {delay}s delay"
        )

        await asyncio.sleep(delay)
        error_context.retry_count += 1

        return RecoveryResult(
            success=True,
            strategy_used="retry_exponential_backoff",
            execution_time=time.time() - start_time
        )


class FileRollbackStrategy(RecoveryStrategy):
    """Strategy for rolling back file system changes."""

    def __init__(self, backup_dir: Optional[Path] = None):
        self.backup_dir = backup_dir or Path.home() / ".hydra" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def can_recover(self, error_context: ErrorContext) -> bool:
        return error_context.error_type == ErrorType.FILE_SYSTEM

    async def recover(self, error_context: ErrorContext) -> RecoveryResult:
        start_time = time.time()

        try:
            operation_id = error_context.metadata.get("operation_id")
            if not operation_id:
                return RecoveryResult(
                    success=False,
                    error=ValueError("No operation_id for rollback"),
                    execution_time=time.time() - start_time
                )

            backup_path = self.backup_dir / f"{operation_id}.backup"
            if backup_path.exists():
                with open(backup_path, 'r') as f:
                    backup_data = json.load(f)

                await self._restore_files(backup_data)

                return RecoveryResult(
                    success=True,
                    rollback_performed=True,
                    strategy_used="file_rollback",
                    execution_time=time.time() - start_time
                )

            return RecoveryResult(
                success=False,
                error=FileNotFoundError(
                    f"No backup found for operation {operation_id}"
                ),
                execution_time=time.time() - start_time
            )

        except Exception as e:
            return RecoveryResult(
                success=False,
                error=e,
                execution_time=time.time() - start_time
            )

    async def _restore_files(self, backup_data: Dict[str, Any]):
        """Restore files from backup data."""
        for file_path, backup_info in backup_data.get("files", {}).items():
            original_path = Path(file_path)

            if backup_info["action"] == "created":
                if original_path.exists():
                    original_path.unlink()
            elif backup_info["action"] == "modified":
                backup_content = backup_info["content"]
                original_path.write_text(backup_content)
            elif backup_info["action"] == "deleted":
                original_path.write_text(backup_info["content"])


class ProcessRecoveryStrategy(RecoveryStrategy):
    """Strategy for recovering from process execution failures."""

    def can_recover(self, error_context: ErrorContext) -> bool:
        return error_context.error_type == ErrorType.PROCESS_EXECUTION

    async def recover(self, error_context: ErrorContext) -> RecoveryResult:
        start_time = time.time()

        try:
            if "cleanup_commands" in error_context.metadata:
                for cmd in error_context.metadata["cleanup_commands"]:
                    logger.info(f"Running cleanup command: {cmd}")
                    process = await asyncio.create_subprocess_shell(
                        cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await process.communicate()

            return RecoveryResult(
                success=True,
                strategy_used="process_cleanup",
                execution_time=time.time() - start_time
            )

        except Exception as e:
            return RecoveryResult(
                success=False,
                error=e,
                execution_time=time.time() - start_time
            )


class CircuitBreaker:
    """Circuit breaker to prevent repeated failures."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED

    def can_execute(self) -> bool:
        """Check if operation can be executed based on circuit state."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if (self.last_failure_time and
                (datetime.now() - self.last_failure_time).total_seconds() >
                self.recovery_timeout):
                self.state = CircuitState.HALF_OPEN
                return True
            return False

        return True

    def record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )


class ErrorRecoveryManager:
    """Main error recovery manager with failure detection and recovery orchestration."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or Path.home() / ".hydra" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.strategies: List[RecoveryStrategy] = [
            RetryStrategy(),
            FileRollbackStrategy(),
            ProcessRecoveryStrategy()
        ]

        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.error_history: List[ErrorContext] = []
        self.max_history = 1000

    def add_strategy(self, strategy: RecoveryStrategy):
        """Add a custom recovery strategy."""
        self.strategies.append(strategy)

    def get_circuit_breaker(self, operation: str) -> CircuitBreaker:
        """Get or create circuit breaker for operation."""
        if operation not in self.circuit_breakers:
            self.circuit_breakers[operation] = CircuitBreaker()
        return self.circuit_breakers[operation]

    def classify_error(self, error: Exception, operation: str) -> ErrorType:
        """Classify error type for appropriate recovery strategy."""
        error_msg = str(error).lower()

        if isinstance(error, (ConnectionError, TimeoutError)) or \
           "timeout" in error_msg or "connection" in error_msg:
            if "provider" in operation.lower():
                return ErrorType.PROVIDER_TIMEOUT
            return ErrorType.TRANSIENT_NETWORK

        if isinstance(error, (OSError, IOError, PermissionError)) or \
           "permission" in error_msg or "access" in error_msg:
            if "permission" in error_msg:
                return ErrorType.PERMISSION
            return ErrorType.FILE_SYSTEM

        if isinstance(error, subprocess.SubprocessError) or \
           "process" in error_msg or "command" in error_msg:
            return ErrorType.PROCESS_EXECUTION

        if "memory" in error_msg or "resource" in error_msg or "limit" in error_msg:
            return ErrorType.RESOURCE_EXHAUSTION

        if "config" in error_msg or "setting" in error_msg:
            return ErrorType.CONFIGURATION

        if ("provider" in operation.lower() and
            ("error" in error_msg or "fail" in error_msg)):
            return ErrorType.PROVIDER_ERROR

        return ErrorType.UNKNOWN

    async def handle_error(self,
                          error: Exception,
                          operation: str,
                          metadata: Optional[Dict[str, Any]] = None) -> RecoveryResult:
        """Handle error with appropriate recovery strategy."""
        error_type = self.classify_error(error, operation)
        error_context = ErrorContext(
            error=error,
            error_type=error_type,
            operation=operation,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )

        self._log_error(error_context)
        self.error_history.append(error_context)
        if len(self.error_history) > self.max_history:
            self.error_history.pop(0)

        circuit_breaker = self.get_circuit_breaker(operation)
        if not circuit_breaker.can_execute():
            return RecoveryResult(
                success=False,
                error=Exception(f"Circuit breaker open for operation: {operation}")
            )

        for strategy in self.strategies:
            if strategy.can_recover(error_context):
                logger.info(
                    f"Attempting recovery with strategy: {strategy.__class__.__name__}"
                )

                try:
                    result = await strategy.recover(error_context)

                    if result.success:
                        circuit_breaker.record_success()
                        error_context.recovery_attempted = True
                        self._log_recovery(error_context, result)
                        return result
                    else:
                        logger.warning(
                            f"Recovery strategy {strategy.__class__.__name__} failed"
                        )

                except Exception as recovery_error:
                    logger.error(f"Recovery strategy failed: {recovery_error}")
                    result = RecoveryResult(
                        success=False,
                        error=recovery_error
                    )

        circuit_breaker.record_failure()
        return RecoveryResult(
            success=False,
            error=error
        )

    def _log_error(self, error_context: ErrorContext):
        """Log error details for diagnostics."""
        log_file = self.log_dir / f"errors_{datetime.now().strftime('%Y%m%d')}.log"

        error_data = {
            "timestamp": error_context.timestamp.isoformat(),
            "operation": error_context.operation,
            "error_type": error_context.error_type.value,
            "error_class": error_context.error.__class__.__name__,
            "error_message": str(error_context.error),
            "metadata": error_context.metadata,
            "retry_count": error_context.retry_count
        }

        with open(log_file, 'a') as f:
            f.write(json.dumps(error_data) + '\n')

    def _log_recovery(self, error_context: ErrorContext, result: RecoveryResult):
        """Log recovery attempt results."""
        log_file = self.log_dir / f"recovery_{datetime.now().strftime('%Y%m%d')}.log"

        recovery_data = {
            "timestamp": datetime.now().isoformat(),
            "operation": error_context.operation,
            "error_type": error_context.error_type.value,
            "recovery_success": result.success,
            "strategy_used": result.strategy_used,
            "rollback_performed": result.rollback_performed,
            "execution_time": result.execution_time
        }

        with open(log_file, 'a') as f:
            f.write(json.dumps(recovery_data) + '\n')

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error and recovery statistics."""
        if not self.error_history:
            return {"total_errors": 0}

        error_types = {}
        recovery_attempts = 0
        successful_recoveries = 0

        for error_ctx in self.error_history:
            error_type = error_ctx.error_type.value
            error_types[error_type] = error_types.get(error_type, 0) + 1

            if error_ctx.recovery_attempted:
                recovery_attempts += 1
                successful_recoveries += 1

        return {
            "total_errors": len(self.error_history),
            "error_types": error_types,
            "recovery_attempts": recovery_attempts,
            "successful_recoveries": successful_recoveries,
            "recovery_rate": (
                successful_recoveries / recovery_attempts
                if recovery_attempts > 0 else 0
            ),
            "circuit_breaker_states": {
                op: cb.state.value for op, cb in self.circuit_breakers.items()
            }
        }

    async def create_checkpoint(self, operation_id: str, files_to_backup: List[Path]):
        """Create a checkpoint before risky operations."""
        backup_dir = Path.home() / ".hydra" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_data = {
            "timestamp": datetime.now().isoformat(),
            "operation_id": operation_id,
            "files": {}
        }

        for file_path in files_to_backup:
            if file_path.exists():
                if file_path.is_file():
                    backup_data["files"][str(file_path)] = {
                        "action": "modify",
                        "content": file_path.read_text(),
                        "size": file_path.stat().st_size
                    }
                else:
                    backup_data["files"][str(file_path)] = {
                        "action": "directory",
                        "exists": True
                    }

        backup_file = backup_dir / f"{operation_id}.backup"
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)

        logger.info(f"Created checkpoint for operation {operation_id}")
