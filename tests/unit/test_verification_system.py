"""
Unit tests for the verification system.
"""

import pytest
import tempfile
import json
import yaml
from pathlib import Path
from unittest.mock import Mock, patch

from hydra.verification_system import (
    VerificationEngine,
    QualityChecker,
    CoverageAnalyzer,
    CriteriaParser,
    ReportGenerator,
    CLIIntegration,
    VerificationConfig
)


class TestVerificationEngine:
    """Test the verification engine."""
    
    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = VerificationEngine(temp_dir)
            assert engine.project_root == Path(temp_dir)
            assert engine.results == []
    
    def test_scan_directory_existing(self):
        """Test scanning an existing directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            test_dir = Path(temp_dir) / "test_dir"
            test_dir.mkdir()
            (test_dir / "file1.py").write_text("print('hello')")
            (test_dir / "file2.txt").write_text("content")
            (test_dir / "subdir").mkdir()
            
            engine = VerificationEngine(temp_dir)
            result = engine.scan_directory("test_dir")
            
            assert result["exists"] is True
            assert result["total_files"] == 2
            assert len(result["files"]) == 2
            assert len(result["subdirectories"]) == 1
    
    def test_scan_directory_nonexistent(self):
        """Test scanning a non-existent directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = VerificationEngine(temp_dir)
            result = engine.scan_directory("nonexistent")
            
            assert result["exists"] is False
            assert result["total_files"] == 0
    
    def test_validate_file_existence(self):
        """Test file existence validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test file
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("print('hello')")
            
            engine = VerificationEngine(temp_dir)
            artifacts = [
                {"type": "file", "path": "test.py"},
                {"type": "file", "path": "missing.py"}
            ]
            
            results = engine.validate_file_existence(artifacts)
            
            assert len(results) == 2
            assert results[0].passed is True
            assert results[1].passed is False
    
    def test_load_ticket_file_yaml(self):
        """Test loading YAML ticket file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            ticket_data = {
                "tickets": [
                    {"id": "001", "title": "Test Ticket"}
                ]
            }
            yaml.dump(ticket_data, f)
            f.flush()
            
            engine = VerificationEngine(".")
            result = engine.load_ticket_file(f.name)
            
            assert result["tickets"][0]["id"] == "001"
    
    def test_find_ticket_by_id(self):
        """Test finding ticket by ID."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            ticket_data = {
                "tickets": [
                    {"id": "001", "title": "Test Ticket 1"},
                    {"id": "002", "title": "Test Ticket 2"}
                ]
            }
            yaml.dump(ticket_data, f)
            f.flush()
            
            engine = VerificationEngine(".")
            ticket = engine.find_ticket_by_id(f.name, "002")
            
            assert ticket is not None
            assert ticket["title"] == "Test Ticket 2"
            
            missing_ticket = engine.find_ticket_by_id(f.name, "999")
            assert missing_ticket is None


class TestQualityChecker:
    """Test the quality checker."""
    
    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            checker = QualityChecker(temp_dir)
            assert checker.project_root == Path(temp_dir)
    
    def test_check_python_syntax_valid(self):
        """Test syntax check with valid Python."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("def hello():\n    print('world')")
            
            checker = QualityChecker(temp_dir)
            result = checker.check_python_syntax("test.py")
            
            assert result.passed is True
            assert result.score == 1.0
    
    def test_check_python_syntax_invalid(self):
        """Test syntax check with invalid Python."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("def hello(\n    print('world')")  # Missing closing paren
            
            checker = QualityChecker(temp_dir)
            result = checker.check_python_syntax("test.py")
            
            assert result.passed is False
            assert result.score == 0.0
    
    def test_check_code_style(self):
        """Test code style checking."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("def hello():\n    print('world')")
            
            checker = QualityChecker(temp_dir)
            result = checker.check_code_style("test.py")
            
            assert result.passed is True
            assert result.score >= 0.8
    
    def test_run_all_checks(self):
        """Test running all quality checks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("def hello():\n    print('world')")
            
            checker = QualityChecker(temp_dir)
            result = checker.run_all_checks("test.py")
            
            assert "overall_score" in result
            assert "checks" in result
            assert len(result["checks"]) == 4


class TestCoverageAnalyzer:
    """Test the coverage analyzer."""
    
    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = CoverageAnalyzer(temp_dir)
            assert analyzer.project_root == Path(temp_dir)
            assert analyzer.min_coverage == 0.8
    
    def test_extract_functions_and_classes(self):
        """Test extracting functions and classes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("""
class TestClass:
    def method1(self):
        pass

def function1():
    pass

def function2():
    pass
""")
            
            analyzer = CoverageAnalyzer(temp_dir)
            result = analyzer.extract_functions_and_classes("test.py")
            
            assert "TestClass" in result["classes"]
            assert "method1" in result["functions"]
            assert "function1" in result["functions"]
            assert "function2" in result["functions"]
    
    def test_find_corresponding_test_file(self):
        """Test finding corresponding test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source and test files
            (Path(temp_dir) / "module.py").write_text("def func(): pass")
            (Path(temp_dir) / "test_module.py").write_text("def test_func(): pass")
            
            analyzer = CoverageAnalyzer(temp_dir)
            test_file = analyzer.find_corresponding_test_file("module.py")
            
            assert test_file == "test_module.py"
    
    def test_estimate_line_coverage(self):
        """Test estimating line coverage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source file
            source_file = Path(temp_dir) / "module.py"
            source_file.write_text("def func():\n    return 'hello'")
            
            # Create test file
            test_file = Path(temp_dir) / "test_module.py"
            test_file.write_text("def test_func():\n    assert func() == 'hello'")
            
            analyzer = CoverageAnalyzer(temp_dir)
            result = analyzer.estimate_line_coverage("module.py")
            
            assert result["has_tests"] is True
            assert result["total_lines"] > 0


