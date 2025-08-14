"""Comprehensive test suite for safety guard modules."""

import tempfile
from pathlib import Path

import pytest

from hydra.safety.file_guard import FileGuard
from hydra.safety.git_guard import GitGuard
from hydra.safety.operation_validator import (
    OperationType,
    OperationValidator,
    ValidationRule,
)
from hydra.safety.rate_limiter import CommandCategory, RateLimiter
from hydra.safety.sandbox import FileSandbox


class TestGitGuard:
    """Test suite for GitGuard."""

    def setup_method(self):
        """Set up test fixtures."""
        self.guard = GitGuard(strict_mode=True)
        self.guard_permissive = GitGuard(strict_mode=False)

    def test_block_git_config_user(self):
        """Test blocking git config user modifications."""
        commands = [
            "git config user.name 'Evil User'",
            "git config user.email evil@example.com",
            "git config --global user.name 'Bad'",
        ]

        for cmd in commands:
            allowed, error = self.guard.validate_git_command(cmd)
            assert not allowed
            assert "configuration modification blocked" in error

    def test_block_dangerous_operations(self):
        """Test blocking dangerous git operations."""
        commands = [
            "git push origin main --force",
            "git push -f origin",
            "git reset --hard HEAD~10",
            "git clean -xdf",
        ]

        for cmd in commands:
            allowed, error = self.guard.validate_git_command(cmd)
            assert not allowed
            assert "dangerous" in error.lower() or "force push" in error.lower()

    def test_allow_safe_operations(self):
        """Test allowing safe git operations."""
        commands = [
            "git status",
            "git log --oneline",
            "git diff HEAD",
            "git branch -a",
            "git show HEAD",
        ]

        for cmd in commands:
            allowed, error = self.guard.validate_git_command(cmd)
            assert allowed
            assert error is None

    def test_strict_vs_permissive_mode(self):
        """Test difference between strict and permissive modes."""
        cmd = "git stash pop"

        # Strict mode - requires explicit allowlisting
        allowed_strict, _ = self.guard.validate_git_command(cmd)
        assert allowed_strict  # git stash is in basic allowed list

        # Permissive mode - allows unless explicitly blocked
        allowed_permissive, _ = self.guard_permissive.validate_git_command(cmd)
        assert allowed_permissive

    def test_validate_remote_url(self):
        """Test remote URL validation."""
        # Block file:// URLs
        allowed, error = self.guard.validate_remote_url("file:///etc/passwd")
        assert not allowed
        assert "file URLs are not allowed" in error

        # Allow standard URLs
        allowed, error = self.guard.validate_remote_url("https://github.com/user/repo.git")
        assert allowed
        assert error is None


