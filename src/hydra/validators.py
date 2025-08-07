"""Input validation and security checks for Hydra system."""

import ast
import re
from typing import Any, Dict, Optional

from .exceptions import SecurityError, ValidationError


class CodeValidator:
    """Validates generated code for security and correctness."""

    # Dangerous imports that should be blocked
    DANGEROUS_IMPORTS = {
        'os', 'subprocess', 'shutil', 'tempfile', 'socket',
        'urllib', 'requests', 'http', 'ftplib', 'smtplib',
        'eval', 'exec', 'compile', '__import__',
        'open', 'file', 'input', 'raw_input'
    }

    # Dangerous built-in functions
    DANGEROUS_BUILTINS = {
        'eval', 'exec', 'compile', '__import__', 'globals', 'locals',
        'vars', 'dir', 'getattr', 'setattr', 'delattr', 'hasattr'
    }

    # Allowed safe modules
    SAFE_MODULES = {
        'math', 'random', 'datetime', 'json', 'collections',
        'itertools', 'functools', 're', 'string', 'typing',
        'dataclasses', 'enum', 'abc', 'copy', 'decimal'
    }

    @classmethod
    def validate_code(cls, code: str, allow_imports: bool = False) -> Dict[str, Any]:
        """Validate code for safety and correctness."""
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "imports": [],
            "dangerous_patterns": []
        }

        try:
            # Parse AST to check syntax
            tree = ast.parse(code)

            # Walk through AST nodes to check for dangerous patterns
            for node in ast.walk(tree):
                cls._check_node_security(node, result)

            # Additional pattern-based checks
            cls._check_string_patterns(code, result)

            if not allow_imports and result["imports"]:
                result["errors"].append(
                    f"Imports not allowed: {', '.join(result['imports'])}"
                )
                result["valid"] = False

        except SyntaxError as e:
            result["valid"] = False
            result["errors"].append(f"Syntax error: {str(e)}")
        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Validation error: {str(e)}")

        return result

    @classmethod
    def _check_node_security(cls, node: ast.AST, result: Dict[str, Any]):
        """Check AST node for security issues."""
        if isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(alias.name)
                if alias.name in cls.DANGEROUS_IMPORTS:
                    result["dangerous_patterns"].append(f"Dangerous import: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                result["imports"].append(node.module)
                if node.module in cls.DANGEROUS_IMPORTS:
                    result["dangerous_patterns"].append(f"Dangerous import: {node.module}")

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in cls.DANGEROUS_BUILTINS:
                    result["dangerous_patterns"].append(f"Dangerous function: {node.func.id}")

        elif isinstance(node, ast.Attribute):
            # Check for dangerous attribute access
            if isinstance(node.value, ast.Name) and node.attr in ['system', 'popen', 'spawn']:
                result["dangerous_patterns"].append(f"Dangerous method: {node.attr}")

    @classmethod
    def _check_string_patterns(cls, code: str, result: Dict[str, Any]):
        """Check for dangerous string patterns."""
        dangerous_patterns = [
            r'__.*__',  # Dunder methods
            r'\.system\(',
            r'\.popen\(',
            r'\.spawn\(',
            r'subprocess\.',
            r'os\.',
            r'eval\(',
            r'exec\(',
            r'open\(',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                result["warnings"].append(f"Potentially dangerous pattern: {pattern}")


class TaskValidator:
    """Validates task inputs for safety and reasonableness."""

    MAX_TASK_LENGTH = 10000
    MIN_TASK_LENGTH = 5

    # Patterns that might indicate malicious intent
    SUSPICIOUS_PATTERNS = [
        r'delete.*file', r'remove.*file', r'rm\s+', r'del\s+',
        r'format.*drive', r'format.*disk',
        r'kill.*process', r'terminate.*process',
        r'access.*password', r'steal.*data', r'hack.*',
        r'ddos', r'dos\s+attack', r'brute.*force',
        r'sql.*injection', r'xss.*attack',
        r'download.*executable', r'install.*malware'
    ]

    @classmethod
    def validate_task(cls, task: str) -> Dict[str, Any]:
        """Validate task input."""
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "sanitized_task": task.strip()
        }

        # Length checks
        if len(task.strip()) < cls.MIN_TASK_LENGTH:
            result["errors"].append("Task too short")
            result["valid"] = False

        if len(task) > cls.MAX_TASK_LENGTH:
            result["errors"].append("Task too long")
            result["valid"] = False

        # Pattern checks
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, task.lower()):
                result["warnings"].append(f"Suspicious pattern detected: {pattern}")

        # Basic sanitization - more aggressive for security
        sanitized = re.sub(r'[<>"\';{}()\/]', ' ', task.strip())
        sanitized = re.sub(r'\s+', ' ', sanitized)  # Collapse multiple spaces
        result["sanitized_task"] = sanitized.strip()

        return result


class InputSanitizer:
    """Sanitizes various inputs to prevent injection attacks."""

    @staticmethod
    def sanitize_agent_name(name: str) -> str:
        """Sanitize agent name to prevent injection."""
        # First remove dangerous words completely
        dangerous_words = ['script', 'eval', 'exec', 'import', 'system']
        name.lower()
        for word in dangerous_words:
            name = re.sub(re.escape(word), '', name, flags=re.IGNORECASE)

        # Keep only alphanumeric, underscore, hyphen
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', name.strip())
        return sanitized[:50]  # Max length

    @staticmethod
    def sanitize_file_path(path: str) -> Optional[str]:
        """Sanitize file path to prevent directory traversal."""
        if not path:
            return None

        # Remove dangerous patterns
        dangerous = ['../', '..\\', '~/', '/etc/', '/var/', '/usr/']
        for pattern in dangerous:
            if pattern in path:
                raise SecurityError(f"Dangerous path pattern: {pattern}")

        # Allow only safe characters
        sanitized = re.sub(r'[^a-zA-Z0-9._/-]', '', path)
        return sanitized

    @staticmethod
    def sanitize_model_name(model: str) -> str:
        """Sanitize model name."""
        allowed_models = {
            'sonnet', 'opus', 'haiku', 'claude-3-5-sonnet-20241022',
            'claude-3-opus-20240229', 'claude-3-haiku-20240307',
            'gpt-4', 'gpt-3.5-turbo', 'qwen-2.5-coder-32b'
        }

        model = model.lower().strip()
        if model not in allowed_models:
            raise ValidationError(f"Invalid model name: {model}")

        return model
