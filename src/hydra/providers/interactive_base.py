"""Abstract base provider interface for interactive AI tools.

This module defines generic interfaces for ANY interactive AI tool, not just Claude Code.
It provides session management, task execution, and state persistence without tool-specific assumptions.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ProviderCapability(Enum):
    """Enumeration of provider capabilities."""

    FILE_OPERATIONS = "file_operations"
    SHELL_EXECUTION = "shell_execution"
    SESSION_PERSISTENCE = "session_persistence"
    STREAMING_RESPONSE = "streaming_response"
    CONCURRENT_SESSIONS = "concurrent_sessions"
    TASK_EXECUTION = "task_execution"
    PROMPT_HANDLING = "prompt_handling"
    STATE_SERIALIZATION = "state_serialization"
    TOOL_INTEGRATION = "tool_integration"
    MEMORY_MANAGEMENT = "memory_management"


class SessionState(Enum):
    """Enumeration of session states."""

    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    BUSY = "busy"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class ProviderConfig:
    """Configuration schema for interactive AI providers."""

    provider_name: str
    tool_executable: Optional[str] = None
    auto_discover: bool = True
    session_timeout: int = 300  # 5 minutes default
    max_concurrent_sessions: int = 1
    working_directory: Optional[str] = None
    environment_variables: Dict[str, str] = field(default_factory=dict)
    capabilities: Set[ProviderCapability] = field(default_factory=set)
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        result = asdict(self)
        result["capabilities"] = [cap.value for cap in self.capabilities]
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderConfig":
        """Create config from dictionary."""
        if "capabilities" in data:
            data["capabilities"] = {
                ProviderCapability(cap) for cap in data["capabilities"]
            }
        return cls(**data)


@dataclass
class SessionInfo:
    """Information about a provider session."""

    session_id: str
    state: SessionState
    created_at: float
    last_activity: float
    working_directory: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session info to dictionary."""
        result = asdict(self)
        result["state"] = self.state.value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionInfo":
        """Create session info from dictionary."""
        if "state" in data:
            data["state"] = SessionState(data["state"])
        return cls(**data)


@dataclass
class TaskResult:
    """Result of a task execution."""

    task_id: str
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task result to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        """Create task result from dictionary."""
        return cls(**data)


