"""Claude Code CLI Orchestrator for Hydra.

This module provides high-level orchestration for Claude Code CLI,
managing interactive sessions through tmux for complex development tasks.
"""

import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from hydra.providers.base import LLMConfig
from hydra.providers.claude_tmux import ClaudeTmuxProvider
from hydra.utils.claude_path import get_claude_cli_path


class TaskStatus(Enum):
    """Status of a Claude Code task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ClaudeCodeTask:
    """Represents a task for Claude Code to execute."""

    task_id: str
    description: str
    prompt: str
    working_directory: str
    timeout: int = 300
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    files_changed: List[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class ClaudeCodeOrchestrator:
    """Orchestrates Claude Code CLI for complex development tasks."""

    def __init__(self, claude_path: Optional[str] = None, default_timeout: int = 300):
        """Initialize the Claude Code orchestrator.

        Args:
            claude_path: Path to Claude Code CLI executable
            default_timeout: Default timeout for tasks in seconds

        """
        self.claude_path = claude_path or os.environ.get(
            'CLAUDE_CLI_PATH', get_claude_cli_path()
        )
        self.default_timeout = default_timeout
        self.active_sessions = {}
        self.task_history = []

        # Validate Claude Code is available
        self._validate_claude_installation()

    def _validate_claude_installation(self):
        """Validate that Claude Code CLI is installed and accessible."""
        if not Path(self.claude_path).exists():
            raise ValueError(f"Claude Code CLI not found at: {self.claude_path}")

        # Check if tmux is available
        try:
            subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            msg = ("tmux is required for Claude Code orchestration. "
                   "Install with: sudo apt-get install tmux")
            raise ValueError(msg) from None

    def create_task(
        self,
        description: str,
        prompt: str,
        working_directory: Optional[str] = None,
        timeout: Optional[int] = None,
        task_id: Optional[str] = None
    ) -> ClaudeCodeTask:
        """Create a new task for Claude Code to execute.

        Args:
            description: Short description of the task
            prompt: Full prompt for Claude Code
            working_directory: Directory to execute in (defaults to cwd)
            timeout: Task timeout in seconds
            task_id: Optional specific task ID (e.g., ticket number)

        Returns:
            ClaudeCodeTask instance

        """
        task = ClaudeCodeTask(
            task_id=task_id or str(uuid.uuid4())[:8],
            description=description,
            prompt=prompt,
            working_directory=working_directory or os.getcwd(),
            timeout=timeout or self.default_timeout
        )
        return task

    def execute_task(self, task: ClaudeCodeTask) -> ClaudeCodeTask:
        """Execute a Claude Code task using tmux provider.

        Args:
            task: The task to execute

        Returns:
            Updated task with results

        """
        print(f"🚀 Executing task: {task.description}")
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()

        try:
            # Create tmux provider config
            config = LLMConfig(
                provider_type='claude_tmux',
                timeout=task.timeout,
                extra_params={'claude_path': self.claude_path}
            )

            # Create provider instance
            provider = ClaudeTmuxProvider(config)

            # Execute the task
            result = provider.generate(
                task.prompt,
                cwd=task.working_directory,
                ticket_id=task.task_id
            )

            # Get files changed
            git_status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                cwd=task.working_directory
            )

            if git_status.stdout:
                task.files_changed = [
                    line.split()[-1] for line in git_status.stdout.strip().split('\n')
                    if line
                ]

            task.result = result
            task.status = TaskStatus.COMPLETED

        except subprocess.TimeoutExpired:
            task.status = TaskStatus.TIMEOUT
            task.error = f"Task timed out after {task.timeout} seconds"

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)

        finally:
            task.end_time = time.time()
            self.task_history.append(task)

        return task

    def execute_batch(
        self,
        tasks: List[ClaudeCodeTask],
        parallel: bool = False,
        max_parallel: int = 2
    ) -> List[ClaudeCodeTask]:
        """Execute multiple tasks in sequence or parallel.

        Args:
            tasks: List of tasks to execute
            parallel: Whether to run tasks in parallel
            max_parallel: Maximum parallel tasks (if parallel=True)

        Returns:
            List of completed tasks

        """
        if not parallel:
            # Sequential execution
            results = []
            for task in tasks:
                print(f"\n{'='*60}")
                print(f"Task {len(results)+1}/{len(tasks)}: {task.description}")
                print('='*60)
                result = self.execute_task(task)
                results.append(result)

                if result.status == TaskStatus.FAILED:
                    print(f"⚠️  Task failed: {result.error}")
                    if input("Continue with next task? (y/n): ").lower() != 'y':
                        break

            return results
        else:
            # Parallel execution using threading
            from concurrent.futures import ThreadPoolExecutor, as_completed

            results = []
            with ThreadPoolExecutor(max_workers=max_parallel) as executor:
                future_to_task = {
                    executor.submit(self.execute_task, task): task
                    for task in tasks
                }

                for future in as_completed(future_to_task):
                    task = future.result()
                    results.append(task)

            return results

    def create_development_session(
        self,
        project_path: str,
        session_name: Optional[str] = None
    ) -> str:
        """Create a persistent Claude Code development session.

        Args:
            project_path: Path to the project directory
            session_name: Optional session name (auto-generated if not provided)

        Returns:
            Session identifier

        """
        session_name = session_name or f"claude_dev_{uuid.uuid4().hex[:8]}"

        # Check if session already exists
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True
        )

        if result.returncode == 0:
            print(f"⚠️  Session {session_name} already exists")
            return session_name

        # Create new tmux session with Claude Code
        subprocess.run(
            [
                "tmux", "new-session", "-d", "-s", session_name,
                "-c", project_path,
                self.claude_path
            ],
            check=True
        )

        self.active_sessions[session_name] = {
            'project_path': project_path,
            'created_at': time.time()
        }

        print(f"✅ Created development session: {session_name}")
        print(f"📁 Project: {project_path}")
        print(f"💡 Attach with: tmux attach -t {session_name}")

        return session_name

    def attach_to_session(self, session_name: str):
        """Attach to an existing Claude Code session.

        Args:
            session_name: Name of the session to attach to

        """
        subprocess.run(["tmux", "attach", "-t", session_name])

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active Claude Code sessions.

        Returns:
            List of session information

        """
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True
        )

        sessions = []
        if result.returncode == 0:
            for session_name in result.stdout.strip().split('\n'):
                is_claude_session = session_name.startswith('claude_')
                is_hydra_session = session_name.startswith('hydra_')
                if is_claude_session or is_hydra_session:
                    session_info = self.active_sessions.get(session_name, {})
                    sessions.append({
                        'name': session_name,
                        'project_path': session_info.get('project_path', 'Unknown'),
                        'created_at': session_info.get('created_at', None)
                    })

        return sessions

    def kill_session(self, session_name: str):
        """Kill a Claude Code session.

        Args:
            session_name: Name of the session to kill

        """
        subprocess.run(["tmux", "kill-session", "-t", session_name])
        if session_name in self.active_sessions:
            del self.active_sessions[session_name]
        print(f"✅ Killed session: {session_name}")

    def get_task_summary(self) -> Dict[str, Any]:
        """Get summary of all executed tasks.

        Returns:
            Summary statistics

        """
        total = len(self.task_history)
        completed = sum(
            1 for t in self.task_history if t.status == TaskStatus.COMPLETED
        )
        failed = sum(1 for t in self.task_history if t.status == TaskStatus.FAILED)
        timeout = sum(1 for t in self.task_history if t.status == TaskStatus.TIMEOUT)

        total_time = sum(
            (t.end_time - t.start_time) for t in self.task_history
            if t.start_time and t.end_time
        )

        return {
            'total_tasks': total,
            'completed': completed,
            'failed': failed,
            'timeout': timeout,
            'success_rate': (completed / total * 100) if total > 0 else 0,
            'total_execution_time': total_time,
            'average_execution_time': (total_time / total) if total > 0 else 0
        }
