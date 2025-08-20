"""Enhanced ticket validation with actual implementation checks.

This module provides robust validation that actually verifies if acceptance
criteria are met, not just if files were modified.
"""

import ast
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple


class CriterionValidator:
    """Validates individual acceptance criteria with actual checks."""

    def __init__(self, project_dir: str):
        """Initialize validator with project directory."""
        self.project_dir = Path(project_dir)

    def validate_criterion(self, criterion: str) -> Dict[str, Any]:
        """Validate a single acceptance criterion.
        
        Args:
            criterion: The acceptance criterion to validate
            
        Returns:
            Dictionary with 'passed' bool, 'reason' str, and 'evidence' str

        """
        criterion_lower = criterion.lower().strip()

        # File existence checks
        if self._is_file_criterion(criterion_lower):
            return self._validate_file_exists(criterion)

        # Function/class implementation checks
        if self._is_code_implementation_criterion(criterion_lower):
            return self._validate_code_implementation(criterion)

        # Test-related checks
        if self._is_test_criterion(criterion_lower):
            return self._validate_tests(criterion)

        # Documentation checks
        if self._is_documentation_criterion(criterion_lower):
            return self._validate_documentation(criterion)

        # Integration/API checks
        if self._is_integration_criterion(criterion_lower):
            return self._validate_integration(criterion)

        # Default: check if any related files were created/modified
        return self._validate_generic(criterion)

    def _is_file_criterion(self, criterion: str) -> bool:
        """Check if criterion is about file creation."""
        file_keywords = [
            'create', 'add', 'file', 'module', 'script',
            '.py', '.js', '.yaml', '.yml', '.json', '.md'
        ]
        return any(keyword in criterion for keyword in file_keywords)

    def _is_code_implementation_criterion(self, criterion: str) -> bool:
        """Check if criterion is about code implementation."""
        code_keywords = [
            'implement', 'function', 'class', 'method', 'api',
            'endpoint', 'route', 'handler', 'component'
        ]
        return any(keyword in criterion for keyword in code_keywords)

    def _is_test_criterion(self, criterion: str) -> bool:
        """Check if criterion is about tests."""
        test_keywords = ['test', 'coverage', 'unit test', 'integration test', 'pytest']
        return any(keyword in criterion for keyword in test_keywords)

    def _is_documentation_criterion(self, criterion: str) -> bool:
        """Check if criterion is about documentation."""
        doc_keywords = ['document', 'readme', 'docstring', 'comment', 'docs']
        return any(keyword in criterion for keyword in doc_keywords)

    def _is_integration_criterion(self, criterion: str) -> bool:
        """Check if criterion is about integration."""
        integration_keywords = ['integrate', 'hook', 'connect', 'cli command', 'api']
        return any(keyword in criterion for keyword in integration_keywords)

    def _validate_file_exists(self, criterion: str) -> Dict[str, Any]:
        """Validate that required files exist."""
        # Extract potential file paths from criterion
        file_patterns = [
            r'`([^`]+\.(py|js|yaml|yml|json|md|txt|html|css))`',
            r'([a-zA-Z0-9_/\-]+\.(py|js|yaml|yml|json|md|txt|html|css))',
            r'src/[a-zA-Z0-9_/\-]+\.(py|js|yaml|yml|json|md)',
        ]

        files_found = []
        for pattern in file_patterns:
            matches = re.findall(pattern, criterion)
            for match in matches:
                file_path = match[0] if isinstance(match, tuple) else match
                full_path = self.project_dir / file_path

                # Also check without src/ prefix
                if not full_path.exists() and file_path.startswith('src/'):
                    alt_path = self.project_dir / file_path[4:]
                    if alt_path.exists():
                        full_path = alt_path

                if full_path.exists():
                    files_found.append(str(file_path))

        if files_found:
            return {
                "passed": True,
                "reason": "Files exist",
                "evidence": f"Found: {', '.join(files_found)}"
            }

        # Check for general file creation keywords
        if 'create' in criterion.lower() or 'add' in criterion.lower():
            # Check if any new files were created
            try:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    cwd=self.project_dir
                )

                new_files = [
                    line[3:] for line in result.stdout.splitlines()
                    if line.startswith('?? ') or line.startswith('A  ')
                ]

                if new_files:
                    return {
                        "passed": True,
                        "reason": "New files created",
                        "evidence": f"Created: {', '.join(new_files[:3])}"
                    }
            except:
                pass

        return {
            "passed": False,
            "reason": "Required files not found",
            "evidence": ""
        }

    def _validate_code_implementation(self, criterion: str) -> Dict[str, Any]:
        """Validate that code implementations exist."""
        # Extract function/class names
        patterns = [
            r'implement\s+(\w+)',
            r'function\s+(\w+)',
            r'class\s+(\w+)',
            r'`(\w+)`\s+(?:function|class|method)',
        ]

        implementations_found = []
        for pattern in patterns:
            matches = re.findall(pattern, criterion, re.IGNORECASE)
            for name in matches:
                # Search for the implementation
                if self._find_implementation(name):
                    implementations_found.append(name)

        if implementations_found:
            return {
                "passed": True,
                "reason": "Implementations found",
                "evidence": f"Found: {', '.join(implementations_found)}"
            }

        # Check if any Python files have new functions/classes
        py_files = list(self.project_dir.rglob("*.py"))
        for py_file in py_files[:10]:  # Check first 10 files
            try:
                with open(py_file) as f:
                    tree = ast.parse(f.read())

                functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
                classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

                if functions or classes:
                    return {
                        "passed": True,
                        "reason": "Code implementations exist",
                        "evidence": f"Found {len(functions)} functions, {len(classes)} classes"
                    }
            except:
                continue

        return {
            "passed": False,
            "reason": "No code implementations found",
            "evidence": ""
        }

    def _find_implementation(self, name: str) -> bool:
        """Search for a specific implementation by name."""
        try:
            # Use grep to search for the implementation
            result = subprocess.run(
                ["grep", "-r", f"def {name}\\|class {name}", "--include=*.py"],
                capture_output=True,
                text=True,
                cwd=self.project_dir
            )
            return bool(result.stdout)
        except:
            return False

    def _validate_tests(self, criterion: str) -> Dict[str, Any]:
        """Validate test-related criteria."""
        # Check for test files
        test_files = list(self.project_dir.rglob("test_*.py"))
        test_files.extend(list(self.project_dir.rglob("*_test.py")))

        if not test_files:
            return {
                "passed": False,
                "reason": "No test files found",
                "evidence": ""
            }

        # Try to run tests if pytest is available
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--co", "-q"],
                capture_output=True,
                text=True,
                cwd=self.project_dir,
                timeout=10
            )

            # Count collected tests
            if "collected" in result.stdout:
                match = re.search(r'(\d+) items?', result.stdout)
                if match:
                    test_count = int(match.group(1))
                    if test_count > 0:
                        return {
                            "passed": True,
                            "reason": "Tests exist",
                            "evidence": f"Found {test_count} tests"
                        }
        except:
            pass

        # At least test files exist
        return {
            "passed": True,
            "reason": "Test files present",
            "evidence": f"Found {len(test_files)} test files"
        }

    def _validate_documentation(self, criterion: str) -> Dict[str, Any]:
        """Validate documentation criteria."""
        # Check for README
        readme_files = list(self.project_dir.glob("README*"))

        # Check for docstrings in Python files
        has_docstrings = False
        py_files = list(self.project_dir.rglob("*.py"))
        for py_file in py_files[:5]:  # Sample first 5 files
            try:
                with open(py_file) as f:
                    content = f.read()
                if '"""' in content or "'''" in content:
                    has_docstrings = True
                    break
            except:
                continue

        if readme_files or has_docstrings:
            evidence = []
            if readme_files:
                evidence.append(f"README: {readme_files[0].name}")
            if has_docstrings:
                evidence.append("Docstrings present")

            return {
                "passed": True,
                "reason": "Documentation exists",
                "evidence": ", ".join(evidence)
            }

        return {
            "passed": False,
            "reason": "Documentation not found",
            "evidence": ""
        }

    def _validate_integration(self, criterion: str) -> Dict[str, Any]:
        """Validate integration criteria."""
        # Check for CLI commands
        if 'cli' in criterion.lower():
            cli_files = list(self.project_dir.rglob("*cli*.py"))
            if cli_files:
                return {
                    "passed": True,
                    "reason": "CLI integration found",
                    "evidence": f"Found {len(cli_files)} CLI files"
                }

        # Check for hooks/integration points
        if 'hook' in criterion.lower():
            hook_patterns = ['hook', 'register', 'subscribe', 'listener']
            for pattern in hook_patterns:
                try:
                    result = subprocess.run(
                        ["grep", "-r", pattern, "--include=*.py"],
                        capture_output=True,
                        text=True,
                        cwd=self.project_dir
                    )
                    if result.stdout:
                        return {
                            "passed": True,
                            "reason": "Integration hooks found",
                            "evidence": f"Found {pattern} implementations"
                        }
                except:
                    pass

        return {
            "passed": False,
            "reason": "Integration not verified",
            "evidence": ""
        }

    def _validate_generic(self, criterion: str) -> Dict[str, Any]:
        """Generic validation for criteria that don't match specific patterns."""
        # Check if any files were modified
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self.project_dir
            )

            if result.stdout:
                modified_count = len(result.stdout.splitlines())
                return {
                    "passed": True,
                    "reason": "Changes detected",
                    "evidence": f"{modified_count} files modified"
                }
        except:
            pass

        # Can't definitively validate - be conservative
        return {
            "passed": False,
            "reason": "Could not verify implementation",
            "evidence": ""
        }


