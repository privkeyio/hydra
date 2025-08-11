"""File operations executor for safe file creation and modification.

This module implements file-related actions with proper validation,
rollback support, and binary file handling.
"""

import base64
import hashlib
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Union

from .errors import ExecutionError, ValidationError
from .interface import ActionExecutor
from .types import Action, ActionResult, ActionType, ExecutionContext

logger = logging.getLogger(__name__)


class FileOperationsExecutor(ActionExecutor):
    """Executor for file system operations with rollback support.

    This executor handles all file-related actions including:
    - Creating new files
    - Modifying existing files
    - Handling binary files
    - Safe operations with backup and rollback

    Attributes:
        context: Execution context with configuration
        backup_dir: Directory for storing file backups
        file_checksums: Map of file paths to their checksums

    """

    def __init__(self, context: ExecutionContext) -> None:
        """Initialize the file operations executor.

        Args:
            context: The execution context

        """
        super().__init__(context)
        self.backup_dir = Path(tempfile.mkdtemp(prefix="hydra_backup_"))
        self.file_checksums: Dict[str, str] = {}
        self._created_files: set = set()
        self._modified_files: Dict[str, Path] = {}  # original -> backup

    def __del__(self) -> None:
        """Clean up backup directory on deletion."""
        try:
            if hasattr(self, 'backup_dir') and self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up backup directory: {e}")

    def execute(self, action: Action) -> ActionResult:
        """Execute a file-related action.

        Args:
            action: The action to execute

        Returns:
            Result of the execution

        """
        # Map action types to handler methods
        handlers = {
            ActionType.CREATE_FILE: self._create_file,
            ActionType.MODIFY_FILE: self._modify_file,
            ActionType.DELETE_FILE: self._delete_file,
            ActionType.APPEND_FILE: self._append_file,
            ActionType.REPLACE_IN_FILE: self._replace_in_file,
            ActionType.MOVE_FILE: self._move_file,
            ActionType.COPY_FILE: self._copy_file,
            ActionType.CREATE_DIRECTORY: self._create_directory,
            ActionType.DELETE_DIRECTORY: self._delete_directory,
            ActionType.READ_FILE: self._read_file,
        }

        handler = handlers.get(action.type)
        if not handler:
            return ActionResult(
                action=action,
                success=False,
                error=f"Unsupported action type: {action.type}"
            )

        # Execute with error handling
        try:
            if self.context.dry_run and not action.is_safe:
                return self._simulate_action(action)

            return handler(action)
        except Exception as e:
            logger.error(f"Action failed: {action.type.name} on {action.target}: {e}")
            return ActionResult(
                action=action,
                success=False,
                error=str(e)
            )

    def validate(self, action: Action) -> bool:
        """Validate a file action before execution.

        Args:
            action: The action to validate

        Returns:
            True if the action is valid

        Raises:
            ValidationError: If validation fails

        """
        # Check if action type is supported
        supported_types = {
            ActionType.CREATE_FILE,
            ActionType.MODIFY_FILE,
            ActionType.DELETE_FILE,
            ActionType.APPEND_FILE,
            ActionType.REPLACE_IN_FILE,
            ActionType.MOVE_FILE,
            ActionType.COPY_FILE,
            ActionType.CREATE_DIRECTORY,
            ActionType.DELETE_DIRECTORY,
            ActionType.READ_FILE,
        }

        if action.type not in supported_types:
            raise ValidationError(
                f"Unsupported action type: {action.type}",
                action=action
            )

        # Validate target path
        if not action.target:
            raise ValidationError("Missing target path", action=action)

        target_path = self.context.resolve_path(action.target)

        # Check for dangerous paths
        self._validate_safe_path(target_path, action)

        # Validate content requirements
        if action.type in [ActionType.CREATE_FILE, ActionType.MODIFY_FILE]:
            if action.content is None:
                raise ValidationError(
                    f"Action {action.type.name} requires content",
                    action=action
                )

        # Validate move/copy operations
        if action.type in [ActionType.MOVE_FILE, ActionType.COPY_FILE]:
            if "source" not in action.options:
                raise ValidationError(
                    f"Action {action.type.name} requires 'source' in options",
                    action=action
                )
            source_path = self.context.resolve_path(action.options["source"])
            self._validate_safe_path(source_path, action)

        return True

    def _perform_rollback(self, result: ActionResult) -> None:
        """Perform rollback for a file action.

        Args:
            result: The action result to rollback

        """
        action = result.action

        try:
            if action.type == ActionType.CREATE_FILE:
                # Delete the created file
                file_path = self.context.resolve_path(action.target)
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Rolled back file creation: {file_path}")

            elif action.type == ActionType.MODIFY_FILE:
                # Restore from backup
                if action.target in self._modified_files:
                    backup_path = self._modified_files[action.target]
                    file_path = self.context.resolve_path(action.target)
                    shutil.copy2(backup_path, file_path)
                    logger.info(f"Rolled back file modification: {file_path}")

            elif action.type == ActionType.DELETE_FILE:
                # Restore deleted file from backup if available
                if result.rollback_data and "backup_path" in result.rollback_data:
                    backup_path = Path(result.rollback_data["backup_path"])
                    file_path = self.context.resolve_path(action.target)
                    shutil.copy2(backup_path, file_path)
                    logger.info(f"Rolled back file deletion: {file_path}")

            elif action.type == ActionType.CREATE_DIRECTORY:
                # Remove the created directory
                dir_path = self.context.resolve_path(action.target)
                if dir_path.exists() and dir_path.is_dir():
                    shutil.rmtree(dir_path)
                    logger.info(f"Rolled back directory creation: {dir_path}")

        except Exception as e:
            logger.error(f"Rollback failed for {action.type.name}: {e}")
            raise

    def _create_file(self, action: Action) -> ActionResult:
        """Create a new file.

        Args:
            action: The create file action

        Returns:
            Result of file creation

        """
        file_path = self.context.resolve_path(action.target)

        # Check if file already exists
        if file_path.exists():
            if action.options.get("overwrite", False):
                # Backup existing file before overwrite
                self._backup_file(file_path, action.target)
            else:
                return ActionResult(
                    action=action,
                    success=False,
                    error=f"File already exists: {file_path}"
                )

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine if content is binary
        content = action.content or ""
        is_binary = action.options.get("binary", False)

        try:
            if is_binary:
                # Handle binary content (base64 encoded)
                binary_data = base64.b64decode(content)
                file_path.write_bytes(binary_data)
            else:
                # Handle text content
                encoding = action.options.get("encoding", "utf-8")
                file_path.write_text(content, encoding=encoding)

            # Track created file
            self._created_files.add(str(file_path))

            # Calculate checksum
            self.file_checksums[str(file_path)] = self._calculate_checksum(file_path)

            logger.info(f"Created file: {file_path}")
            return ActionResult(
                action=action,
                success=True,
                output=f"File created: {file_path}",
                rollback_data={"created": True}
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to create file: {e}",
                action=action,
                recoverable=True
            ) from e

    def _modify_file(self, action: Action) -> ActionResult:
        """Modify an existing file.

        Args:
            action: The modify file action

        Returns:
            Result of file modification

        """
        file_path = self.context.resolve_path(action.target)

        # Check if file exists
        if not file_path.exists():
            if action.options.get("create_if_missing", True):
                # Create the file if it doesn't exist
                return self._create_file(action)
            else:
                return ActionResult(
                    action=action,
                    success=False,
                    error=f"File not found: {file_path}"
                )

        # Backup the file before modification
        backup_path = self._backup_file(file_path, action.target)
        self._modified_files[action.target] = backup_path

        # Determine if content is binary
        content = action.content or ""
        is_binary = action.options.get("binary", False)

        try:
            if is_binary:
                # Handle binary content
                binary_data = base64.b64decode(content)
                file_path.write_bytes(binary_data)
            else:
                # Handle text content
                encoding = action.options.get("encoding", "utf-8")
                file_path.write_text(content, encoding=encoding)

            # Update checksum
            self.file_checksums[str(file_path)] = self._calculate_checksum(file_path)

            logger.info(f"Modified file: {file_path}")
            return ActionResult(
                action=action,
                success=True,
                output=f"File modified: {file_path}",
                rollback_data={"backup_path": str(backup_path)}
            )

        except Exception as e:
            # Attempt to restore from backup
            try:
                shutil.copy2(backup_path, file_path)
            except Exception:
                pass

            raise ExecutionError(
                f"Failed to modify file: {e}",
                action=action,
                recoverable=True
            ) from e

    def _append_file(self, action: Action) -> ActionResult:
        """Append content to an existing file.

        Args:
            action: The append file action

        Returns:
            Result of file append

        """
        file_path = self.context.resolve_path(action.target)

        if not file_path.exists():
            if action.options.get("create_if_missing", True):
                return self._create_file(action)
            else:
                return ActionResult(
                    action=action,
                    success=False,
                    error=f"File not found: {file_path}"
                )

        # Backup before modification
        backup_path = self._backup_file(file_path, action.target)

        try:
            content = action.content or ""
            encoding = action.options.get("encoding", "utf-8")

            with file_path.open("a", encoding=encoding) as f:
                f.write(content)

            logger.info(f"Appended to file: {file_path}")
            return ActionResult(
                action=action,
                success=True,
                output=f"Content appended to: {file_path}",
                rollback_data={"backup_path": str(backup_path)}
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to append to file: {e}",
                action=action,
                recoverable=True
            ) from e

    def _replace_in_file(self, action: Action) -> ActionResult:
        """Replace content in a file.

        Args:
            action: The replace in file action

        Returns:
            Result of replacement

        """
        file_path = self.context.resolve_path(action.target)

        if not file_path.exists():
            return ActionResult(
                action=action,
                success=False,
                error=f"File not found: {file_path}"
            )

        # Get search and replace patterns
        search = action.options.get("search", "")
        replace = action.content or ""

        if not search:
            return ActionResult(
                action=action,
                success=False,
                error="Missing 'search' pattern in options"
            )

        # Backup before modification
        backup_path = self._backup_file(file_path, action.target)

        try:
            encoding = action.options.get("encoding", "utf-8")
            content = file_path.read_text(encoding=encoding)

            # Perform replacement
            count = content.count(search)
            new_content = content.replace(search, replace)

            file_path.write_text(new_content, encoding=encoding)

            logger.info(f"Replaced {count} occurrences in: {file_path}")
            return ActionResult(
                action=action,
                success=True,
                output=f"Replaced {count} occurrences in: {file_path}",
                rollback_data={"backup_path": str(backup_path)}
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to replace in file: {e}",
                action=action,
                recoverable=True
            ) from e

    def _delete_file(self, action: Action) -> ActionResult:
        """Delete a file.

        Args:
            action: The delete file action

        Returns:
            Result of file deletion

        """
        file_path = self.context.resolve_path(action.target)

        if not file_path.exists():
            return ActionResult(
                action=action,
                success=True,
                output=f"File already absent: {file_path}"
            )

        # Backup before deletion
        backup_path = self._backup_file(file_path, action.target)

        try:
            file_path.unlink()
            logger.info(f"Deleted file: {file_path}")

            return ActionResult(
                action=action,
                success=True,
                output=f"File deleted: {file_path}",
                rollback_data={"backup_path": str(backup_path)}
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to delete file: {e}",
                action=action,
                recoverable=False
            ) from e

    def _move_file(self, action: Action) -> ActionResult:
        """Move a file to a new location.

        Args:
            action: The move file action

        Returns:
            Result of file move

        """
        source = action.options.get("source", "")
        if not source:
            return ActionResult(
                action=action,
                success=False,
                error="Missing 'source' in options"
            )

        source_path = self.context.resolve_path(source)
        dest_path = self.context.resolve_path(action.target)

        if not source_path.exists():
            return ActionResult(
                action=action,
                success=False,
                error=f"Source file not found: {source_path}"
            )

        # Create parent directories for destination
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.move(str(source_path), str(dest_path))
            logger.info(f"Moved file: {source_path} -> {dest_path}")

            return ActionResult(
                action=action,
                success=True,
                output=f"File moved: {source_path} -> {dest_path}",
                rollback_data={"original_path": str(source_path)}
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to move file: {e}",
                action=action,
                recoverable=True
            ) from e

    def _copy_file(self, action: Action) -> ActionResult:
        """Copy a file to a new location.

        Args:
            action: The copy file action

        Returns:
            Result of file copy

        """
        source = action.options.get("source", "")
        if not source:
            return ActionResult(
                action=action,
                success=False,
                error="Missing 'source' in options"
            )

        source_path = self.context.resolve_path(source)
        dest_path = self.context.resolve_path(action.target)

        if not source_path.exists():
            return ActionResult(
                action=action,
                success=False,
                error=f"Source file not found: {source_path}"
            )

        # Create parent directories for destination
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(source_path), str(dest_path))
            logger.info(f"Copied file: {source_path} -> {dest_path}")

            # Track created file
            self._created_files.add(str(dest_path))

            return ActionResult(
                action=action,
                success=True,
                output=f"File copied: {source_path} -> {dest_path}",
                rollback_data={"created": True}
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to copy file: {e}",
                action=action,
                recoverable=True
            ) from e

    def _create_directory(self, action: Action) -> ActionResult:
        """Create a new directory.

        Args:
            action: The create directory action

        Returns:
            Result of directory creation

        """
        dir_path = self.context.resolve_path(action.target)

        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {dir_path}")

            return ActionResult(
                action=action,
                success=True,
                output=f"Directory created: {dir_path}",
                rollback_data={"created": True}
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to create directory: {e}",
                action=action,
                recoverable=True
            ) from e

    def _delete_directory(self, action: Action) -> ActionResult:
        """Delete a directory.

        Args:
            action: The delete directory action

        Returns:
            Result of directory deletion

        """
        dir_path = self.context.resolve_path(action.target)

        if not dir_path.exists():
            return ActionResult(
                action=action,
                success=True,
                output=f"Directory already absent: {dir_path}"
            )

        # Backup directory before deletion
        dir_hash = hashlib.md5(str(dir_path).encode()).hexdigest()
        backup_path = self.backup_dir / f"dir_{dir_hash}"

        try:
            shutil.copytree(dir_path, backup_path)
            shutil.rmtree(dir_path)
            logger.info(f"Deleted directory: {dir_path}")

            return ActionResult(
                action=action,
                success=True,
                output=f"Directory deleted: {dir_path}",
                rollback_data={"backup_path": str(backup_path)}
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to delete directory: {e}",
                action=action,
                recoverable=False
            ) from e

    def _read_file(self, action: Action) -> ActionResult:
        """Read file contents.

        Args:
            action: The read file action

        Returns:
            Result with file contents

        """
        file_path = self.context.resolve_path(action.target)

        if not file_path.exists():
            return ActionResult(
                action=action,
                success=False,
                error=f"File not found: {file_path}"
            )

        try:
            is_binary = action.options.get("binary", False)

            if is_binary:
                content = base64.b64encode(file_path.read_bytes()).decode()
            else:
                encoding = action.options.get("encoding", "utf-8")
                content = file_path.read_text(encoding=encoding)

            return ActionResult(
                action=action,
                success=True,
                output=content
            )

        except Exception as e:
            raise ExecutionError(
                f"Failed to read file: {e}",
                action=action,
                recoverable=True
            ) from e

    def _backup_file(self, file_path: Path, relative_path: str) -> Path:
        """Create a backup of a file.

        Args:
            file_path: Absolute path to the file
            relative_path: Relative path for organizing backup

        Returns:
            Path to the backup file

        """
        # Create unique backup name
        path_hash = hashlib.md5(relative_path.encode()).hexdigest()
        backup_name = f"{path_hash}_{file_path.name}"
        backup_path = self.backup_dir / backup_name

        # Copy file to backup location
        shutil.copy2(file_path, backup_path)
        logger.debug(f"Backed up {file_path} to {backup_path}")

        return backup_path

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hexadecimal checksum string

        """
        sha256_hash = hashlib.sha256()
        with file_path.open("rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _validate_safe_path(self, path: Path, action: Action) -> None:
        """Validate that a path is safe to operate on.

        Args:
            path: Path to validate
            action: The action being validated

        Raises:
            ValidationError: If path is unsafe

        """
        # Convert to string for pattern matching
        path_str = str(path)

        # Check for dangerous patterns
        dangerous_patterns = [
            "/etc/",
            "/sys/",
            "/proc/",
            "/boot/",
            "/dev/",
            "/.ssh/",
            "/.gnupg/",
        ]

        for pattern in dangerous_patterns:
            if pattern in path_str:
                raise ValidationError(
                    f"Potentially dangerous path: {path}",
                    action=action,
                    validation_errors=[f"Path contains {pattern}"]
                )

        # Check if path tries to escape working directory
        try:
            resolved = path.resolve()
            working_dir = self.context.working_directory.resolve()

            # Allow operations in working directory and temp directories
            if not (
                resolved.is_relative_to(working_dir) or
                str(resolved).startswith("/tmp/") or
                str(resolved).startswith(tempfile.gettempdir())
            ):
                # Check if explicitly allowed
                if not action.options.get("allow_outside_working_dir", False):
                    raise ValidationError(
                        f"Path outside working directory: {path}",
                        action=action,
                        validation_errors=["Path escapes working directory"]
                    )
        except Exception as e:
            # If resolution fails, consider it unsafe
            raise ValidationError(
                f"Cannot validate path: {path}",
                action=action
            ) from e

    def _simulate_action(self, action: Action) -> ActionResult:
        """Simulate an action in dry-run mode.

        Args:
            action: The action to simulate

        Returns:
            Simulated result

        """
        return ActionResult(
            action=action,
            success=True,
            output=f"[DRY RUN] Would execute: {action.type.name} on {action.target}"
        )


class BinaryFileHandler:
    """Handler for binary file operations.

    This class provides specialized handling for binary files,
    including detection, encoding, and safe operations.
    """

    # Common binary file extensions
    BINARY_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
        '.exe', '.dll', '.so', '.dylib', '.bin',
        '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac',
        '.ttf', '.otf', '.woff', '.woff2',
        '.db', '.sqlite', '.dbf',
    }

    @classmethod
    def is_binary_file(cls, file_path: Union[str, Path]) -> bool:
        """Check if a file is binary based on extension or content.

        Args:
            file_path: Path to the file

        Returns:
            True if file is binary

        """
        path = Path(file_path)

        # Check extension
        if path.suffix.lower() in cls.BINARY_EXTENSIONS:
            return True

        # Check content if file exists
        if path.exists():
            try:
                with path.open('rb') as f:
                    # Read first 8192 bytes
                    chunk = f.read(8192)
                    # Check for null bytes (common in binary files)
                    if b'\x00' in chunk:
                        return True
                    # Try to decode as UTF-8
                    try:
                        chunk.decode('utf-8')
                        return False
                    except UnicodeDecodeError:
                        return True
            except Exception:
                # If we can't read it, assume binary for safety
                return True

        return False

    @classmethod
    def encode_binary_content(cls, file_path: Union[str, Path]) -> str:
        """Encode binary file content as base64.

        Args:
            file_path: Path to the binary file

        Returns:
            Base64 encoded string

        """
        path = Path(file_path)
        binary_data = path.read_bytes()
        return base64.b64encode(binary_data).decode('ascii')

    @classmethod
    def decode_binary_content(cls, encoded_content: str) -> bytes:
        """Decode base64 content to binary.

        Args:
            encoded_content: Base64 encoded string

        Returns:
            Binary data

        """
        return base64.b64decode(encoded_content)

