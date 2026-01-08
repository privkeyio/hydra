"""Core types and data structures for the Action Executor system."""

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class ActionType(Enum):
    """Enumeration of all supported action types."""

    # File operations
    CREATE_FILE = auto()
    MODIFY_FILE = auto()
    DELETE_FILE = auto()
    APPEND_FILE = auto()
    REPLACE_IN_FILE = auto()
    MOVE_FILE = auto()
    COPY_FILE = auto()

    # Directory operations
    CREATE_DIRECTORY = auto()
    DELETE_DIRECTORY = auto()
    MOVE_DIRECTORY = auto()
    COPY_DIRECTORY = auto()

    # Command execution
    RUN_COMMAND = auto()
    RUN_SCRIPT = auto()
    INSTALL_PACKAGE = auto()

    # Git operations
    GIT_ADD = auto()
    GIT_COMMIT = auto()
    GIT_PUSH = auto()
    GIT_PULL = auto()
    GIT_CHECKOUT = auto()
    GIT_BRANCH = auto()
    GIT_MERGE = auto()
    GIT_STATUS = auto()

    # Testing operations
    RUN_TEST = auto()
    RUN_LINT = auto()
    RUN_FORMAT = auto()
    RUN_TYPECHECK = auto()

    # Build operations
    BUILD_PROJECT = auto()
    COMPILE_CODE = auto()
    PACKAGE_APPLICATION = auto()

    # Information gathering
    READ_FILE = auto()
    LIST_DIRECTORY = auto()
    CHECK_FILE_EXISTS = auto()
    GET_FILE_INFO = auto()

    # Environment operations
    SET_ENVIRONMENT_VAR = auto()
    CREATE_VIRTUAL_ENV = auto()
    ACTIVATE_VIRTUAL_ENV = auto()


@dataclass
class Action:
    """Represents a single action to be executed.

    Attributes:
        type: The type of action to perform
        target: The primary target (file path, command, etc.)
        content: The content for file operations or command arguments
        options: Additional options specific to the action type
        metadata: Extra metadata for tracking and debugging

    """

    type: ActionType
    target: str
    content: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate action after initialization."""
        if (
            self.type
            in [
                ActionType.CREATE_FILE,
                ActionType.MODIFY_FILE,
                ActionType.APPEND_FILE,
                ActionType.REPLACE_IN_FILE,
            ]
            and self.content is None
        ):
            raise ValueError(f"Action type {self.type.name} requires content")

    @property
    def requires_rollback(self) -> bool:
        """Check if this action type supports rollback."""
        return self.type in [
            ActionType.CREATE_FILE,
            ActionType.MODIFY_FILE,
            ActionType.DELETE_FILE,
            ActionType.APPEND_FILE,
            ActionType.REPLACE_IN_FILE,
            ActionType.MOVE_FILE,
            ActionType.CREATE_DIRECTORY,
            ActionType.DELETE_DIRECTORY,
            ActionType.MOVE_DIRECTORY,
        ]

    @property
    def is_safe(self) -> bool:
        """Check if this action is considered safe (read-only)."""
        return self.type in [
            ActionType.READ_FILE,
            ActionType.LIST_DIRECTORY,
            ActionType.CHECK_FILE_EXISTS,
            ActionType.GET_FILE_INFO,
            ActionType.GIT_STATUS,
        ]


@dataclass
class ActionResult:
    """Result of executing an action.

    Attributes:
        action: The action that was executed
        success: Whether the action succeeded
        output: The output from the action (stdout for commands, content for reads)
        error: Error message if the action failed
        rollback_data: Data needed to rollback this action
        execution_time: Time taken to execute in seconds

    """

    action: Action
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    rollback_data: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0

    @property
    def needs_retry(self) -> bool:
        """Check if this action should be retried."""
        if self.success:
            return False
        # Don't retry certain types of errors
        if self.error and any(
            msg in self.error.lower()
            for msg in ["permission denied", "file not found", "directory not empty"]
        ):
            return False
        return True


@dataclass
class ExecutionContext:
    """Context for executing a series of actions.

    Attributes:
        working_directory: The base directory for relative paths
        environment: Environment variables to set
        dry_run: If True, simulate actions without executing
        max_retries: Maximum number of retries for failed actions
        timeout: Maximum time for command execution in seconds
        rollback_on_failure: Whether to rollback on failure
        parallel_execution: Whether to execute independent actions in parallel
        user: User context for permission checks
        session_id: Unique session identifier

    """

    working_directory: Path
    environment: Dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    max_retries: int = 3
    timeout: int = 300
    rollback_on_failure: bool = True
    parallel_execution: bool = False
    user: Optional[str] = None
    session_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Ensure working_directory is a Path object."""
        if not isinstance(self.working_directory, Path):
            self.working_directory = Path(self.working_directory)

    def resolve_path(self, path: Union[str, Path]) -> Path:
        """Resolve a path relative to the working directory.

        Args:
            path: Path to resolve

        Returns:
            Absolute path resolved from working directory

        """
        path = Path(path) if not isinstance(path, Path) else path
        if path.is_absolute():
            return path
        return (self.working_directory / path).resolve()


@dataclass
class ActionBatch:
    """A batch of actions to be executed together.

    Attributes:
        actions: List of actions in this batch
        dependencies: Map of action indices to their dependencies
        parallel: Whether actions in this batch can run in parallel
        description: Human-readable description of the batch

    """

    actions: List[Action]
    dependencies: Dict[int, List[int]] = field(default_factory=dict)
    parallel: bool = False
    description: Optional[str] = None

    def get_execution_order(self) -> List[int]:
        """Get the order in which actions should be executed.

        Returns:
            List of action indices in execution order

        """
        if not self.dependencies:
            return list(range(len(self.actions)))

        # Topological sort for dependency resolution
        visited = set()
        order = []

        def visit(idx: int) -> None:
            if idx in visited:
                return
            visited.add(idx)
            for dep in self.dependencies.get(idx, []):
                visit(dep)
            order.append(idx)

        for i in range(len(self.actions)):
            visit(i)

        return order[::-1]
