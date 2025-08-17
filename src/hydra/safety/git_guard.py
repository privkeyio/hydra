"""Git operation safety guard module.

Provides protection against unauthorized git configuration modifications
and other potentially dangerous git operations.
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class GitGuard:
    """Guards against unauthorized git operations."""

    # Patterns for blocked git config commands
    BLOCKED_CONFIG_PATTERNS = [
        r"git\s+config\s+.*user\.(name|email)",
        r"git\s+config\s+.*core\.(editor|pager|excludesfile)",
        r"git\s+config\s+.*credential\.",
        r"git\s+config\s+.*http\.(proxy|sslVerify)",
        r"git\s+config\s+--global",
        r"git\s+config\s+--system",
    ]

    # Patterns for dangerous git operations
    DANGEROUS_OPERATIONS = [
        r"git\s+push\s+.*--force",
        r"git\s+push\s+.*-f\s",
        r"git\s+reset\s+--hard\s+HEAD",
        r"git\s+clean\s+-[xXdf]+",
        r"git\s+filter-branch",
        r"git\s+rebase\s+.*--force",
    ]

    # Safe git operations that are always allowed
    SAFE_OPERATIONS = [
        "git status",
        "git log",
        "git diff",
        "git branch",
        "git show",
        "git ls-files",
        "git blame",
        "git remote -v",
    ]

    def __init__(self, strict_mode: bool = True):
        """Initialize GitGuard.

        Args:
            strict_mode: If True, blocks all potentially dangerous operations.
                        If False, only blocks explicitly forbidden operations.

        """
        self.strict_mode = strict_mode
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficiency."""
        self.blocked_config_regex = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.BLOCKED_CONFIG_PATTERNS
        ]
        self.dangerous_ops_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.DANGEROUS_OPERATIONS
        ]

    def validate_git_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validate a git command for safety.

        Args:
            command: The git command to validate

        Returns:
            Tuple of (is_allowed, error_message)

        """
        command = command.strip()

        # Check if it's a git command
        if not command.startswith("git "):
            return True, None

        # Check against safe operations first
        for safe_op in self.SAFE_OPERATIONS:
            if command.startswith(safe_op):
                logger.debug(f"Git command allowed (safe operation): {command}")
                return True, None

        # Check for blocked config modifications
        for pattern in self.blocked_config_regex:
            if pattern.search(command):
                error_msg = (
                    f"Git configuration modification blocked: {command}\n"
                    "Modifying git configuration is not allowed for security reasons."
                )
                logger.warning(error_msg)
                return False, error_msg

        # Check for dangerous operations
        for pattern in self.dangerous_ops_regex:
            if pattern.search(command):
                error_msg = (
                    f"Dangerous git operation blocked: {command}\n"
                    "This operation could cause data loss or repository damage."
                )
                logger.warning(error_msg)
                return False, error_msg

        # In strict mode, require explicit allowlisting
        if self.strict_mode:
            # Allow basic operations even in strict mode
            basic_allowed = [
                "git add",
                "git commit",
                "git push",
                "git pull",
                "git fetch",
                "git checkout",
                "git merge",
                "git stash",
            ]

            for allowed in basic_allowed:
                if command.startswith(allowed):
                    # Additional checks for push
                    if command.startswith("git push") and (
                        "--force" in command or "-f" in command
                    ):
                        error_msg = "Force push is not allowed in strict mode"
                        logger.warning(f"{error_msg}: {command}")
                        return False, error_msg

                    logger.debug(f"Git command allowed: {command}")
                    return True, None

            error_msg = (
                f"Git command not explicitly allowed in strict mode: {command}\n"
                "Only basic git operations are permitted."
            )
            logger.info(error_msg)
            return False, error_msg

        logger.debug(f"Git command allowed: {command}")
        return True, None

    def check_git_hooks(self, repo_path: Path) -> Dict[str, List[str]]:
        """Check for potentially dangerous git hooks.

        Args:
            repo_path: Path to the git repository

        Returns:
            Dictionary of hook names to list of suspicious patterns found

        """
        suspicious_hooks = {}
        hooks_dir = repo_path / ".git" / "hooks"

        if not hooks_dir.exists():
            return suspicious_hooks

        # Patterns that might indicate malicious hooks
        suspicious_patterns = [
            r"curl\s+.*\|.*sh",  # Download and execute
            r"wget\s+.*\|.*sh",
            r"rm\s+-rf\s+/",  # Dangerous deletions
            r"chmod\s+777",  # Overly permissive permissions
            r"eval\s*\(",  # Dynamic code execution
            r"exec\s*\(",
        ]

        for hook_file in hooks_dir.glob("*"):
            if hook_file.is_file() and hook_file.stat().st_mode & 0o111:  # Executable
                try:
                    content = hook_file.read_text()
                    found_patterns = []

                    for pattern in suspicious_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            found_patterns.append(pattern)

                    if found_patterns:
                        suspicious_hooks[hook_file.name] = found_patterns
                        logger.warning(
                            f"Suspicious patterns found in git hook {hook_file.name}: {found_patterns}"
                        )
                except Exception as e:
                    logger.error(f"Error reading git hook {hook_file}: {e}")

        return suspicious_hooks

    def validate_remote_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """Validate a git remote URL for safety.

        Args:
            url: The remote URL to validate

        Returns:
            Tuple of (is_allowed, error_message)

        """
        # Block file:// URLs that could access local filesystem
        if url.startswith("file://"):
            return False, "Local file URLs are not allowed for security reasons"

        # Warn about non-standard protocols
        if not (url.startswith(("https://", "git@", "ssh://"))):
            logger.warning(f"Non-standard git remote URL: {url}")

        return True, None

    def get_safe_git_info(self, repo_path: Path) -> Dict[str, str]:
        """Get safe git repository information.

        Args:
            repo_path: Path to the git repository

        Returns:
            Dictionary of safe git information

        """
        info = {}

        try:
            # Get current branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info["current_branch"] = result.stdout.strip()

            # Get remote URLs (safe to expose)
            result = subprocess.run(
                ["git", "remote", "-v"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info["remotes"] = result.stdout.strip()

            # Get last commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info["head_commit"] = result.stdout.strip()[:8]

        except subprocess.TimeoutExpired:
            logger.error("Git command timed out")
        except Exception as e:
            logger.error(f"Error getting git info: {e}")

        return info
