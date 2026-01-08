"""Tests for verification criteria templates module."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from hydra.verification_system.criteria_templates import (
    StrictnessLevel,
    CriteriaType,
    VerificationCriteria,
    CriteriaTemplate,
    BaseCriteriaTemplate,
    APIEndpointTemplate,
    CLIToolTemplate,
    LibraryTemplate,
    WebAppTemplate,
    CriteriaComposer,
    BossAgentIntegration,
    create_template_for_project_type,
    evaluate_project_against_template
)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_api_project(temp_project_dir):
    """Create a sample API project structure."""
    project_dir = temp_project_dir
    
    # Create main files
    (project_dir / "api.py").write_text("""
from flask import Flask
app = Flask(__name__)

try:
    @app.route('/test')
    def test():
        return 'Hello'
except Exception as e:
    print(f"Error: {e}")
""")
    
    (project_dir / "routes.py").write_text("""
@app.get('/users')
def get_users():
    return []

@app.post('/users')
def create_user():
    return {}
""")
    
    (project_dir / "models.py").write_text("""
class User:
    def __init__(self, name):
        self.name = name
""")
    
    (project_dir / "test_api.py").write_text("""
def test_api():
    assert True
""")
    
    return project_dir


@pytest.fixture
def sample_cli_project(temp_project_dir):
    """Create a sample CLI project structure."""
    project_dir = temp_project_dir
    
    (project_dir / "cli.py").write_text("""
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(help='CLI tool')
    parser.add_argument('--version', help='Show version')
    args = parser.parse_args()
    
    if args.version:
        print('1.0.0')
        sys.exit(0)

if __name__ == '__main__':
    main()
""")
    
    return project_dir


@pytest.fixture
def sample_library_project(temp_project_dir):
    """Create a sample library project structure."""
    project_dir = temp_project_dir
    
    (project_dir / "__init__.py").write_text('''
"""Sample library module."""

def add_numbers(a: int, b: int) -> int:
    """Add two numbers together.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        Sum of a and b
    """
    return a + b

class Calculator:
    """Simple calculator class."""
    
    def multiply(self, x, y):
        return x * y
''')
    
    # Create tests directory
    tests_dir = project_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("""
from library import add_numbers

def test_add_numbers():
    assert add_numbers(2, 3) == 5
""")
    
    return project_dir


@pytest.fixture
def sample_web_app_project(temp_project_dir):
    """Create a sample web app project structure."""
    project_dir = temp_project_dir
    
    (project_dir / "app.py").write_text("""
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    # Some validation logic
    validate_input()
    return 'Success'

def validate_input():
    pass
""")
    
    # Create templates directory
    templates_dir = project_dir / "templates"
    templates_dir.mkdir()
    (templates_dir / "index.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>Test App</title></head>
<body><h1>Hello World</h1></body>
</html>
""")
    
    # Create static directory
    static_dir = project_dir / "static"
    static_dir.mkdir()
    (static_dir / "style.css").write_text("body { margin: 0; }")
    (static_dir / "script.js").write_text("console.log('Hello');")
    
    return project_dir


class TestStrictnessLevel:
    """Test StrictnessLevel enum."""
    
    def test_strictness_levels(self):
        assert StrictnessLevel.LENIENT.value == "lenient"
        assert StrictnessLevel.BALANCED.value == "balanced"
        assert StrictnessLevel.STRICT.value == "strict"


class TestCriteriaType:
    """Test CriteriaType enum."""
    
    def test_criteria_types(self):
        assert CriteriaType.FILE_EXISTS.value == "file_exists"
        assert CriteriaType.CONTENT_CONTAINS.value == "content_contains"
        assert CriteriaType.FUNCTION_EXISTS.value == "function_exists"


class TestVerificationCriteria:
    """Test VerificationCriteria dataclass."""
    
    def test_criteria_creation(self):
        def dummy_check():
            return True
        
        criteria = VerificationCriteria(
            name="Test Criteria",
            type=CriteriaType.FILE_EXISTS,
            description="Test description",
            check_function=dummy_check
        )
        
        assert criteria.name == "Test Criteria"
        assert criteria.type == CriteriaType.FILE_EXISTS
        assert criteria.description == "Test description"
        assert criteria.check_function == dummy_check
        assert criteria.required is True
        assert criteria.strictness_level == StrictnessLevel.BALANCED