class InteractiveAIProvider(ABC):
    """Abstract base class for interactive AI tool providers.

    This interface defines generic methods for ANY interactive AI tool,
    supporting session management, task execution, and state persistence
    without tool-specific assumptions.
    """

    def __init__(self, config: ProviderConfig):
        """Initialize the provider with configuration."""
        self.config = config
        self._sessions: Dict[str, SessionInfo] = {}
        self._capabilities: Optional[Set[ProviderCapability]] = None
        self.validate_config()

    @abstractmethod
    def validate_config(self) -> None:
        """Validate provider-specific configuration.

        Raises:
            ValueError: If configuration is invalid.

        """
        pass

    @abstractmethod
    def discover_tool(self) -> bool:
        """Automatically discover the AI tool in system PATH.

        Returns:
            bool: True if tool was discovered and is available.

        """
        pass

    @abstractmethod
    def detect_capabilities(self) -> Set[ProviderCapability]:
        """Dynamically detect provider capabilities.

        Returns:
            Set[ProviderCapability]: Set of capabilities this provider supports.

        """
        pass

    @abstractmethod
    def start_session(
        self, session_id: Optional[str] = None, working_directory: Optional[str] = None
    ) -> str:
        """Start a new interactive session.

        Args:
            session_id: Optional session ID. If None, generates a new one.
            working_directory: Optional working directory for the session.

        Returns:
            str: The session ID.

        Raises:
            RuntimeError: If session cannot be started.

        """
        pass

    @abstractmethod
    def stop_session(self, session_id: str) -> None:
        """Stop an interactive session.

        Args:
            session_id: The session ID to stop.

        Raises:
            KeyError: If session doesn't exist.

        """
        pass

    @abstractmethod
    def execute_task(
        self, session_id: str, task_prompt: str, timeout: Optional[int] = None
    ) -> TaskResult:
        """Execute a task in the specified session.

        Args:
            session_id: The session ID to execute in.
            task_prompt: The task prompt/command to execute.
            timeout: Optional timeout in seconds.

        Returns:
            TaskResult: The result of task execution.

        Raises:
            KeyError: If session doesn't exist.
            TimeoutError: If task times out.

        """
        pass

    @abstractmethod
    def handle_prompt(
        self, session_id: str, prompt: str, auto_respond: bool = False
    ) -> str:
        """Handle an interactive prompt from the AI tool.

        Args:
            session_id: The session ID.
            prompt: The prompt text received.
            auto_respond: Whether to automatically respond to the prompt.

        Returns:
            str: The response to send back.

        Raises:
            KeyError: If session doesn't exist.

        """
        pass

    @abstractmethod
    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Get serializable state of a session.

        Args:
            session_id: The session ID.

        Returns:
            Dict[str, Any]: Serializable session state.

        Raises:
            KeyError: If session doesn't exist.

        """
        pass

    @abstractmethod
    def restore_session_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Restore a session from serialized state.

        Args:
            session_id: The session ID.
            state: The serialized session state.

        Raises:
            KeyError: If session doesn't exist.
            ValueError: If state is invalid.

        """
        pass

    def get_capabilities(self) -> Set[ProviderCapability]:
        """Get provider capabilities (cached).

        Returns:
            Set[ProviderCapability]: Set of capabilities this provider supports.

        """
        if self._capabilities is None:
            self._capabilities = self.detect_capabilities()
        return self._capabilities

    def has_capability(self, capability: ProviderCapability) -> bool:
        """Check if provider has a specific capability.

        Args:
            capability: The capability to check for.

        Returns:
            bool: True if provider has the capability.

        """
        return capability in self.get_capabilities()

    def list_sessions(self) -> List[SessionInfo]:
        """List all active sessions.

        Returns:
            List[SessionInfo]: List of session information.

        """
        return list(self._sessions.values())

    def get_session_info(self, session_id: str) -> SessionInfo:
        """Get information about a specific session.

        Args:
            session_id: The session ID.

        Returns:
            SessionInfo: Session information.

        Raises:
            KeyError: If session doesn't exist.

        """
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        return self._sessions[session_id]

    def generate_session_id(self) -> str:
        """Generate a unique session ID.

        Returns:
            str: A unique session ID.

        """
        return f"{self.config.provider_name}_{uuid.uuid4().hex[:8]}"

    def serialize_state(self) -> Dict[str, Any]:
        """Serialize provider state for persistence.

        Returns:
            Dict[str, Any]: Serializable provider state.

        """
        return {
            "provider_name": self.config.provider_name,
            "config": self.config.to_dict(),
            "sessions": {
                sid: session.to_dict() for sid, session in self._sessions.items()
            },
            "capabilities": [cap.value for cap in self.get_capabilities()],
        }

    def deserialize_state(self, state: Dict[str, Any]) -> None:
        """Deserialize provider state from persistence.

        Args:
            state: The serialized provider state.

        Raises:
            ValueError: If state format is invalid.

        """
        if "sessions" in state:
            self._sessions = {
                sid: SessionInfo.from_dict(session_data)
                for sid, session_data in state["sessions"].items()
            }

        if "capabilities" in state:
            self._capabilities = {
                ProviderCapability(cap) for cap in state["capabilities"]
            }

    @property
    def name(self) -> str:
        """Get the provider name.

        Returns:
            str: The provider name.

        """
        return self.config.provider_name

    def __repr__(self) -> str:
        """Get string representation of the provider."""
        active_sessions = len(
            [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]
        )
        capabilities_count = len(self.get_capabilities())
        return f"{self.name}(sessions={active_sessions}, capabilities={capabilities_count})"