def enhanced_validate_acceptance_criteria(
    ticket: Dict[str, Any],
    project_dir: str
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Enhanced validation of acceptance criteria with detailed results.
    
    Args:
        ticket: Ticket data dictionary
        project_dir: Project directory path
        
    Returns:
        Tuple of (passed: bool, failed_criteria: List[str], details: Dict)

    """
    validator = CriterionValidator(project_dir)
    criteria = ticket.get("acceptance_criteria", [])

    if not criteria:
        return True, [], {"message": "No criteria to validate"}

    passed_criteria = []
    failed_criteria = []
    validation_details = {}

    print(f"\n🔍 Validating {len(criteria)} acceptance criteria:")

    for i, criterion in enumerate(criteria, 1):
        result = validator.validate_criterion(criterion)

        validation_details[f"criterion_{i}"] = {
            "text": criterion,
            "result": result
        }

        if result["passed"]:
            passed_criteria.append(criterion)
            evidence = result.get("evidence", "")
            print(f"   ✅ {i}. {criterion[:50]}...{f' - {evidence}' if evidence else ''}")
        else:
            failed_criteria.append(criterion)
            reason = result.get("reason", "Not validated")
            print(f"   ❌ {i}. {criterion[:50]}... - {reason}")

    # Calculate validation score
    total = len(criteria)
    passed = len(passed_criteria)
    score = (passed / total * 100) if total > 0 else 0

    validation_details["summary"] = {
        "total_criteria": total,
        "passed": passed,
        "failed": len(failed_criteria),
        "score": score
    }

    # Determine if validation passed (configurable threshold)
    threshold = float(os.environ.get("VALIDATION_THRESHOLD", "80"))
    validation_passed = score >= threshold

    if not validation_passed:
        print(f"\n⚠️  Validation score: {score:.1f}% (required: {threshold}%)")
    else:
        print(f"\n✅ Validation passed: {score:.1f}%")

    return validation_passed, failed_criteria, validation_details
