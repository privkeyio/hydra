"""Hydra safety and security module.

This package provides comprehensive safety guards for file and git operations,
ensuring secure execution of agent tasks.
"""

from .claude_file_interceptor import ClaudeFileInterceptor, SmartFileLockManager
from .file_guard import FileGuard
from .file_lock import FileLockManager, get_file_lock_manager
from .git_guard import GitGuard
from .operation_validator import OperationValidator
from .rate_limiter import RateLimiter
from .sandbox import FileSandbox

__all__ = [
    "FileLockManager",
    "get_file_lock_manager",
    "ClaudeFileInterceptor",
    "SmartFileLockManager",
    "FileGuard",
    "GitGuard",
    "OperationValidator",
    "RateLimiter",
    "FileSandbox",
]
