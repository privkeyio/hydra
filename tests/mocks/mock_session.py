"""Mock session management for testing."""

import time
from typing import Any, Dict, List, Optional


class MockSession:
    """Mock session for testing session-based operations."""

    def __init__(self, session_id: str, provider: str = "mock"):
        self.session_id = session_id
        self.provider = provider
        self.created_at = time.time()
        self.last_activity = time.time()
        self.active = True
        self.history = []
        self.state = {}
        self.error_count = 0

    def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        """Execute a mock command in the session."""
        self.last_activity = time.time()

        result = {
            "session_id": self.session_id,
            "command": command,
            "success": True,
            "output": f"Mock output for: {command}",
            "timestamp": self.last_activity,
            "kwargs": kwargs,
        }

        # Simulate some command failures
        if "fail" in command.lower() or "error" in command.lower():
            result["success"] = False
            result["error"] = "Mock command failure"
            self.error_count += 1

        self.history.append(result)
        return result

    def get_state(self) -> Dict[str, Any]:
        """Get current session state."""
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "active": self.active,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "command_count": len(self.history),
            "error_count": self.error_count,
            "state": self.state.copy(),
        }

    def set_state(self, key: str, value: Any):
        """Set a state value."""
        self.state[key] = value

    def close(self):
        """Close the session."""
        self.active = False

    def is_healthy(self) -> bool:
        """Check if session is healthy."""
        return self.active and (time.time() - self.last_activity) < 300  # 5 minutes


class MockSessionManager:
    """Mock session manager for testing session management."""

    def __init__(self):
        self.sessions: Dict[str, MockSession] = {}
        self.session_counter = 0

    def create_session(self, provider: str = "mock") -> MockSession:
        """Create a new mock session."""
        self.session_counter += 1
        session_id = f"mock-session-{self.session_counter}-{int(time.time())}"
        session = MockSession(session_id, provider)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[MockSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def list_sessions(self) -> List[MockSession]:
        """List all sessions."""
        return list(self.sessions.values())

    def close_session(self, session_id: str) -> bool:
        """Close a session."""
        if session_id in self.sessions:
            self.sessions[session_id].close()
            return True
        return False

    def cleanup_inactive(self, max_age_seconds: int = 300) -> int:
        """Clean up inactive sessions."""
        current_time = time.time()
        to_remove = []

        for session_id, session in self.sessions.items():
            if (
                not session.is_healthy()
                or (current_time - session.last_activity) > max_age_seconds
            ):
                to_remove.append(session_id)

        for session_id in to_remove:
            del self.sessions[session_id]

        return len(to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        active_sessions = sum(1 for s in self.sessions.values() if s.active)
        total_commands = sum(len(s.history) for s in self.sessions.values())
        total_errors = sum(s.error_count for s in self.sessions.values())

        return {
            "total_sessions": len(self.sessions),
            "active_sessions": active_sessions,
            "total_commands": total_commands,
            "total_errors": total_errors,
            "session_counter": self.session_counter,
        }