class TestCriteriaParser:
    """Test the criteria parser."""
    
    def test_init(self):
        """Test initialization."""
        parser = CriteriaParser()
        assert len(parser.requirement_patterns) > 0
        assert len(parser.validation_keywords) > 0
    
    def test_extract_requirements_from_text(self):
        """Test extracting requirements from criterion text."""
        parser = CriteriaParser()
        text = "Create engine.py file and implement functionality"
        
        requirements = parser.extract_requirements_from_text(text)
        
        assert any("engine.py" in req for req in requirements)
        assert any("functionality" in req for req in requirements)
    
    def test_extract_validation_rules(self):
        """Test extracting validation rules."""
        parser = CriteriaParser()
        text = "Create tests with coverage and validate functionality"
        
        rules = parser.extract_validation_rules(text)
        
        assert "requires_test" in rules
        assert "requires_coverage" in rules
        assert "requires_validate" in rules
    
    def test_parse_criterion_string(self):
        """Test parsing criterion from string."""
        parser = CriteriaParser()
        criterion_text = "Create engine.py module that scans directories"
        
        result = parser.parse_criterion(criterion_text, 1)
        
        assert result.id == "criterion_001"
        assert result.text == criterion_text
        assert result.completed is False
        assert result.verified is False
    
    def test_parse_criterion_dict(self):
        """Test parsing criterion from dictionary."""
        parser = CriteriaParser()
        criterion_data = {
            "criterion": "Create engine.py module",
            "completed": True,
            "verified": False
        }
        
        result = parser.parse_criterion(criterion_data, 1)
        
        assert result.completed is True
        assert result.verified is False


class TestReportGenerator:
    """Test the report generator."""
    
    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = ReportGenerator(temp_dir)
            assert generator.output_dir == Path(temp_dir)
    
    def test_generate_summary_data(self):
        """Test generating summary data."""
        generator = ReportGenerator()
        
        verification_results = {
            "ticket_id": "test_001",
            "title": "Test Ticket",
            "file_verification": {
                "overall_status": "PASS",
                "success_rate": 1.0
            },
            "quality_checks": {
                "overall_score": 0.9,
                "overall_passed": True
            }
        }
        
        summary = generator.generate_summary_data(verification_results)
        
        assert summary["ticket_id"] == "test_001"
        assert "component_scores" in summary
        assert summary["overall_status"] in ["PASS", "FAIL"]
    
    def test_generate_json_report(self):
        """Test generating JSON report."""
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = ReportGenerator(temp_dir)
            
            verification_results = {
                "ticket_id": "test_001",
                "title": "Test Ticket"
            }
            
            report_path = generator.generate_json_report(verification_results, "test_report.json")
            
            assert Path(report_path).exists()
            with open(report_path, 'r') as f:
                report_data = json.load(f)
            
            assert report_data["detailed_results"]["ticket_id"] == "test_001"


