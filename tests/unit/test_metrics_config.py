"""Unit tests for metrics configuration module"""

import os
import tempfile
import yaml
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from hydra.metrics.config import (
    MetricsConfig,
    MetricsConfigManager,
    ComplexityThresholds,
    CoverageThresholds,
    DocumentationThresholds,
    ErrorHandlingThresholds,
    PerformanceThresholds,
    SecurityThresholds,
    QualityGates,
    get_config_manager,
    get_metrics_config,
    create_preset_config,
    PRESET_CONFIGS,
)


class TestComplexityThresholds(TestCase):
    """Test complexity thresholds configuration"""

    def test_default_values(self):
        """Test default threshold values"""
        thresholds = ComplexityThresholds()
        
        self.assertEqual(thresholds.max_cyclomatic_complexity, 15)
        self.assertEqual(thresholds.max_cognitive_complexity, 20)
        self.assertEqual(thresholds.max_nesting_depth, 4)
        self.assertEqual(thresholds.max_function_length, 50)
        self.assertEqual(thresholds.max_duplicate_ratio, 0.1)
        self.assertEqual(thresholds.max_lines_per_file, 500)

    def test_custom_values(self):
        """Test custom threshold values"""
        thresholds = ComplexityThresholds(
            max_cyclomatic_complexity=10,
            max_cognitive_complexity=15,
            max_nesting_depth=3
        )
        
        self.assertEqual(thresholds.max_cyclomatic_complexity, 10)
        self.assertEqual(thresholds.max_cognitive_complexity, 15)
        self.assertEqual(thresholds.max_nesting_depth, 3)
        # Defaults should remain
        self.assertEqual(thresholds.max_function_length, 50)


class TestCoverageThresholds(TestCase):
    """Test coverage thresholds configuration"""

    def test_default_values(self):
        """Test default coverage values"""
        thresholds = CoverageThresholds()
        
        self.assertEqual(thresholds.min_line_coverage, 70.0)
        self.assertEqual(thresholds.min_branch_coverage, 60.0)
        self.assertEqual(thresholds.min_function_coverage, 80.0)
        self.assertEqual(thresholds.min_test_to_code_ratio, 0.5)
        self.assertTrue(thresholds.require_test_files)

    def test_custom_values(self):
        """Test custom coverage values"""
        thresholds = CoverageThresholds(
            min_line_coverage=85.0,
            require_test_files=False
        )
        
        self.assertEqual(thresholds.min_line_coverage, 85.0)
        self.assertFalse(thresholds.require_test_files)


class TestSecurityThresholds(TestCase):
    """Test security thresholds configuration"""

    def test_default_values(self):
        """Test default security values"""
        thresholds = SecurityThresholds()
        
        self.assertFalse(thresholds.allow_secrets_in_code)
        self.assertTrue(thresholds.require_sql_injection_safe)
        self.assertTrue(thresholds.require_xss_protection)
        self.assertTrue(thresholds.require_input_validation)
        self.assertFalse(thresholds.require_authentication)
        self.assertFalse(thresholds.require_authorization)
        self.assertFalse(thresholds.require_audit_logging)

    def test_security_configuration(self):
        """Test security-focused configuration"""
        thresholds = SecurityThresholds(
            require_authentication=True,
            require_authorization=True,
            require_audit_logging=True
        )
        
        self.assertTrue(thresholds.require_authentication)
        self.assertTrue(thresholds.require_authorization)
        self.assertTrue(thresholds.require_audit_logging)


class TestMetricsConfig(TestCase):
    """Test complete metrics configuration"""

    def test_default_config(self):
        """Test default configuration creation"""
        config = MetricsConfig()
        
        self.assertIsInstance(config.complexity, ComplexityThresholds)
        self.assertIsInstance(config.coverage, CoverageThresholds)
        self.assertIsInstance(config.documentation, DocumentationThresholds)
        self.assertIsInstance(config.error_handling, ErrorHandlingThresholds)
        self.assertIsInstance(config.performance, PerformanceThresholds)
        self.assertIsInstance(config.security, SecurityThresholds)
        self.assertIsInstance(config.quality_gates, QualityGates)
        
        self.assertFalse(config.strict_mode)
        self.assertTrue(config.enable_ai_detection)
        self.assertTrue(config.enable_performance_benchmarks)
        self.assertTrue(config.include_test_files)
        self.assertEqual(config.timeout_seconds, 300)

    def test_custom_config(self):
        """Test custom configuration"""
        config = MetricsConfig(
            complexity=ComplexityThresholds(max_cyclomatic_complexity=10),
            strict_mode=True,
            timeout_seconds=600
        )
        
        self.assertEqual(config.complexity.max_cyclomatic_complexity, 10)
        self.assertTrue(config.strict_mode)
        self.assertEqual(config.timeout_seconds, 600)


