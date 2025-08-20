"""Verification Criteria Templates Module

Provides reusable verification criteria templates for common project types including
API endpoints, CLI tools, libraries, and web applications with configurable strictness levels.
"""

import json
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


class StrictnessLevel(Enum):
    """Defines verification strictness levels."""

    LENIENT = "lenient"
    BALANCED = "balanced"
    STRICT = "strict"


class CriteriaType(Enum):
    """Types of verification criteria."""

    FILE_EXISTS = "file_exists"
    DIRECTORY_EXISTS = "directory_exists"
    CONTENT_CONTAINS = "content_contains"
    CONTENT_MATCHES = "content_matches"
    FUNCTION_EXISTS = "function_exists"
    CLASS_EXISTS = "class_exists"
    TEST_COVERAGE = "test_coverage"
    DOCUMENTATION = "documentation"
    PERFORMANCE = "performance"
    SECURITY = "security"
    FUNCTIONALITY = "functionality"
    COMMAND_RUNS = "command_runs"
    API_ENDPOINT = "api_endpoint"
    CUSTOM = "custom"


@dataclass
class VerificationCriteria:
    """Single verification criteria with check function."""

    name: str
    type: CriteriaType
    description: str
    check_function: Callable[..., bool]
    args: Dict[str, Any] = field(default_factory=dict)
    required: bool = True
    strictness_level: StrictnessLevel = StrictnessLevel.BALANCED


@dataclass
class CriteriaTemplate:
    """Template containing multiple verification criteria for a project type."""

    name: str
    description: str
    project_type: str
    criteria: List[VerificationCriteria] = field(default_factory=list)
    strictness_level: StrictnessLevel = StrictnessLevel.BALANCED