class TestBaseCriteriaTemplate:
    """Test BaseCriteriaTemplate functionality."""
    
    def test_file_exists_check(self, sample_api_project):
        template = APIEndpointTemplate()
        template.set_project_root(sample_api_project)
        
        assert template.file_exists_check("api.py") is True
        assert template.file_exists_check("nonexistent.py") is False
    
    def test_directory_exists_check(self, sample_web_app_project):
        template = WebAppTemplate()
        template.set_project_root(sample_web_app_project)
        
        assert template.directory_exists_check("templates") is True
        assert template.directory_exists_check("nonexistent") is False
    
    def test_content_contains_check(self, sample_api_project):
        template = APIEndpointTemplate()
        template.set_project_root(sample_api_project)
        
        assert template.content_contains_check("api.py", "Flask") is True
        assert template.content_contains_check("api.py", "Django") is False
    
    def test_content_matches_check(self, sample_cli_project):
        template = CLIToolTemplate()
        template.set_project_root(sample_cli_project)
        
        assert template.content_matches_check("cli.py", r"def\s+main") is True
        assert template.content_matches_check("cli.py", r"class\s+Test") is False
    
    def test_function_exists_check(self, sample_library_project):
        template = LibraryTemplate()
        template.set_project_root(sample_library_project)
        
        assert template.function_exists_check("__init__.py", "add_numbers") is True
        assert template.function_exists_check("__init__.py", "nonexistent_func") is False
    
    def test_class_exists_check(self, sample_library_project):
        template = LibraryTemplate()
        template.set_project_root(sample_library_project)
        
        assert template.class_exists_check("__init__.py", "Calculator") is True
        assert template.class_exists_check("__init__.py", "NonexistentClass") is False
    
    @patch('subprocess.run')
    def test_command_runs_check(self, mock_run, temp_project_dir):
        mock_run.return_value.returncode = 0
        
        template = CLIToolTemplate()
        template.set_project_root(temp_project_dir)
        
        assert template.command_runs_check("python --version") is True
        
        mock_run.return_value.returncode = 1
        assert template.command_runs_check("python --invalid") is False


class TestAPIEndpointTemplate:
    """Test API endpoint template."""
    
    def test_balanced_template(self, sample_api_project):
        template = APIEndpointTemplate(StrictnessLevel.BALANCED)
        template.set_project_root(sample_api_project)
        criteria_template = template.get_template()
        
        assert criteria_template.name == "API Endpoint Template"
        assert criteria_template.project_type == "api_endpoint"
        assert len(criteria_template.criteria) == 6
        
        # Check specific criteria exist
        criteria_names = [c.name for c in criteria_template.criteria]
        assert "API module exists" in criteria_names
        assert "Routes module exists" in criteria_names
        assert "HTTP methods implemented" in criteria_names
    
    def test_strict_template(self):
        template = APIEndpointTemplate(StrictnessLevel.STRICT)
        criteria_template = template.get_template()
        
        # Strict should have additional criteria
        assert len(criteria_template.criteria) > 6
        
        criteria_names = [c.name for c in criteria_template.criteria]
        assert "Input validation" in criteria_names
        assert "Authentication present" in criteria_names
        assert "API documentation" in criteria_names


class TestCLIToolTemplate:
    """Test CLI tool template."""
    
    def test_balanced_template(self, sample_cli_project):
        template = CLIToolTemplate(StrictnessLevel.BALANCED)
        template.set_project_root(sample_cli_project)
        criteria_template = template.get_template()
        
        assert criteria_template.name == "CLI Tool Template"
        assert criteria_template.project_type == "cli_tool"
        
        criteria_names = [c.name for c in criteria_template.criteria]
        assert "Main CLI file exists" in criteria_names
        assert "Argument parser implemented" in criteria_names
        assert "Help text available" in criteria_names
    
    def test_strict_template(self):
        template = CLIToolTemplate(StrictnessLevel.STRICT)
        criteria_template = template.get_template()
        
        criteria_names = [c.name for c in criteria_template.criteria]
        assert "Subcommands implemented" in criteria_names
        assert "CLI tests exist" in criteria_names


class TestLibraryTemplate:
    """Test library template."""
    
    def test_balanced_template(self, sample_library_project):
        template = LibraryTemplate(StrictnessLevel.BALANCED)
        template.set_project_root(sample_library_project)
        criteria_template = template.get_template()
        
        assert criteria_template.name == "Library Template"
        assert criteria_template.project_type == "library"
        
        criteria_names = [c.name for c in criteria_template.criteria]
        assert "Main module exists" in criteria_names
        assert "Core functionality implemented" in criteria_names
        assert "Docstrings present" in criteria_names
    
    def test_strict_template(self):
        template = LibraryTemplate(StrictnessLevel.STRICT)
        criteria_template = template.get_template()
        
        criteria_names = [c.name for c in criteria_template.criteria]
        assert "Type hints" in criteria_names
        assert "Setup file exists" in criteria_names
        assert "Documentation exists" in criteria_names


