"""File operation sandbox module.

Provides a sandboxed environment for file operations with comprehensive
validation and rollback capabilities.
"""

import hashlib
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from hydra.logging_config import get_logger
from hydra.safety.file_guard import FileGuard
from hydra.safety.operation_validator import OperationType, OperationValidator

logger = get_logger(__name__)


@dataclass
class FileOperation:
    """Represents a file operation for tracking and rollback."""

    operation_type: str  # create, modify, delete, move, copy
    source_path: Path
    target_path: Optional[Path] = None
    backup_path: Optional[Path] = None
    original_hash: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class FileSandbox:
    """Sandbox for safe file operations with validation and rollback."""

    def __init__(
        self,
        sandbox_root: Optional[Path] = None,
        enable_backups: bool = True,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB default
        allowed_extensions: Optional[Set[str]] = None,
        file_guard: Optional[FileGuard] = None,
        operation_validator: Optional[OperationValidator] = None,
    ):
        """Initialize FileSandbox.

        Args:
            sandbox_root: Root directory for sandboxed operations
            enable_backups: Whether to create backups before modifications
            max_file_size: Maximum allowed file size in bytes
            allowed_extensions: Set of allowed file extensions (None = all allowed)
            file_guard: FileGuard instance for additional validation
            operation_validator: OperationValidator for operation validation

        """
        if sandbox_root:
            self.sandbox_root = Path(sandbox_root).resolve()
            self.sandbox_root.mkdir(parents=True, exist_ok=True)
        else:
            self.sandbox_root = Path(
                tempfile.mkdtemp(prefix="hydra_sandbox_")
            ).resolve()

        self.enable_backups = enable_backups
        self.max_file_size = max_file_size
        self.allowed_extensions = allowed_extensions
        self.file_guard = file_guard or FileGuard()
        self.operation_validator = operation_validator or OperationValidator()

        # Track operations for rollback
        self.operations: List[FileOperation] = []
        self.backup_dir = self.sandbox_root / ".backups"
        if self.enable_backups:
            self.backup_dir.mkdir(exist_ok=True)

        logger.info(f"FileSandbox initialized at {self.sandbox_root}")

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hex digest of the file hash

        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _validate_path(self, path: Path, operation: str) -> Tuple[bool, Optional[str]]:
        """Validate a path for an operation.

        Args:
            path: Path to validate
            operation: Type of operation

        Returns:
            Tuple of (is_valid, error_message)

        """
        # Check with FileGuard
        is_allowed, error = self.file_guard.validate_file_access(str(path), operation)
        if not is_allowed:
            return False, error

        # Check with OperationValidator
        op_type_map = {
            "read": OperationType.FILE_READ,
            "write": OperationType.FILE_WRITE,
            "delete": OperationType.FILE_DELETE,
        }
        op_type = op_type_map.get(operation, OperationType.FILE_WRITE)
        is_allowed, reason, _ = self.operation_validator.validate_operation(
            op_type, str(path)
        )
        if not is_allowed:
            return False, reason

        # Check file size for read/write operations
        if operation in ["read", "write"] and path.exists():
            try:
                file_size = path.stat().st_size
                if file_size > self.max_file_size:
                    return (
                        False,
                        f"File size ({file_size} bytes) exceeds maximum ({self.max_file_size} bytes)",
                    )
            except Exception as e:
                return False, f"Error checking file size: {e}"

        # Check extension if restrictions are in place
        if self.allowed_extensions and operation == "write":
            if path.suffix.lower() not in self.allowed_extensions:
                return False, f"File extension {path.suffix} not in allowed list"

        return True, None

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """Create a backup of a file.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the backup file, or None if backup failed

        """
        if not self.enable_backups or not file_path.exists():
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.name}.{timestamp}.bak"
            backup_path = self.backup_dir / backup_name

            shutil.copy2(file_path, backup_path)
            logger.debug(f"Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup of {file_path}: {e}")
            return None

    @contextmanager
    def sandboxed_operation(self, description: str = ""):
        """Context manager for sandboxed operations with automatic rollback on failure.

        Args:
            description: Description of the operation

        Yields:
            The sandbox instance for operations

        """
        operation_start = len(self.operations)

        try:
            logger.info(f"Starting sandboxed operation: {description}")
            yield self
            logger.info(f"Completed sandboxed operation: {description}")
        except Exception as e:
            logger.error(f"Error in sandboxed operation: {e}")
            # Rollback operations since the start of this context
            self.rollback(operation_start)
            raise

    def read_file(self, file_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """Safely read a file.

        Args:
            file_path: Path to the file to read

        Returns:
            Tuple of (content, error_message)

        """
        file_path = file_path.resolve()

        # Validate the path
        is_valid, error = self._validate_path(file_path, "read")
        if not is_valid:
            logger.warning(f"Read denied for {file_path}: {error}")
            return None, error

        try:
            content = file_path.read_text()
            logger.debug(
                f"Successfully read {len(content)} characters from {file_path}"
            )
            return content, None
        except Exception as e:
            error_msg = f"Error reading file {file_path}: {e}"
            logger.error(error_msg)
            return None, error_msg

    def write_file(
        self, file_path: Path, content: str, create_dirs: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """Safely write to a file.

        Args:
            file_path: Path to the file to write
            content: Content to write
            create_dirs: Whether to create parent directories if they don't exist

        Returns:
            Tuple of (success, error_message)

        """
        file_path = file_path.resolve()

        # Validate the path
        is_valid, error = self._validate_path(file_path, "write")
        if not is_valid:
            logger.warning(f"Write denied for {file_path}: {error}")
            return False, error

        # Create backup if file exists
        backup_path = None
        original_hash = None
        if file_path.exists():
            original_hash = self._calculate_file_hash(file_path)
            backup_path = self._create_backup(file_path)

        try:
            # Create parent directories if needed
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the file
            file_path.write_text(content)

            # Record the operation
            operation = FileOperation(
                operation_type="modify" if backup_path else "create",
                source_path=file_path,
                backup_path=backup_path,
                original_hash=original_hash,
            )
            self.operations.append(operation)

            logger.info(f"Successfully wrote {len(content)} characters to {file_path}")
            return True, None

        except Exception as e:
            error_msg = f"Error writing file {file_path}: {e}"
            logger.error(error_msg)
            # Restore backup if available
            if backup_path and backup_path.exists():
                try:
                    shutil.copy2(backup_path, file_path)
                    logger.info(f"Restored file from backup: {file_path}")
                except Exception as restore_error:
                    logger.error(f"Failed to restore backup: {restore_error}")
            return False, error_msg

    def delete_file(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """Safely delete a file.

        Args:
            file_path: Path to the file to delete

        Returns:
            Tuple of (success, error_message)

        """
        file_path = file_path.resolve()

        # Validate the path
        is_valid, error = self._validate_path(file_path, "delete")
        if not is_valid:
            logger.warning(f"Delete denied for {file_path}: {error}")
            return False, error

        if not file_path.exists():
            return False, f"File does not exist: {file_path}"

        # Create backup before deletion
        backup_path = self._create_backup(file_path)
        original_hash = self._calculate_file_hash(file_path)

        try:
            file_path.unlink()

            # Record the operation
            operation = FileOperation(
                operation_type="delete",
                source_path=file_path,
                backup_path=backup_path,
                original_hash=original_hash,
            )
            self.operations.append(operation)

            logger.info(f"Successfully deleted {file_path}")
            return True, None

        except Exception as e:
            error_msg = f"Error deleting file {file_path}: {e}"
            logger.error(error_msg)
            return False, error_msg

    def move_file(
        self, source_path: Path, target_path: Path
    ) -> Tuple[bool, Optional[str]]:
        """Safely move a file.

        Args:
            source_path: Source file path
            target_path: Target file path

        Returns:
            Tuple of (success, error_message)

        """
        source_path = source_path.resolve()
        target_path = target_path.resolve()

        # Validate both paths
        is_valid, error = self._validate_path(source_path, "read")
        if not is_valid:
            return False, f"Source validation failed: {error}"

        is_valid, error = self._validate_path(target_path, "write")
        if not is_valid:
            return False, f"Target validation failed: {error}"

        if not source_path.exists():
            return False, f"Source file does not exist: {source_path}"

        # Create backup of target if it exists
        backup_path = None
        if target_path.exists():
            backup_path = self._create_backup(target_path)

        try:
            shutil.move(str(source_path), str(target_path))

            # Record the operation
            operation = FileOperation(
                operation_type="move",
                source_path=source_path,
                target_path=target_path,
                backup_path=backup_path,
            )
            self.operations.append(operation)

            logger.info(f"Successfully moved {source_path} to {target_path}")
            return True, None

        except Exception as e:
            error_msg = f"Error moving file: {e}"
            logger.error(error_msg)
            return False, error_msg

    def rollback(self, to_operation: Optional[int] = None) -> bool:
        """Rollback operations.

        Args:
            to_operation: Rollback to this operation index (None = rollback all)

        Returns:
            True if rollback was successful

        """
        if not self.operations:
            logger.info("No operations to rollback")
            return True

        operations_to_rollback = self.operations[to_operation:]
        success = True

        for operation in reversed(operations_to_rollback):
            try:
                if operation.operation_type == "create":
                    # Delete the created file only if it wasn't subsequently modified
                    # Check if there are any modify operations for this file after this create
                    has_subsequent_modify = any(
                        op.operation_type == "modify"
                        and op.source_path == operation.source_path
                        for op in self.operations[
                            self.operations.index(operation) + 1 :
                        ]
                    )
                    if not has_subsequent_modify and operation.source_path.exists():
                        operation.source_path.unlink()
                        logger.info(
                            f"Rolled back file creation: {operation.source_path}"
                        )

                elif operation.operation_type == "modify":
                    # Restore from backup
                    if operation.backup_path and operation.backup_path.exists():
                        shutil.copy2(operation.backup_path, operation.source_path)
                        logger.info(
                            f"Restored file from backup: {operation.source_path}"
                        )

                elif operation.operation_type == "delete":
                    # Restore from backup
                    if operation.backup_path and operation.backup_path.exists():
                        shutil.copy2(operation.backup_path, operation.source_path)
                        logger.info(f"Restored deleted file: {operation.source_path}")

                elif operation.operation_type == "move":
                    # Move back to original location
                    if operation.target_path and operation.target_path.exists():
                        shutil.move(
                            str(operation.target_path), str(operation.source_path)
                        )
                        logger.info(f"Rolled back move: {operation.source_path}")
                    # Restore original target if it was overwritten
                    if operation.backup_path and operation.backup_path.exists():
                        shutil.copy2(operation.backup_path, operation.target_path)

            except Exception as e:
                logger.error(f"Error rolling back operation: {e}")
                success = False

        # Remove rolled back operations from the list
        if to_operation is not None:
            self.operations = self.operations[:to_operation]
        else:
            self.operations.clear()

        return success

    def cleanup(self) -> None:
        """Clean up the sandbox environment."""
        try:
            if self.sandbox_root.exists() and str(self.sandbox_root).startswith("/tmp"):
                shutil.rmtree(self.sandbox_root)
                logger.info(f"Cleaned up sandbox: {self.sandbox_root}")
        except Exception as e:
            logger.error(f"Error cleaning up sandbox: {e}")

    def get_operation_history(self) -> List[Dict[str, Any]]:
        """Get the history of operations performed.

        Returns:
            List of operation details

        """
        return [
            {
                "type": op.operation_type,
                "source": str(op.source_path),
                "target": str(op.target_path) if op.target_path else None,
                "timestamp": op.timestamp.isoformat(),
                "has_backup": op.backup_path is not None,
            }
            for op in self.operations
        ]