class BaseCriteriaTemplate(ABC):
    """Base class for all criteria templates."""

    def __init__(self, strictness_level: StrictnessLevel = StrictnessLevel.BALANCED):
        self.strictness_level = strictness_level
        self.project_root = Path.cwd()

    @abstractmethod
    def get_template(self) -> CriteriaTemplate:
        """Return the criteria template for this project type."""
        pass

    def set_project_root(self, path: Union[str, Path]) -> None:
        """Set the project root directory."""
        self.project_root = Path(path)

    def file_exists_check(self, file_path: str) -> bool:
        """Check if a file exists."""
        return (self.project_root / file_path).exists()

    def directory_exists_check(self, dir_path: str) -> bool:
        """Check if a directory exists."""
        return (self.project_root / dir_path).is_dir()

    def content_contains_check(self, file_path: str, pattern: str) -> bool:
        """Check if file content contains specific pattern."""
        try:
            with open(self.project_root / file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return pattern in content
        except (FileNotFoundError, UnicodeDecodeError):
            return False

    def content_matches_check(self, file_path: str, regex_pattern: str) -> bool:
        """Check if file content matches regex pattern."""
        try:
            with open(self.project_root / file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return bool(re.search(regex_pattern, content, re.MULTILINE))
        except (FileNotFoundError, UnicodeDecodeError):
            return False

    def function_exists_check(self, file_path: str, function_name: str) -> bool:
        """Check if a function exists in a Python file."""
        pattern = rf"^def\s+{re.escape(function_name)}\s*\("
        return self.content_matches_check(file_path, pattern)

    def class_exists_check(self, file_path: str, class_name: str) -> bool:
        """Check if a class exists in a Python file."""
        pattern = rf"^class\s+{re.escape(class_name)}\s*[\(:]"
        return self.content_matches_check(file_path, pattern)

    def command_runs_check(self, command: str, cwd: Optional[str] = None) -> bool:
        """Check if a command runs successfully."""
        try:
            work_dir = self.project_root / cwd if cwd else self.project_root
            result = subprocess.run(
                command.split(),
                cwd=work_dir,
                capture_output=True,
                timeout=30,
                check=False
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def test_coverage_check(self, min_coverage: float = 80.0) -> bool:
        """Check if test coverage meets minimum threshold."""
        try:
            # Try pytest-cov
            result = subprocess.run(
                ["python", "-m", "pytest", "--cov=.", "--cov-report=json"],
                cwd=self.project_root,
                capture_output=True,
                timeout=60
            )
            if result.returncode == 0:
                try:
                    with open(self.project_root / "coverage.json", "r") as f:
                        data = json.load(f)
                        coverage = data.get("totals", {}).get("percent_covered", 0)
                        return coverage >= min_coverage
                except (FileNotFoundError, json.JSONDecodeError, KeyError):
                    pass

            # Fallback: check for test files
            test_files = list(self.project_root.rglob("test_*.py"))
            test_files.extend(list(self.project_root.rglob("*_test.py")))
            return len(test_files) > 0
        except Exception:
            return False


class APIEndpointTemplate(BaseCriteriaTemplate):
    """Template for API endpoint verification."""

    def get_template(self) -> CriteriaTemplate:
        criteria = [
            VerificationCriteria(
                name="API module exists",
                type=CriteriaType.FILE_EXISTS,
                description="Main API module file exists",
                check_function=self.file_exists_check,
                args={"file_path": "api.py"}
            ),
            VerificationCriteria(
                name="Routes module exists",
                type=CriteriaType.FILE_EXISTS,
                description="Routes definition file exists",
                check_function=self.file_exists_check,
                args={"file_path": "routes.py"}
            ),
            VerificationCriteria(
                name="Models defined",
                type=CriteriaType.CONTENT_CONTAINS,
                description="Data models are defined",
                check_function=self.content_contains_check,
                args={"file_path": "models.py", "pattern": "class"}
            ),
            VerificationCriteria(
                name="HTTP methods implemented",
                type=CriteriaType.CONTENT_MATCHES,
                description="HTTP methods (GET, POST, etc.) are implemented",
                check_function=self.content_matches_check,
                args={"file_path": "routes.py", "regex_pattern": r"@.*\.(get|post|put|delete)"}
            ),
            VerificationCriteria(
                name="Error handling present",
                type=CriteriaType.CONTENT_CONTAINS,
                description="Error handling is implemented",
                check_function=self.content_contains_check,
                args={"file_path": "api.py", "pattern": "try:"}
            ),
            VerificationCriteria(
                name="API tests exist",
                type=CriteriaType.FILE_EXISTS,
                description="API test file exists",
                check_function=self.file_exists_check,
                args={"file_path": "test_api.py"}
            )
        ]

        if self.strictness_level == StrictnessLevel.STRICT:
            criteria.extend([
                VerificationCriteria(
                    name="Input validation",
                    type=CriteriaType.CONTENT_CONTAINS,
                    description="Input validation is implemented",
                    check_function=self.content_contains_check,
                    args={"file_path": "api.py", "pattern": "validate"}
                ),
                VerificationCriteria(
                    name="Authentication present",
                    type=CriteriaType.CONTENT_CONTAINS,
                    description="Authentication mechanism is present",
                    check_function=self.content_contains_check,
                    args={"file_path": "api.py", "pattern": "auth"}
                ),
                VerificationCriteria(
                    name="API documentation",
                    type=CriteriaType.FILE_EXISTS,
                    description="API documentation exists",
                    check_function=self.file_exists_check,
                    args={"file_path": "api_docs.md"}
                )
            ])

        return CriteriaTemplate(
            name="API Endpoint Template",
            description="Verification template for REST API endpoints",
            project_type="api_endpoint",
            criteria=criteria,
            strictness_level=self.strictness_level
        )


class CLIToolTemplate(BaseCriteriaTemplate):
    """Template for CLI tool verification."""

    def get_template(self) -> CriteriaTemplate:
        criteria = [
            VerificationCriteria(
                name="Main CLI file exists",
                type=CriteriaType.FILE_EXISTS,
                description="Main CLI entry point exists",
                check_function=self.file_exists_check,
                args={"file_path": "cli.py"}
            ),
            VerificationCriteria(
                name="Argument parser implemented",
                type=CriteriaType.CONTENT_CONTAINS,
                description="Command line argument parsing is implemented",
                check_function=self.content_contains_check,
                args={"file_path": "cli.py", "pattern": "argparse"}
            ),
            VerificationCriteria(
                name="Help text available",
                type=CriteriaType.CONTENT_CONTAINS,
                description="Help text is available for commands",
                check_function=self.content_contains_check,
                args={"file_path": "cli.py", "pattern": "help="}
            ),
            VerificationCriteria(
                name="Exit codes handled",
                type=CriteriaType.CONTENT_CONTAINS,
                description="Proper exit codes are used",
                check_function=self.content_contains_check,
                args={"file_path": "cli.py", "pattern": "sys.exit"}
            ),
            VerificationCriteria(
                name="CLI can run",
                type=CriteriaType.COMMAND_RUNS,
                description="CLI tool runs without errors",
                check_function=self.command_runs_check,
                args={"command": "python cli.py --help"}
            )
        ]

        if self.strictness_level == StrictnessLevel.STRICT:
            criteria.extend([
                VerificationCriteria(
                    name="Subcommands implemented",
                    type=CriteriaType.CONTENT_CONTAINS,
                    description="Subcommands are properly implemented",
                    check_function=self.content_contains_check,
                    args={"file_path": "cli.py", "pattern": "subparsers"}
                ),
                VerificationCriteria(
                    name="Input validation",
                    type=CriteriaType.CONTENT_CONTAINS,
                    description="Input validation for arguments",
                    check_function=self.content_contains_check,
                    args={"file_path": "cli.py", "pattern": "validate"}
                ),
                VerificationCriteria(
                    name="CLI tests exist",
                    type=CriteriaType.FILE_EXISTS,
                    description="CLI test file exists",
                    check_function=self.file_exists_check,
                    args={"file_path": "test_cli.py"}
                )
            ])

        return CriteriaTemplate(
            name="CLI Tool Template",
            description="Verification template for command line tools",
            project_type="cli_tool",
            criteria=criteria,
            strictness_level=self.strictness_level
        )


class LibraryTemplate(BaseCriteriaTemplate):
    """Template for library verification."""

    def get_template(self) -> CriteriaTemplate:
        criteria = [
            VerificationCriteria(
                name="Main module exists",
                type=CriteriaType.FILE_EXISTS,
                description="Main library module exists",
                check_function=self.file_exists_check,
                args={"file_path": "__init__.py"}
            ),
            VerificationCriteria(
                name="Core functionality implemented",
                type=CriteriaType.CONTENT_CONTAINS,
                description="Core functions or classes are implemented",
                check_function=self.content_contains_check,
                args={"file_path": "__init__.py", "pattern": "def "}
            ),
            VerificationCriteria(
                name="Docstrings present",
                type=CriteriaType.CONTENT_CONTAINS,
                description="Functions have docstrings",
                check_function=self.content_contains_check,
                args={"file_path": "__init__.py", "pattern": '"""'}
            ),
            VerificationCriteria(
                name="Package structure",
                type=CriteriaType.DIRECTORY_EXISTS,
                description="Proper package structure exists",
                check_function=self.directory_exists_check,
                args={"dir_path": "."}
            ),
            VerificationCriteria(
                name="Tests exist",
                type=CriteriaType.FILE_EXISTS,
                description="Test files exist",
                check_function=self.file_exists_check,
                args={"file_path": "tests/test_main.py"}
            )
        ]

        if self.strictness_level == StrictnessLevel.STRICT:
            criteria.extend([
                VerificationCriteria(
                    name="Type hints",
                    type=CriteriaType.CONTENT_CONTAINS,
                    description="Type hints are used",
                    check_function=self.content_contains_check,
                    args={"file_path": "__init__.py", "pattern": "->"}
                ),
                VerificationCriteria(
                    name="Setup file exists",
                    type=CriteriaType.FILE_EXISTS,
                    description="setup.py or pyproject.toml exists",
                    check_function=self.file_exists_check,
                    args={"file_path": "setup.py"}
                ),
                VerificationCriteria(
                    name="Documentation exists",
                    type=CriteriaType.FILE_EXISTS,
                    description="Documentation file exists",
                    check_function=self.file_exists_check,
                    args={"file_path": "README.md"}
                )
            ])

        return CriteriaTemplate(
            name="Library Template",
            description="Verification template for Python libraries",
            project_type="library",
            criteria=criteria,
            strictness_level=self.strictness_level
        )


class WebAppTemplate(BaseCriteriaTemplate):
    """Template for web application verification."""

    def get_template(self) -> CriteriaTemplate:
        criteria = [
            VerificationCriteria(
                name="App entry point exists",
                type=CriteriaType.FILE_EXISTS,
                description="Main application file exists",
                check_function=self.file_exists_check,
                args={"file_path": "app.py"}
            ),
            VerificationCriteria(
                name="Templates directory",
                type=CriteriaType.DIRECTORY_EXISTS,
                description="Templates directory exists",
                check_function=self.directory_exists_check,
                args={"dir_path": "templates"}
            ),
            VerificationCriteria(
                name="Static files directory",
                type=CriteriaType.DIRECTORY_EXISTS,
                description="Static files directory exists",
                check_function=self.directory_exists_check,
                args={"dir_path": "static"}
            ),
            VerificationCriteria(
                name="Routes configured",
                type=CriteriaType.CONTENT_CONTAINS,
                description="Routes are configured",
                check_function=self.content_contains_check,
                args={"file_path": "app.py", "pattern": "@app.route"}
            ),
            VerificationCriteria(
                name="HTML templates exist",
                type=CriteriaType.FILE_EXISTS,
                description="HTML template files exist",
                check_function=self.file_exists_check,
                args={"file_path": "templates/index.html"}
            )
        ]

        if self.strictness_level == StrictnessLevel.STRICT:
            criteria.extend([
                VerificationCriteria(
                    name="CSS styles exist",
                    type=CriteriaType.FILE_EXISTS,
                    description="CSS stylesheet exists",
                    check_function=self.file_exists_check,
                    args={"file_path": "static/style.css"}
                ),
                VerificationCriteria(
                    name="JavaScript exists",
                    type=CriteriaType.FILE_EXISTS,
                    description="JavaScript file exists",
                    check_function=self.file_exists_check,
                    args={"file_path": "static/script.js"}
                ),
                VerificationCriteria(
                    name="Form validation",
                    type=CriteriaType.CONTENT_CONTAINS,
                    description="Form validation is implemented",
                    check_function=self.content_contains_check,
                    args={"file_path": "app.py", "pattern": "validate"}
                )
            ])

        return CriteriaTemplate(
            name="Web App Template",
            description="Verification template for web applications",
            project_type="web_app",
            criteria=criteria,
            strictness_level=self.strictness_level
        )


class CriteriaComposer:
    """Compose custom verification criteria from templates."""

    def __init__(self):
        self.available_templates = {
            "api_endpoint": APIEndpointTemplate,
            "cli_tool": CLIToolTemplate,
            "library": LibraryTemplate,
            "web_app": WebAppTemplate
        }

    def create_template(self, template_type: str, strictness_level: StrictnessLevel = StrictnessLevel.BALANCED) -> CriteriaTemplate:
        """Create a criteria template by type."""
        if template_type not in self.available_templates:
            raise ValueError(f"Unknown template type: {template_type}")

        template_class = self.available_templates[template_type]
        template_instance = template_class(strictness_level)
        return template_instance.get_template()

    def compose_custom_template(self, name: str, description: str, criteria: List[VerificationCriteria]) -> CriteriaTemplate:
        """Create a custom template from individual criteria."""
        return CriteriaTemplate(
            name=name,
            description=description,
            project_type="custom",
            criteria=criteria
        )

    def merge_templates(self, templates: List[CriteriaTemplate], name: str, description: str) -> CriteriaTemplate:
        """Merge multiple templates into one."""
        all_criteria = []
        for template in templates:
            all_criteria.extend(template.criteria)

        return CriteriaTemplate(
            name=name,
            description=description,
            project_type="merged",
            criteria=all_criteria
        )

    def get_available_templates(self) -> List[str]:
        """Get list of available template types."""
        return list(self.available_templates.keys())


class CriteriaTemplateFactory:
    """Factory for creating verification criteria templates.
    
    This is the main entry point for creating criteria templates for different
    project types with configurable strictness levels.
    """

    def __init__(self):
        self.composer = CriteriaComposer()
        self.templates = {
            "api": APIEndpointTemplate,
            "cli": CLIToolTemplate,
            "library": LibraryTemplate,
            "webapp": WebAppTemplate,
            "api_endpoint": APIEndpointTemplate,
            "cli_tool": CLIToolTemplate,
            "web_app": WebAppTemplate
        }

    def create(
        self,
        project_type: str,
        strictness: Union[str, StrictnessLevel] = StrictnessLevel.BALANCED
    ) -> CriteriaTemplate:
        """Create a criteria template for the specified project type.
        
        Args:
            project_type: Type of project (api, cli, library, webapp, etc.)
            strictness: Strictness level for verification
            
        Returns:
            CriteriaTemplate configured for the project type

        """
        if isinstance(strictness, str):
            strictness = StrictnessLevel(strictness)

        if project_type not in self.templates:
            # Fall back to composer for unknown types
            return self.composer.create_template(project_type, strictness)

        template_class = self.templates[project_type]
        template_instance = template_class(strictness)
        return template_instance.get_template()

    def create_custom(
        self,
        name: str,
        description: str,
        criteria: List[VerificationCriteria]
    ) -> CriteriaTemplate:
        """Create a custom criteria template.
        
        Args:
            name: Template name
            description: Template description
            criteria: List of verification criteria
            
        Returns:
            Custom CriteriaTemplate

        """
        return self.composer.compose_custom_template(name, description, criteria)

    def merge(
        self,
        templates: List[CriteriaTemplate],
        name: str,
        description: str
    ) -> CriteriaTemplate:
        """Merge multiple templates into one.
        
        Args:
            templates: List of templates to merge
            name: Name for merged template
            description: Description for merged template
            
        Returns:
            Merged CriteriaTemplate

        """
        return self.composer.merge_templates(templates, name, description)

    def list_available(self) -> List[str]:
        """Get list of available template types.
        
        Returns:
            List of available template type names

        """
        return list(self.templates.keys())


# Convenience function for backward compatibility
def get_template(project_type: str, strictness: str = "balanced") -> CriteriaTemplate:
    """Get a criteria template for the specified project type.
    
    Args:
        project_type: Type of project
        strictness: Strictness level
        
    Returns:
        CriteriaTemplate for the project type

    """
    factory = CriteriaTemplateFactory()
    return factory.create(project_type, strictness)


class BossAgentIntegration:
    """Integration layer for boss agent verification system."""

    def __init__(self, composer: CriteriaComposer):
        self.composer = composer

    def evaluate_criteria_template(self, template: CriteriaTemplate, project_root: str) -> Dict[str, Any]:
        """Evaluate all criteria in a template against a project."""
        results = []
        passed_count = 0
        total_count = len(template.criteria)

        for criteria in template.criteria:
            try:
                # Set up the check function with project root
                if hasattr(criteria.check_function, '__self__'):
                    criteria.check_function.__self__.set_project_root(project_root)

                # Execute the check
                passed = criteria.check_function(**criteria.args)

                results.append({
                    "name": criteria.name,
                    "type": criteria.type.value,
                    "description": criteria.description,
                    "passed": passed,
                    "required": criteria.required,
                    "strictness_level": criteria.strictness_level.value
                })

                if passed:
                    passed_count += 1

            except Exception as e:
                results.append({
                    "name": criteria.name,
                    "type": criteria.type.value,
                    "description": criteria.description,
                    "passed": False,
                    "required": criteria.required,
                    "strictness_level": criteria.strictness_level.value,
                    "error": str(e)
                })

        return {
            "template_name": template.name,
            "template_description": template.description,
            "project_type": template.project_type,
            "total_criteria": total_count,
            "passed_criteria": passed_count,
            "success_rate": (passed_count / total_count) if total_count > 0 else 0,
            "overall_status": "PASS" if passed_count == total_count else "FAIL",
            "criteria_results": results
        }

    def generate_failure_feedback(self, evaluation_result: Dict[str, Any]) -> str:
        """Generate feedback for failed criteria."""
        if evaluation_result["overall_status"] == "PASS":
            return "All criteria passed successfully."

        failed_criteria = [
            result for result in evaluation_result["criteria_results"]
            if not result["passed"] and result["required"]
        ]

        feedback_lines = [
            f"Template '{evaluation_result['template_name']}' failed verification.",
            f"Passed: {evaluation_result['passed_criteria']}/{evaluation_result['total_criteria']} criteria",
            "",
            "Failed required criteria:"
        ]

        for criteria in failed_criteria:
            feedback_lines.append(f"- {criteria['name']}: {criteria['description']}")
            if "error" in criteria:
                feedback_lines.append(f"  Error: {criteria['error']}")

        return "\n".join(feedback_lines)


def create_template_for_project_type(project_type: str, strictness_level: StrictnessLevel = StrictnessLevel.BALANCED) -> CriteriaTemplate:
    """Convenience function to create a template for a project type."""
    composer = CriteriaComposer()
    return composer.create_template(project_type, strictness_level)


def evaluate_project_against_template(project_root: str, template: CriteriaTemplate) -> Dict[str, Any]:
    """Convenience function to evaluate a project against a template."""
    composer = CriteriaComposer()
    integration = BossAgentIntegration(composer)
    return integration.evaluate_criteria_template(template, project_root)
