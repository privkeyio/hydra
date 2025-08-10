"""Retry utilities for provider operations."""

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Optional

from .error_handler import ErrorCategory, RetryConfig, get_error_handler

logger = logging.getLogger(__name__)


def with_retry(
    max_retries: Optional[int] = None,
    retry_on: Optional[list[ErrorCategory]] = None,
    provider_name: Optional[str] = None,
    fallback_result: Any = None
):
    """Decorator for adding retry logic to provider methods.

    Args:
        max_retries: Maximum number of retries (uses config default if None)
        retry_on: List of error categories to retry on
        provider_name: Provider name for error tracking
        fallback_result: Result to return if all retries fail

    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get provider name from self if available
            nonlocal provider_name
            if not provider_name and args and hasattr(args[0], 'name'):
                provider_name = args[0].name
            if not provider_name:
                provider_name = 'unknown'

            error_handler = get_error_handler()
            retry_config = RetryConfig(
                max_retries=max_retries or error_handler.retry_config.max_retries,
                retry_on=retry_on or error_handler.retry_config.retry_on
            )

            last_error = None
            for attempt in range(retry_config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = error_handler.handle_error(
                        provider=provider_name,
                        error=e,
                        context={'attempt': attempt + 1, 'function': func.__name__}
                    )
                    last_error.retry_count = attempt

                    if not error_handler.should_retry(last_error):
                        break

                    if attempt < retry_config.max_retries:
                        delay = retry_config.get_delay(attempt)
                        logger.info(
                            f"Retrying {func.__name__} after {delay:.1f}s "
                            f"(attempt {attempt + 2}/{retry_config.max_retries + 1})"
                        )
                        time.sleep(delay)

            # All retries failed
            if fallback_result is not None:
                logger.warning(
                    f"All retries failed for {func.__name__}, using fallback result"
                )
                return fallback_result

            if last_error and last_error.original_error:
                raise last_error.original_error
            raise Exception(f"All retries failed for {func.__name__}")

        return wrapper
    return decorator


def async_with_retry(
    max_retries: Optional[int] = None,
    retry_on: Optional[list[ErrorCategory]] = None,
    provider_name: Optional[str] = None,
    fallback_result: Any = None
):
    """Async decorator for adding retry logic to provider methods.

    Args:
        max_retries: Maximum number of retries
        retry_on: List of error categories to retry on
        provider_name: Provider name for error tracking
        fallback_result: Result to return if all retries fail

    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get provider name from self if available
            nonlocal provider_name
            if not provider_name and args and hasattr(args[0], 'name'):
                provider_name = args[0].name
            if not provider_name:
                provider_name = 'unknown'

            error_handler = get_error_handler()
            retry_config = RetryConfig(
                max_retries=max_retries or error_handler.retry_config.max_retries,
                retry_on=retry_on or error_handler.retry_config.retry_on
            )

            last_error = None
            for attempt in range(retry_config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = error_handler.handle_error(
                        provider=provider_name,
                        error=e,
                        context={'attempt': attempt + 1, 'function': func.__name__}
                    )
                    last_error.retry_count = attempt

                    if not error_handler.should_retry(last_error):
                        break

                    if attempt < retry_config.max_retries:
                        delay = retry_config.get_delay(attempt)
                        logger.info(
                            f"Retrying {func.__name__} after {delay:.1f}s "
                            f"(attempt {attempt + 2}/{retry_config.max_retries + 1})"
                        )
                        await asyncio.sleep(delay)

            # All retries failed
            if fallback_result is not None:
                logger.warning(
                    f"All retries failed for {func.__name__}, using fallback result"
                )
                return fallback_result

            if last_error and last_error.original_error:
                raise last_error.original_error
            raise Exception(f"All retries failed for {func.__name__}")

        return wrapper
    return decorator


class RetryableOperation:
    """Context manager for retryable operations."""

    def __init__(
        self,
        provider: str,
        operation: str,
        max_retries: int = 3,
        retry_on: Optional[list[ErrorCategory]] = None
    ):
        """Initialize retryable operation.

        Args:
            provider: Provider name
            operation: Operation description
            max_retries: Maximum retries
            retry_on: Error categories to retry on

        """
        self.provider = provider
        self.operation = operation
        self.max_retries = max_retries
        self.retry_on = retry_on or [
            ErrorCategory.NETWORK,
            ErrorCategory.API_LIMIT,
            ErrorCategory.TIMEOUT
        ]
        self.attempt = 0
        self.error_handler = get_error_handler()

    def __enter__(self):
        """Enter context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Handle exceptions with retry logic."""
        if exc_type is None:
            return True

        self.attempt += 1

        # Handle the error
        error = self.error_handler.handle_error(
            provider=self.provider,
            error=exc_val,
            context={
                'operation': self.operation,
                'attempt': self.attempt
            }
        )

        # Check if we should retry
        if self.attempt <= self.max_retries and error.category in self.retry_on:
            delay = self.error_handler.retry_config.get_delay(self.attempt - 1)
            logger.info(
                f"Retrying {self.operation} after {delay:.1f}s "
                f"(attempt {self.attempt + 1}/{self.max_retries + 1})"
            )
            time.sleep(delay)
            return False  # Don't suppress, will retry

        # Max retries exceeded or non-retryable error
        return False  # Propagate exception

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        """
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                with self:
                    return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt >= self.max_retries:
                    break

        raise last_error


def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True
) -> float:
    """Calculate exponential backoff delay.

    Args:
        attempt: Retry attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Add random jitter to delay

    Returns:
        Delay in seconds

    """
    delay = min(base_delay * (2 ** attempt), max_delay)

    if jitter:
        import random
        delay *= (0.5 + random.random())

    return delay


class CircuitBreaker:
    """Circuit breaker for provider operations."""

    def __init__(
        self,
        provider: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_requests: int = 1
    ):
        """Initialize circuit breaker.

        Args:
            provider: Provider name
            failure_threshold: Failures before opening circuit
            recovery_timeout: Seconds before attempting recovery
            half_open_requests: Requests to allow in half-open state

        """
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests

        self.failure_count = 0
        self.last_failure_time = 0
        self.state = 'closed'  # closed, open, half-open
        self.half_open_count = 0

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception: If circuit is open or function fails

        """
        if self.state == 'open':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'half-open'
                self.half_open_count = 0
            else:
                raise Exception(
                    f"Circuit breaker is open for {self.provider}. "
                    f"Retry after {self.recovery_timeout}s"
                )

        if self.state == 'half-open':
            if self.half_open_count >= self.half_open_requests:
                self.state = 'open'
                raise Exception(
                    f"Circuit breaker is open for {self.provider}. "
                    "Half-open requests exceeded"
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call."""
        if self.state == 'half-open':
            self.half_open_count += 1
            if self.half_open_count >= self.half_open_requests:
                self.state = 'closed'
                self.failure_count = 0
                logger.info(f"Circuit breaker closed for {self.provider}")
        else:
            self.failure_count = 0

    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = 'open'
            logger.warning(
                f"Circuit breaker opened for {self.provider} "
                f"after {self.failure_count} failures"
            )

    def reset(self):
        """Reset circuit breaker to closed state."""
        self.state = 'closed'
        self.failure_count = 0
        self.half_open_count = 0