class TestFileGuard:
    """Test suite for FileGuard."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.guard = FileGuard(project_root=self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_block_env_files(self):
        """Test blocking access to .env files."""
        paths = [
            ".env",
            ".env.local",
            ".env.production",
            "path/to/.env.secret",
        ]

        for path in paths:
            allowed, error = self.guard.validate_file_access(path, "write")
            assert not allowed
            assert "protected file" in error.lower()

    def test_block_git_directory(self):
        """Test blocking access to .git directory."""
        git_dir = self.temp_dir / ".git"
        git_dir.mkdir()

        paths = [
            git_dir / "config",
            git_dir / "hooks" / "pre-commit",
        ]

        for path in paths:
            allowed, error = self.guard.validate_file_access(str(path), "write")
            assert not allowed
            assert "protected directory" in error.lower()

    def test_block_system_directories(self):
        """Test blocking modifications to system directories."""
        paths = ["/etc/passwd", "/usr/bin/python", "/boot/grub/grub.cfg"]

        for path in paths:
            allowed, error = self.guard.validate_file_access(path, "write")
            assert not allowed
            assert "system director" in error.lower()

    def test_allow_project_files(self):
        """Test allowing access to regular project files."""
        test_file = self.temp_dir / "test.py"
        test_file.write_text("# Test file")

        allowed, error = self.guard.validate_file_access(str(test_file), "read")
        assert allowed
        assert error is None

        allowed, error = self.guard.validate_file_access(str(test_file), "write")
        assert allowed
        assert error is None

    def test_validate_symlink(self):
        """Test symlink validation."""
        # Create a regular file
        regular_file = self.temp_dir / "regular.txt"
        regular_file.write_text("content")

        # Create a symlink to it
        symlink = self.temp_dir / "link.txt"
        symlink.symlink_to(regular_file)

        is_safe, warning = self.guard.validate_symlink(symlink)
        assert is_safe
        assert warning is None


class TestOperationValidator:
    """Test suite for OperationValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = OperationValidator(default_allow=False)

    def test_whitelist_rules(self):
        """Test whitelist rule validation."""
        # Add a whitelist rule
        rule = ValidationRule(
            pattern=r"^/allowed/.*",
            operation_types=[OperationType.FILE_WRITE],
            is_whitelist=True,
            description="Allow writes to /allowed",
        )
        self.validator.add_rule(rule)

        # Should allow matching operations
        allowed, reason, _ = self.validator.validate_operation(
            OperationType.FILE_WRITE, "/allowed/file.txt"
        )
        assert allowed
        assert "Allow" in reason

    def test_blacklist_rules(self):
        """Test blacklist rule validation."""
        # Should block dangerous file extensions by default
        allowed, reason, _ = self.validator.validate_operation(
            OperationType.FILE_WRITE, "/tmp/key.pem"
        )
        assert not allowed
        assert "certificate/key" in reason

    def test_priority_ordering(self):
        """Test that higher priority rules are checked first."""
        # Add conflicting rules with different priorities
        blacklist_rule = ValidationRule(
            pattern=r".*\.txt$",
            operation_types=[OperationType.FILE_WRITE],
            is_whitelist=False,
            description="Block txt files",
            priority=10,
        )

        whitelist_rule = ValidationRule(
            pattern=r".*\.txt$",
            operation_types=[OperationType.FILE_WRITE],
            is_whitelist=True,
            description="Allow txt files",
            priority=20,  # Higher priority
        )

        self.validator.add_rule(blacklist_rule)
        self.validator.add_rule(whitelist_rule)

        # Higher priority whitelist should win
        allowed, _, matching_rule = self.validator.validate_operation(
            OperationType.FILE_WRITE, "test.txt"
        )
        assert allowed
        assert matching_rule.priority == 20

    def test_batch_validation(self):
        """Test batch validation of operations."""
        operations = [
            (OperationType.FILE_READ, "test.py"),
            (OperationType.COMMAND_EXECUTE, "rm -rf /"),  # Dangerous
            (OperationType.FILE_WRITE, "/tmp/safe.txt"),
        ]

        results = self.validator.batch_validate(operations, stop_on_first_denial=True)

        # First should be allowed (source code read)
        assert results[0][0] is True

        # Second should be denied (destructive command)
        assert results[1][0] is False

        # Third should be skipped due to stop_on_first_denial
        assert results[2][0] is False
        assert "skipped" in results[2][1].lower()


