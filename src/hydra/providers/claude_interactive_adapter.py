"""Claude provider adapter for InteractiveAIProvider interface.

This demonstrates how existing providers can inherit from the new abstract base
without breaking existing functionality.
"""
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set

from .interactive_base import (
    InteractiveAIProvider,
    ProviderCapability,
    ProviderConfig,
    SessionInfo,
    SessionState,
    TaskResult,
)


class ClaudeInteractiveAdapter(InteractiveAIProvider):
    """Adapter that wraps existing Claude providers to use the new interface."""

    def __init__(self, config: ProviderConfig):
        """Initialize with provider config."""
        super().__init__(config)
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    def validate_config(self) -> None:
        """Validate Claude CLI configuration."""
        if self.config.auto_discover:
            if not self.discover_tool():
                raise ValueError("Claude CLI not found in PATH or specified location")
        else:
            if not self.config.tool_executable:
                msg = "tool_executable must be specified when auto_discover is False"
                raise ValueError(msg)

            tool_path = Path(self.config.tool_executable)
            if not tool_path.exists():
                msg = f"Claude CLI not found at: {self.config.tool_executable}"
                raise ValueError(msg)

    def discover_tool(self) -> bool:
        """Automatically discover Claude CLI in system PATH."""
        from .discovery import ProviderDiscovery

        claude_config = ProviderDiscovery.discover_by_name('claude')
        if claude_config:
            if not self.config.tool_executable:
                self.config.tool_executable = claude_config.tool_executable
            return True

        # Check common installation paths
        common_paths = [
            '/home/kyle/.claude/local/claude',
            '/usr/local/bin/claude',
            '/opt/claude/bin/claude'
        ]

        for path in common_paths:
            if Path(path).exists():
                if not self.config.tool_executable:
                    self.config.tool_executable = path
                return True

        return False

    def detect_capabilities(self) -> Set[ProviderCapability]:
        """Detect Claude CLI capabilities."""
        capabilities = {
            ProviderCapability.FILE_OPERATIONS,
            ProviderCapability.SHELL_EXECUTION,
            ProviderCapability.TASK_EXECUTION,
            ProviderCapability.PROMPT_HANDLING,
            ProviderCapability.SESSION_PERSISTENCE,
            ProviderCapability.TOOL_INTEGRATION,
            ProviderCapability.MEMORY_MANAGEMENT
        }

        # Check if streaming is supported by trying to read help
        try:
            import subprocess
            result = subprocess.run(
                [self.config.tool_executable or 'claude', '--help'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if 'stream' in result.stdout.lower():
                capabilities.add(ProviderCapability.STREAMING_RESPONSE)
        except Exception:
            pass  # Streaming not supported or tool not accessible

        return capabilities

    def start_session(self, session_id: Optional[str] = None,
                     working_directory: Optional[str] = None) -> str:
        """Start a new Claude CLI session."""
        if session_id is None:
            session_id = self.generate_session_id()

        if session_id in self._sessions:
            raise ValueError(f"Session {session_id} already exists")

        # Create session info
        session_info = SessionInfo(
            session_id=session_id,
            state=SessionState.INITIALIZING,
            created_at=time.time(),
            last_activity=time.time(),
            working_directory=working_directory or os.getcwd(),
            metadata={
                'claude_path': self.config.tool_executable,
                'environment': dict(os.environ)
            }
        )

        try:
            # Initialize Claude session state
            session_state = {
                'working_directory': working_directory or os.getcwd(),
                'environment_vars': self.config.environment_variables.copy(),
                'session_history': [],
                'initialized': True
            }

            # Store session
            self._sessions[session_id] = session_info
            self._active_sessions[session_id] = session_state

            # Mark as active
            session_info.state = SessionState.ACTIVE

            return session_id

        except Exception as e:
            # Mark as error state
            session_info.state = SessionState.ERROR
            raise RuntimeError(f"Failed to start Claude session: {e}") from e

    def stop_session(self, session_id: str) -> None:
        """Stop a Claude CLI session."""
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")

        # Mark session as terminated
        self._sessions[session_id].state = SessionState.TERMINATED

        # Clean up session state
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]

    def execute_task(self, session_id: str, task_prompt: str,
                    timeout: Optional[int] = None) -> TaskResult:
        """Execute a task in the specified Claude session."""
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")

        session_info = self._sessions[session_id]
        if session_info.state != SessionState.ACTIVE:
            msg = f"Session {session_id} is not active (state: {session_info.state})"
            raise RuntimeError(msg)

        # Mark session as busy
        session_info.state = SessionState.BUSY
        session_info.last_activity = time.time()

        try:
            start_time = time.time()

            # Execute Claude CLI command
            import subprocess
            working_dir = session_info.working_directory or os.getcwd()
            env = os.environ.copy()
            env.update(self.config.environment_variables)

            # Use non-interactive mode for task execution
            result = subprocess.run(
                [self.config.tool_executable or 'claude', '--print', task_prompt],
                capture_output=True,
                text=True,
                timeout=timeout or self.config.session_timeout,
                cwd=working_dir,
                env=env
            )

            execution_time = time.time() - start_time

            # Create task result
            task_result = TaskResult(
                task_id=f"task_{session_id}_{int(time.time())}",
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None,
                execution_time=execution_time,
                metadata={
                    'return_code': result.returncode,
                    'working_directory': working_dir
                }
            )

            # Update session history
            session_state = self._active_sessions[session_id]
            session_state['session_history'].append({
                'task': task_prompt,
                'result': task_result.to_dict(),
                'timestamp': time.time()
            })

            return task_result

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Task execution timed out after {timeout} seconds")
        except Exception as e:
            return TaskResult(
                task_id=f"task_{session_id}_{int(time.time())}",
                success=False,
                output="",
                error=str(e),
                metadata={'exception_type': type(e).__name__}
            )
        finally:
            # Mark session as active again
            session_info.state = SessionState.ACTIVE

    def handle_prompt(self, session_id: str, prompt: str,
                     auto_respond: bool = False) -> str:
        """Handle an interactive prompt from Claude CLI."""
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")

        # For Claude CLI, most prompts can be auto-approved for basic operations
        if auto_respond:
            # Auto-approve safe operations
            safe_responses = {
                'continue': 'y',
                'proceed': 'y',
                'confirm': 'y',
                'yes/no': 'y'
            }

            prompt_lower = prompt.lower()
            for keyword, response in safe_responses.items():
                if keyword in prompt_lower:
                    return response

            return 'y'  # Default auto-response

        # For manual handling, return a descriptive response
        return f"Manual response needed for: {prompt[:100]}..."

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Get serializable state of a Claude session."""
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")

        session_state = self._active_sessions.get(session_id, {})
        session_info = self._sessions[session_id]

        return {
            'session_info': session_info.to_dict(),
            'state': session_state,
            'provider_config': self.config.to_dict()
        }

    def restore_session_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Restore a Claude session from serialized state."""
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")

        if 'state' in state:
            self._active_sessions[session_id] = state['state']

        if 'session_info' in state:
            # Update session info from restored state
            restored_info = SessionInfo.from_dict(state['session_info'])
            self._sessions[session_id] = restored_info


def create_claude_interactive_provider(claude_path: Optional[str] = None) -> ClaudeInteractiveAdapter:
    """Factory function to create a Claude interactive provider.
    
    Args:
        claude_path: Optional path to Claude CLI executable.
        
    Returns:
        ClaudeInteractiveAdapter: Configured Claude provider.

    """
    config = ProviderConfig(
        provider_name='claude_interactive',
        tool_executable=claude_path,
        auto_discover=claude_path is None,
        max_concurrent_sessions=5,
        session_timeout=300,
        capabilities={
            ProviderCapability.FILE_OPERATIONS,
            ProviderCapability.SHELL_EXECUTION,
            ProviderCapability.TASK_EXECUTION,
            ProviderCapability.PROMPT_HANDLING,
            ProviderCapability.SESSION_PERSISTENCE,
        }
    )

    return ClaudeInteractiveAdapter(config)
