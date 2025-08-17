"""Error handling for the Action Executor system.

This module defines custom exceptions and error handling strategies
for robust action execution and meaningful error reporting.
"""

from typing import Any, Dict, List, Optional

from .types import Action, ActionResult, ActionType


class ActionExecutorError(Exception):
    """Base exception for all action executor errors."""

    def __init__(
        self,
        message: str,
        action: Optional[Action] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the error with context.

        Args:
            message: Error message
            action: The action that caused the error
            details: Additional error details

        """
        super().__init__(message)
        self.action = action
        self.details = details or {}


class ParseError(ActionExecutorError):
    """Raised when parsing an LLM response fails.

    This indicates the response format could not be understood
    or contained invalid syntax.
    """

    def __init__(
        self,
        message: str,
        response: str,
        position: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize parse error with response context.

        Args:
            message: Error message
            response: The response that failed to parse
            position: Character position where parsing failed
            details: Additional error details

        """
        super().__init__(message, details=details)
        self.response = response
        self.position = position

    def get_context(self, width: int = 40) -> str:
        """Get the context around the parse error.

        Args:
            width: Number of characters to show before/after error

        Returns:
            String showing error context

        """
        if self.position is None:
            if len(self.response) > 100:
                return self.response[:100] + "..."
            return self.response

        start = max(0, self.position - width)
        end = min(len(self.response), self.position + width)
        context = self.response[start:end]

        if start > 0:
            context = "..." + context
        if end < len(self.response):
            context = context + "..."

        return context


class ValidationError(ActionExecutorError):
    """Raised when an action fails validation.

    This indicates the action is malformed, unsafe, or inappropriate
    for the current context.
    """

    def __init__(
        self,
        message: str,
        action: Action,
        validation_errors: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize validation error.

        Args:
            message: Error message
            action: The action that failed validation
            validation_errors: List of specific validation failures
            details: Additional error details

        """
        super().__init__(message, action, details)
        self.validation_errors = validation_errors or []

    def get_report(self) -> str:
        """Get a formatted validation error report.

        Returns:
            Formatted string with all validation errors

        """
        lines = [f"Validation failed for {self.action.type.name}: {self.message}"]

        if self.validation_errors:
            lines.append("\nValidation errors:")
            for error in self.validation_errors:
                lines.append(f"  - {error}")

        if self.action:
            lines.append(f"\nAction target: {self.action.target}")

        return "\n".join(lines)


class ExecutionError(ActionExecutorError):
    """Raised when action execution fails.

    This indicates the action was valid but could not be completed
    due to runtime issues.
    """

    def __init__(
        self,
        message: str,
        action: Action,
        result: Optional[ActionResult] = None,
        recoverable: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize execution error.

        Args:
            message: Error message
            action: The action that failed
            result: The partial result if available
            recoverable: Whether the error can be recovered
            details: Additional error details

        """
        super().__init__(message, action, details)
        self.result = result
        self.recoverable = recoverable

    def should_retry(self) -> bool:
        """Check if the failed action should be retried.

        Returns:
            True if retry is recommended

        """
        if not self.recoverable:
            return False

        # Check for permanent failure indicators
        permanent_errors = [
            "permission denied",
            "access denied",
            "not found",
            "invalid",
            "unsupported",
        ]

        message_lower = str(self).lower()
        return not any(error in message_lower for error in permanent_errors)


class RollbackError(ActionExecutorError):
    """Raised when rollback operations fail.

    This is a critical error indicating the system could not
    restore to a previous state after a failure.
    """

    def __init__(
        self,
        message: str,
        failed_rollbacks: List[ActionResult],
        original_error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize rollback error.

        Args:
            message: Error message
            failed_rollbacks: List of rollback operations that failed
            original_error: The error that triggered rollback
            details: Additional error details

        """
        super().__init__(message, details=details)
        self.failed_rollbacks = failed_rollbacks
        self.original_error = original_error

    def get_report(self) -> str:
        """Get a detailed rollback failure report.

        Returns:
            Formatted string with rollback failure details

        """
        lines = [f"Rollback failed: {self.message}"]

        if self.original_error:
            lines.append(f"\nOriginal error: {self.original_error}")

        if self.failed_rollbacks:
            lines.append(f"\n{len(self.failed_rollbacks)} rollback operations failed:")
            for result in self.failed_rollbacks:
                lines.append(f"  - {result.action.type.name}: {result.error}")

        return "\n".join(lines)


class TimeoutError(ExecutionError):
    """Raised when an action exceeds its timeout.

    This is a specific type of execution error for timeout scenarios.
    """

    def __init__(
        self,
        action: Action,
        timeout: int,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize timeout error.

        Args:
            action: The action that timed out
            timeout: The timeout value in seconds
            details: Additional error details

        """
        message = f"Action timed out after {timeout} seconds"
        super().__init__(message, action, recoverable=True, details=details)
        self.timeout = timeout


class ErrorHandler:
    """Central error handling and recovery strategies.

    This class provides methods for handling different error types
    and implementing recovery strategies.
    """

    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0) -> None:
        """Initialize error handler.

        Args:
            max_retries: Maximum number of retry attempts
            backoff_factor: Factor for exponential backoff

        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.error_history: List[ActionExecutorError] = []

    def handle_error(
        self, error: Exception, action: Optional[Action] = None
    ) -> ActionResult:
        """Handle an error and return an appropriate result.

        Args:
            error: The error to handle
            action: The action that caused the error

        Returns:
            ActionResult with error information

        """
        # Track error history
        if isinstance(error, ActionExecutorError):
            self.error_history.append(error)

        # Create error result
        result = ActionResult(
            action=action or Action(type=ActionType.RUN_COMMAND, target="unknown"),
            success=False,
            error=str(error),
        )

        # Add recovery suggestions
        if isinstance(error, ValidationError):
            result.error = error.get_report()
        elif isinstance(error, ExecutionError):
            if error.should_retry():
                result.error += "\n(This error may be recoverable with retry)"
        elif isinstance(error, RollbackError):
            result.error = error.get_report()

        return result

    def get_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay using exponential backoff.

        Args:
            attempt: The retry attempt number (0-based)

        Returns:
            Delay in seconds

        """
        return self.backoff_factor**attempt

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if an operation should be retried.

        Args:
            error: The error that occurred
            attempt: Current retry attempt number

        Returns:
            True if retry should be attempted

        """
        if attempt >= self.max_retries:
            return False

        if isinstance(error, ExecutionError):
            return error.should_retry()

        if isinstance(error, TimeoutError):
            return True

        if isinstance(error, (ValidationError, ParseError, RollbackError)):
            return False

        # Default to retry for unknown errors
        return True

    def get_error_summary(self) -> Dict[str, Any]:
        """Get a summary of all errors encountered.

        Returns:
            Dictionary with error statistics and details

        """
        summary = {
            "total_errors": len(self.error_history),
            "by_type": {},
            "recoverable": 0,
            "permanent": 0,
        }

        for error in self.error_history:
            error_type = type(error).__name__
            summary["by_type"][error_type] = summary["by_type"].get(error_type, 0) + 1

            if isinstance(error, ExecutionError):
                if error.recoverable:
                    summary["recoverable"] += 1
                else:
                    summary["permanent"] += 1

        return summary
