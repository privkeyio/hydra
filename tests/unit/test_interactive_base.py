"""Unit tests for interactive base provider interface."""

import time
from typing import Any, Dict, Optional, Set

import pytest

from src.hydra.providers.interactive_base import (
    InteractiveAIProvider,
    ProviderCapability,
    ProviderConfig,
    SessionInfo,
    SessionState,
    TaskResult,
)


class MockInteractiveProvider(InteractiveAIProvider):
    """Mock implementation of InteractiveAIProvider for testing."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._tool_available = True
        self._mock_capabilities = {
            ProviderCapability.FILE_OPERATIONS,
            ProviderCapability.TASK_EXECUTION,
            ProviderCapability.SESSION_PERSISTENCE,
        }
        self._session_states = {}

    def validate_config(self) -> None:
        if not self.config.provider_name:
            raise ValueError("Provider name is required")

    def discover_tool(self) -> bool:
        return self._tool_available

    def detect_capabilities(self) -> Set[ProviderCapability]:
        return self._mock_capabilities.copy()

    def start_session(
        self, session_id: Optional[str] = None, working_directory: Optional[str] = None
    ) -> str:
        if session_id is None:
            session_id = self.generate_session_id()

        session_info = SessionInfo(
            session_id=session_id,
            state=SessionState.ACTIVE,
            created_at=time.time(),
            last_activity=time.time(),
            working_directory=working_directory,
        )
        self._sessions[session_id] = session_info
        self._session_states[session_id] = {"working_dir": working_directory}
        return session_id

    def stop_session(self, session_id: str) -> None:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        self._sessions[session_id].state = SessionState.TERMINATED
        if session_id in self._session_states:
            del self._session_states[session_id]

    def execute_task(
        self, session_id: str, task_prompt: str, timeout: Optional[int] = None
    ) -> TaskResult:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")

        self._sessions[session_id].last_activity = time.time()

        return TaskResult(
            task_id=f"task_{session_id}_{len(task_prompt)}",
            success=True,
            output=f"Executed: {task_prompt[:50]}",
            execution_time=0.1,
        )

    def handle_prompt(
        self, session_id: str, prompt: str, auto_respond: bool = False
    ) -> str:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")

        if auto_respond:
            return "auto_response"
        return f"handled: {prompt}"

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        return self._session_states.get(session_id, {})

    def restore_session_state(self, session_id: str, state: Dict[str, Any]) -> None:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        self._session_states[session_id] = state


class TestProviderConfig:
    """Test ProviderConfig dataclass."""

    def test_default_config(self):
        config = ProviderConfig(provider_name="test")
        assert config.provider_name == "test"
        assert config.tool_executable is None
        assert config.auto_discover is True
        assert config.session_timeout == 300
        assert config.max_concurrent_sessions == 1
        assert len(config.capabilities) == 0
        assert len(config.extra_config) == 0

    def test_config_with_capabilities(self):
        capabilities = {
            ProviderCapability.FILE_OPERATIONS,
            ProviderCapability.TASK_EXECUTION,
        }
        config = ProviderConfig(provider_name="test", capabilities=capabilities)
        assert config.capabilities == capabilities

    def test_config_serialization(self):
        capabilities = {ProviderCapability.FILE_OPERATIONS}
        config = ProviderConfig(
            provider_name="test",
            tool_executable="/usr/bin/test",
            capabilities=capabilities,
            extra_config={"key": "value"},
        )

        data = config.to_dict()
        assert data["provider_name"] == "test"
        assert data["tool_executable"] == "/usr/bin/test"
        assert data["capabilities"] == ["file_operations"]
        assert data["extra_config"]["key"] == "value"

        restored_config = ProviderConfig.from_dict(data)
        assert restored_config.provider_name == config.provider_name
        assert restored_config.tool_executable == config.tool_executable
        assert restored_config.capabilities == config.capabilities
        assert restored_config.extra_config == config.extra_config


class TestSessionInfo:
    """Test SessionInfo dataclass."""

    def test_session_info_creation(self):
        session = SessionInfo(
            session_id="test_session",
            state=SessionState.ACTIVE,
            created_at=1000.0,
            last_activity=1100.0,
        )
        assert session.session_id == "test_session"
        assert session.state == SessionState.ACTIVE
        assert session.created_at == 1000.0
        assert session.last_activity == 1100.0

    def test_session_info_serialization(self):
        session = SessionInfo(
            session_id="test_session",
            state=SessionState.ACTIVE,
            created_at=1000.0,
            last_activity=1100.0,
            metadata={"key": "value"},
        )

        data = session.to_dict()
        assert data["state"] == "active"
        assert data["metadata"]["key"] == "value"

        restored_session = SessionInfo.from_dict(data)
        assert restored_session.state == SessionState.ACTIVE
        assert restored_session.metadata == session.metadata


class TestTaskResult:
    """Test TaskResult dataclass."""

    def test_task_result_creation(self):
        result = TaskResult(
            task_id="task_123",
            success=True,
            output="Success output",
            execution_time=1.5,
        )
        assert result.task_id == "task_123"
        assert result.success is True
        assert result.output == "Success output"
        assert result.execution_time == 1.5
        assert result.error is None

    def test_task_result_with_error(self):
        result = TaskResult(
            task_id="task_456", success=False, output="", error="Task failed"
        )
        assert result.success is False
        assert result.error == "Task failed"

    def test_task_result_serialization(self):
        result = TaskResult(
            task_id="task_789", success=True, output="Output", metadata={"info": "test"}
        )

        data = result.to_dict()
        restored_result = TaskResult.from_dict(data)

        assert restored_result.task_id == result.task_id
        assert restored_result.success == result.success
        assert restored_result.output == result.output
        assert restored_result.metadata == result.metadata


class TestInteractiveAIProvider:
    """Test InteractiveAIProvider abstract base class."""

    def test_provider_initialization(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        assert provider.config == config
        assert provider.name == "test_provider"
        assert len(provider._sessions) == 0

    def test_capability_detection(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        capabilities = provider.get_capabilities()
        assert ProviderCapability.FILE_OPERATIONS in capabilities
        assert ProviderCapability.TASK_EXECUTION in capabilities
        assert ProviderCapability.SESSION_PERSISTENCE in capabilities

    def test_has_capability(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        assert provider.has_capability(ProviderCapability.FILE_OPERATIONS)
        assert provider.has_capability(ProviderCapability.TASK_EXECUTION)
        assert not provider.has_capability(ProviderCapability.STREAMING_RESPONSE)

    def test_session_management(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        # Test session creation
        session_id = provider.start_session(working_directory="/test")
        assert session_id.startswith("test_provider_")

        # Test session info retrieval
        session_info = provider.get_session_info(session_id)
        assert session_info.session_id == session_id
        assert session_info.state == SessionState.ACTIVE
        assert session_info.working_directory == "/test"

        # Test session listing
        sessions = provider.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == session_id

        # Test session termination
        provider.stop_session(session_id)
        session_info = provider.get_session_info(session_id)
        assert session_info.state == SessionState.TERMINATED

    def test_session_not_found_errors(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        with pytest.raises(KeyError):
            provider.get_session_info("nonexistent")

        with pytest.raises(KeyError):
            provider.stop_session("nonexistent")

        with pytest.raises(KeyError):
            provider.execute_task("nonexistent", "test task")

    def test_task_execution(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        session_id = provider.start_session()
        result = provider.execute_task(session_id, "test task")

        assert isinstance(result, TaskResult)
        assert result.success is True
        assert "test task" in result.output
        assert result.execution_time is not None

    def test_prompt_handling(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        session_id = provider.start_session()

        # Test manual prompt handling
        response = provider.handle_prompt(session_id, "test prompt", auto_respond=False)
        assert "handled: test prompt" in response

        # Test auto prompt handling
        response = provider.handle_prompt(session_id, "test prompt", auto_respond=True)
        assert response == "auto_response"

    def test_session_state_persistence(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        session_id = provider.start_session()

        # Get initial state
        state = provider.get_session_state(session_id)

        # Modify and restore state
        test_state = {"test_key": "test_value"}
        provider.restore_session_state(session_id, test_state)
        restored_state = provider.get_session_state(session_id)

        assert restored_state == test_state

    def test_provider_state_serialization(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        # Create a session
        session_id = provider.start_session(working_directory="/test")

        # Serialize state
        state = provider.serialize_state()

        assert state["provider_name"] == "test_provider"
        assert session_id in state["sessions"]
        assert len(state["capabilities"]) > 0

        # Create new provider and deserialize state
        new_provider = MockInteractiveProvider(config)
        new_provider.deserialize_state(state)

        # Check restored sessions
        restored_sessions = new_provider.list_sessions()
        assert len(restored_sessions) == 1
        assert restored_sessions[0].session_id == session_id

    def test_generate_session_id(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        session_id = provider.generate_session_id()
        assert session_id.startswith("test_provider_")
        assert len(session_id) > len("test_provider_")

        # Generate another to ensure uniqueness
        another_id = provider.generate_session_id()
        assert session_id != another_id

    def test_provider_repr(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        provider.start_session()
        repr_str = repr(provider)

        assert "test_provider" in repr_str
        assert "sessions=1" in repr_str
        assert "capabilities=" in repr_str

    def test_config_validation_error(self):
        config = ProviderConfig(provider_name="")  # Empty name

        with pytest.raises(ValueError):
            MockInteractiveProvider(config)

    def test_session_id_custom(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        custom_id = "custom_session_123"
        returned_id = provider.start_session(session_id=custom_id)

        assert returned_id == custom_id
        assert custom_id in provider._sessions

    def test_discover_tool(self):
        config = ProviderConfig(provider_name="test_provider")
        provider = MockInteractiveProvider(config)

        assert provider.discover_tool() is True

        # Test when tool is not available
        provider._tool_available = False
        assert provider.discover_tool() is False
