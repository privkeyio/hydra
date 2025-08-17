"""Security hardening module for Hydra."""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class InputSanitizer:
    """Sanitizes inputs to prevent code injection and malicious payloads."""

    # Patterns that indicate potential security risks
    DANGEROUS_PATTERNS = [
        r"__import__",
        r"eval\s*\(",
        r"exec\s*\(",
        r"compile\s*\(",
        r"os\.",
        r"subprocess\.",
        r"open\s*\(",
        r"file\s*\(",
        r"input\s*\(",
        r"raw_input\s*\(",
        r"__.*__",
        r"globals\s*\(",
        r"locals\s*\(",
        r"vars\s*\(",
        r"dir\s*\(",
    ]

    # File extensions that should never be accessed
    FORBIDDEN_EXTENSIONS = {
        ".env",
        ".pem",
        ".key",
        ".cert",
        ".crt",
        ".p12",
        ".pfx",
        ".jks",
        ".keystore",
        ".truststore",
        ".kdb",
        ".wallet",
    }

    # Path traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\.",
        r"\.\./",
        r"\.\.\\",
        r"%2e%2e",
        r"%252e%252e",
        r"..%c0%af",
        r"..%c1%9c",
    ]

    def __init__(self):
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.DANGEROUS_PATTERNS
        ]
        self.path_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.PATH_TRAVERSAL_PATTERNS
        ]

    def sanitize_code_input(self, code: str) -> Tuple[bool, str]:
        """Sanitize code generation prompts."""
        if not code or not isinstance(code, str):
            return False, "Invalid input type"

        # Check length limits
        if len(code) > 10000:
            return False, "Input too long"

        # Check for dangerous patterns
        for pattern in self.compiled_patterns:
            if pattern.search(code):
                logger.warning(f"Dangerous pattern detected: {pattern.pattern}")
                return False, "Potentially dangerous code pattern detected"

        return True, code

    def sanitize_path(self, path: str) -> Tuple[bool, str]:
        """Sanitize file paths to prevent directory traversal."""
        if not path or not isinstance(path, str):
            return False, "Invalid path"

        # Check for path traversal attempts
        for pattern in self.path_patterns:
            if pattern.search(path):
                logger.warning(f"Path traversal attempt: {path}")
                return False, "Invalid path format"

        # Check for forbidden extensions
        for ext in self.FORBIDDEN_EXTENSIONS:
            if path.lower().endswith(ext):
                logger.warning(f"Forbidden file type: {path}")
                return False, "Access to this file type is restricted"

        # Normalize path
        try:
            normalized = os.path.normpath(path)
            # Ensure path doesn't escape allowed directories
            if normalized.startswith("/etc/") or normalized.startswith("/root/"):
                return False, "Access to system directories denied"
            return True, normalized
        except Exception:
            return False, "Invalid path format"

    def sanitize_json(self, data: Any) -> Tuple[bool, Any]:
        """Sanitize JSON input data."""
        try:
            # Convert to JSON and back to ensure it's valid
            json_str = json.dumps(data)
            if len(json_str) > 1000000:  # 1MB limit
                return False, "JSON data too large"

            # Check for dangerous content in JSON
            if any(pattern.search(json_str) for pattern in self.compiled_patterns):
                return False, "Potentially dangerous content in JSON"

            return True, json.loads(json_str)
        except Exception:
            return False, "Invalid JSON format"


class SecureExecutor:
    """Manages secure code execution in sandboxed environments."""

    def __init__(self):
        self.docker_image = os.getenv("HYDRA_SANDBOX_IMAGE", "alpine:latest")
        self.max_execution_time = int(os.getenv("HYDRA_MAX_EXEC_TIME", "30"))
        self.max_memory = os.getenv("HYDRA_MAX_MEMORY", "512m")
        self.max_cpu = os.getenv("HYDRA_MAX_CPU", "0.5")

    def execute_in_sandbox(self, code: str, language: str) -> Tuple[bool, str]:
        """Execute code in a Docker sandbox with restrictions."""
        # Create temporary file with code
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_file = f.name

        try:
            # Docker run command with security restrictions
            cmd = [
                "docker",
                "run",
                "--rm",  # Remove container after execution
                "--network=none",  # No network access
                "--memory=" + self.max_memory,  # Memory limit
                "--cpus=" + self.max_cpu,  # CPU limit
                "--read-only",  # Read-only root filesystem
                "--security-opt=no-new-privileges",  # No privilege escalation
                "--cap-drop=ALL",  # Drop all capabilities
                "-v",
                f"{temp_file}:/code.py:ro",  # Mount code read-only
                self.docker_image,
                "timeout",
                str(self.max_execution_time),
                "python",
                "/code.py",
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.max_execution_time + 5
            )

            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or "Execution failed"

        except subprocess.TimeoutExpired:
            return False, "Execution timeout"
        except Exception as e:
            logger.error(f"Sandbox execution error: {e}")
            return False, "Execution error"
        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)


