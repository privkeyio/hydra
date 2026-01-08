"""Action Executor System for Hydra.

This module provides the core infrastructure for parsing and executing
actions from LLM responses, enabling non-interactive providers to perform
file operations, run commands, and manage project state.
"""

from .errors import (
    ActionExecutorError,
    ExecutionError,
    ParseError,
    RollbackError,
    ValidationError,
)
from .file_executor import BinaryFileHandler, FileOperationsExecutor
from .interface import ActionExecutor
from .parser import MultiFileParser, ResponseParser
from .types import Action, ActionResult, ActionType, ExecutionContext

__all__ = [
    "ActionType",
    "Action",
    "ActionResult",
    "ExecutionContext",
    "ActionExecutor",
    "ActionExecutorError",
    "ParseError",
    "ExecutionError",
    "ValidationError",
    "RollbackError",
    "FileOperationsExecutor",
    "BinaryFileHandler",
    "ResponseParser",
    "MultiFileParser",
]
