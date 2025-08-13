"""Hydra State module."""

import atexit
import json
import shutil
import signal
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class SessionInfo:
    session_id: str
    start_time: str
    last_activity: str
    provider: str
    status: str
    working_directory: str
    task_history: List[Dict[str, Any]]
    metadata: Dict[str, Any]


@dataclass
class AppState:
    version: str
    last_update: str
    active_sessions: Dict[str, SessionInfo]
    global_config: Dict[str, Any]
    recent_tasks: List[Dict[str, Any]]
    performance_metrics: Dict[str, Any]


class HydraStateManager:
    """Manages persistent state for Hydra application in .hydra directory structure.

    Provides automatic saving, graceful shutdown, crash recovery, and state migration.
    """

    def __init__(self, hydra_dir: Optional[Union[str, Path]] = None):
        self.hydra_dir = Path(hydra_dir or ".hydra")
        self.sessions_dir = self.hydra_dir / "sessions"
        self.state_dir = self.hydra_dir / "state"
        self.recovery_dir = self.hydra_dir / "recovery"
        self.logs_dir = self.hydra_dir / "logs"

        self.state_file = self.state_dir / "app_state.json"
        self.backup_dir = self.state_dir / "archive"

        self._state = AppState(
            version="1.0.0",
            last_update="",
            active_sessions={},
            global_config={},
            recent_tasks=[],
            performance_metrics={}
        )

        self._lock = threading.RLock()
        self._auto_save_thread: Optional[threading.Thread] = None
        self._auto_save_interval = 300  # 5 minutes
        self._shutdown_requested = False

        self._initialize_directories()
        self._load_state()
        self._setup_auto_save()
        self._setup_signal_handlers()

    def _initialize_directories(self) -> None:
        """Create all required directories."""
        for directory in [self.hydra_dir, self.sessions_dir, self.state_dir,
                         self.recovery_dir, self.logs_dir, self.backup_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.shutdown()

        # Register handlers for common termination signals
        for sig in [signal.SIGTERM, signal.SIGINT]:
            signal.signal(sig, signal_handler)

        # Register atexit handler as fallback
        atexit.register(self.shutdown)

    def _setup_auto_save(self) -> None:
        """Start automatic state saving thread."""
        if self._auto_save_thread is not None:
            return

        def auto_save_worker():
            while not self._shutdown_requested:
                time.sleep(self._auto_save_interval)
                if not self._shutdown_requested:
                    try:
                        self._save_state_internal()
                    except Exception as e:
                        self._log_error(f"Auto-save failed: {e}")

        try:
            self._auto_save_thread = threading.Thread(target=auto_save_worker, daemon=True)
            self._auto_save_thread.start()
        except RuntimeError as e:
            # Handle thread creation failure gracefully in test environments
            self._log_error(f"Could not start auto-save thread: {e}")
            self._auto_save_thread = None

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def _log_error(self, message: str) -> None:
        """Log error to logs directory."""
        log_file = self.logs_dir / "state_manager.log"
        timestamp = self._get_timestamp()
        with open(log_file, "a") as f:
            f.write(f"{timestamp} ERROR: {message}\n")

    def _load_state(self) -> None:
        """Load application state from disk."""
        with self._lock:
            if self.state_file.exists():
                try:
                    with open(self.state_file, 'r') as f:
                        data = json.load(f)

                    # Convert session data back to SessionInfo objects
                    sessions = {}
                    active_sessions_data = data.get('active_sessions', {})
                    for session_id, session_data in active_sessions_data.items():
                        sessions[session_id] = SessionInfo(**session_data)

                    self._state = AppState(
                        version=data.get('version', '1.0.0'),
                        last_update=data.get('last_update', ''),
                        active_sessions=sessions,
                        global_config=data.get('global_config', {}),
                        recent_tasks=data.get('recent_tasks', []),
                        performance_metrics=data.get('performance_metrics', {})
                    )

                    # Migrate state if needed
                    self._migrate_state()

                except Exception as e:
                    self._log_error(f"Failed to load state: {e}")
                    # Keep default state if loading fails

    def _migrate_state(self) -> None:
        """Migrate state format for version compatibility."""
        current_version = "1.0.0"
        if self._state.version != current_version:
            # Perform migrations here as needed
            # For now, just update version
            self._state.version = current_version
            self._save_state_internal()

    def _save_state_internal(self) -> None:
        """Save state internally with error handling."""
        try:
            # Create backup before saving
            self._archive_current_state()

            # Prepare data for JSON serialization
            data = {
                'version': self._state.version,
                'last_update': self._get_timestamp(),
                'active_sessions': {
                    k: asdict(v) for k, v in self._state.active_sessions.items()
                },
                'global_config': self._state.global_config,
                'recent_tasks': self._state.recent_tasks,
                'performance_metrics': self._state.performance_metrics
            }

            # Write to temporary file first, then rename (atomic operation)
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            temp_file.rename(self.state_file)

        except Exception as e:
            self._log_error(f"Failed to save state: {e}")
            raise

    def _archive_current_state(self) -> None:
        """Archive current state file before overwriting."""
        if self.state_file.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_file = self.backup_dir / f"app_state_{timestamp}.json"
            shutil.copy2(self.state_file, archive_file)

            # Keep only last 10 archives
            archives = sorted(self.backup_dir.glob("app_state_*.json"))
            if len(archives) > 10:
                for old_archive in archives[:-10]:
                    old_archive.unlink()

    def save_state(self) -> None:
        """Save current application state to disk."""
        with self._lock:
            self._save_state_internal()

    def create_checkpoint(
        self, checkpoint_name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a checkpoint before risky operations."""
        with self._lock:
            timestamp = self._get_timestamp()
            filename = f"checkpoint_{checkpoint_name}_{timestamp}.json"
            checkpoint_file = self.recovery_dir / filename

            checkpoint_data = {
                'name': checkpoint_name,
                'timestamp': timestamp,
                'metadata': metadata or {},
                'state': {
                    'version': self._state.version,
                    'active_sessions': {
                        k: asdict(v) for k, v in self._state.active_sessions.items()
                    },
                    'global_config': self._state.global_config,
                    'recent_tasks': self._state.recent_tasks,
                    'performance_metrics': self._state.performance_metrics
                }
            }

            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

            return str(checkpoint_file)

    def restore_checkpoint(self, checkpoint_file: str) -> bool:
        """Restore state from a checkpoint."""
        with self._lock:
            try:
                with open(checkpoint_file, 'r') as f:
                    checkpoint_data = json.load(f)

                state_data = checkpoint_data['state']

                # Convert session data back to SessionInfo objects
                sessions = {}
                sessions_data = state_data.get('active_sessions', {})
                for session_id, session_data in sessions_data.items():
                    sessions[session_id] = SessionInfo(**session_data)

                self._state = AppState(
                    version=state_data.get('version', '1.0.0'),
                    last_update=self._get_timestamp(),
                    active_sessions=sessions,
                    global_config=state_data.get('global_config', {}),
                    recent_tasks=state_data.get('recent_tasks', []),
                    performance_metrics=state_data.get('performance_metrics', {})
                )

                self._save_state_internal()
                return True

            except Exception as e:
                self._log_error(f"Failed to restore checkpoint: {e}")
                return False

    def get_recovery_checkpoints(self) -> List[Dict[str, Any]]:
        """Get list of available recovery checkpoints."""
        checkpoints = []
        for checkpoint_file in self.recovery_dir.glob("checkpoint_*.json"):
            try:
                with open(checkpoint_file, 'r') as f:
                    data = json.load(f)
                checkpoints.append({
                    'file': str(checkpoint_file),
                    'name': data.get('name', 'unknown'),
                    'timestamp': data.get('timestamp', ''),
                    'metadata': data.get('metadata', {})
                })
            except Exception:
                continue
        return sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)

    def register_session(self, session_id: str, provider: str, working_directory: str,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        """Register a new active session."""
        with self._lock:
            session = SessionInfo(
                session_id=session_id,
                start_time=self._get_timestamp(),
                last_activity=self._get_timestamp(),
                provider=provider,
                status="active",
                working_directory=working_directory,
                task_history=[],
                metadata=metadata or {}
            )
            self._state.active_sessions[session_id] = session
            self._save_state_internal()

    def update_session_activity(
        self, session_id: str, task_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update session activity timestamp and optionally add task."""
        with self._lock:
            if session_id in self._state.active_sessions:
                session = self._state.active_sessions[session_id]
                session.last_activity = self._get_timestamp()

                if task_info:
                    session.task_history.append({
                        **task_info,
                        'timestamp': self._get_timestamp()
                    })
                    # Keep only last 50 tasks per session
                    session.task_history = session.task_history[-50:]

    def close_session(self, session_id: str) -> None:
        """Mark a session as closed."""
        with self._lock:
            if session_id in self._state.active_sessions:
                self._state.active_sessions[session_id].status = "closed"
                session = self._state.active_sessions[session_id]
                session.last_activity = self._get_timestamp()

    def remove_session(self, session_id: str) -> None:
        """Remove a session from active sessions."""
        with self._lock:
            if session_id in self._state.active_sessions:
                del self._state.active_sessions[session_id]
                self._save_state_internal()

    def get_active_sessions(self) -> Dict[str, SessionInfo]:
        """Get all active sessions."""
        with self._lock:
            return self._state.active_sessions.copy()

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get information about a specific session."""
        with self._lock:
            return self._state.active_sessions.get(session_id)

    def update_config(self, key: str, value: Any) -> None:
        """Update global configuration."""
        with self._lock:
            self._state.global_config[key] = value

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        with self._lock:
            return self._state.global_config.get(key, default)

    def add_recent_task(self, task_info: Dict[str, Any]) -> None:
        """Add task to recent tasks list."""
        with self._lock:
            task_entry = {
                **task_info,
                'timestamp': self._get_timestamp()
            }
            self._state.recent_tasks.append(task_entry)
            # Keep only last 100 tasks
            self._state.recent_tasks = self._state.recent_tasks[-100:]

    def get_recent_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent tasks."""
        with self._lock:
            return self._state.recent_tasks[-limit:]

    def update_metrics(self, metrics: Dict[str, Any]) -> None:
        """Update performance metrics."""
        with self._lock:
            self._state.performance_metrics.update(metrics)

    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        with self._lock:
            return self._state.performance_metrics.copy()

    def shutdown(self) -> None:
        """Graceful shutdown with state saving."""
        if self._shutdown_requested:
            return

        self._shutdown_requested = True

        try:
            # Save final state
            with self._lock:
                self._save_state_internal()

            # Stop auto-save thread
            if self._auto_save_thread and self._auto_save_thread.is_alive():
                self._auto_save_thread.join(timeout=5.0)

        except Exception as e:
            self._log_error(f"Error during shutdown: {e}")

    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current state for debugging."""
        with self._lock:
            return {
                'version': self._state.version,
                'last_update': self._state.last_update,
                'active_sessions_count': len(self._state.active_sessions),
                'recent_tasks_count': len(self._state.recent_tasks),
                'config_keys': list(self._state.global_config.keys()),
                'metrics_keys': list(self._state.performance_metrics.keys()),
                'directories': {
                    'hydra_dir': str(self.hydra_dir),
                    'sessions_dir': str(self.sessions_dir),
                    'state_dir': str(self.state_dir),
                    'recovery_dir': str(self.recovery_dir),
                    'logs_dir': str(self.logs_dir)
                }
            }


# Global state manager instance
_state_manager: Optional[HydraStateManager] = None


def get_state_manager(
    hydra_dir: Optional[Union[str, Path]] = None
) -> HydraStateManager:
    """Get or create global state manager instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = HydraStateManager(hydra_dir)
    return _state_manager


def cleanup_state_manager() -> None:
    """Cleanup global state manager."""
    global _state_manager
    if _state_manager is not None:
        _state_manager.shutdown()
        _state_manager = None
