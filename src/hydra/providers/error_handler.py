"""Provider error handling and fallback mechanisms."""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Severity levels for provider errors."""

    CRITICAL = "critical"  # Provider completely unavailable
    HIGH = "high"  # Major functionality broken
    MEDIUM = "medium"  # Some features unavailable
    LOW = "low"  # Minor issues, can continue
    WARNING = "warning"  # Non-blocking issues


class ErrorCategory(Enum):
    """Categories of provider errors."""

    INITIALIZATION = "initialization"
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    API_LIMIT = "api_limit"
    INVALID_REQUEST = "invalid_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    SESSION = "session"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class ErrorType(Enum):
    """Types of provider errors (backward compatibility)."""

    PROVIDER_ERROR = "provider_error"
    INITIALIZATION_ERROR = "initialization_error"
    AUTHENTICATION_ERROR = "authentication_error"
    NETWORK_ERROR = "network_error"
    API_LIMIT_ERROR = "api_limit_error"
    INVALID_REQUEST_ERROR = "invalid_request_error"
    MODEL_UNAVAILABLE_ERROR = "model_unavailable_error"
    SESSION_ERROR = "session_error"
    TIMEOUT_ERROR = "timeout_error"
    RESOURCE_ERROR = "resource_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ProviderError:
    """Structured provider error information."""

    provider: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    original_error: Optional[Exception] = None
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    error_type: Optional[ErrorType] = None  # For backward compatibility

    def __str__(self) -> str:
        """Format error for display."""
        base_msg = f"[{self.provider}] {self.severity.value.upper()}: {self.message}"
        if self.original_error:
            base_msg += f" (Original: {str(self.original_error)})"
        return base_msg

    def is_retryable(self) -> bool:
        """Check if error is retryable."""
        retryable_categories = {
            ErrorCategory.NETWORK,
            ErrorCategory.API_LIMIT,
            ErrorCategory.TIMEOUT,
            ErrorCategory.SESSION,
        }
        return self.category in retryable_categories


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: List[ErrorCategory] = field(
        default_factory=lambda: [
            ErrorCategory.NETWORK,
            ErrorCategory.API_LIMIT,
            ErrorCategory.TIMEOUT,
        ]
    )

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt."""
        delay = min(
            self.initial_delay * (self.exponential_base**attempt), self.max_delay
        )
        if self.jitter:
            import random

            delay *= 0.5 + random.random()
        return delay


