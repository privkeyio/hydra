"""Comprehensive safety framework for Hydra operations.

Provides configurable security policies for git operations, file system access,
network security, and subprocess execution validation.
"""

import os
import re
import subprocess
import threading
import time
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse


class OperationResult(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityPolicy(ABC):
    """Abstract base class for security policies."""

    enabled: bool = True
    strict_mode: bool = False
    allow_overrides: bool = True

    @abstractmethod
    def evaluate(self, operation: str, context: Dict[str, Any]) -> OperationResult:
        """Evaluate if an operation should be allowed."""
        pass

    @abstractmethod
    def get_risk_level(self, operation: str, context: Dict[str, Any]) -> RiskLevel:
        """Determine risk level of an operation."""
        pass


@dataclass
class GitSafetyPolicy(SecurityPolicy):
    """Policy for git operation safety."""

    dangerous_operations: Set[str] = field(
        default_factory=lambda: {
            "commit",
            "push",
            "merge",
            "rebase",
            "reset",
            "checkout",
            "branch -d",
            "branch -D",
            "stash drop",
            "clean -f",
            "rm --cached",
            "filter-branch",
            "reflog expire",
        }
    )

    protected_branches: Set[str] = field(
        default_factory=lambda: {"main", "master", "production", "prod", "release"}
    )

    require_approval_patterns: List[str] = field(
        default_factory=lambda: [
            r"git\s+(push|merge)\s.*origin",
            r"git\s+reset\s+--hard",
            r"git\s+clean\s+-[fF]",
            r"git\s+rm\s+--cached",
        ]
    )

    def evaluate(self, operation: str, context: Dict[str, Any]) -> OperationResult:
        if not self.enabled:
            return OperationResult.ALLOW

        cmd = operation.lower().strip()

        # Check if it's a git command
        if not cmd.startswith("git "):
            return OperationResult.ALLOW

        # Extract git subcommand
        git_parts = cmd.split()
        if len(git_parts) < 2:
            return OperationResult.ALLOW

        subcommand = " ".join(git_parts[1:3]) if len(git_parts) > 2 else git_parts[1]

        # Check dangerous operations
        dangerous_found = any(
            dangerous_op in subcommand for dangerous_op in self.dangerous_operations
        )
        if dangerous_found:
            if self.strict_mode:
                return OperationResult.DENY

            # Check if targeting protected branch
            branch = context.get("branch", "")
            if branch in self.protected_branches:
                return OperationResult.REQUIRE_APPROVAL

            # Check approval patterns
            for pattern in self.require_approval_patterns:
                if re.search(pattern, operation, re.IGNORECASE):
                    return OperationResult.REQUIRE_APPROVAL

        return OperationResult.ALLOW

    def get_risk_level(self, operation: str, context: Dict[str, Any]) -> RiskLevel:
        cmd = operation.lower().strip()

        if "push" in cmd and "origin" in cmd:
            return RiskLevel.CRITICAL
        if any(op in cmd for op in ["reset --hard", "clean -f", "rm --cached"]):
            return RiskLevel.HIGH
        if any(op in cmd for op in ["commit", "merge", "rebase"]):
            return RiskLevel.MEDIUM

        return RiskLevel.LOW


@dataclass
class FileSystemSandbox(SecurityPolicy):
    """File system access control policy."""

    allowed_directories: Set[str] = field(default_factory=set)
    forbidden_directories: Set[str] = field(
        default_factory=lambda: {
            "/etc",
            "/usr/bin",
            "/bin",
            "/sbin",
            "/root",
            "/boot",
            "/sys",
            "/proc",
            "/dev",
            "/var/log",
            "/tmp/sensitive",
        }
    )

    allowed_extensions: Set[str] = field(
        default_factory=lambda: {
            ".py",
            ".js",
            ".ts",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".txt",
            ".csv",
            ".log",
            ".conf",
            ".cfg",
            ".ini",
        }
    )

    forbidden_patterns: List[str] = field(
        default_factory=lambda: [
            r".*\.ssh/.*",
            r".*\.aws/.*",
            r".*\.env$",
            r".*password.*",
            r".*secret.*",
            r".*private.*key.*",
        ]
    )

    def __post_init__(self):
        """Initialize with default allowed directories."""
        if not self.allowed_directories:
            # Default to current working directory and common development paths
            cwd = os.getcwd()
            self.allowed_directories = {
                cwd,
                os.path.join(cwd, "src"),
                os.path.join(cwd, "tests"),
                os.path.join(cwd, "docs"),
                "/tmp/hydra",
                os.path.expanduser("~/.hydra"),
            }

    def evaluate(self, operation: str, context: Dict[str, Any]) -> OperationResult:
        if not self.enabled:
            return OperationResult.ALLOW

        file_path = context.get("path", "")
        if not file_path:
            return OperationResult.ALLOW

        abs_path = os.path.abspath(file_path)

        # Check forbidden directories
        for forbidden_dir in self.forbidden_directories:
            if abs_path.startswith(forbidden_dir):
                return (
                    OperationResult.DENY
                    if self.strict_mode
                    else OperationResult.REQUIRE_APPROVAL
                )

        # Check forbidden patterns
        for pattern in self.forbidden_patterns:
            if re.search(pattern, abs_path, re.IGNORECASE):
                return (
                    OperationResult.DENY
                    if self.strict_mode
                    else OperationResult.REQUIRE_APPROVAL
                )

        # Check if in allowed directories
        if self.allowed_directories:
            path_allowed = any(
                abs_path.startswith(allowed_dir)
                for allowed_dir in self.allowed_directories
            )
            if not path_allowed:
                return OperationResult.REQUIRE_APPROVAL

        # Check file extension for write operations
        if context.get("operation_type") in ["write", "modify", "delete"]:
            ext = Path(file_path).suffix.lower()
            if ext and ext not in self.allowed_extensions:
                return OperationResult.REQUIRE_APPROVAL

        return OperationResult.ALLOW

    def get_risk_level(self, operation: str, context: Dict[str, Any]) -> RiskLevel:
        file_path = context.get("path", "")
        abs_path = os.path.abspath(file_path)

        # Check critical system paths
        critical_paths = ["/etc", "/usr/bin", "/bin"]
        if any(abs_path.startswith(critical) for critical in critical_paths):
            return RiskLevel.CRITICAL

        # Check sensitive patterns
        for pattern in self.forbidden_patterns:
            if re.search(pattern, abs_path, re.IGNORECASE):
                return RiskLevel.HIGH

        # Check operation type
        op_type = context.get("operation_type", "")
        if op_type in ["delete", "modify"]:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW


@dataclass
class NetworkAccessControl(SecurityPolicy):
    """Network access control policy."""

    allowed_domains: Set[str] = field(
        default_factory=lambda: {
            "api.anthropic.com",
            "api.openai.com",
            "huggingface.co",
            "github.com",
            "pypi.org",
            "npmjs.com",
        }
    )

    blocked_domains: Set[str] = field(
        default_factory=lambda: {"malware-site.com", "phishing-domain.net"}
    )

    allowed_ports: Set[int] = field(default_factory=lambda: {80, 443, 8000, 8080, 3000})

    require_approval_patterns: List[str] = field(
        default_factory=lambda: [
            r".*\.onion$",
            r".*localhost.*",
            r".*127\.0\.0\.1.*",
            r".*internal.*",
        ]
    )

    def evaluate(self, operation: str, context: Dict[str, Any]) -> OperationResult:
        if not self.enabled:
            return OperationResult.ALLOW

        url = context.get("url", "")
        if not url:
            return OperationResult.ALLOW

        parsed = urlparse(url)
        domain = parsed.hostname or ""
        port = parsed.port

        # Check blocked domains
        if domain in self.blocked_domains:
            return OperationResult.DENY

        # Check allowed domains
        if self.allowed_domains:
            domain_allowed = any(
                domain.endswith(allowed) for allowed in self.allowed_domains
            )
            if not domain_allowed:
                return OperationResult.REQUIRE_APPROVAL

        # Check ports
        if port and port not in self.allowed_ports:
            return OperationResult.REQUIRE_APPROVAL

        # Check approval patterns
        for pattern in self.require_approval_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return OperationResult.REQUIRE_APPROVAL

        return OperationResult.ALLOW

    def get_risk_level(self, operation: str, context: Dict[str, Any]) -> RiskLevel:
        url = context.get("url", "")

        suspicious_patterns = [".onion", "localhost", "127.0.0.1"]
        if any(pattern in url.lower() for pattern in suspicious_patterns):
            return RiskLevel.HIGH

        parsed = urlparse(url)
        if parsed.scheme != "https":
            return RiskLevel.MEDIUM

        return RiskLevel.LOW


@dataclass
class CodeExecutionValidator(SecurityPolicy):
    """Validator for generated code execution."""

    dangerous_imports: Set[str] = field(
        default_factory=lambda: {
            "os.system",
            "subprocess.call",
            "eval",
            "exec",
            "compile",
            "__import__",
            "pickle.loads",
            "marshal.loads",
        }
    )

    dangerous_functions: Set[str] = field(
        default_factory=lambda: {"system", "popen", "spawn", "fork", "execv", "execve"}
    )

    suspicious_patterns: List[str] = field(
        default_factory=lambda: [
            r"rm\s+-rf\s+/",
            r"sudo\s+",
            r"passwd\s+",
            r"chmod\s+777",
            r"curl.*\|.*sh",
            r"wget.*\|.*sh",
            r"base64.*decode",
        ]
    )

    def evaluate(self, operation: str, context: Dict[str, Any]) -> OperationResult:
        if not self.enabled:
            return OperationResult.ALLOW

        code = context.get("code", "")
        if not code:
            return OperationResult.ALLOW

        # Check dangerous imports
        for dangerous in self.dangerous_imports:
            if dangerous in code:
                if self.strict_mode:
                    return OperationResult.DENY
                return OperationResult.REQUIRE_APPROVAL

        # Check dangerous functions
        for func in self.dangerous_functions:
            if re.search(rf"\b{func}\s*\(", code):
                return OperationResult.REQUIRE_APPROVAL

        # Check suspicious patterns
        for pattern in self.suspicious_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return OperationResult.REQUIRE_APPROVAL

        return OperationResult.ALLOW

    def get_risk_level(self, operation: str, context: Dict[str, Any]) -> RiskLevel:
        code = context.get("code", "")

        if any(dangerous in code for dangerous in self.dangerous_imports):
            return RiskLevel.CRITICAL

        if any(re.search(rf"\b{func}\s*\(", code) for func in self.dangerous_functions):
            return RiskLevel.HIGH

        suspicious_found = any(
            re.search(pattern, code, re.IGNORECASE)
            for pattern in self.suspicious_patterns
        )
        if suspicious_found:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW


@dataclass
class ApprovalWorkflow:
    """Manages approval workflow for dangerous operations."""

    auto_approve_low_risk: bool = True
    require_confirmation: bool = True
    timeout_seconds: int = 300  # 5 minutes

    def __init__(self, approval_callback: Optional[Callable] = None):
        self.approval_callback = approval_callback or self._default_approval
        self.pending_approvals: Dict[str, Any] = {}
        self.lock = threading.Lock()

    def request_approval(
        self, operation: str, risk_level: RiskLevel, context: Dict[str, Any]
    ) -> bool:
        """Request approval for an operation."""
        if risk_level == RiskLevel.LOW and self.auto_approve_low_risk:
            return True

        approval_id = f"approval_{int(time.time())}_{hash(operation)}"

        with self.lock:
            self.pending_approvals[approval_id] = {
                "operation": operation,
                "risk_level": risk_level,
                "context": context,
                "timestamp": time.time(),
            }

        try:
            return self.approval_callback(approval_id, operation, risk_level, context)
        finally:
            with self.lock:
                self.pending_approvals.pop(approval_id, None)

    def _default_approval(
        self,
        approval_id: str,
        operation: str,
        risk_level: RiskLevel,
        context: Dict[str, Any],
    ) -> bool:
        """Provide default denial for operations requiring approval."""
        warnings.warn(
            f"Operation requires approval but no callback configured: {operation}",
            UserWarning,
            stacklevel=2,
        )
        return False


class SecurityManager:
    """Main security manager that coordinates all safety policies."""

    def __init__(
        self,
        git_policy: Optional[GitSafetyPolicy] = None,
        fs_policy: Optional[FileSystemSandbox] = None,
        network_policy: Optional[NetworkAccessControl] = None,
        code_policy: Optional[CodeExecutionValidator] = None,
        approval_workflow: Optional[ApprovalWorkflow] = None,
    ):
        self.git_policy = git_policy or GitSafetyPolicy()
        self.fs_policy = fs_policy or FileSystemSandbox()
        self.network_policy = network_policy or NetworkAccessControl()
        self.code_policy = code_policy or CodeExecutionValidator()
        self.approval_workflow = approval_workflow or ApprovalWorkflow()

        self.policies: Dict[str, SecurityPolicy] = {
            "git": self.git_policy,
            "filesystem": self.fs_policy,
            "network": self.network_policy,
            "code": self.code_policy,
        }

        self.audit_log: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    def check_operation(
        self,
        operation_type: str,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Check if an operation is allowed."""
        context = context or {}

        # Get relevant policy
        policy = self.policies.get(operation_type)
        if not policy:
            self._log_audit(
                operation_type, operation, OperationResult.ALLOW, RiskLevel.LOW, context
            )
            return True, "No policy configured"

        # Evaluate operation
        result = policy.evaluate(operation, context)
        risk_level = policy.get_risk_level(operation, context)

        # Handle result
        if result == OperationResult.ALLOW:
            self._log_audit(operation_type, operation, result, risk_level, context)
            return True, "Operation allowed"

        elif result == OperationResult.DENY:
            self._log_audit(operation_type, operation, result, risk_level, context)
            return False, "Operation denied by policy"

        elif result == OperationResult.REQUIRE_APPROVAL:
            approved = self.approval_workflow.request_approval(
                operation, risk_level, context
            )
            final_result = OperationResult.ALLOW if approved else OperationResult.DENY
            self._log_audit(
                operation_type, operation, final_result, risk_level, context
            )

            if approved:
                return True, "Operation approved"
            else:
                return False, "Operation denied - approval required but not granted"

        return False, "Unknown result"

    def safe_subprocess_run(
        self, cmd: Union[str, List[str]], **kwargs
    ) -> subprocess.CompletedProcess:
        """Safe subprocess execution with security checks."""
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd

        operation_type = "git" if "git" in cmd_str else "code"
        allowed, reason = self.check_operation(operation_type, cmd_str)
        if not allowed:
            raise SecurityError(f"Subprocess execution denied: {reason}")

        return subprocess.run(cmd, **kwargs)

    def safe_file_operation(
        self, operation_type: str, file_path: str, **kwargs
    ) -> Tuple[bool, str]:
        """Safe file operation with security checks."""
        context = {"path": file_path, "operation_type": operation_type, **kwargs}

        operation_desc = f"{operation_type} {file_path}"
        return self.check_operation("filesystem", operation_desc, context)

    def safe_network_request(self, url: str, **kwargs) -> Tuple[bool, str]:
        """Safe network request with security checks."""
        context = {"url": url, **kwargs}

        return self.check_operation("network", f"request {url}", context)

    def validate_code(self, code: str, **kwargs) -> Tuple[bool, str]:
        """Validate generated code for safety."""
        context = {"code": code, **kwargs}

        return self.check_operation("code", "execute code", context)

    def _log_audit(
        self,
        operation_type: str,
        operation: str,
        result: OperationResult,
        risk_level: RiskLevel,
        context: Dict[str, Any],
    ):
        """Log operation to audit trail."""
        with self.lock:
            self.audit_log.append(
                {
                    "timestamp": time.time(),
                    "operation_type": operation_type,
                    "operation": operation,
                    "result": result.value,
                    "risk_level": risk_level.value,
                    "context": context,
                }
            )

            # Keep only recent entries
            if len(self.audit_log) > 10000:
                self.audit_log = self.audit_log[-5000:]

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        with self.lock:
            return self.audit_log[-limit:] if limit > 0 else self.audit_log[:]

    def configure_policy(self, policy_type: str, **config):
        """Configure a security policy."""
        if policy_type not in self.policies:
            raise ValueError(f"Unknown policy type: {policy_type}")

        policy = self.policies[policy_type]
        for key, value in config.items():
            if hasattr(policy, key):
                setattr(policy, key, value)

    def enable_strict_mode(self, policy_types: Optional[List[str]] = None):
        """Enable strict mode for specified policies."""
        targets = policy_types or list(self.policies.keys())
        for policy_type in targets:
            if policy_type in self.policies:
                self.policies[policy_type].strict_mode = True

    def disable_strict_mode(self, policy_types: Optional[List[str]] = None):
        """Disable strict mode for specified policies."""
        targets = policy_types or list(self.policies.keys())
        for policy_type in targets:
            if policy_type in self.policies:
                self.policies[policy_type].strict_mode = False


class SecurityError(Exception):
    """Exception raised when security policy is violated."""

    pass


# Global security manager instance
security_manager = SecurityManager()