class SecretsManager:
    """Manages secrets with rotation and secure storage."""

    def __init__(self):
        self.rotation_interval = int(os.getenv("SECRET_ROTATION_DAYS", "30"))
        self.secrets_file = os.getenv("SECRETS_FILE", "/var/lib/hydra/secrets.json")
        self._secrets_cache = {}
        self._load_secrets()

    def _load_secrets(self):
        """Load secrets from secure storage."""
        try:
            if os.path.exists(self.secrets_file):
                with open(self.secrets_file, "r") as f:
                    data = json.load(f)
                    self._secrets_cache = data.get("secrets", {})
        except Exception as e:
            logger.error(f"Failed to load secrets: {e}")

    def get_secret(self, key: str) -> Optional[str]:
        """Get a secret value."""
        secret_data = self._secrets_cache.get(key)
        if not secret_data:
            return None

        # Check if rotation needed
        created_at = datetime.fromisoformat(secret_data["created_at"])
        if datetime.utcnow() - created_at > timedelta(days=self.rotation_interval):
            logger.info(f"Secret {key} needs rotation")
            return self.rotate_secret(key)

        return secret_data["value"]

    def rotate_secret(self, key: str) -> str:
        """Rotate a secret."""
        new_secret = secrets.token_urlsafe(32)
        self._secrets_cache[key] = {
            "value": new_secret,
            "created_at": datetime.utcnow().isoformat(),
            "rotated_at": datetime.utcnow().isoformat(),
        }
        self._save_secrets()
        logger.info(f"Rotated secret: {key}")
        return new_secret

    def _save_secrets(self):
        """Save secrets to secure storage."""
        try:
            os.makedirs(os.path.dirname(self.secrets_file), exist_ok=True)
            with open(self.secrets_file, "w") as f:
                json.dump({"secrets": self._secrets_cache}, f)
            # Set restrictive permissions
            os.chmod(self.secrets_file, 0o600)
        except Exception as e:
            logger.error(f"Failed to save secrets: {e}")


class RequestSigner:
    """Handles API request signing and verification."""

    def __init__(self):
        self.signing_key = os.getenv("HYDRA_SIGNING_KEY", secrets.token_bytes(32))
        if isinstance(self.signing_key, str):
            self.signing_key = self.signing_key.encode()

    def sign_request(self, method: str, path: str, body: str, timestamp: int) -> str:
        """Generate HMAC signature for request."""
        message = f"{method}\n{path}\n{body}\n{timestamp}".encode()
        signature = hmac.new(self.signing_key, message, hashlib.sha256).hexdigest()
        return signature

    def verify_signature(
        self, method: str, path: str, body: str, timestamp: int, signature: str
    ) -> bool:
        """Verify request signature."""
        # Check timestamp to prevent replay attacks
        current_time = int(time.time())
        if abs(current_time - timestamp) > 300:  # 5 minute window
            logger.warning("Request timestamp outside valid window")
            return False

        expected_signature = self.sign_request(method, path, body, timestamp)
        return hmac.compare_digest(expected_signature, signature)


class AuditLogger:
    """Comprehensive audit logging for all operations."""

    def __init__(self):
        self.audit_file = os.getenv("AUDIT_LOG_FILE", "/var/log/hydra/audit.log")
        try:
            self._ensure_log_dir()
        except PermissionError:
            # Fall back to temp directory if no permission
            import tempfile

            temp_dir = tempfile.gettempdir()
            self.audit_file = os.path.join(temp_dir, "hydra_audit.log")
            logger.warning(f"Using temp directory for audit logs: {self.audit_file}")

    def _ensure_log_dir(self):
        """Ensure audit log directory exists."""
        log_dir = os.path.dirname(self.audit_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, mode=0o750)

    def log_operation(
        self,
        operation: str,
        user: str,
        resource: str,
        result: str,
        metadata: Optional[Dict] = None,
    ):
        """Log an operation with full context."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "user": user,
            "resource": resource,
            "result": result,
            "metadata": metadata or {},
            "ip_address": metadata.get("ip_address") if metadata else None,
            "user_agent": metadata.get("user_agent") if metadata else None,
        }

        try:
            with open(self.audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def log_security_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        metadata: Optional[Dict] = None,
    ):
        """Log security-specific events."""
        self.log_operation(
            f"SECURITY_{event_type}",
            metadata.get("user", "system") if metadata else "system",
            metadata.get("resource", "system") if metadata else "system",
            severity,
            {
                "description": description,
                "event_type": event_type,
                "severity": severity,
                **(metadata or {}),
            },
        )


class SecurityHeaders:
    """Manages security headers for API responses."""

    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }

    @classmethod
    def apply_headers(cls, response):
        """Apply security headers to response."""
        for header, value in cls.SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


# Global instances
input_sanitizer = InputSanitizer()
secure_executor = SecureExecutor()
secrets_manager = SecretsManager()
request_signer = RequestSigner()
audit_logger = AuditLogger()
