"""Custom exceptions for Hydra system."""


class HydraError(Exception):
    """Base exception for Hydra system."""

    pass


class ConfigurationError(HydraError):
    """Configuration related errors."""

    pass


class ProviderError(HydraError):
    """LLM provider related errors."""

    pass


class AgentError(HydraError):
    """Agent execution errors."""

    pass


class WorkflowError(HydraError):
    """Workflow execution errors."""

    pass


class ValidationError(HydraError):
    """Data validation errors."""

    pass


class SecurityError(HydraError):
    """Security related errors."""

    pass


class RecursionLimitError(HydraError):
    """Agent depth/recursion limit exceeded."""

    pass


class CodeGenerationError(AgentError):
    """Code generation specific errors."""

    pass


class ExecutionTimeoutError(AgentError):
    """Code execution timeout errors."""

    pass