class TestWebAppTemplate:
    """Test web app template."""
    
    def test_balanced_template(self, sample_web_app_project):
        template = WebAppTemplate(StrictnessLevel.BALANCED)
        template.set_project_root(sample_web_app_project)
        criteria_template = template.get_template()
        
        assert criteria_template.name == "Web App Template"
        assert criteria_template.project_type == "web_app"
        
        criteria_names = [c.name for c in criteria_template.criteria]
        assert "App entry point exists" in criteria_names
        assert "Templates directory" in criteria_names
        assert "Routes configured" in criteria_names
    
    def test_strict_template(self):
        template = WebAppTemplate(StrictnessLevel.STRICT)
        criteria_template = template.get_template()
        
        criteria_names = [c.name for c in criteria_template.criteria]
        assert "CSS styles exist" in criteria_names
        assert "JavaScript exists" in criteria_names
        assert "Form validation" in criteria_names


class TestCriteriaComposer:
    """Test CriteriaComposer functionality."""
    
    def test_create_template(self):
        composer = CriteriaComposer()
        template = composer.create_template("api_endpoint", StrictnessLevel.STRICT)
        
        assert template.name == "API Endpoint Template"
        assert template.strictness_level == StrictnessLevel.STRICT
    
    def test_create_template_invalid_type(self):
        composer = CriteriaComposer()
        
        with pytest.raises(ValueError, match="Unknown template type"):
            composer.create_template("invalid_type")
    
    def test_compose_custom_template(self):
        composer = CriteriaComposer()
        
        def dummy_check():
            return True
        
        criteria = VerificationCriteria(
            name="Custom Check",
            type=CriteriaType.CUSTOM,
            description="Custom verification",
            check_function=dummy_check
        )
        
        template = composer.compose_custom_template(
            "Custom Template",
            "Custom description",
            [criteria]
        )
        
        assert template.name == "Custom Template"
        assert template.project_type == "custom"
        assert len(template.criteria) == 1
        assert template.criteria[0].name == "Custom Check"
    
    def test_merge_templates(self):
        composer = CriteriaComposer()
        
        api_template = composer.create_template("api_endpoint")
        cli_template = composer.create_template("cli_tool")
        
        merged = composer.merge_templates(
            [api_template, cli_template],
            "Merged Template",
            "API with CLI"
        )
        
        assert merged.name == "Merged Template"
        assert merged.project_type == "merged"
        assert len(merged.criteria) > len(api_template.criteria)
        assert len(merged.criteria) > len(cli_template.criteria)
    
    def test_get_available_templates(self):
        composer = CriteriaComposer()
        templates = composer.get_available_templates()
        
        assert "api_endpoint" in templates
        assert "cli_tool" in templates
        assert "library" in templates
        assert "web_app" in templates


