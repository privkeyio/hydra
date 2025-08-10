"""Generic session management system for Hydra.

Provides a provider-agnostic abstraction for terminal multiplexers,
direct process management, containerized execution, and other session backends.
"""

import os
import subprocess
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class SessionBackendType(Enum):
    """Types of session backends."""
    TMUX = "tmux"
    SCREEN = "screen"
    DIRECT_PROCESS = "direct_process"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"


@dataclass
class SessionInfo:
    """Information about a session."""
    session_id: str
    backend_type: SessionBackendType
    project_path: str
    created_at: float
    pid: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SessionConfig:
    """Configuration for a session."""
    session_id: Optional[str] = None
    project_path: Optional[str] = None
    environment: Optional[Dict[str, str]] = None
    timeout: int = 300
    metadata: Optional[Dict[str, Any]] = None


class SessionBackend(ABC):
    """Abstract interface for session management backends."""

    def __init__(self, config: SessionConfig):
        self.config = config

    @property
    @abstractmethod
    def backend_type(self) -> SessionBackendType:
        """Return the backend type."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available on the system."""
        pass

    @abstractmethod
    def create_session(self, command: List[str], session_id: Optional[str] = None) -> str:
        """Create a new session and return its ID."""
        pass

    @abstractmethod
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        pass

    @abstractmethod
    def send_input(self, session_id: str, text: str) -> bool:
        """Send input to a session."""
        pass

    @abstractmethod
    def capture_output(self, session_id: str) -> str:
        """Capture output from a session."""
        pass

    @abstractmethod
    def terminate_session(self, session_id: str) -> bool:
        """Terminate a session."""
        pass

    @abstractmethod
    def list_sessions(self) -> List[SessionInfo]:
        """List all active sessions managed by this backend."""
        pass

    @abstractmethod
    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get information about a specific session."""
        pass

    def generate_session_id(self, prefix: str = "hydra") -> str:
        """Generate a unique session ID."""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def cleanup(self):
        """Clean up any resources used by this backend."""
        pass


class TmuxBackend(SessionBackend):
    """Tmux session backend implementation."""

    @property
    def backend_type(self) -> SessionBackendType:
        return SessionBackendType.TMUX

    def is_available(self) -> bool:
        """Check if tmux is available."""
        try:
            subprocess.run(["tmux", "-V"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def create_session(self, command: List[str], session_id: Optional[str] = None) -> str:
        """Create a new tmux session."""
        if session_id is None:
            session_id = self.generate_session_id("tmux")
        
        # Terminate any existing session with the same name
        if self.session_exists(session_id):
            self.terminate_session(session_id)

        project_path = self.config.project_path or os.getcwd()
        
        # Build tmux command
        tmux_cmd = ["tmux", "new-session", "-d", "-s", session_id, "-c", project_path]
        tmux_cmd.extend(command)
        
        subprocess.run(tmux_cmd, check=True)
        return session_id

    def session_exists(self, session_id: str) -> bool:
        """Check if a tmux session exists."""
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_id],
            capture_output=True
        )
        return result.returncode == 0

    def send_input(self, session_id: str, text: str) -> bool:
        """Send input to a tmux session."""
        try:
            # For multiline text, use tmux's load-buffer/paste-buffer approach
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
                f.write(text)
                temp_file = f.name

            try:
                subprocess.run(
                    ["tmux", "load-buffer", "-t", session_id, temp_file],
                    capture_output=True, check=True
                )
                subprocess.run(
                    ["tmux", "paste-buffer", "-t", session_id],
                    capture_output=True, check=True
                )
                subprocess.run(
                    ["tmux", "send-keys", "-t", session_id, "Enter"],
                    capture_output=True, check=True
                )
                return True
            finally:
                Path(temp_file).unlink(missing_ok=True)
        except subprocess.CalledProcessError:
            return False

    def capture_output(self, session_id: str) -> str:
        """Capture output from a tmux session."""
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_id, "-p"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return ""

    def terminate_session(self, session_id: str) -> bool:
        """Terminate a tmux session."""
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", session_id],
                capture_output=True, check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def list_sessions(self) -> List[SessionInfo]:
        """List all tmux sessions."""
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}:#{session_created}"],
                capture_output=True,
                text=True,
                check=True
            )
            sessions = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        session_id = parts[0]
                        created_at = float(parts[1])
                        sessions.append(SessionInfo(
                            session_id=session_id,
                            backend_type=self.backend_type,
                            project_path="",  # tmux doesn't provide this info directly
                            created_at=created_at
                        ))
            return sessions
        except subprocess.CalledProcessError:
            return []

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get information about a specific tmux session."""
        if not self.session_exists(session_id):
            return None
        
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-t", session_id, "-F", "#{session_created}"],
                capture_output=True,
                text=True,
                check=True
            )
            created_at = float(result.stdout.strip())
            return SessionInfo(
                session_id=session_id,
                backend_type=self.backend_type,
                project_path="",  # Not directly available
                created_at=created_at
            )
        except subprocess.CalledProcessError:
            return None


