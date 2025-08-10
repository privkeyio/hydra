"""Extended base provider interface for LLM abstraction."""

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional

from hydra.providers.base import LLMConfig, LLMProvider


class SessionState(Enum):
    """Session state enumeration."""

    ACTIVE = "active"
    IDLE = "idle"
    TERMINATED = "terminated"
    ERROR = "error"


class FileOperationType(Enum):
    """File operation types for interception."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    CREATE = "create"
    MODIFY = "modify"


@dataclass
class ModelInfo:
    """Model information container."""

    identifier: str  # Provider-specific identifier
    display_name: str  # User-friendly name
    category: str  # e.g., "fast", "smart", "balanced"
    context_window: int
    max_output_tokens: int
    supports_streaming: bool
    supports_interactive: bool
    cost_per_token: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """Provider session information."""

    id: str
    provider: str
    model: str
    created_at: datetime
    last_activity: datetime
    state: SessionState
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeBlock:
    """Extracted code block from response."""

    language: str
    content: str
    line_start: int
    line_end: int
    executable: bool = True
    filename: Optional[str] = None


@dataclass
class ParsedResponse:
    """Parsed provider response with metadata."""

    text: str
    code_blocks: List[CodeBlock]
    metadata: Dict[str, Any]
    tokens_used: Optional[int] = None
    execution_time: Optional[float] = None


@dataclass
class FileOperation:
    """File operation for interception."""

    operation_type: FileOperationType
    path: str
    content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseProvider(LLMProvider):
    """Extended abstract base class for all LLM providers.

    This class extends the basic LLMProvider with additional methods
    required for full provider abstraction as identified in the audit.
    """

    def __init__(self, config: LLMConfig):
        """Initialize provider with configuration.

        Args:
            config: Provider configuration

        """
        super().__init__(config)
        self._sessions: Dict[str, Session] = {}
        self._current_session: Optional[Session] = None

    # Core Generation Methods
    @abstractmethod
    def generate_code(
        self, prompt: str, context: Dict[str, Any], **kwargs
    ) -> str:
        """Generate code with context awareness.

        Args:
            prompt: The prompt for code generation
            context: Additional context (files, dependencies, etc.)
            **kwargs: Provider-specific parameters

        Returns:
            Generated code as string

        """
        pass

    @abstractmethod
    def generate_streaming(
        self, prompt: str, **kwargs
    ) -> Iterator[str]:
        """Generate streaming response for real-time output.

        Args:
            prompt: The prompt for generation
            **kwargs: Provider-specific parameters

        Yields:
            Chunks of generated text

        """
        pass

    # Session Management
    @abstractmethod
    def create_session(
        self, session_id: str, **kwargs
    ) -> Session:
        """Create a new provider session.

        Args:
            session_id: Unique identifier for the session
            **kwargs: Provider-specific session parameters

        Returns:
            Created session object

        """
        pass

    @abstractmethod
    def attach_session(self, session_id: str) -> Session:
        """Attach to existing session.

        Args:
            session_id: Session identifier to attach to

        Returns:
            Attached session object

        Raises:
            SessionError: If session doesn't exist

        """
        pass

    @abstractmethod
    def list_sessions(self) -> List[Session]:
        """List all active sessions.

        Returns:
            List of active session objects

        """
        pass

    @abstractmethod
    def kill_session(self, session_id: str) -> bool:
        """Terminate a session.

        Args:
            session_id: Session identifier to terminate

        Returns:
            True if successful, False otherwise

        """
        pass

    def save_session(self, session_id: str, path: str) -> bool:
        """Save session state for later restoration.

        Args:
            session_id: Session to save
            path: Path to save session data

        Returns:
            True if successful

        """
        # Default implementation - providers can override
        return False

    def restore_session(self, path: str) -> Optional[Session]:
        """Restore session from saved state.

        Args:
            path: Path to saved session data

        Returns:
            Restored session or None

        """
        # Default implementation - providers can override
        return None

    # Model Management
    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """List available models with metadata.

        Returns:
            List of available model information

        """
        pass

    @abstractmethod
    def select_model(self, model_identifier: str) -> bool:
        """Select a specific model by identifier.

        Args:
            model_identifier: Model to select (provider-specific or generic)

        Returns:
            True if model selected successfully

        """
        pass

    @abstractmethod
    def get_model_mapping(self) -> Dict[str, str]:
        """Map generic model names to provider-specific identifiers.

        Returns:
            Dictionary mapping generic names to provider identifiers

        """
        pass

    def get_current_model(self) -> Optional[ModelInfo]:
        """Get information about currently selected model.

        Returns:
            Current model info or None

        """
        models = self.list_models()
        current = self.config.model
        for model in models:
            if model.identifier == current or model.display_name == current:
                return model
        return None

    # Output Handling
    @abstractmethod
    def parse_response(self, response: str) -> ParsedResponse:
        """Parse provider-specific response format.

        Args:
            response: Raw response from provider

        Returns:
            Parsed response with metadata

        """
        pass

    @abstractmethod
    def extract_code_blocks(self, response: str) -> List[CodeBlock]:
        """Extract code blocks from response.

        Args:
            response: Response text containing code

        Returns:
            List of extracted code blocks

        """
        pass

    # Interactive Features
    @abstractmethod
    def supports_interactive(self) -> bool:
        """Check if provider supports interactive mode.

        Returns:
            True if interactive mode is supported

        """
        pass

    @abstractmethod
    def wait_for_prompt(self, timeout: int = 30) -> bool:
        """Wait for interactive prompt if supported.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if prompt detected, False on timeout

        """
        pass

    def send_interactive_command(self, command: str) -> Optional[str]:
        """Send command in interactive mode.

        Args:
            command: Command to send

        Returns:
            Response if available

        """
        if not self.supports_interactive():
            return None
        # Provider-specific implementation
        return None

    # File Operations
    @abstractmethod
    def intercept_file_operation(
        self, operation: FileOperation
    ) -> bool:
        """Intercept and validate file operations.

        Args:
            operation: File operation to intercept

        Returns:
            True if operation should proceed

        """
        pass

    def supports_file_interception(self) -> bool:
        """Check if provider supports file operation interception.

        Returns:
            True if file interception is supported

        """
        # Default to False, providers override if supported
        return False

    # Provider Capabilities
    def get_capabilities(self) -> Dict[str, bool]:
        """Get provider capability flags.

        Returns:
            Dictionary of capability flags

        """
        return {
            "interactive": self.supports_interactive(),
            "streaming": self.supports_streaming(),
            "file_interception": self.supports_file_interception(),
            "session_persistence": self.supports_session_persistence(),
            "code_execution": self.supports_code_execution(),
            "context_window_extension": self.supports_context_extension(),
        }

    def supports_streaming(self) -> bool:
        """Check if provider supports streaming responses.

        Returns:
            True if streaming is supported

        """
        # Default implementation - check if streaming method is overridden
        try:
            # For bound methods
            return (
                self.generate_streaming.__func__
                != BaseProvider.generate_streaming.__func__
            )
        except AttributeError:
            # For unbound methods or when __func__ is not available
            return (
                self.__class__.generate_streaming
                != BaseProvider.generate_streaming
            )

    def supports_session_persistence(self) -> bool:
        """Check if provider supports session save/restore.

        Returns:
            True if session persistence is supported

        """
        # Check if save/restore are overridden
        try:
            return (
                self.save_session.__func__ != BaseProvider.save_session.__func__
                or self.restore_session.__func__ != BaseProvider.restore_session.__func__
            )
        except AttributeError:
            # For unbound methods or when __func__ is not available
            return (
                self.__class__.save_session != BaseProvider.save_session
                or self.__class__.restore_session != BaseProvider.restore_session
            )

    def supports_code_execution(self) -> bool:
        """Check if provider can execute code directly.

        Returns:
            True if code execution is supported

        """
        # Default to False
        return False

    def supports_context_extension(self) -> bool:
        """Check if provider supports extended context windows.

        Returns:
            True if context extension is supported

        """
        # Default to False
        return False

    # Billing and Usage
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get provider usage statistics.

        Returns:
            Dictionary of usage metrics

        """
        return {
            "sessions_active": len(
                [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]
            ),
            "total_sessions": len(self._sessions),
            "current_model": self.config.model,
        }

    def estimate_cost(self, prompt: str, max_tokens: int) -> Optional[float]:
        """Estimate cost for a request.

        Args:
            prompt: Input prompt
            max_tokens: Maximum response tokens

        Returns:
            Estimated cost or None if not available

        """
        model_info = self.get_current_model()
        if model_info and model_info.cost_per_token:
            # Simple estimation - providers can override with better logic
            prompt_tokens = len(prompt.split()) * 1.3  # Rough token estimation
            total_tokens = prompt_tokens + max_tokens
            return total_tokens * model_info.cost_per_token
        return None

    # Prompt Management
    def preprocess_prompt(self, prompt: str) -> str:
        """Preprocess prompt before sending to provider.

        Args:
            prompt: Original prompt

        Returns:
            Preprocessed prompt

        """
        # Default implementation - providers can override
        return prompt

    def postprocess_response(self, response: str) -> str:
        """Postprocess response from provider.

        Args:
            response: Raw provider response

        Returns:
            Postprocessed response

        """
        # Default implementation - providers can override
        return response

    # Error Handling
    def handle_error(self, error: Exception) -> Optional[str]:
        """Handle provider-specific errors.

        Args:
            error: Exception that occurred

        Returns:
            Error message or None to propagate

        """
        # Use centralized error handler
        from .error_handler import get_error_handler

        error_handler = get_error_handler()
        provider_error = error_handler.handle_error(
            provider=self.name if hasattr(self, 'name') else 'unknown',
            error=error,
            context={'method': 'handle_error'}
        )

        # Return user-friendly message
        return str(provider_error)

    # Cleanup
    def cleanup(self) -> None:
        """Clean up provider resources."""
        # Terminate all sessions
        for session_id in list(self._sessions.keys()):
            self.kill_session(session_id)
        self._sessions.clear()
        self._current_session = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.cleanup()
        return False