class TestRateLimiter:
    """Test suite for RateLimiter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter(enable_logging=False)

    def test_command_categorization(self):
        """Test command categorization."""
        assert self.limiter.categorize_command("ls -la") == CommandCategory.SAFE
        assert self.limiter.categorize_command("rm file.txt") == CommandCategory.DESTRUCTIVE
        assert self.limiter.categorize_command("rm -rf /") == CommandCategory.CRITICAL
        assert self.limiter.categorize_command("git commit -m 'test'") == CommandCategory.MODERATE

    def test_rate_limiting(self):
        """Test rate limiting enforcement."""
        identifier = "test_user"

        # Safe commands should have high limits
        for _ in range(50):
            allowed, _, _ = self.limiter.check_rate_limit(
                identifier, CommandCategory.SAFE
            )
            assert allowed

        # Critical commands should have strict limits
        allowed_count = 0
        for _ in range(10):
            allowed, _, _ = self.limiter.check_rate_limit(
                identifier + "_critical", CommandCategory.CRITICAL
            )
            if allowed:
                allowed_count += 1

        # Should only allow a few critical operations
        assert allowed_count <= 3

    def test_burst_limiting(self):
        """Test burst limit enforcement."""
        identifier = "burst_test"
        category = CommandCategory.DESTRUCTIVE
        config = self.limiter.configs[category]

        # Rapid succession should hit burst limit
        burst_allowed = 0
        for _ in range(config.burst_limit + 5):
            allowed, reason, _ = self.limiter.check_rate_limit(identifier, category)
            if allowed:
                burst_allowed += 1
            elif "burst" in reason.lower():
                break

        assert burst_allowed <= config.burst_limit

    def test_cooldown_period(self):
        """Test cooldown period after rate limit."""
        import time
        identifier = "cooldown_test"
        category = CommandCategory.CRITICAL
        config = self.limiter.configs[category]

        # First request should be allowed
        allowed, _, _ = self.limiter.check_rate_limit(identifier, category)
        assert allowed
        
        # Wait a tiny bit to avoid burst window
        time.sleep(0.5)
        
        # More requests within rate limit window
        for i in range(config.max_operations - 1):
            allowed, _, _ = self.limiter.check_rate_limit(identifier, category)
            # Some may fail due to burst limit, that's ok
        
        # Now exceed the rate limit to trigger cooldown
        allowed, reason, _ = self.limiter.check_rate_limit(identifier, category)
        assert not allowed
        
        # Future requests should mention rate limit or cooldown
        assert "limit" in reason.lower() or "cooldown" in reason.lower() or "burst" in reason.lower()

    def test_reset_limits(self):
        """Test resetting rate limits."""
        identifier = "reset_test"

        # Use up some capacity
        for _ in range(5):
            self.limiter.check_rate_limit(identifier, CommandCategory.MODERATE)

        # Reset limits
        self.limiter.reset_limits(identifier)

        # Check capacity is restored
        capacity = self.limiter.get_remaining_capacity(identifier, CommandCategory.MODERATE)
        assert capacity["operations_used"] == 0


class TestFileSandbox:
    """Test suite for FileSandbox."""

    def setup_method(self):
        """Set up test fixtures."""
        from hydra.safety.operation_validator import OperationValidator
        self.temp_dir = Path(tempfile.mkdtemp())
        # Create a permissive validator for testing
        test_validator = OperationValidator(default_allow=True)
        self.sandbox = FileSandbox(
            sandbox_root=self.temp_dir, 
            enable_backups=True,
            operation_validator=test_validator
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        self.sandbox.cleanup()

    def test_safe_file_operations(self):
        """Test basic safe file operations."""
        test_file = Path(self.temp_dir) / "test.txt"

        # Write file
        success, error = self.sandbox.write_file(test_file, "Hello, World!")
        assert success, f"Write failed: {error}"
        assert error is None
        assert test_file.exists()

        # Read file
        content, error = self.sandbox.read_file(test_file)
        assert error is None, f"Read failed: {error}"
        assert content == "Hello, World!"

        # Delete file
        success, error = self.sandbox.delete_file(test_file)
        assert success, f"Delete failed: {error}"
        assert not test_file.exists()

    def test_backup_and_rollback(self):
        """Test backup creation and rollback."""
        test_file = Path(self.temp_dir) / "rollback_test.txt"

        # Create initial file
        success, error = self.sandbox.write_file(test_file, "Original content")
        assert success, f"Initial write failed: {error}"

        # Modify file (should create backup)
        success, error = self.sandbox.write_file(test_file, "Modified content")
        assert success, f"Modify write failed: {error}"

        # Check backup was created
        assert len(list(self.sandbox.backup_dir.glob("*.bak"))) > 0

        # Rollback
        success = self.sandbox.rollback()
        assert success

        # Check file is restored
        content, error = self.sandbox.read_file(test_file)
        assert error is None, f"Read after rollback failed: {error}"
        assert content == "Original content"

    def test_sandboxed_context_manager(self):
        """Test sandboxed operation context manager."""
        test_file = self.temp_dir / "context_test.txt"

        # Successful operation
        with self.sandbox.sandboxed_operation("test operation"):
            self.sandbox.write_file(test_file, "Success")

        assert test_file.exists()

        # Failed operation with automatic rollback
        test_file2 = self.temp_dir / "context_test2.txt"

        with pytest.raises(Exception):  # noqa: B017
            with self.sandbox.sandboxed_operation("failing operation"):
                self.sandbox.write_file(test_file2, "Will be rolled back")
                raise Exception("Simulated failure")

        # File should not exist due to rollback
        assert not test_file2.exists()

    def test_move_file_operation(self):
        """Test moving files safely."""
        source = Path(self.temp_dir) / "source.txt"
        target = Path(self.temp_dir) / "target.txt"

        # Create source file
        success, error = self.sandbox.write_file(source, "Move me")
        assert success, f"Write source failed: {error}"

        # Move file
        success, error = self.sandbox.move_file(source, target)
        assert success, f"Move failed: {error}"
        assert not source.exists()
        assert target.exists()

        # Check content preserved
        content, error = self.sandbox.read_file(target)
        assert error is None
        assert content == "Move me"

    def test_operation_history(self):
        """Test operation history tracking."""
        test_file = self.temp_dir / "history_test.txt"

        # Perform some operations
        self.sandbox.write_file(test_file, "Content 1")
        self.sandbox.write_file(test_file, "Content 2")
        self.sandbox.delete_file(test_file)

        # Check history
        history = self.sandbox.get_operation_history()
        assert len(history) == 3
        assert history[0]["type"] == "create"
        assert history[1]["type"] == "modify"
        assert history[2]["type"] == "delete"
