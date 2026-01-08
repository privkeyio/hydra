"""Tests for the session management system."""

from unittest.mock import MagicMock, patch

from hydra.sessions.manager import (
    DirectProcessBackend,
    DockerBackend,
    ScreenBackend,
    SessionBackendType,
    SessionConfig,
    SessionManager,
    TmuxBackend,
)


class TestSessionManager:
    """Test the main SessionManager class."""

    def test_discover_backends(self):
        """Test that backends are discovered correctly."""
        manager = SessionManager(enable_persistence=False)
        backends = manager.get_available_backends()

        # At least DirectProcessBackend should always be available
        assert SessionBackendType.DIRECT_PROCESS in backends

    def test_select_backend_priority(self):
        """Test backend selection priority."""
        manager = SessionManager(enable_persistence=False)

        # Should select an available backend
        backend = manager.select_backend()
        assert backend is not None

    def test_session_state_persistence(self):
        """Test session state can be saved and loaded."""
        manager = SessionManager(enable_persistence=False)

        # Save a state
        state = {
            "session_id": "test_session",
            "backend_type": "tmux",
            "project_path": "/test/path",
        }
        manager.save_session_state("test_session", state)

        # Load the state
        loaded_state = manager.load_session_state("test_session")
        assert loaded_state is not None
        assert loaded_state["session_id"] == "test_session"
        assert loaded_state["backend_type"] == "tmux"


class TestDirectProcessBackend:
    """Test the DirectProcessBackend."""

    def test_is_available(self):
        """Test that DirectProcessBackend is always available."""
        config = SessionConfig()
        backend = DirectProcessBackend(config)
        assert backend.is_available() is True

    def test_backend_type(self):
        """Test backend type is correct."""
        config = SessionConfig()
        backend = DirectProcessBackend(config)
        assert backend.backend_type == SessionBackendType.DIRECT_PROCESS

    def test_generate_session_id(self):
        """Test session ID generation."""
        config = SessionConfig()
        backend = DirectProcessBackend(config)
        session_id = backend.generate_session_id("test")
        assert session_id.startswith("test_")
        assert len(session_id) > 5


class TestScreenBackend:
    """Test the ScreenBackend."""

    def test_backend_type(self):
        """Test backend type is correct."""
        config = SessionConfig()
        backend = ScreenBackend(config)
        assert backend.backend_type == SessionBackendType.SCREEN

    @patch("subprocess.run")
    def test_is_available_true(self, mock_run):
        """Test when screen is available."""
        mock_run.return_value = MagicMock(returncode=0)
        config = SessionConfig()
        backend = ScreenBackend(config)
        assert backend.is_available() is True

    @patch("subprocess.run")
    def test_is_available_false(self, mock_run):
        """Test when screen is not available."""
        mock_run.side_effect = FileNotFoundError()
        config = SessionConfig()
        backend = ScreenBackend(config)
        assert backend.is_available() is False


class TestBackendAbstraction:
    """Test that all backends implement the required interface."""

    def test_all_backends_have_required_methods(self):
        """Verify all backends implement the abstract interface."""
        config = SessionConfig()

        backends = [
            TmuxBackend(config),
            DirectProcessBackend(config),
            DockerBackend(config),
            ScreenBackend(config),
        ]

        for backend in backends:
            # Check all required methods exist
            assert hasattr(backend, "backend_type")
            assert hasattr(backend, "is_available")
            assert hasattr(backend, "create_session")
            assert hasattr(backend, "session_exists")
            assert hasattr(backend, "send_input")
            assert hasattr(backend, "capture_output")
            assert hasattr(backend, "terminate_session")
            assert hasattr(backend, "list_sessions")
            assert hasattr(backend, "get_session_info")
            assert hasattr(backend, "cleanup")

            # Verify they are callable
            assert callable(backend.is_available)
            assert callable(backend.create_session)
            assert callable(backend.session_exists)
            assert callable(backend.send_input)
            assert callable(backend.capture_output)
            assert callable(backend.terminate_session)
            assert callable(backend.list_sessions)
            assert callable(backend.get_session_info)
            assert callable(backend.cleanup)