class ProviderErrorHandler:
    """Centralized error handling for providers."""

    def __init__(self):
        """Initialize error handler."""
        self.error_history: List[ProviderError] = []
        self.error_handlers: Dict[ErrorCategory, List[Callable]] = {}
        self.fallback_providers: List[str] = []
        self.retry_config = RetryConfig()

    def register_handler(
        self, category: ErrorCategory, handler: Callable[[ProviderError], Optional[Any]]
    ):
        """Register a custom error handler for a category.

        Args:
            category: Error category to handle
            handler: Function that takes ProviderError and returns optional result

        """
        if category not in self.error_handlers:
            self.error_handlers[category] = []
        self.error_handlers[category].append(handler)

    def set_fallback_providers(self, providers: List[str]):
        """Set ordered list of fallback providers.

        Args:
            providers: List of provider names in order of preference

        """
        self.fallback_providers = providers

    def handle_error(
        self, provider: str, error: Exception, context: Optional[Dict[str, Any]] = None
    ) -> ProviderError:
        """Handle and categorize a provider error.

        Args:
            provider: Provider name that raised the error
            error: The exception that was raised
            context: Additional context about the error

        Returns:
            Structured ProviderError object

        """
        # Categorize the error
        category, severity = self._categorize_error(error)

        # Create structured error
        provider_error = ProviderError(
            provider=provider,
            category=category,
            severity=severity,
            message=self._get_user_friendly_message(category, error),
            original_error=error,
            context=context or {},
            error_type=self._get_error_type(category),
        )

        # Log the error
        self._log_error(provider_error)

        # Store in history
        self.error_history.append(provider_error)

        # Run custom handlers
        self._run_handlers(provider_error)

        return provider_error

    def _categorize_error(
        self, error: Exception
    ) -> tuple[ErrorCategory, ErrorSeverity]:
        """Categorize an error based on its type and message.

        Args:
            error: The exception to categorize

        Returns:
            Tuple of (category, severity)

        """
        error_str = str(error).lower()
        type(error).__name__

        # Authentication errors
        if any(
            x in error_str
            for x in ["api key", "authentication", "unauthorized", "forbidden"]
        ):
            return ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL

        # Network errors
        if any(
            x in error_str
            for x in ["connection", "network", "dns", "ssl", "certificate"]
        ):
            return ErrorCategory.NETWORK, ErrorSeverity.HIGH

        # Rate limiting
        if any(x in error_str for x in ["rate limit", "too many requests", "429"]):
            return ErrorCategory.API_LIMIT, ErrorSeverity.MEDIUM

        # Timeout errors
        if any(x in error_str for x in ["timeout", "timed out"]):
            return ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM

        # Model unavailable
        if any(x in error_str for x in ["model", "not found", "unavailable"]):
            return ErrorCategory.MODEL_UNAVAILABLE, ErrorSeverity.HIGH

        # Session errors
        if any(x in error_str for x in ["session", "tmux", "terminal"]):
            return ErrorCategory.SESSION, ErrorSeverity.MEDIUM

        # Resource errors
        if any(x in error_str for x in ["memory", "disk", "resource", "quota"]):
            return ErrorCategory.RESOURCE, ErrorSeverity.HIGH

        # Invalid request
        if any(x in error_str for x in ["invalid", "bad request", "400"]):
            return ErrorCategory.INVALID_REQUEST, ErrorSeverity.LOW

        # Initialization errors
        if any(x in error_str for x in ["init", "setup", "config", "not found at"]):
            return ErrorCategory.INITIALIZATION, ErrorSeverity.CRITICAL

        # Critical errors
        if any(x in error_str for x in ["critical", "fatal", "severe"]):
            return ErrorCategory.UNKNOWN, ErrorSeverity.CRITICAL

        # Default
        return ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM

    def _get_error_type(self, category: ErrorCategory) -> ErrorType:
        """Get error type from category for backward compatibility.

        Args:
            category: Error category

        Returns:
            Corresponding ErrorType

        """
        mapping = {
            ErrorCategory.AUTHENTICATION: ErrorType.AUTHENTICATION_ERROR,
            ErrorCategory.NETWORK: ErrorType.NETWORK_ERROR,
            ErrorCategory.API_LIMIT: ErrorType.API_LIMIT_ERROR,
            ErrorCategory.INVALID_REQUEST: ErrorType.INVALID_REQUEST_ERROR,
            ErrorCategory.MODEL_UNAVAILABLE: ErrorType.MODEL_UNAVAILABLE_ERROR,
            ErrorCategory.SESSION: ErrorType.SESSION_ERROR,
            ErrorCategory.TIMEOUT: ErrorType.TIMEOUT_ERROR,
            ErrorCategory.RESOURCE: ErrorType.RESOURCE_ERROR,
            ErrorCategory.INITIALIZATION: ErrorType.INITIALIZATION_ERROR,
            ErrorCategory.UNKNOWN: ErrorType.PROVIDER_ERROR,
        }
        return mapping.get(category, ErrorType.PROVIDER_ERROR)

    def _get_user_friendly_message(
        self, category: ErrorCategory, error: Exception
    ) -> str:
        """Generate user-friendly error message.

        Args:
            category: Error category
            error: Original exception

        Returns:
            User-friendly error message

        """
        messages = {
            ErrorCategory.AUTHENTICATION: (
                "Authentication failed. Please check your API key or credentials. "
                "Set the appropriate environment variable (e.g., VENICE_API_KEY, ANTHROPIC_API_KEY)."
            ),
            ErrorCategory.NETWORK: (
                "Network connection error. Please check your internet connection and try again. "
                "If using a proxy, ensure it's properly configured."
            ),
            ErrorCategory.API_LIMIT: (
                "API rate limit reached. Please wait a moment before retrying. "
                "Consider upgrading your plan or reducing request frequency."
            ),
            ErrorCategory.TIMEOUT: (
                "Request timed out. The provider is taking longer than expected to respond. "
                "Try again or consider using a different model."
            ),
            ErrorCategory.MODEL_UNAVAILABLE: (
                "The requested model is not available. Please check the model name and availability. "
                "Use 'hydra provider list-models' to see available models."
            ),
            ErrorCategory.SESSION: (
                "Session management error. The interactive session may have been terminated. "
                "Try creating a new session or restarting the provider."
            ),
            ErrorCategory.RESOURCE: (
                "Resource limit exceeded. The system may be low on memory or disk space. "
                "Try closing other applications or freeing up disk space."
            ),
            ErrorCategory.INVALID_REQUEST: (
                "Invalid request format. Please check your input and try again. "
                "Ensure the prompt and parameters are correctly formatted."
            ),
            ErrorCategory.INITIALIZATION: (
                "Provider initialization failed. Please check the provider configuration. "
                "Ensure all required dependencies are installed and paths are correct."
            ),
            ErrorCategory.UNKNOWN: (
                f"An unexpected error occurred: {str(error)}. "
                "Please check the logs for more details."
            ),
        }

        base_message = messages.get(category, str(error))

        # Add specific details from the error if available
        error_str = str(error)
        if len(error_str) < 200 and error_str not in base_message:
            base_message += f"\nDetails: {error_str}"

        return base_message

    def _log_error(self, error: ProviderError):
        """Log error with appropriate level.

        Args:
            error: The provider error to log

        """
        log_levels = {
            ErrorSeverity.CRITICAL: logging.CRITICAL,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
        }

        level = log_levels.get(error.severity, logging.ERROR)
        logger.log(
            level,
            f"Provider error: {error}",
            extra={
                "provider": error.provider,
                "category": error.category.value,
                "severity": error.severity.value,
                "context": error.context,
            },
        )

    def _run_handlers(self, error: ProviderError):
        """Run registered handlers for the error category.

        Args:
            error: The provider error to handle

        """
        handlers = self.error_handlers.get(error.category, [])
        for handler in handlers:
            try:
                handler(error)
            except Exception as e:
                logger.error(f"Error in custom handler: {e}")

    def get_fallback_provider(self, current_provider: str) -> Optional[str]:
        """Get next fallback provider.

        Args:
            current_provider: The provider that failed

        Returns:
            Name of fallback provider or None

        """
        if not self.fallback_providers:
            return None

        try:
            current_index = self.fallback_providers.index(current_provider)
            if current_index < len(self.fallback_providers) - 1:
                return self.fallback_providers[current_index + 1]
        except ValueError:
            # Current provider not in list, return first fallback
            if self.fallback_providers:
                return self.fallback_providers[0]

        return None

    def should_retry(self, error: ProviderError) -> bool:
        """Check if error should be retried.

        Args:
            error: The provider error

        Returns:
            True if should retry

        """
        if error.retry_count >= self.retry_config.max_retries:
            return False

        return error.category in self.retry_config.retry_on

    def get_retry_delay(self, error: ProviderError) -> float:
        """Get delay before retry.

        Args:
            error: The provider error

        Returns:
            Delay in seconds

        """
        return self.retry_config.get_delay(error.retry_count)

    def clear_history(self, provider: Optional[str] = None):
        """Clear error history.

        Args:
            provider: Optional provider to clear history for

        """
        if provider:
            self.error_history = [
                e for e in self.error_history if e.provider != provider
            ]
        else:
            self.error_history.clear()

    def get_provider_health(self, provider: str) -> Dict[str, Any]:
        """Get health status of a provider based on error history.

        Args:
            provider: Provider name

        Returns:
            Health status dictionary

        """
        provider_errors = [e for e in self.error_history if e.provider == provider]

        if not provider_errors:
            return {"status": "healthy", "error_count": 0, "last_error": None}

        recent_errors = [
            e
            for e in provider_errors
            if time.time() - e.timestamp < 300  # Last 5 minutes
        ]

        critical_errors = [
            e
            for e in recent_errors
            if e.severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]
        ]

        status = "healthy"
        if len(critical_errors) > 0:
            status = "unhealthy"
        elif len(recent_errors) > 5:
            status = "degraded"

        return {
            "status": status,
            "error_count": len(recent_errors),
            "last_error": provider_errors[-1] if provider_errors else None,
            "critical_errors": len(critical_errors),
        }


# Global error handler instance
_error_handler = None


def get_error_handler() -> ProviderErrorHandler:
    """Get global error handler instance.

    Returns:
        Global ProviderErrorHandler instance

    """
    global _error_handler
    if _error_handler is None:
        _error_handler = ProviderErrorHandler()
    return _error_handler
