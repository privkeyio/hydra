"""Claude Code Agent module."""

import json
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from hydra.agents.base import CodeAgent
from hydra.config import get_config


class TaskType(Enum):
    FILE_OPERATION = "file_operation"
    CODE_GENERATION = "code_generation"
    SHELL_COMMAND = "shell_command"
    ANALYSIS = "analysis"
    PLANNING = "planning"


@dataclass
class FileOperation:
    action: str
    path: str
    content: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: Optional[str] = None


@dataclass
class Decision:
    context: str
    decision: str
    reasoning: str
    confidence: float
    timestamp: float = field(default_factory=time.time)
    task_id: Optional[str] = None


@dataclass
class ProgressEvent:
    event_type: str
    message: str
    timestamp: float = field(default_factory=time.time)
    task_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionContext:
    project_root: Path
    working_directory: Path
    known_files: Set[str] = field(default_factory=set)
    file_contents_cache: Dict[str, str] = field(default_factory=dict)
    current_task: Optional[str] = None
    task_history: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class ClaudeCodeAgent:
    def __init__(
        self,
        name: str,
        project_root: Optional[str] = None,
        max_context_size: int = 50000,
        memory_limit: int = 1000
    ):
        self.name = name
        self.agent_id = f"{name}_{uuid.uuid4().hex[:8]}"
        self.config = get_config()

        if project_root:
            self.project_root = Path(project_root).resolve()
        else:
            self.project_root = Path.cwd()

        self.session = SessionContext(
            project_root=self.project_root,
            working_directory=self.project_root
        )

        self.max_context_size = max_context_size
        self.memory_limit = memory_limit

        # Memory systems
        self.file_operations = deque(maxlen=memory_limit)
        self.decisions = deque(maxlen=memory_limit)
        self.progress_events = deque(maxlen=memory_limit)
        self.conversation_history = deque(maxlen=100)

        # State tracking
        self.active_tasks = {}
        self.completed_tasks = set()
        self.failed_tasks = set()

        # Performance metrics
        self.start_time = time.time()
        self.total_operations = 0
        self.successful_operations = 0

        # Initialize file system awareness
        self._scan_project_structure()

        self._log_progress("INIT", f"Agent {self.agent_id} initialized")

    def _scan_project_structure(self):
        """Scan and cache the project file structure."""
        try:
            for path in self.project_root.rglob("*"):
                if path.is_file() and not self._should_ignore_file(path):
                    relative_path = str(path.relative_to(self.project_root))
                    self.session.known_files.add(relative_path)

        except Exception as e:
            self._log_progress("ERROR", f"Failed to scan project: {e}")

    def _should_ignore_file(self, path: Path) -> bool:
        """Check if file should be ignored based on common patterns."""
        ignore_patterns = {
            '.git', '__pycache__', '.pytest_cache', 'node_modules',
            '.venv', 'venv', '.env', 'logs', '.DS_Store'
        }

        return any(pattern in str(path) for pattern in ignore_patterns)

    def _log_progress(
        self,
        event_type: str,
        message: str,
        task_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log a progress event."""
        event = ProgressEvent(
            event_type=event_type,
            message=message,
            task_id=task_id,
            details=details or {}
        )
        self.progress_events.append(event)

        # Also log to standard logger if available
        if hasattr(self, 'logger'):
            self.logger.info(f"[{event_type}] {message}")

    def _record_decision(
        self,
        context: str,
        decision: str,
        reasoning: str,
        confidence: float = 0.8,
        task_id: Optional[str] = None
    ):
        """Record a decision for future reference."""
        decision_record = Decision(
            context=context,
            decision=decision,
            reasoning=reasoning,
            confidence=confidence,
            task_id=task_id
        )
        self.decisions.append(decision_record)

    def _record_file_operation(
        self,
        action: str,
        path: str,
        content: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None
    ):
        """Record a file operation for tracking."""
        operation = FileOperation(
            action=action,
            path=path,
            content=content,
            success=success,
            error=error
        )
        self.file_operations.append(operation)

        self.total_operations += 1
        if success:
            self.successful_operations += 1

    def read_file(self, path: str) -> Tuple[bool, str]:
        """Read a file with caching and error handling."""
        try:
            file_path = self.project_root / path

            if not file_path.exists():
                error = f"File not found: {path}"
                self._record_file_operation("read", path, success=False,
                                            error=error)
                return False, error

            content = file_path.read_text(encoding='utf-8')

            # Cache content for context
            self.session.file_contents_cache[path] = content
            self.session.known_files.add(path)

            self._record_file_operation("read", path, success=True)
            self._log_progress("FILE_READ", f"Read {path} ({len(content)} chars)")

            return True, content

        except Exception as e:
            error = f"Failed to read {path}: {e}"
            self._record_file_operation("read", path, success=False, error=error)
            return False, error

    def write_file(self, path: str, content: str) -> Tuple[bool, str]:
        """Write a file with proper error handling."""
        try:
            file_path = self.project_root / path

            # Create directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(content, encoding='utf-8')

            # Update cache and tracking
            self.session.file_contents_cache[path] = content
            self.session.known_files.add(path)

            self._record_file_operation("write", path, content, success=True)
            self._log_progress("FILE_WRITE",
                               f"Wrote {path} ({len(content)} chars)")

            return True, "File written successfully"

        except Exception as e:
            error = f"Failed to write {path}: {e}"
            self._record_file_operation(
                "write", path, content, success=False, error=error
            )
            return False, error

    def edit_file(
        self, path: str, old_content: str, new_content: str
    ) -> Tuple[bool, str]:
        """Edit a file by replacing old content with new content."""
        try:
            success, current_content = self.read_file(path)
            if not success:
                return False, current_content

            if old_content not in current_content:
                error = "Old content not found in file"
                self._record_file_operation("edit", path, success=False,
                                            error=error)
                return False, error

            updated_content = current_content.replace(old_content, new_content)

            # Record the edit operation specifically
            success, result = self.write_file(path, updated_content)
            if success:
                self._record_file_operation("edit", path, updated_content, success=True)
            return success, result

        except Exception as e:
            error = f"Failed to edit {path}: {e}"
            self._record_file_operation("edit", path, success=False,
                                        error=error)
            return False, error

    def execute_command(
        self,
        command: str,
        timeout: int = 30,
        working_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a shell command with proper error handling."""
        try:
            work_dir = working_dir or str(self.session.working_directory)

            self._log_progress("COMMAND", f"Executing: {command}")

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=work_dir
            )

            execution_result = {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": command,
                "working_dir": work_dir
            }

            status = "SUCCESS" if execution_result["success"] else "ERROR"
            self._log_progress(
                f"COMMAND_{status}",
                f"Command completed with code {result.returncode}",
                details={"command": command, "output_length": len(result.stdout)}
            )

            return execution_result

        except subprocess.TimeoutExpired:
            error_result = {
                "success": False,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "returncode": -1,
                "command": command,
                "working_dir": work_dir
            }
            self._log_progress("COMMAND_TIMEOUT",
                               f"Command timed out: {command}")
            return error_result

        except Exception as e:
            error_result = {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "command": command,
                "working_dir": work_dir
            }
            self._log_progress("COMMAND_ERROR", f"Command failed: {e}")
            return error_result

    def analyze_task(self, task: str) -> Dict[str, Any]:
        """Analyze a task and determine the best approach."""
        self._log_progress("ANALYSIS", f"Analyzing task: {task[:100]}...")

        # Use the base agent's reasoning with enhanced context
        base_agent = CodeAgent(f"{self.name}_analyzer", safe_mode=True)

        context = self._build_context_prompt()
        enhanced_prompt = f"""
Context:
{context}

Task to analyze: {task}

Analyze this task considering the current project state and determine:
1. Task type and complexity
2. Required file operations
3. Dependencies and prerequisites
4. Estimated effort and time
5. Potential risks or challenges

Respond with valid JSON containing these fields:
- task_type: string
- complexity: "simple" | "moderate" | "complex"
- required_files: array of file paths
- dependencies: array of strings
- estimated_time_minutes: number
- risks: array of strings
- approach: string describing the strategy
"""

        try:
            result = base_agent.reason(enhanced_prompt)

            self._record_decision(
                context=f"Task analysis: {task[:200]}",
                decision=result.get("approach", "Unknown"),
                reasoning=f"Complexity: {result.get('complexity', 'unknown')}",
                confidence=0.8
            )

            return result

        except Exception as e:
            self._log_progress("ANALYSIS_ERROR", f"Failed to analyze task: {e}")
            return {
                "task_type": "unknown",
                "complexity": "moderate",
                "required_files": [],
                "dependencies": [],
                "estimated_time_minutes": 30,
                "risks": [str(e)],
                "approach": "Fallback approach due to analysis failure"
            }

    def _build_context_prompt(self) -> str:
        """Build a context prompt with current project state."""
        context_parts = [
            f"Project root: {self.project_root}",
            f"Working directory: {self.session.working_directory}",
            f"Known files: {len(self.session.known_files)}"
        ]

        # Add recent file operations
        recent_ops = list(self.file_operations)[-10:]
        if recent_ops:
            context_parts.append("Recent file operations:")
            for op in recent_ops:
                context_parts.append(f"  - {op.action}: {op.path}")

        # Add recent decisions
        recent_decisions = list(self.decisions)[-5:]
        if recent_decisions:
            context_parts.append("Recent decisions:")
            for decision in recent_decisions:
                context_parts.append(f"  - {decision.decision}: "
                                     f"{decision.reasoning}")

        return "\n".join(context_parts)

    def execute_long_running_task(
        self, task: str, timeout: int = 300
    ) -> Dict[str, Any]:
        """Execute a long-running task with progress tracking."""
        task_id = str(uuid.uuid4())[:8]

        self._log_progress("TASK_START", f"Starting task: {task[:100]}...",
                           task_id)
        self.active_tasks[task_id] = {
            "task": task,
            "start_time": time.time(),
            "status": "running"
        }

        try:
            # Analyze the task first
            analysis = self.analyze_task(task)

            # Create enhanced agent for execution
            executor = CodeAgent(f"{self.name}_executor", safe_mode=True)

            # Build comprehensive prompt with context
            context = self._build_context_prompt()
            execution_prompt = f"""
Context:
{context}

Analysis:
{json.dumps(analysis, indent=2)}

Task: {task}

Execute this task step by step, providing detailed output about your progress.
If you need to read files, create files, or execute commands, describe what
you're doing.
"""

            # Execute with progress tracking
            result = executor.complete_task(execution_prompt)

            # Record completion
            self.active_tasks[task_id]["status"] = "completed"
            self.active_tasks[task_id]["end_time"] = time.time()
            self.completed_tasks.add(task_id)

            self._log_progress(
                "TASK_COMPLETE", f"Task completed: {task[:100]}...", task_id
            )

            return {
                "success": True,
                "task_id": task_id,
                "analysis": analysis,
                "result": result,
                "execution_time": (
                    time.time() - self.active_tasks[task_id]["start_time"]
                )
            }

        except Exception as e:
            self.active_tasks[task_id]["status"] = "failed"
            self.active_tasks[task_id]["error"] = str(e)
            self.failed_tasks.add(task_id)

            self._log_progress("TASK_ERROR", f"Task failed: {e}", task_id)

            return {
                "success": False,
                "task_id": task_id,
                "error": str(e),
                "execution_time": (
                    time.time() - self.active_tasks[task_id]["start_time"]
                )
            }

    def get_progress_report(self) -> Dict[str, Any]:
        """Get a detailed progress report."""
        runtime = time.time() - self.start_time

        return {
            "agent_id": self.agent_id,
            "runtime_seconds": runtime,
            "total_operations": self.total_operations,
            "successful_operations": self.successful_operations,
            "success_rate": (
                self.successful_operations / self.total_operations
                if self.total_operations > 0 else 0
            ),
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "known_files": len(self.session.known_files),
            "cached_files": len(self.session.file_contents_cache),
            "recent_events": [
                {
                    "type": event.event_type,
                    "message": event.message,
                    "timestamp": event.timestamp
                }
                for event in list(self.progress_events)[-10:]
            ]
        }

    def maintain_context_across_interactions(self, interaction: str) -> str:
        """Maintain context across multiple interactions."""
        self.conversation_history.append({
            "timestamp": time.time(),
            "interaction": interaction,
            "context_size": len(self._build_context_prompt())
        })

        # Clean up old context if getting too large
        if len(self._build_context_prompt()) > self.max_context_size:
            self._cleanup_old_context()

        return self._build_context_prompt()

    def _cleanup_old_context(self):
        """Clean up old context to keep within limits."""
        # Remove oldest cached file contents
        if len(self.session.file_contents_cache) > 50:
            old_files = sorted(
                self.session.file_contents_cache.keys(),
                key=lambda f: len(self.session.file_contents_cache[f])
            )[:10]

            for file_path in old_files:
                del self.session.file_contents_cache[file_path]

        self._log_progress("CLEANUP", "Context cleanup completed")

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        return {
            "file_operations": len(self.file_operations),
            "decisions": len(self.decisions),
            "progress_events": len(self.progress_events),
            "conversation_history": len(self.conversation_history),
            "cached_files": len(self.session.file_contents_cache),
            "known_files": len(self.session.known_files),
            "active_tasks": len(self.active_tasks)
        }