class TestCLIIntegration:
    """Test the CLI integration."""
    
    def test_init(self):
        """Test initialization."""
        cli = CLIIntegration()
        assert cli.verification_engine is None
        assert cli.quality_checker is None
    
    def test_create_argument_parser(self):
        """Test creating argument parser."""
        cli = CLIIntegration()
        parser = cli.create_argument_parser()
        
        # Test that parser can parse basic arguments
        args = parser.parse_args(['verify', 'tickets.yaml', 'test_001'])
        assert args.command == 'verify'
        assert args.ticket_file == 'tickets.yaml'
        assert args.ticket_id == 'test_001'
    
    def test_setup_components(self):
        """Test setting up components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cli = CLIIntegration()
            cli.setup_components(temp_dir)
            
            assert cli.verification_engine is not None
            assert cli.quality_checker is not None
            assert cli.coverage_analyzer is not None
            assert cli.criteria_parser is not None
            assert cli.report_generator is not None


class TestVerificationConfig:
    """Test the verification configuration."""
    
    def test_init_with_defaults(self):
        """Test initialization with default config."""
        config = VerificationConfig()
        assert config.config_data is not None
        assert "quality_thresholds" in config.config_data
    
    def test_get_setting(self):
        """Test getting settings."""
        config = VerificationConfig()
        
        # Test getting nested setting
        syntax_score = config.get_setting("quality_thresholds.syntax_score", 0.5)
        assert syntax_score == 1.0
        
        # Test getting non-existent setting with default
        missing = config.get_setting("missing.setting", "default_value")
        assert missing == "default_value"
    
    def test_set_setting(self):
        """Test setting values."""
        config = VerificationConfig()
        
        config.set_setting("quality_thresholds.syntax_score", 0.95)
        assert config.get_setting("quality_thresholds.syntax_score") == 0.95
    
    def test_validate_config(self):
        """Test config validation."""
        config = VerificationConfig()
        assert config.validate_config() is True
        
        # Test with invalid config
        config.set_setting("quality_thresholds.syntax_score", 1.5)  # Invalid > 1.0
        assert config.validate_config() is False
    
    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config = VerificationConfig()
            config.set_setting("test_setting", "test_value")
            
            # Save config
            assert config.save_config(f.name) is True
            
            # Load config
            new_config = VerificationConfig(f.name)
            assert new_config.get_setting("test_setting") == "test_value"


class TestIntegration:
    """Integration tests for the verification system."""
    
    def test_complete_verification_workflow(self):
        """Test complete verification workflow."""
        import os
        from unittest.mock import patch
        
        # Ensure proper test environment
        with patch.dict(os.environ, {"TESTING": "1"}):
            with tempfile.TemporaryDirectory() as temp_dir:
                # Create ticket file
                ticket_data = {
                    "tickets": [{
                        "id": "test_001",
                        "title": "Test Integration",
                        "acceptance_criteria": [
                            "Create test.py file with valid syntax"
                        ],
                        "artifacts": [
                            {"type": "file", "path": "test.py"}
                        ]
                    }]
                }
                
                ticket_file = Path(temp_dir) / "tickets.yaml"
                with open(ticket_file, 'w') as f:
                    yaml.dump(ticket_data, f)
                
                # Create the required file
                test_file = Path(temp_dir) / "test.py"
                test_file.write_text("def hello():\n    return 'world'")
                
                # Mock subprocess calls to avoid git errors
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stdout = ""
                    
                    # Run verification
                    cli = CLIIntegration()
                    cli.setup_components(temp_dir)
                    
                    results = cli.run_complete_verification(str(ticket_file), "test_001")
                    
                    assert results["success"] is True
                    assert "file_verification" in results
                    assert "quality_checks" in results
                    assert "coverage_analysis" in results
                    assert "criteria_validation" in results


if __name__ == "__main__":
    pytest.main([__file__])