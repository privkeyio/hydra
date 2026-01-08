"""Tests for security module."""

import json
import os
import time
import unittest
from unittest.mock import Mock

from hydra.security import (
    AuditLogger,
    InputSanitizer,
    RequestSigner,
    SecretsManager,
    SecurityHeaders,
)


class TestInputSanitizer(unittest.TestCase):
    def setUp(self):
        self.sanitizer = InputSanitizer()

    def test_sanitize_safe_code(self):
        """Test that safe code passes validation."""
        safe_code = "def hello_world():\n    return 'Hello, World!'"
        is_valid, result = self.sanitizer.sanitize_code_input(safe_code)
        self.assertTrue(is_valid)
        self.assertEqual(result, safe_code)

    def test_reject_dangerous_patterns(self):
        """Test that dangerous patterns are rejected."""
        dangerous_inputs = [
            "__import__('os').system('rm -rf /')",
            "eval('malicious code')",
            "exec(compile('bad', 'string', 'exec'))",
            "import os; os.system('bad')",
            "open('/etc/passwd').read()",
        ]

        for dangerous_input in dangerous_inputs:
            is_valid, result = self.sanitizer.sanitize_code_input(dangerous_input)
            self.assertFalse(is_valid)
            self.assertIn("dangerous", result.lower())

    def test_reject_long_input(self):
        """Test that overly long inputs are rejected."""
        long_input = "x" * 20000
        is_valid, result = self.sanitizer.sanitize_code_input(long_input)
        self.assertFalse(is_valid)
        self.assertIn("too long", result.lower())

    def test_sanitize_path_traversal(self):
        """Test path traversal detection."""
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "%2e%2e/etc/passwd",
            "files/../../../etc/passwd",
        ]

        for path in dangerous_paths:
            is_valid, result = self.sanitizer.sanitize_path(path)
            self.assertFalse(is_valid)

    def test_reject_forbidden_extensions(self):
        """Test rejection of sensitive file types."""
        forbidden_files = [
            "secrets.env",
            "private.key",
            "certificate.pem",
            "keystore.jks",
        ]

        for file in forbidden_files:
            is_valid, result = self.sanitizer.sanitize_path(file)
            self.assertFalse(is_valid)
            self.assertIn("restricted", result.lower())

    def test_sanitize_json(self):
        """Test JSON sanitization."""
        valid_json = {"key": "value", "number": 123}
        is_valid, result = self.sanitizer.sanitize_json(valid_json)
        self.assertTrue(is_valid)
        self.assertEqual(result, valid_json)

        # Test dangerous content in JSON
        dangerous_json = {"code": "__import__('os')"}
        is_valid, result = self.sanitizer.sanitize_json(dangerous_json)
        self.assertFalse(is_valid)


class TestRequestSigner(unittest.TestCase):
    def setUp(self):
        self.signer = RequestSigner()

    def test_sign_and_verify(self):
        """Test request signing and verification."""
        method = "POST"
        path = "/api/generate"
        body = '{"prompt": "test"}'
        timestamp = int(time.time())

        signature = self.signer.sign_request(method, path, body, timestamp)
        self.assertIsInstance(signature, str)
        self.assertTrue(len(signature) > 0)

        # Verify signature
        is_valid = self.signer.verify_signature(
            method, path, body, timestamp, signature
        )
        self.assertTrue(is_valid)

    def test_reject_invalid_signature(self):
        """Test rejection of invalid signatures."""
        method = "POST"
        path = "/api/generate"
        body = '{"prompt": "test"}'
        timestamp = int(time.time())

        # Invalid signature
        is_valid = self.signer.verify_signature(
            method, path, body, timestamp, "invalid_signature"
        )
        self.assertFalse(is_valid)

    def test_reject_old_timestamp(self):
        """Test rejection of old timestamps."""
        method = "POST"
        path = "/api/generate"
        body = '{"prompt": "test"}'
        old_timestamp = int(time.time()) - 400  # 400 seconds ago

        signature = self.signer.sign_request(method, path, body, old_timestamp)
        is_valid = self.signer.verify_signature(
            method, path, body, old_timestamp, signature
        )
        self.assertFalse(is_valid)


class TestSecretsManager(unittest.TestCase):
    def setUp(self):
        self.test_file = "/tmp/test_secrets.json"
        os.environ["SECRETS_FILE"] = self.test_file
        self.manager = SecretsManager()

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.unlink(self.test_file)

    def test_rotate_secret(self):
        """Test secret rotation."""
        key = "test_key"
        secret1 = self.manager.rotate_secret(key)
        self.assertIsInstance(secret1, str)
        self.assertTrue(len(secret1) > 0)

        # Rotate again
        secret2 = self.manager.rotate_secret(key)
        self.assertNotEqual(secret1, secret2)

    def test_get_secret(self):
        """Test secret retrieval."""
        key = "test_key"
        secret = self.manager.rotate_secret(key)
        retrieved = self.manager.get_secret(key)
        self.assertEqual(secret, retrieved)


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        self.test_file = "/tmp/test_audit.log"
        os.environ["AUDIT_LOG_FILE"] = self.test_file
        self.logger = AuditLogger()

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.unlink(self.test_file)

    def test_log_operation(self):
        """Test operation logging."""
        self.logger.log_operation(
            "TEST_OPERATION", "test_user", "test_resource", "SUCCESS", {"key": "value"}
        )

        # Verify log was written
        self.assertTrue(os.path.exists(self.test_file))
        with open(self.test_file, "r") as f:
            log_entry = json.loads(f.readline())
            self.assertEqual(log_entry["operation"], "TEST_OPERATION")
            self.assertEqual(log_entry["user"], "test_user")

    def test_log_security_event(self):
        """Test security event logging."""
        self.logger.log_security_event(
            "INTRUSION_ATTEMPT",
            "HIGH",
            "Suspicious activity detected",
            {"ip": "192.168.1.1"},
        )

        with open(self.test_file, "r") as f:
            log_entry = json.loads(f.readline())
            self.assertIn("SECURITY", log_entry["operation"])
            self.assertEqual(log_entry["result"], "HIGH")


class TestSecurityHeaders(unittest.TestCase):
    def test_apply_headers(self):
        """Test security header application."""
        mock_response = Mock()
        mock_response.headers = {}

        SecurityHeaders.apply_headers(mock_response)

        # Check all security headers are present
        expected_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "Referrer-Policy",
            "Permissions-Policy",
        ]

        for header in expected_headers:
            self.assertIn(header, mock_response.headers)


if __name__ == "__main__":
    unittest.main()
