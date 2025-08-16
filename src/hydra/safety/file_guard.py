"""File operation safety guard module.

Provides protection against unauthorized access to sensitive files and directories,
including .env files, .git directories, and other restricted locations.
"""

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class FileGuard:
    """Guards against unauthorized file operations."""

    # Protected file patterns (regex)
    PROTECTED_FILE_PATTERNS = [
        r".*\.env.*",  # .env, .env.local, .env.production, etc.
        r".*\.pem$",  # Private keys
        r".*\.key$",  # Private keys
        r".*\.crt$",  # Certificates
        r".*\.p12$",  # PKCS12 files
        r".*\.pfx$",  # Personal Information Exchange
        r".*id_rsa.*",  # SSH keys
        r".*id_dsa.*",  # SSH keys
        r".*id_ecdsa.*",  # SSH keys
        r".*id_ed25519.*",  # SSH keys
        r".*\.kdbx?$",  # KeePass databases
        r".*\.keystore$",  # Java keystores
        r".*\.jks$",  # Java keystores
    ]

    # Protected directory patterns
    PROTECTED_DIRECTORIES = [
        ".git",
        ".svn",
        ".hg",
        ".bzr",
        ".aws",
        ".ssh",
        ".gnupg",
        ".docker",
        ".kube",
        ".config/gcloud",
        ".azure",
        "node_modules/.cache",
    ]

    # System directories that should never be modified
    SYSTEM_DIRECTORIES = [
        "/etc",
        "/usr",
        "/bin",
        "/sbin",
        "/lib",
        "/lib64",
        "/boot",
        "/dev",
        "/proc",
        "/sys",
        "/root",
        "C:\\Windows",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
    ]

    def __init__(
        self,
        project_root: Optional[Path] = None,
        additional_protected_patterns: Optional[List[str]] = None,
        additional_protected_dirs: Optional[List[str]] = None,
    ):
        """Initialize FileGuard.

        Args:
            project_root: Root directory of the project (defaults to current working directory)
            additional_protected_patterns: Additional file patterns to protect
            additional_protected_dirs: Additional directories to protect

        """
        self.project_root = project_root or Path.cwd()
        self.protected_patterns = self.PROTECTED_FILE_PATTERNS.copy()
        self.protected_dirs = self.PROTECTED_DIRECTORIES.copy()

        if additional_protected_patterns:
            self.protected_patterns.extend(additional_protected_patterns)
        if additional_protected_dirs:
            self.protected_dirs.extend(additional_protected_dirs)

        self._compile_patterns()
        self._resolved_protected_dirs = self._resolve_protected_directories()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficiency."""
        self.protected_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.protected_patterns
        ]

    def _resolve_protected_directories(self) -> Set[Path]:
        """Resolve protected directories to absolute paths."""
        resolved = set()

        for dir_pattern in self.protected_dirs:
            # Check if it's an absolute path
            if os.path.isabs(dir_pattern):
                resolved.add(Path(dir_pattern))
            else:
                # Resolve relative to project root and home directory
                project_path = self.project_root / dir_pattern
                if project_path.exists():
                    resolved.add(project_path.resolve())

                home_path = Path.home() / dir_pattern
                if home_path.exists():
                    resolved.add(home_path.resolve())

        return resolved

    def validate_file_access(
        self, file_path: str, operation: str = "read"
    ) -> Tuple[bool, Optional[str]]:
        """Validate access to a file.

        Args:
            file_path: Path to the file
            operation: Type of operation (read, write, delete)

        Returns:
            Tuple of (is_allowed, error_message)

        """
        try:
            path = Path(file_path).resolve()
        except Exception as e:
            return False, f"Invalid file path: {e}"

        # Check if file matches protected patterns
        for pattern in self.protected_regex:
            if pattern.match(str(path)):
                error_msg = (
                    f"Access to protected file denied: {file_path}\n"
                    f"Operation '{operation}' is not allowed on sensitive files."
                )
                logger.warning(error_msg)
                return False, error_msg

        # Check if file is in a protected directory
        for protected_dir in self._resolved_protected_dirs:
            try:
                if protected_dir in path.parents or path == protected_dir:
                    error_msg = (
                        f"Access to protected directory denied: {file_path}\n"
                        f"Files in {protected_dir} cannot be modified."
                    )
                    logger.warning(error_msg)
                    return False, error_msg
            except ValueError:
                # Paths might be on different drives on Windows
                continue
        
        # Also check for protected directory names in the path
        for part in path.parts:
            if part in self.protected_dirs:
                error_msg = (
                    f"Access to protected directory denied: {file_path}\n"
                    f"Files in {part} directories cannot be modified."
                )
                logger.warning(error_msg)
                return False, error_msg

        # Check system directories
        for sys_dir in self.SYSTEM_DIRECTORIES:
            sys_path = Path(sys_dir)
            if sys_path.exists():
                try:
                    sys_path_resolved = sys_path.resolve()
                    if sys_path_resolved in path.parents or path == sys_path_resolved:
                        if operation != "read":
                            error_msg = (
                                f"Modification of system directory denied: {file_path}\n"
                                "System directories cannot be modified."
                            )
                            logger.warning(error_msg)
                            return False, error_msg
                except Exception:
                    continue

        # Additional checks for write/delete operations
        if operation in ["write", "delete"]:
            # Prevent operations outside project root (configurable)
            if not self._is_within_project(path):
                logger.info(f"File operation outside project root: {file_path}")
                # This is informational - not blocking by default

        logger.debug(f"File access allowed: {operation} on {file_path}")
        return True, None

    def _is_within_project(self, path: Path) -> bool:
        """Check if a path is within the project root.

        Args:
            path: Path to check

        Returns:
            True if path is within project root

        """
        try:
            path.relative_to(self.project_root)
            return True
        except ValueError:
            return False

    def scan_directory_for_sensitive_files(
        self, directory: Path
    ) -> List[Tuple[Path, str]]:
        """Scan a directory for potentially sensitive files.

        Args:
            directory: Directory to scan

        Returns:
            List of tuples (file_path, reason_for_sensitivity)

        """
        sensitive_files = []

        try:
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    # Check against protected patterns
                    for i, pattern in enumerate(self.protected_regex):
                        if pattern.match(str(file_path)):
                            reason = f"Matches protected pattern: {self.protected_patterns[i]}"
                            sensitive_files.append((file_path, reason))
                            break

                    # Check file permissions (Unix-like systems)
                    try:
                        mode = file_path.stat().st_mode
                        if mode & 0o077 == 0:  # No permissions for group/others
                            sensitive_files.append(
                                (file_path, "Restrictive file permissions")
                            )
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")

        return sensitive_files

    def get_safe_temp_directory(self) -> Path:
        """Get a safe temporary directory for file operations.

        Returns:
            Path to a safe temporary directory

        """
        import tempfile

        # Create a project-specific temp directory
        temp_base = Path(tempfile.gettempdir()) / "hydra_safe_temp"
        temp_base.mkdir(exist_ok=True, mode=0o700)  # Owner-only permissions

        # Create a session-specific subdirectory
        import uuid
        session_dir = temp_base / str(uuid.uuid4())
        session_dir.mkdir(mode=0o700)

        logger.info(f"Created safe temporary directory: {session_dir}")
        return session_dir

    def validate_symlink(self, link_path: Path) -> Tuple[bool, Optional[str]]:
        """Validate a symbolic link for safety.

        Args:
            link_path: Path to the symbolic link

        Returns:
            Tuple of (is_safe, warning_message)

        """
        if not link_path.is_symlink():
            return True, None

        try:
            target = link_path.resolve()

            # Check if symlink points to a protected location
            is_allowed, error = self.validate_file_access(str(target), "read")
            if not is_allowed:
                return False, f"Symlink points to protected location: {target}"

            # Check for symlink loops
            visited = set()
            current = link_path
            while current.is_symlink():
                if current in visited:
                    return False, "Symlink loop detected"
                visited.add(current)
                current = Path(os.readlink(current))

        except Exception as e:
            return False, f"Error validating symlink: {e}"

        return True, None