class DirectProcessBackend(SessionBackend):
    """Direct process session backend for systems without terminal multiplexers."""

    def __init__(self, config: SessionConfig):
        super().__init__(config)
        self._processes: Dict[str, subprocess.Popen] = {}
        self._session_data: Dict[str, SessionInfo] = {}

    @property
    def backend_type(self) -> SessionBackendType:
        return SessionBackendType.DIRECT_PROCESS

    def is_available(self) -> bool:
        """Direct process backend is always available."""
        return True

    def create_session(self, command: List[str], session_id: Optional[str] = None) -> str:
        """Create a new direct process session."""
        if session_id is None:
            session_id = self.generate_session_id("direct")
        
        # Terminate any existing session with the same name
        if self.session_exists(session_id):
            self.terminate_session(session_id)

        project_path = self.config.project_path or os.getcwd()
        env = dict(os.environ)
        if self.config.environment:
            env.update(self.config.environment)

        # Start the process
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=project_path,
            env=env,
            text=True,
            bufsize=1
        )

        self._processes[session_id] = process
        self._session_data[session_id] = SessionInfo(
            session_id=session_id,
            backend_type=self.backend_type,
            project_path=project_path,
            created_at=float(os.times().elapsed),
            pid=process.pid
        )

        return session_id

    def session_exists(self, session_id: str) -> bool:
        """Check if a direct process session exists."""
        if session_id not in self._processes:
            return False
        
        process = self._processes[session_id]
        return process.poll() is None

    def send_input(self, session_id: str, text: str) -> bool:
        """Send input to a direct process session."""
        if not self.session_exists(session_id):
            return False
        
        try:
            process = self._processes[session_id]
            process.stdin.write(text + '\n')
            process.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def capture_output(self, session_id: str) -> str:
        """Capture output from a direct process session."""
        if not self.session_exists(session_id):
            return ""
        
        try:
            process = self._processes[session_id]
            # Non-blocking read
            import select
            import sys
            
            if sys.platform != "win32" and select.select([process.stdout], [], [], 0.1)[0]:
                return process.stdout.read()
            return ""
        except (OSError, AttributeError):
            return ""

    def terminate_session(self, session_id: str) -> bool:
        """Terminate a direct process session."""
        if session_id not in self._processes:
            return False
        
        try:
            process = self._processes[session_id]
            process.terminate()
            
            # Wait a bit for graceful shutdown
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            
            del self._processes[session_id]
            if session_id in self._session_data:
                del self._session_data[session_id]
            return True
        except (ProcessLookupError, OSError):
            return False

    def list_sessions(self) -> List[SessionInfo]:
        """List all direct process sessions."""
        active_sessions = []
        sessions_to_remove = []
        
        for session_id, info in self._session_data.items():
            if self.session_exists(session_id):
                active_sessions.append(info)
            else:
                sessions_to_remove.append(session_id)
        
        # Clean up dead sessions
        for session_id in sessions_to_remove:
            if session_id in self._processes:
                del self._processes[session_id]
            if session_id in self._session_data:
                del self._session_data[session_id]
        
        return active_sessions

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get information about a specific direct process session."""
        if session_id in self._session_data and self.session_exists(session_id):
            return self._session_data[session_id]
        return None

    def cleanup(self):
        """Clean up all processes."""
        for session_id in list(self._processes.keys()):
            self.terminate_session(session_id)


class DockerBackend(SessionBackend):
    """Docker container session backend."""

    def __init__(self, config: SessionConfig):
        super().__init__(config)
        self._containers: Dict[str, str] = {}  # session_id -> container_id
        self.image = "python:3.11-slim"  # Default image

    @property
    def backend_type(self) -> SessionBackendType:
        return SessionBackendType.DOCKER

    def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def create_session(self, command: List[str], session_id: Optional[str] = None) -> str:
        """Create a new Docker container session."""
        if session_id is None:
            session_id = self.generate_session_id("docker")
        
        # Terminate any existing session with the same name
        if self.session_exists(session_id):
            self.terminate_session(session_id)

        project_path = self.config.project_path or os.getcwd()
        
        # Build docker run command
        docker_cmd = [
            "docker", "run", "-d", "-i",
            "--name", session_id,
            "-v", f"{project_path}:/workspace",
            "-w", "/workspace",
            self.image
        ]
        docker_cmd.extend(command)
        
        try:
            result = subprocess.run(docker_cmd, capture_output=True, text=True, check=True)
            container_id = result.stdout.strip()
            self._containers[session_id] = container_id
            return session_id
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create Docker session: {e}")

    def session_exists(self, session_id: str) -> bool:
        """Check if a Docker container session exists."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={session_id}"],
                capture_output=True,
                text=True
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def send_input(self, session_id: str, text: str) -> bool:
        """Send input to a Docker container session."""
        if not self.session_exists(session_id):
            return False
        
        try:
            subprocess.run(
                ["docker", "exec", "-i", session_id, "bash", "-c", f"echo '{text}'"],
                capture_output=True, check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def capture_output(self, session_id: str) -> str:
        """Capture output from a Docker container session."""
        if not self.session_exists(session_id):
            return ""
        
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", "50", session_id],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return ""

    def terminate_session(self, session_id: str) -> bool:
        """Terminate a Docker container session."""
        try:
            subprocess.run(
                ["docker", "stop", session_id],
                capture_output=True, check=True
            )
            subprocess.run(
                ["docker", "rm", session_id],
                capture_output=True, check=True
            )
            if session_id in self._containers:
                del self._containers[session_id]
            return True
        except subprocess.CalledProcessError:
            return False

    def list_sessions(self) -> List[SessionInfo]:
        """List all Docker container sessions."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}:{{.CreatedAt}}"],
                capture_output=True,
                text=True,
                check=True
            )
            sessions = []
            for line in result.stdout.strip().split('\n'):
                if line and line.startswith("docker_"):
                    parts = line.split(':')
                    if len(parts) >= 2:
                        session_id = parts[0]
                        # Docker CreatedAt format is complex, use current time as approximation
                        sessions.append(SessionInfo(
                            session_id=session_id,
                            backend_type=self.backend_type,
                            project_path="/workspace",
                            created_at=float(os.times().elapsed)
                        ))
            return sessions
        except subprocess.CalledProcessError:
            return []

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get information about a specific Docker container session."""
        if not self.session_exists(session_id):
            return None
        
        return SessionInfo(
            session_id=session_id,
            backend_type=self.backend_type,
            project_path="/workspace",
            created_at=float(os.times().elapsed)
        )

    def cleanup(self):
        """Clean up all containers."""
        for session_id in list(self._containers.keys()):
            self.terminate_session(session_id)


class SessionManager:
    """Main session manager that auto-discovers and uses the best available backend."""

    def __init__(self, preferred_backend: Optional[SessionBackendType] = None):
        self.preferred_backend = preferred_backend
        self._backends: Dict[SessionBackendType, SessionBackend] = {}
        self._active_backend: Optional[SessionBackend] = None
        self._discover_backends()

    def _discover_backends(self):
        """Discover available session backends."""
        config = SessionConfig()  # Default config for discovery
        
        # Try each backend type
        backends_to_try = [
            (SessionBackendType.TMUX, TmuxBackend),
            (SessionBackendType.DIRECT_PROCESS, DirectProcessBackend),
            (SessionBackendType.DOCKER, DockerBackend)
        ]
        
        for backend_type, backend_class in backends_to_try:
            try:
                backend = backend_class(config)
                if backend.is_available():
                    self._backends[backend_type] = backend
            except Exception:
                pass  # Backend not available

    def get_available_backends(self) -> List[SessionBackendType]:
        """Get list of available backends."""
        return list(self._backends.keys())

    def select_backend(self, backend_type: Optional[SessionBackendType] = None) -> SessionBackend:
        """Select the best available backend."""
        if backend_type and backend_type in self._backends:
            return self._backends[backend_type]
        
        if self.preferred_backend and self.preferred_backend in self._backends:
            return self._backends[self.preferred_backend]
        
        # Default priority order
        priority = [
            SessionBackendType.TMUX,
            SessionBackendType.DIRECT_PROCESS,
            SessionBackendType.DOCKER
        ]
        
        for backend_type in priority:
            if backend_type in self._backends:
                return self._backends[backend_type]
        
        raise RuntimeError("No session backend available")

    def create_session(
        self,
        command: List[str],
        config: Optional[SessionConfig] = None,
        backend_type: Optional[SessionBackendType] = None
    ) -> tuple[str, SessionBackend]:
        """Create a session using the best available backend."""
        backend = self.select_backend(backend_type)
        
        # Update backend config if provided
        if config:
            backend.config = config
        
        session_id = backend.create_session(command, config.session_id if config else None)
        return session_id, backend

    def get_session_backend(self, session_id: str) -> Optional[SessionBackend]:
        """Find which backend manages a specific session."""
        for backend in self._backends.values():
            if backend.session_exists(session_id):
                return backend
        return None

    def list_all_sessions(self) -> List[tuple[SessionInfo, SessionBackend]]:
        """List all sessions across all backends."""
        all_sessions = []
        for backend in self._backends.values():
            sessions = backend.list_sessions()
            for session in sessions:
                all_sessions.append((session, backend))
        return all_sessions

    def cleanup(self):
        """Clean up all backends."""
        for backend in self._backends.values():
            backend.cleanup()