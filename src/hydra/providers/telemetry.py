"""Telemetry and monitoring for provider operations."""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class OperationMetrics:
    """Metrics for a provider operation."""

    provider: str
    operation: str
    start_time: float
    end_time: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> Optional[float]:
        """Calculate operation duration."""
        if self.end_time is None:
            return None
        return self.end_time - self.start_time

    def finish(self, success: bool = True, error: Optional[str] = None):
        """Mark operation as finished."""
        self.end_time = time.time()
        self.success = success
        self.error = error


class TelemetryManager:
    """Manager for provider telemetry and monitoring."""

    def __init__(self):
        """Initialize telemetry manager."""
        self.metrics_history = []
        self.active_operations = {}

    def start_operation(self,
                       provider: str,
                       operation: str,
                       operation_id: Optional[str] = None,
                       **context) -> str:
        """Start tracking an operation.
        
        Args:
            provider: Provider name
            operation: Operation name (e.g., 'generate', 'create_session')
            operation_id: Optional unique operation ID
            **context: Additional context for logging
            
        Returns:
            Operation ID for tracking

        """
        if operation_id is None:
            operation_id = f"{provider}_{operation}_{int(time.time() * 1000)}"

        metrics = OperationMetrics(
            provider=provider,
            operation=operation,
            start_time=time.time(),
            context=context
        )

        self.active_operations[operation_id] = metrics

        logger.debug(f"Started {provider}.{operation} (ID: {operation_id})")

        return operation_id

    def finish_operation(self,
                        operation_id: str,
                        success: bool = True,
                        error: Optional[str] = None,
                        **additional_context):
        """Finish tracking an operation.
        
        Args:
            operation_id: Operation ID from start_operation
            success: Whether operation succeeded
            error: Error message if failed
            **additional_context: Additional context to record

        """
        if operation_id not in self.active_operations:
            logger.warning(f"Unknown operation ID: {operation_id}")
            return

        metrics = self.active_operations[operation_id]
        metrics.finish(success=success, error=error)
        metrics.context.update(additional_context)

        # Move to history
        self.metrics_history.append(metrics)
        del self.active_operations[operation_id]

        # Log completion
        status = "SUCCESS" if success else "FAILED"
        duration = metrics.duration or 0

        log_msg = f"Completed {metrics.provider}.{metrics.operation} in {duration:.2f}s [{status}]"
        if error:
            log_msg += f" - {error}"

        if success:
            logger.debug(log_msg)
        else:
            logger.warning(log_msg)

    def record_error(self,
                    provider: str,
                    operation: str,
                    error: Exception,
                    **context):
        """Record an error without operation tracking.
        
        Args:
            provider: Provider name
            operation: Operation name
            error: Exception that occurred
            **context: Additional context

        """
        error_msg = f"{type(error).__name__}: {str(error)}"

        metrics = OperationMetrics(
            provider=provider,
            operation=operation,
            start_time=time.time(),
            end_time=time.time(),
            success=False,
            error=error_msg,
            context=context
        )

        self.metrics_history.append(metrics)

        logger.error(f"Error in {provider}.{operation}: {error_msg}")

    def get_provider_stats(self, provider: str, last_minutes: int = 60) -> Dict[str, Any]:
        """Get statistics for a provider.
        
        Args:
            provider: Provider name
            last_minutes: Look at operations in the last N minutes
            
        Returns:
            Statistics dictionary

        """
        cutoff_time = time.time() - (last_minutes * 60)

        relevant_metrics = [
            m for m in self.metrics_history
            if m.provider == provider and m.start_time >= cutoff_time
        ]

        if not relevant_metrics:
            return {
                "provider": provider,
                "total_operations": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
                "errors": []
            }

        total_ops = len(relevant_metrics)
        successful_ops = sum(1 for m in relevant_metrics if m.success)
        success_rate = successful_ops / total_ops

        durations = [m.duration for m in relevant_metrics if m.duration is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        errors = [m.error for m in relevant_metrics if not m.success and m.error]

        return {
            "provider": provider,
            "total_operations": total_ops,
            "successful_operations": successful_ops,
            "success_rate": success_rate,
            "avg_duration": avg_duration,
            "errors": errors[-10:]  # Last 10 errors
        }

    def get_overall_stats(self, last_minutes: int = 60) -> Dict[str, Any]:
        """Get overall statistics across all providers.
        
        Args:
            last_minutes: Look at operations in the last N minutes
            
        Returns:
            Overall statistics dictionary

        """
        cutoff_time = time.time() - (last_minutes * 60)

        relevant_metrics = [
            m for m in self.metrics_history
            if m.start_time >= cutoff_time
        ]

        if not relevant_metrics:
            return {
                "total_operations": 0,
                "success_rate": 0.0,
                "providers": []
            }

        total_ops = len(relevant_metrics)
        successful_ops = sum(1 for m in relevant_metrics if m.success)
        success_rate = successful_ops / total_ops

        # Group by provider
        providers = {}
        for metrics in relevant_metrics:
            if metrics.provider not in providers:
                providers[metrics.provider] = []
            providers[metrics.provider].append(metrics)

        provider_stats = {}
        for provider, metrics_list in providers.items():
            total = len(metrics_list)
            successful = sum(1 for m in metrics_list if m.success)
            durations = [m.duration for m in metrics_list if m.duration is not None]
            avg_duration = sum(durations) / len(durations) if durations else 0.0

            provider_stats[provider] = {
                "total_operations": total,
                "successful_operations": successful,
                "success_rate": successful / total,
                "avg_duration": avg_duration
            }

        return {
            "total_operations": total_ops,
            "successful_operations": successful_ops,
            "success_rate": success_rate,
            "providers": provider_stats
        }

    def cleanup_old_metrics(self, max_age_hours: int = 24):
        """Clean up old metrics to prevent memory growth.
        
        Args:
            max_age_hours: Maximum age of metrics to keep in hours

        """
        cutoff_time = time.time() - (max_age_hours * 3600)

        original_count = len(self.metrics_history)
        self.metrics_history = [
            m for m in self.metrics_history
            if m.start_time >= cutoff_time
        ]

        cleaned_count = original_count - len(self.metrics_history)
        if cleaned_count > 0:
            logger.debug(f"Cleaned up {cleaned_count} old telemetry metrics")


# Global telemetry manager instance
_telemetry_manager = None


def get_telemetry_manager() -> TelemetryManager:
    """Get global telemetry manager instance.
    
    Returns:
        Global TelemetryManager instance

    """
    global _telemetry_manager
    if _telemetry_manager is None:
        _telemetry_manager = TelemetryManager()
    return _telemetry_manager


class OperationTracker:
    """Context manager for tracking operations."""

    def __init__(self, provider: str, operation: str, **context):
        """Initialize operation tracker.
        
        Args:
            provider: Provider name
            operation: Operation name
            **context: Additional context

        """
        self.provider = provider
        self.operation = operation
        self.context = context
        self.operation_id = None
        self.telemetry = get_telemetry_manager()

    def __enter__(self):
        """Start tracking operation."""
        self.operation_id = self.telemetry.start_operation(
            self.provider,
            self.operation,
            **self.context
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finish tracking operation."""
        if exc_type is None:
            self.telemetry.finish_operation(self.operation_id, success=True)
        else:
            error_msg = f"{exc_type.__name__}: {str(exc_val)}" if exc_val else str(exc_type)
            self.telemetry.finish_operation(
                self.operation_id,
                success=False,
                error=error_msg
            )
        return False  # Don't suppress exceptions

    def add_context(self, **context):
        """Add additional context during operation.
        
        Args:
            **context: Additional context to add

        """
        if self.operation_id and self.operation_id in self.telemetry.active_operations:
            self.telemetry.active_operations[self.operation_id].context.update(context)


def track_operation(provider: str, operation: str, **context):
    """Decorator for tracking operations.
    
    Args:
        provider: Provider name
        operation: Operation name
        **context: Additional context
        
    Returns:
        Decorator function

    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with OperationTracker(provider, operation, **context):
                return func(*args, **kwargs)
        return wrapper
    return decorator