class TestMetricsConfigManager(TestCase):
    """Test metrics configuration manager"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "test_config.yaml"

    def test_default_config(self):
        """Test loading default configuration"""
        manager = MetricsConfigManager()
        config = manager.get_config()
        
        self.assertIsInstance(config, MetricsConfig)
        self.assertFalse(config.strict_mode)

    def test_config_from_file(self):
        """Test loading configuration from file"""
        config_data = {
            'strict_mode': True,
            'timeout_seconds': 600,
            'complexity': {
                'max_cyclomatic_complexity': 10
            },
            'coverage': {
                'min_line_coverage': 85.0
            }
        }
        
        with open(self.config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        manager = MetricsConfigManager(str(self.config_path))
        config = manager.get_config()
        
        self.assertTrue(config.strict_mode)
        self.assertEqual(config.timeout_seconds, 600)
        self.assertEqual(config.complexity.max_cyclomatic_complexity, 10)
        self.assertEqual(config.coverage.min_line_coverage, 85.0)

    def test_environment_config(self):
        """Test environment-specific configuration"""
        manager = MetricsConfigManager()
        
        # Test strict environment
        strict_config = manager.get_config('strict')
        self.assertTrue(strict_config.strict_mode)
        self.assertEqual(strict_config.quality_gates.min_overall_score, 85.0)
        self.assertEqual(strict_config.coverage.min_line_coverage, 85.0)
        
        # Test development environment
        dev_config = manager.get_config('dev')
        self.assertEqual(dev_config.quality_gates.min_overall_score, 50.0)
        self.assertEqual(dev_config.coverage.min_line_coverage, 40.0)
        self.assertFalse(dev_config.enable_performance_benchmarks)
        
        # Test production environment
        prod_config = manager.get_config('prod')
        self.assertEqual(prod_config.quality_gates.min_overall_score, 80.0)
        self.assertTrue(prod_config.security.require_authentication)
        self.assertTrue(prod_config.performance.require_caching)

    @patch.dict(os.environ, {
        'HYDRA_MIN_OVERALL_SCORE': '90',
        'HYDRA_MIN_COVERAGE': '80',
        'HYDRA_MAX_COMPLEXITY': '8',
        'HYDRA_STRICT_MODE': 'true',
        'HYDRA_ALLOW_SECRETS': 'false'
    })
    def test_environment_variable_overrides(self):
        """Test environment variable overrides"""
        manager = MetricsConfigManager()
        config = manager.get_config()
        
        self.assertEqual(config.quality_gates.min_overall_score, 90.0)
        self.assertEqual(config.coverage.min_line_coverage, 80.0)
        self.assertEqual(config.complexity.max_cyclomatic_complexity, 8)
        self.assertTrue(config.strict_mode)
        self.assertFalse(config.security.allow_secrets_in_code)

    def test_save_config(self):
        """Test saving configuration to file"""
        manager = MetricsConfigManager()
        config = MetricsConfig(strict_mode=True, timeout_seconds=900)
        
        save_path = Path(self.temp_dir) / "saved_config.yaml"
        manager.save_config(config, str(save_path))
        
        self.assertTrue(save_path.exists())
        
        # Load and verify
        with open(save_path, 'r') as f:
            data = yaml.safe_load(f)
        
        self.assertTrue(data['strict_mode'])
        self.assertEqual(data['timeout_seconds'], 900)

    def test_validate_config(self):
        """Test configuration validation"""
        manager = MetricsConfigManager()
        
        # Valid config
        valid_config = MetricsConfig()
        issues = manager.validate_config(valid_config)
        self.assertEqual(len(issues), 0)
        
        # Invalid config
        invalid_config = MetricsConfig()
        invalid_config.quality_gates.min_overall_score = 150  # Invalid: > 100
        invalid_config.coverage.min_line_coverage = -10  # Invalid: < 0
        invalid_config.complexity.max_cyclomatic_complexity = 0  # Invalid: must be positive
        
        issues = manager.validate_config(invalid_config)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("min_overall_score" in issue for issue in issues))
        self.assertTrue(any("min_line_coverage" in issue for issue in issues))
        self.assertTrue(any("max_cyclomatic_complexity" in issue for issue in issues))

    def test_nested_attribute_setting(self):
        """Test setting nested attributes via dot notation"""
        manager = MetricsConfigManager()
        config = MetricsConfig()
        
        manager._set_nested_attribute(config, 'complexity.max_cyclomatic_complexity', 12)
        manager._set_nested_attribute(config, 'quality_gates.min_overall_score', 75.0)
        
        self.assertEqual(config.complexity.max_cyclomatic_complexity, 12)
        self.assertEqual(config.quality_gates.min_overall_score, 75.0)

    def test_invalid_config_file(self):
        """Test handling of invalid configuration file"""
        # Create invalid YAML file
        with open(self.config_path, 'w') as f:
            f.write("invalid: yaml: content: [")
        
        manager = MetricsConfigManager(str(self.config_path))
        config = manager.get_config()
        
        # Should fall back to default config
        self.assertIsInstance(config, MetricsConfig)
        self.assertFalse(config.strict_mode)  # Default value


class TestGlobalFunctions(TestCase):
    """Test global configuration functions"""

    def test_get_config_manager(self):
        """Test global config manager retrieval"""
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        
        # Should return same instance
        self.assertIs(manager1, manager2)

    def test_get_metrics_config(self):
        """Test global config retrieval"""
        config = get_metrics_config()
        self.assertIsInstance(config, MetricsConfig)
        
        strict_config = get_metrics_config('strict')
        self.assertTrue(strict_config.strict_mode)

    def test_create_preset_config(self):
        """Test preset configuration creation"""
        # Test strict preset
        strict_config = create_preset_config('strict')
        self.assertEqual(strict_config.quality_gates.min_overall_score, 85.0)
        self.assertTrue(strict_config.strict_mode)
        
        # Test production preset
        prod_config = create_preset_config('production')
        self.assertEqual(prod_config.quality_gates.min_overall_score, 80.0)
        self.assertTrue(prod_config.security.require_authentication)
        
        # Test development preset
        dev_config = create_preset_config('development')
        self.assertEqual(dev_config.quality_gates.min_overall_score, 50.0)
        self.assertFalse(dev_config.enable_performance_benchmarks)

    def test_invalid_preset(self):
        """Test invalid preset handling"""
        with self.assertRaises(ValueError) as cm:
            create_preset_config('invalid_preset')
        
        self.assertIn("Unknown preset", str(cm.exception))

    def test_preset_configs_exist(self):
        """Test that all preset configurations are defined"""
        self.assertIn('strict', PRESET_CONFIGS)
        self.assertIn('production', PRESET_CONFIGS)
        self.assertIn('development', PRESET_CONFIGS)
        
        for preset_name, preset_data in PRESET_CONFIGS.items():
            self.assertIsInstance(preset_data, dict)


class TestConfigurationIntegration(TestCase):
    """Test configuration integration scenarios"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_full_workflow(self):
        """Test complete configuration workflow"""
        # Create custom config file
        config_data = {
            'strict_mode': False,
            'complexity': {'max_cyclomatic_complexity': 12},
            'coverage': {'min_line_coverage': 75.0},
            'security': {'require_authentication': True}
        }
        
        config_path = Path(self.temp_dir) / "workflow_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Load config
        manager = MetricsConfigManager(str(config_path))
        config = manager.get_config()
        
        # Verify loaded correctly
        self.assertFalse(config.strict_mode)
        self.assertEqual(config.complexity.max_cyclomatic_complexity, 12)
        self.assertEqual(config.coverage.min_line_coverage, 75.0)
        self.assertTrue(config.security.require_authentication)
        
        # Apply environment overlay
        strict_config = manager.get_config('strict')
        self.assertTrue(strict_config.strict_mode)
        self.assertEqual(strict_config.quality_gates.min_overall_score, 85.0)
        
        # Validate configuration
        issues = manager.validate_config(config)
        self.assertEqual(len(issues), 0)
        
        # Save modified config
        config.timeout_seconds = 450
        save_path = Path(self.temp_dir) / "modified_config.yaml"
        manager.save_config(config, str(save_path))
        
        # Verify saved correctly
        self.assertTrue(save_path.exists())
        with open(save_path, 'r') as f:
            saved_data = yaml.safe_load(f)
        self.assertEqual(saved_data['timeout_seconds'], 450)

    @patch.dict(os.environ, {
        'HYDRA_MIN_OVERALL_SCORE': '95',
        'HYDRA_STRICT_MODE': 'true'
    })
    def test_environment_override_priority(self):
        """Test that environment variables take precedence"""
        # Create config file with different values
        config_data = {
            'quality_gates': {'min_overall_score': 60.0},
            'strict_mode': False
        }
        
        config_path = Path(self.temp_dir) / "override_test.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        manager = MetricsConfigManager(str(config_path))
        config = manager.get_config()
        
        # Environment variables should override file values
        self.assertEqual(config.quality_gates.min_overall_score, 95.0)
        self.assertTrue(config.strict_mode)

    def test_partial_configuration(self):
        """Test loading partial configuration files"""
        # Config file with only some sections
        config_data = {
            'complexity': {
                'max_cyclomatic_complexity': 8
            },
            'timeout_seconds': 240
        }
        
        config_path = Path(self.temp_dir) / "partial_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        manager = MetricsConfigManager(str(config_path))
        config = manager.get_config()
        
        # Specified values should be loaded
        self.assertEqual(config.complexity.max_cyclomatic_complexity, 8)
        self.assertEqual(config.timeout_seconds, 240)
        
        # Missing values should use defaults
        self.assertEqual(config.coverage.min_line_coverage, 70.0)  # Default
        self.assertFalse(config.strict_mode)  # Default