"""Verification Configuration Module

Provides configuration system for customizing verification rules and thresholds.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass
class QualityThresholds:
    """Quality check thresholds configuration."""

    syntax_score: float = 1.0
    style_score: float = 0.8
    complexity_score: float = 0.7
    import_resolution_score: float = 0.9


@dataclass
class CoverageSettings:
    """Coverage analysis settings."""

    min_coverage: float = 0.8
    min_function_coverage: float = 0.7
    min_class_coverage: float = 0.6
    require_test_files: bool = True


@dataclass
class FileVerificationSettings:
    """File verification settings."""

    required_extensions: list = None
    excluded_patterns: list = None
    check_file_sizes: bool = True
    max_file_size_mb: float = 10.0

    def __post_init__(self):
        if self.required_extensions is None:
            self.required_extensions = ['.py', '.yaml', '.yml', '.json', '.md']
        if self.excluded_patterns is None:
            self.excluded_patterns = ['__pycache__', '*.pyc', '.git', '.venv']


@dataclass
class ReportSettings:
    """Report generation settings."""

    output_dir: str = ".hydra/reports"
    generate_html: bool = True
    generate_json: bool = True
    include_detailed_logs: bool = False
    max_log_lines: int = 1000


@dataclass
class CriteriaValidationSettings:
    """Criteria validation settings."""

    require_verification_methods: bool = True
    auto_detect_file_requirements: bool = True
    strict_validation: bool = False
    completion_threshold: float = 1.0  # 100% completion required


class VerificationConfig:
    """Configuration manager for the verification system.
    """

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration."""
        self.config_file = config_file or self._find_config_file()
        self.config_data = self._load_config()
        self._validate_loaded_config()

    def _find_config_file(self) -> str:
        """Find configuration file in standard locations."""
        possible_locations = [
            ".hydra/verification_config.yaml",
            ".hydra/verification_config.yml",
            "verification_config.yaml",
            "verification_config.yml",
            ".verification_config.yaml"
        ]

        for location in possible_locations:
            if Path(location).exists():
                return location

        # Return default location even if it doesn't exist
        return ".hydra/verification_config.yaml"

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create defaults."""
        config_path = Path(self.config_file)

        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    if config_path.suffix in ['.yaml', '.yml']:
                        return yaml.safe_load(f) or {}
                    elif config_path.suffix == '.json':
                        return json.load(f)
                    else:
                        raise ValueError(f"Unsupported config file format: {config_path.suffix}")
            except Exception as e:
                print(f"Warning: Failed to load config from {config_path}: {e}")
                print("Using default configuration.")

        return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "version": "1.0",
            "quality_thresholds": asdict(QualityThresholds()),
            "coverage_settings": asdict(CoverageSettings()),
            "file_verification": asdict(FileVerificationSettings()),
            "report_settings": asdict(ReportSettings()),
            "criteria_validation": asdict(CriteriaValidationSettings()),
            "general": {
                "verbose_output": False,
                "fail_fast": False,
                "parallel_checks": True,
                "max_workers": 4,
                "timeout_seconds": 300
            },
            "custom_rules": {
                "enabled": False,
                "rules_file": ".hydra/custom_verification_rules.py"
            }
        }

    def _validate_loaded_config(self):
        """Validate the loaded configuration."""
        required_sections = [
            "quality_thresholds",
            "coverage_settings",
            "file_verification",
            "report_settings",
            "criteria_validation"
        ]

        for section in required_sections:
            if section not in self.config_data:
                print(f"Warning: Missing config section '{section}', using defaults")
                default_config = self._get_default_config()
                self.config_data[section] = default_config[section]

    def get_setting(self, setting_path: str, default: Any = None) -> Any:
        """Get a setting value using dot notation (e.g., 'quality_thresholds.syntax_score')."""
        keys = setting_path.split('.')
        value = self.config_data

        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set_setting(self, setting_path: str, value: Any):
        """Set a setting value using dot notation."""
        keys = setting_path.split('.')
        config_section = self.config_data

        # Navigate to the parent section
        for key in keys[:-1]:
            if key not in config_section:
                config_section[key] = {}
            config_section = config_section[key]

        # Set the final value
        config_section[keys[-1]] = value

    def get_quality_thresholds(self) -> QualityThresholds:
        """Get quality check thresholds."""
        thresholds_data = self.config_data.get("quality_thresholds", {})
        return QualityThresholds(**thresholds_data)

    def get_coverage_settings(self) -> CoverageSettings:
        """Get coverage analysis settings."""
        coverage_data = self.config_data.get("coverage_settings", {})
        return CoverageSettings(**coverage_data)

    def get_file_verification_settings(self) -> FileVerificationSettings:
        """Get file verification settings."""
        file_data = self.config_data.get("file_verification", {})
        return FileVerificationSettings(**file_data)

    def get_report_settings(self) -> ReportSettings:
        """Get report generation settings."""
        report_data = self.config_data.get("report_settings", {})
        return ReportSettings(**report_data)

    def get_criteria_validation_settings(self) -> CriteriaValidationSettings:
        """Get criteria validation settings."""
        criteria_data = self.config_data.get("criteria_validation", {})
        return CriteriaValidationSettings(**criteria_data)

    def save_config(self, config_file: Optional[str] = None) -> bool:
        """Save current configuration to file."""
        output_file = config_file or self.config_file
        output_path = Path(output_file)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                if output_path.suffix in ['.yaml', '.yml']:
                    yaml.dump(self.config_data, f, default_flow_style=False, indent=2)
                elif output_path.suffix == '.json':
                    json.dump(self.config_data, f, indent=2)
                else:
                    # Default to YAML
                    yaml.dump(self.config_data, f, default_flow_style=False, indent=2)

            return True

        except Exception as e:
            print(f"Error saving config to {output_path}: {e}")
            return False

    def create_default_config(self, output_file: Optional[str] = None) -> bool:
        """Create a default configuration file."""
        output_file = output_file or self.config_file
        self.config_data = self._get_default_config()
        return self.save_config(output_file)

    def validate_config(self) -> bool:
        """Validate the current configuration."""
        validation_errors = []

        # Validate quality thresholds
        quality_thresholds = self.config_data.get("quality_thresholds", {})
        for threshold_name, threshold_value in quality_thresholds.items():
            if not isinstance(threshold_value, (int, float)) or not (0.0 <= threshold_value <= 1.0):
                validation_errors.append(f"Invalid quality threshold '{threshold_name}': {threshold_value}")

        # Validate coverage settings
        coverage_settings = self.config_data.get("coverage_settings", {})
        min_coverage = coverage_settings.get("min_coverage", 0.8)
        if not isinstance(min_coverage, (int, float)) or not (0.0 <= min_coverage <= 1.0):
            validation_errors.append(f"Invalid min_coverage: {min_coverage}")

        # Validate file verification settings
        file_verification = self.config_data.get("file_verification", {})
        max_file_size = file_verification.get("max_file_size_mb", 10.0)
        if not isinstance(max_file_size, (int, float)) or max_file_size < 0:
            validation_errors.append(f"Invalid max_file_size_mb: {max_file_size}")

        # Validate report settings
        report_settings = self.config_data.get("report_settings", {})
        output_dir = report_settings.get("output_dir", ".hydra/reports")
        if not isinstance(output_dir, str) or not output_dir.strip():
            validation_errors.append(f"Invalid output_dir: {output_dir}")

        # Validate general settings
        general_settings = self.config_data.get("general", {})
        max_workers = general_settings.get("max_workers", 4)
        if not isinstance(max_workers, int) or max_workers < 1:
            validation_errors.append(f"Invalid max_workers: {max_workers}")

        timeout_seconds = general_settings.get("timeout_seconds", 300)
        if not isinstance(timeout_seconds, int) or timeout_seconds < 1:
            validation_errors.append(f"Invalid timeout_seconds: {timeout_seconds}")

        if validation_errors:
            print("Configuration validation errors:")
            for error in validation_errors:
                print(f"  - {error}")
            return False

        return True

    def display_config(self):
        """Display current configuration in a readable format."""
        print("Current Verification Configuration:")
        print("=" * 50)

        def print_section(section_name: str, section_data: Dict[str, Any], indent: int = 0):
            prefix = "  " * indent
            print(f"{prefix}{section_name}:")

            for key, value in section_data.items():
                if isinstance(value, dict):
                    print_section(key, value, indent + 1)
                else:
                    print(f"{prefix}  {key}: {value}")

        for section_name, section_data in self.config_data.items():
            if isinstance(section_data, dict):
                print_section(section_name, section_data)
            else:
                print(f"{section_name}: {section_data}")
            print()

        print(f"Configuration file: {self.config_file}")
        print(f"File exists: {Path(self.config_file).exists()}")

    def merge_config(self, override_config: Dict[str, Any]):
        """Merge override configuration with current config."""
        def deep_merge(base_dict: Dict[str, Any], override_dict: Dict[str, Any]) -> Dict[str, Any]:
            result = base_dict.copy()

            for key, value in override_dict.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value

            return result

        self.config_data = deep_merge(self.config_data, override_config)

    def export_config_template(self, output_file: str) -> bool:
        """Export a configuration template with comments."""
        template_config = {
            "# Hydra Verification System Configuration": None,
            "# Generated at": datetime.now().isoformat(),
            "version": "1.0",

            "# Quality check thresholds (0.0 to 1.0)": None,
            "quality_thresholds": {
                "# Syntax must be 100% correct": None,
                "syntax_score": 1.0,
                "# Style compliance threshold": None,
                "style_score": 0.8,
                "# Code complexity threshold": None,
                "complexity_score": 0.7,
                "# Import resolution threshold": None,
                "import_resolution_score": 0.9
            },

            "# Test coverage requirements": None,
            "coverage_settings": {
                "# Minimum overall coverage": None,
                "min_coverage": 0.8,
                "# Minimum function coverage": None,
                "min_function_coverage": 0.7,
                "# Minimum class coverage": None,
                "min_class_coverage": 0.6,
                "# Require test files to exist": None,
                "require_test_files": True
            },

            "# File verification settings": None,
            "file_verification": {
                "# Allowed file extensions": None,
                "required_extensions": ['.py', '.yaml', '.yml', '.json', '.md'],
                "# Patterns to exclude from verification": None,
                "excluded_patterns": ['__pycache__', '*.pyc', '.git', '.venv'],
                "# Check file sizes": None,
                "check_file_sizes": True,
                "# Maximum file size in MB": None,
                "max_file_size_mb": 10.0
            },

            "# Report generation settings": None,
            "report_settings": {
                "# Output directory for reports": None,
                "output_dir": ".hydra/reports",
                "# Generate HTML reports": None,
                "generate_html": True,
                "# Generate JSON reports": None,
                "generate_json": True,
                "# Include detailed logs in reports": None,
                "include_detailed_logs": False,
                "# Maximum log lines to include": None,
                "max_log_lines": 1000
            },

            "# Acceptance criteria validation": None,
            "criteria_validation": {
                "# Require verification methods for all criteria": None,
                "require_verification_methods": True,
                "# Auto-detect file requirements from criteria text": None,
                "auto_detect_file_requirements": True,
                "# Use strict validation (fail on warnings)": None,
                "strict_validation": False,
                "# Completion threshold (1.0 = 100%)": None,
                "completion_threshold": 1.0
            },

            "# General settings": None,
            "general": {
                "# Verbose output": None,
                "verbose_output": False,
                "# Stop on first failure": None,
                "fail_fast": False,
                "# Enable parallel checks": None,
                "parallel_checks": True,
                "# Maximum worker threads": None,
                "max_workers": 4,
                "# Timeout for operations (seconds)": None,
                "timeout_seconds": 300
            }
        }

        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                yaml.dump(template_config, f, default_flow_style=False, indent=2)

            return True

        except Exception as e:
            print(f"Error exporting config template to {output_file}: {e}")
            return False