class TestBossAgentIntegration:
    """Test BossAgentIntegration functionality."""
    
    def test_evaluate_criteria_template_pass(self, sample_api_project):
        composer = CriteriaComposer()
        integration = BossAgentIntegration(composer)
        
        template = APIEndpointTemplate(StrictnessLevel.BALANCED)
        template.set_project_root(sample_api_project)
        criteria_template = template.get_template()
        
        result = integration.evaluate_criteria_template(criteria_template, str(sample_api_project))
        
        assert result["template_name"] == "API Endpoint Template"
        assert result["project_type"] == "api_endpoint"
        assert result["total_criteria"] > 0
        assert result["passed_criteria"] >= 0
        assert "criteria_results" in result
    
    def test_evaluate_criteria_template_fail(self, temp_project_dir):
        composer = CriteriaComposer()
        integration = BossAgentIntegration(composer)
        
        # Empty directory should fail most checks
        template = APIEndpointTemplate(StrictnessLevel.BALANCED)
        criteria_template = template.get_template()
        
        result = integration.evaluate_criteria_template(criteria_template, str(temp_project_dir))
        
        assert result["overall_status"] == "FAIL"
        assert result["passed_criteria"] < result["total_criteria"]
    
    def test_generate_failure_feedback_pass(self):
        composer = CriteriaComposer()
        integration = BossAgentIntegration(composer)
        
        pass_result = {
            "template_name": "Test Template",
            "overall_status": "PASS",
            "criteria_results": []
        }
        
        feedback = integration.generate_failure_feedback(pass_result)
        assert "All criteria passed successfully" in feedback
    
    def test_generate_failure_feedback_fail(self):
        composer = CriteriaComposer()
        integration = BossAgentIntegration(composer)
        
        fail_result = {
            "template_name": "Test Template",
            "overall_status": "FAIL",
            "passed_criteria": 1,
            "total_criteria": 3,
            "criteria_results": [
                {
                    "name": "Test 1",
                    "description": "First test",
                    "passed": True,
                    "required": True
                },
                {
                    "name": "Test 2",
                    "description": "Second test",
                    "passed": False,
                    "required": True
                },
                {
                    "name": "Test 3",
                    "description": "Third test",
                    "passed": False,
                    "required": True,
                    "error": "File not found"
                }
            ]
        }
        
        feedback = integration.generate_failure_feedback(fail_result)
        
        assert "Test Template" in feedback
        assert "Passed: 1/3 criteria" in feedback
        assert "Test 2: Second test" in feedback
        assert "Test 3: Third test" in feedback
        assert "Error: File not found" in feedback


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_create_template_for_project_type(self):
        template = create_template_for_project_type("library", StrictnessLevel.STRICT)
        
        assert template.name == "Library Template"
        assert template.project_type == "library"
        assert template.strictness_level == StrictnessLevel.STRICT
    
    def test_evaluate_project_against_template(self, sample_library_project):
        template = create_template_for_project_type("library", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(sample_library_project), template)
        
        assert "template_name" in result
        assert "overall_status" in result
        assert "criteria_results" in result
        assert result["project_type"] == "library"


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""
    
    def test_api_project_evaluation(self, sample_api_project):
        """Test complete API project evaluation."""
        template = create_template_for_project_type("api_endpoint", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(sample_api_project), template)
        
        # Should pass most basic checks
        assert result["passed_criteria"] > 0
        
        # Check specific criteria results
        criteria_names = [c["name"] for c in result["criteria_results"]]
        assert "API module exists" in criteria_names
        assert "Routes module exists" in criteria_names
    
    def test_library_project_evaluation(self, sample_library_project):
        """Test complete library project evaluation."""
        template = create_template_for_project_type("library", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(sample_library_project), template)
        
        # Should pass most checks for well-structured library
        success_rate = result["success_rate"]
        assert success_rate > 0.5  # At least half should pass
    
    def test_web_app_project_evaluation(self, sample_web_app_project):
        """Test complete web app project evaluation."""
        template = create_template_for_project_type("web_app", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(sample_web_app_project), template)
        
        # Should pass structure checks
        structure_checks = [
            c for c in result["criteria_results"] 
            if c["name"] in ["App entry point exists", "Templates directory", "Static files directory"]
        ]
        assert all(c["passed"] for c in structure_checks)
    
    def test_cli_project_evaluation(self, sample_cli_project):
        """Test complete CLI project evaluation."""
        template = create_template_for_project_type("cli_tool", StrictnessLevel.BALANCED)
        result = evaluate_project_against_template(str(sample_cli_project), template)
        
        # Should pass basic CLI checks
        basic_checks = [
            c for c in result["criteria_results"] 
            if c["name"] in ["Main CLI file exists", "Argument parser implemented"]
        ]
        assert all(c["passed"] for c in basic_checks)
    
    def test_custom_template_composition(self, temp_project_dir):
        """Test creating and using custom templates."""
        composer = CriteriaComposer()
        
        # Create a config file
        (temp_project_dir / "config.json").write_text('{"key": "value"}')
        
        # Create custom criteria
        def config_exists_check(file_path):
            return (temp_project_dir / file_path).exists()
        
        config_criteria = VerificationCriteria(
            name="Config file exists",
            type=CriteriaType.FILE_EXISTS,
            description="Configuration file must exist",
            check_function=config_exists_check,
            args={"file_path": "config.json"}
        )
        
        custom_template = composer.compose_custom_template(
            "Custom Project Template",
            "Template with config requirement",
            [config_criteria]
        )
        
        result = evaluate_project_against_template(str(temp_project_dir), custom_template)
        
        assert result["overall_status"] == "PASS"
        assert result["passed_criteria"] == 1
        assert result["criteria_results"][0]["name"] == "Config file exists"
        assert result["criteria_results"][0]["passed"] is True


if __name__ == "__main__":
    pytest.main([__file__])