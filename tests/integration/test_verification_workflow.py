"""
Integration tests for the complete verification workflow.
"""

import pytest
import tempfile
import yaml
import json
from pathlib import Path
from unittest.mock import patch

from hydra.verification_system import CLIIntegration


class TestVerificationWorkflow:
    """Test the complete verification workflow."""
    
    def setup_test_project(self, temp_dir: str) -> tuple[str, str]:
        """Setup a test project with tickets and files."""
        project_path = Path(temp_dir)
        
        # Create project structure
        src_dir = project_path / "src" / "verification_system"
        src_dir.mkdir(parents=True)
        
        tests_dir = project_path / "tests" / "unit"
        tests_dir.mkdir(parents=True)
        
        # Create ticket file
        ticket_data = {
            "version": "1.0",
            "project": {
                "name": "Test Verification Project",
                "description": "Testing verification system workflow"
            },
            "tickets": [{
                "id": "verify_test_001",
                "title": "Implement Test Verification System",
                "status": "TODO",
                "acceptance_criteria": [
                    "Create verification engine module that scans directories and validates file existence",
                    "Implement code quality checker that validates syntax, style, and basic functionality",
                    "Create test coverage analyzer that ensures minimum test coverage for new code",
                    "Build acceptance criteria parser that extracts and validates requirements from tickets",
                    "Implement report generator that creates detailed verification reports in JSON and HTML formats"
                ],
                "artifacts": [
                    {"type": "directory", "path": "src/verification_system"},
                    {"type": "file", "path": "src/verification_system/__init__.py"},
                    {"type": "file", "path": "src/verification_system/engine.py"},
                    {"type": "file", "path": "src/verification_system/quality_checker.py"},
                    {"type": "file", "path": "src/verification_system/coverage_analyzer.py"},
                    {"type": "file", "path": "src/verification_system/criteria_parser.py"},
                    {"type": "file", "path": "src/verification_system/report_generator.py"},
                    {"type": "file", "path": "tests/unit/test_verification_system.py"}
                ]
            }]
        }
        
        ticket_file = project_path / "tickets.yaml"
        with open(ticket_file, 'w') as f:
            yaml.dump(ticket_data, f)
        
        # Create implementation files
        (src_dir / "__init__.py").write_text("""
\"\"\"Verification system package.\"\"\"
from .engine import VerificationEngine
from .quality_checker import QualityChecker
__all__ = ['VerificationEngine', 'QualityChecker']
""")
        
        (src_dir / "engine.py").write_text("""
\"\"\"Verification engine module.\"\"\"
import os
from pathlib import Path

class VerificationEngine:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
    
    def scan_directory(self, directory):
        dir_path = self.project_root / directory
        if not dir_path.exists():
            return {"exists": False, "files": []}
        
        files = [f.name for f in dir_path.iterdir() if f.is_file()]
        return {"exists": True, "files": files}
    
    def validate_file_existence(self, artifacts):
        results = []
        for artifact in artifacts:
            path = self.project_root / artifact["path"]
            exists = path.exists()
            results.append({"passed": exists, "path": artifact["path"]})
        return results
""")
        
        (src_dir / "quality_checker.py").write_text("""
\"\"\"Quality checker module.\"\"\"
import ast
from pathlib import Path

class QualityChecker:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
    
    def check_python_syntax(self, file_path):
        full_path = self.project_root / file_path
        if not full_path.exists():
            return {"passed": False, "score": 0.0}
        
        try:
            with open(full_path, 'r') as f:
                source = f.read()
            ast.parse(source)
            return {"passed": True, "score": 1.0}
        except SyntaxError:
            return {"passed": False, "score": 0.0}
    
    def run_all_checks(self, file_path):
        syntax_result = self.check_python_syntax(file_path)
        return {
            "overall_passed": syntax_result["passed"],
            "overall_score": syntax_result["score"],
            "checks": [syntax_result]
        }
""")
        
        (src_dir / "coverage_analyzer.py").write_text("""
\"\"\"Coverage analyzer module.\"\"\"
from pathlib import Path

class CoverageAnalyzer:
    def __init__(self, project_root, min_coverage=0.8):
        self.project_root = Path(project_root)
        self.min_coverage = min_coverage
    
    def find_test_files(self):
        test_files = list(self.project_root.glob("**/test_*.py"))
        return test_files
    
    def estimate_line_coverage(self, file_path):
        test_files = self.find_test_files()
        has_tests = len(test_files) > 0
        
        return {
            "has_tests": has_tests,
            "estimated_coverage": 0.8 if has_tests else 0.0,
            "meets_threshold": has_tests
        }
    
    def run_coverage_analysis(self, artifacts):
        python_files = [a for a in artifacts if a.get("path", "").endswith(".py")]
        results = []
        
        for artifact in python_files:
            result = self.estimate_line_coverage(artifact["path"])
            result["file_path"] = artifact["path"]
            results.append(result)
        
        total_files = len(results)
        files_with_tests = sum(1 for r in results if r["has_tests"])
        avg_coverage = sum(r["estimated_coverage"] for r in results) / total_files if total_files > 0 else 0
        
        return {
            "total_files": total_files,
            "files_with_tests": files_with_tests,
            "average_coverage": avg_coverage,
            "meets_threshold": avg_coverage >= self.min_coverage,
            "file_results": results
        }
""")
        
        (src_dir / "criteria_parser.py").write_text("""
\"\"\"Criteria parser module.\"\"\"
import re

class CriteriaParser:
    def __init__(self):
        self.file_patterns = [r'([a-zA-Z_][a-zA-Z0-9_/]*\\.py)']
    
    def extract_requirements_from_text(self, text):
        requirements = []
        for pattern in self.file_patterns:
            matches = re.findall(pattern, text)
            requirements.extend(matches)
        return requirements
    
    def parse_criterion(self, criterion_text, index):
        return {
            "id": f"criterion_{index:03d}",
            "text": criterion_text,
            "requirements": self.extract_requirements_from_text(criterion_text),
            "completed": False,
            "verified": False
        }
    
    def parse_ticket_criteria(self, ticket_data):
        criteria_data = ticket_data.get("acceptance_criteria", [])
        criteria = []
        
        for i, criterion_text in enumerate(criteria_data):
            criterion = self.parse_criterion(criterion_text, i + 1)
            criteria.append(criterion)
        
        return {
            "ticket_id": ticket_data.get("id"),
            "criteria": criteria,
            "total_count": len(criteria),
            "completed_count": sum(1 for c in criteria if c["completed"]),
            "verified_count": sum(1 for c in criteria if c["verified"])
        }
""")
        
        (src_dir / "report_generator.py").write_text("""
\"\"\"Report generator module.\"\"\"
import json
from pathlib import Path
from datetime import datetime

class ReportGenerator:
    def __init__(self, output_dir=".hydra/reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_json_report(self, verification_results, filename=None):
        if not filename:
            ticket_id = verification_results.get("ticket_id", "unknown")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"verification_report_{ticket_id}_{timestamp}.json"
        
        output_path = self.output_dir / filename
        
        report_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "report_type": "verification_report"
            },
            "summary": self._generate_summary(verification_results),
            "detailed_results": verification_results
        }
        
        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        return str(output_path)
    
    def generate_html_report(self, verification_results, filename=None):
        if not filename:
            ticket_id = verification_results.get("ticket_id", "unknown")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"verification_report_{ticket_id}_{timestamp}.html"
        
        output_path = self.output_dir / filename
        
        html_content = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Verification Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
        .pass {{ color: green; }}
        .fail {{ color: red; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Verification Report</h1>
        <p>Ticket: {verification_results.get("ticket_id", "Unknown")}</p>
        <p>Generated: {datetime.now().isoformat()}</p>
    </div>
    
    <div class="section">
        <h2>Summary</h2>
        <p>Overall Status: {"PASS" if self._determine_overall_status(verification_results) else "FAIL"}</p>
    </div>
    
    <div class="section">
        <h2>Details</h2>
        <pre>{json.dumps(verification_results, indent=2, default=str)}</pre>
    </div>
</body>
</html>
        '''
        
        with open(output_path, 'w') as f:
            f.write(html_content)
        
        return str(output_path)
    
    def _generate_summary(self, results):
        return {
            "ticket_id": results.get("ticket_id"),
            "timestamp": datetime.now().isoformat(),
            "overall_status": "PASS" if self._determine_overall_status(results) else "FAIL"
        }
    
    def _determine_overall_status(self, results):
        file_passed = results.get("file_verification", {}).get("overall_status") == "PASS"
        quality_passed = results.get("quality_checks", {}).get("overall_passed", False)
        coverage_passed = results.get("coverage_analysis", {}).get("meets_threshold", False)
        return file_passed and quality_passed and coverage_passed
""")
        
        # Create test file
        (tests_dir / "test_verification_system.py").write_text("""
\"\"\"Test file for verification system.\"\"\"
import pytest

def test_verification_engine():
    \"\"\"Test verification engine.\"\"\"
    assert True

def test_quality_checker():
    \"\"\"Test quality checker.\"\"\"
    assert True

def test_coverage_analyzer():
    \"\"\"Test coverage analyzer.\"\"\"
    assert True

def test_criteria_parser():
    \"\"\"Test criteria parser.\"\"\"
    assert True

def test_report_generator():
    \"\"\"Test report generator.\"\"\"
    assert True
""")
        
        return str(project_path), str(ticket_file)
    
    def test_complete_workflow_success(self):
        """Test complete verification workflow with successful results."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path, ticket_file = self.setup_test_project(temp_dir)
            
            # Run verification
            cli = CLIIntegration()
            cli.setup_components(project_path)
            
            results = cli.run_complete_verification(ticket_file, "verify_test_001")
            
            # Verify results
            assert results["success"] is True
            assert results["ticket_id"] == "verify_test_001"
            
            # Check file verification
            file_verification = results["file_verification"]
            assert file_verification["overall_status"] == "PASS"
            assert file_verification["passed_artifacts"] > 0
            
            # Check quality results
            quality_checks = results["quality_checks"]
            assert quality_checks["overall_passed"] is True
            assert quality_checks["total_files"] > 0
            
            # Check coverage results
            coverage_analysis = results["coverage_analysis"]
            static_analysis = coverage_analysis["static_analysis"]
            assert static_analysis["total_files"] > 0
            assert static_analysis["files_with_tests"] > 0
            
            # Check criteria validation
            criteria_validation = results["criteria_validation"]
            assert criteria_validation["total_criteria"] == 5
    
    def test_complete_workflow_with_missing_files(self):
        """Test verification workflow with missing files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path, ticket_file = self.setup_test_project(temp_dir)
            
            # Remove a required file
            missing_file = Path(project_path) / "src" / "verification_system" / "engine.py"
            missing_file.unlink()
            
            # Run verification
            cli = CLIIntegration()
            cli.setup_components(project_path)
            
            results = cli.run_complete_verification(ticket_file, "verify_test_001")
            
            # Verify results show failure
            assert results["success"] is True  # The verification ran successfully
            
            file_verification = results["file_verification"]
            assert file_verification["overall_status"] == "FAIL"
            assert file_verification["passed_artifacts"] < file_verification["total_artifacts"]
    
    def test_report_generation(self):
        """Test report generation functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path, ticket_file = self.setup_test_project(temp_dir)
            
            # Run verification
            cli = CLIIntegration()
            cli.setup_components(project_path)
            
            results = cli.run_complete_verification(ticket_file, "verify_test_001")
            
            # Generate reports
            json_report = cli.report_generator.generate_json_report(results, "test_report.json")
            html_report = cli.report_generator.generate_html_report(results, "test_report.html")
            
            # Verify reports were created
            assert Path(json_report).exists()
            assert Path(html_report).exists()
            
            # Verify JSON report content
            with open(json_report, 'r') as f:
                report_data = json.load(f)
            
            assert report_data["metadata"]["report_type"] == "verification_report"
            assert report_data["detailed_results"]["ticket_id"] == "verify_test_001"
            
            # Verify HTML report content
            with open(html_report, 'r') as f:
                html_content = f.read()
            
            assert "Verification Report" in html_content
            assert "verify_test_001" in html_content
    
    def test_cli_integration_verify_command(self):
        """Test CLI integration with verify command."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path, ticket_file = self.setup_test_project(temp_dir)
            
            # Test CLI argument parsing
            cli = CLIIntegration()
            parser = cli.create_argument_parser()
            
            args = parser.parse_args([
                'verify', ticket_file, 'verify_test_001',
                '--project-root', project_path,
                '--report', '--html'
            ])
            
            assert args.command == 'verify'
            assert args.ticket_file == ticket_file
            assert args.ticket_id == 'verify_test_001'
            assert args.project_root == project_path
            assert args.report is True
            assert args.html is True
    
    def test_cli_files_command(self):
        """Test CLI files command."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path, ticket_file = self.setup_test_project(temp_dir)
            
            cli = CLIIntegration()
            parser = cli.create_argument_parser()
            
            args = parser.parse_args([
                'files', ticket_file, 'verify_test_001',
                '--project-root', project_path
            ])
            
            assert args.command == 'files'
            assert args.ticket_file == ticket_file
            assert args.ticket_id == 'verify_test_001'
    
    def test_criteria_parsing_workflow(self):
        """Test criteria parsing workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path, ticket_file = self.setup_test_project(temp_dir)
            
            cli = CLIIntegration()
            cli.setup_components(project_path)
            
            # Parse criteria
            parsed_criteria = cli.criteria_parser.load_and_parse_ticket(ticket_file, "verify_test_001")
            
            assert parsed_criteria is not None
            assert parsed_criteria.ticket_id == "verify_test_001"
            assert parsed_criteria.total_count == 5
            assert len(parsed_criteria.criteria) == 5
            
            # Check that requirements were extracted
            for criterion in parsed_criteria.criteria:
                assert criterion.id.startswith("criterion_")
                assert len(criterion.text) > 0
    
    def test_configuration_workflow(self):
        """Test configuration workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test default config creation
            from hydra.verification_system.config import VerificationConfig
            
            config = VerificationConfig()
            config_file = Path(temp_dir) / "test_config.yaml"
            
            assert config.create_default_config(str(config_file)) is True
            assert config_file.exists()
            
            # Test loading the created config
            new_config = VerificationConfig(str(config_file))
            assert new_config.validate_config() is True
            
            # Test modifying and saving config
            new_config.set_setting("coverage_settings.min_coverage", 0.9)
            assert new_config.save_config() is True
            
            # Verify the change was saved
            reload_config = VerificationConfig(str(config_file))
            assert reload_config.get_setting("coverage_settings.min_coverage") == 0.9
    
    def test_error_handling(self):
        """Test error handling in verification workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cli = CLIIntegration()
            cli.setup_components(temp_dir)
            
            # Test with non-existent ticket file
            results = cli.run_complete_verification("nonexistent.yaml", "test_001")
            assert results["success"] is False
            assert "error" in results
            
            # Test with non-existent ticket ID
            project_path, ticket_file = self.setup_test_project(temp_dir)
            results = cli.run_complete_verification(ticket_file, "nonexistent_ticket")
            assert results["success"] is False
            assert "error" in results
    
    @pytest.mark.parametrize("command", ["files", "quality", "coverage", "criteria"])
    def test_individual_command_workflows(self, command):
        """Test individual command workflows."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path, ticket_file = self.setup_test_project(temp_dir)
            
            cli = CLIIntegration()
            parser = cli.create_argument_parser()
            
            args = parser.parse_args([
                command, ticket_file, 'verify_test_001',
                '--project-root', project_path
            ])
            
            assert args.command == command
            assert args.ticket_file == ticket_file
            assert args.ticket_id == 'verify_test_001'
            assert args.project_root == project_path


if __name__ == "__main__":
    pytest.main([__file__])