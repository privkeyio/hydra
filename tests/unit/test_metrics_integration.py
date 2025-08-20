"""Unit tests for metrics integration module"""

import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from hydra.verification_system.metrics_integration import (
    MetricsVerifier,
    MetricsVerificationResult,
    MetricsIntegration,
    verify_with_metrics,
)
from hydra.metrics.config import MetricsConfig, ComplexityThresholds, CoverageThresholds, QualityGates
from hydra.metrics.quality_metrics import QualityReport, ComplexityMetrics, CoverageMetrics, SecurityMetrics


class TestMetricsVerificationResult(TestCase):
    """Test metrics verification result structure"""

    def test_result_creation(self):
        """Test creating verification result"""
        result = MetricsVerificationResult(
            passed=True,
            score=85.5,
            failures=[],
            warnings=["Low documentation"],
            metrics={'overall_score': 85.5},
            recommendations=["Add more tests"]
        )
        
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 85.5)
        self.assertEqual(len(result.failures), 0)
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(len(result.recommendations), 1)


class TestMetricsVerifier(TestCase):
    """Test metrics verifier functionality"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_default_initialization(self):
        """Test default verifier initialization"""
        verifier = MetricsVerifier()
        
        self.assertFalse(verifier.strict_mode)
        self.assertIsNotNone(verifier.config)
        self.assertIsNotNone(verifier.thresholds)
        self.assertEqual(verifier.thresholds['min_overall_score'], 70.0)

    def test_strict_mode_initialization(self):
        """Test strict mode initialization"""
        verifier = MetricsVerifier(strict_mode=True)
        
        self.assertTrue(verifier.strict_mode)
        self.assertEqual(verifier.thresholds['min_overall_score'], 85.0)
        self.assertEqual(verifier.thresholds['min_coverage'], 85.0)
        self.assertEqual(verifier.thresholds['max_complexity'], 10)

    def test_custom_config_initialization(self):
        """Test initialization with custom config"""
        custom_config = MetricsConfig(
            complexity=ComplexityThresholds(max_cyclomatic_complexity=8),
            coverage=CoverageThresholds(min_line_coverage=90.0),
            quality_gates=QualityGates(min_overall_score=95.0)
        )
        
        verifier = MetricsVerifier(config=custom_config)
        
        self.assertEqual(verifier.thresholds['max_complexity'], 8)
        self.assertEqual(verifier.thresholds['min_coverage'], 90.0)
        self.assertEqual(verifier.thresholds['min_overall_score'], 95.0)

    @patch('hydra.verification_system.metrics_integration.get_quality_metrics_for_verification')
    def test_verify_project_passing(self, mock_get_metrics):
        """Test project verification that passes"""
        mock_get_metrics.return_value = (True, {
            'overall_score': 80.0,
            'production_ready': True,
            'complexity': {'cyclomatic': 8, 'lines_of_code': 500},
            'coverage': {'line_coverage': 75.0},
            'documentation': {'docstring_coverage': 70.0},
            'error_handling': {'try_except_coverage': 60.0},
            'security': {
                'secrets_in_code': False,
                'sql_injection_safe': True,
                'input_validation': True
            },
            'recommendations': []
        })
        
        verifier = MetricsVerifier()
        result = verifier.verify_project(str(self.temp_dir))
        
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 80.0)
        self.assertEqual(len(result.failures), 0)

    @patch('hydra.verification_system.metrics_integration.get_quality_metrics_for_verification')
    def test_verify_project_failing(self, mock_get_metrics):
        """Test project verification that fails"""
        mock_get_metrics.return_value = (False, {
            'overall_score': 45.0,
            'production_ready': False,
            'complexity': {'cyclomatic': 25, 'lines_of_code': 1000},
            'coverage': {'line_coverage': 30.0},
            'documentation': {'docstring_coverage': 20.0},
            'error_handling': {'try_except_coverage': 10.0},
            'security': {
                'secrets_in_code': True,
                'sql_injection_safe': False,
                'input_validation': False
            },
            'recommendations': ['Reduce complexity', 'Add tests']
        })
        
        verifier = MetricsVerifier()
        result = verifier.verify_project(str(self.temp_dir))
        
        self.assertFalse(result.passed)
        self.assertEqual(result.score, 45.0)
        self.assertGreater(len(result.failures), 0)
        
        # Check specific failures
        failure_text = ' '.join(result.failures)
        self.assertIn('Overall quality score too low', failure_text)
        self.assertIn('Test coverage insufficient', failure_text)
        self.assertIn('Code too complex', failure_text)
        self.assertIn('CRITICAL: Hardcoded secrets', failure_text)
        self.assertIn('CRITICAL: SQL injection', failure_text)

    @patch('hydra.verification_system.metrics_integration.get_quality_metrics_for_verification')
    def test_verify_project_warnings(self, mock_get_metrics):
        """Test project verification with warnings"""
        mock_get_metrics.return_value = (True, {
            'overall_score': 75.0,
            'production_ready': True,
            'complexity': {'cyclomatic': 8, 'lines_of_code': 500},
            'coverage': {'line_coverage': 70.0},
            'documentation': {'docstring_coverage': 30.0},  # Low documentation
            'error_handling': {'try_except_coverage': 40.0},  # Low error handling
            'security': {
                'secrets_in_code': False,
                'sql_injection_safe': True,
                'input_validation': False  # Warning for missing validation
            },
            'recommendations': []
        })
        
        verifier = MetricsVerifier()
        result = verifier.verify_project(str(self.temp_dir))
        
        self.assertTrue(result.passed)
        self.assertGreater(len(result.warnings), 0)
        
        warning_text = ' '.join(result.warnings)
        self.assertIn('Documentation incomplete', warning_text)
        self.assertIn('Error handling insufficient', warning_text)
        self.assertIn('Input validation missing', warning_text)

    @patch('hydra.verification_system.metrics_integration.get_quality_metrics_for_verification')
    def test_verify_ticket_completion(self, mock_get_metrics):
        """Test ticket completion verification"""
        mock_get_metrics.return_value = (True, {
            'overall_score': 80.0,
            'production_ready': True,
            'complexity': {'cyclomatic': 5},
            'coverage': {'line_coverage': 75.0},
            'documentation': {'docstring_coverage': 70.0},
            'error_handling': {'try_except_coverage': 60.0},
            'security': {'secrets_in_code': False, 'sql_injection_safe': True, 'input_validation': True},
            'recommendations': []
        })
        
        verifier = MetricsVerifier()
        result = verifier.verify_ticket_completion(
            "tickets.yaml", 
            "001", 
            str(self.temp_dir)
        )
        
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 80.0)

    @patch('hydra.verification_system.metrics_integration.get_quality_metrics_for_verification')
    def test_verify_ticket_completion_failed(self, mock_get_metrics):
        """Test failed ticket completion verification"""
        mock_get_metrics.return_value = (False, {
            'overall_score': 40.0,
            'production_ready': False,
            'complexity': {'cyclomatic': 20},
            'coverage': {'line_coverage': 30.0},
            'documentation': {'docstring_coverage': 20.0},
            'error_handling': {'try_except_coverage': 10.0},
            'security': {'secrets_in_code': True, 'sql_injection_safe': False, 'input_validation': False},
            'recommendations': []
        })
        
        verifier = MetricsVerifier()
        result = verifier.verify_ticket_completion(
            "tickets.yaml", 
            "001", 
            str(self.temp_dir)
        )
        
        self.assertFalse(result.passed)
        self.assertIn("Ticket 001 verification failed", result.failures[0])


class TestMetricsIntegration(TestCase):
    """Test metrics integration utility functions"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    @patch('hydra.verification_system.metrics_integration.get_quality_metrics_for_verification')
    def test_get_metrics_for_verification(self, mock_get_metrics):
        """Test getting metrics for verification system"""
        mock_get_metrics.return_value = (True, {
            'overall_score': 85.0,
            'production_ready': True,
            'complexity': {'cyclomatic': 8, 'lines_of_code': 500},
            'coverage': {'line_coverage': 80.0},
            'documentation': {'docstring_coverage': 75.0},
            'security': {'secrets_in_code': False, 'sql_injection_safe': True, 'input_validation': True}
        })
        
        result = MetricsIntegration.get_metrics_for_verification(str(self.temp_dir))
        
        self.assertTrue(result['passed'])
        self.assertEqual(result['score'], 85.0)
        self.assertTrue(result['production_ready'])
        self.assertIn('summary', result)
        self.assertIn('complexity', result['summary'])
        self.assertIn('coverage', result['summary'])
        self.assertIn('documentation', result['summary'])
        self.assertIn('security', result['summary'])

    @patch('hydra.verification_system.metrics_integration.get_quality_metrics_for_verification')
    def test_get_metrics_for_verification_strict(self, mock_get_metrics):
        """Test getting metrics with strict mode"""
        mock_get_metrics.return_value = (False, {
            'overall_score': 75.0,  # Would pass normal but fail strict
            'production_ready': True,
            'complexity': {'cyclomatic': 12, 'lines_of_code': 800},
            'coverage': {'line_coverage': 70.0},  # Would fail strict
            'documentation': {'docstring_coverage': 60.0},
            'security': {'secrets_in_code': False, 'sql_injection_safe': True, 'input_validation': True}
        })
        
        result = MetricsIntegration.get_metrics_for_verification(
            str(self.temp_dir), 
            strict_mode=True
        )
        
        self.assertFalse(result['passed'])
        self.assertEqual(result['score'], 75.0)

    @patch('hydra.verification_system.metrics_integration.analyze_code_quality')
    def test_check_acceptance_criteria(self, mock_analyze):
        """Test checking acceptance criteria"""
        mock_analyze.return_value = {
            'coverage': {'line_coverage': 80.0},
            'documentation': {'docstring_coverage': 70.0},
            'error_handling': {'try_except_coverage': 60.0},
            'performance': {
                'caching': True,
                'async_operations': False,
                'connection_pooling': False
            },
            'security': {
                'secrets_in_code': False,
                'input_validation': True
            }
        }
        
        criteria = [
            "Must have test coverage above 75%",
            "Should include documentation for all functions",
            "Implement proper error handling",
            "Add performance optimizations",
            "Include security measures"
        ]
        
        all_met, unmet = MetricsIntegration.check_acceptance_criteria(
            str(self.temp_dir), 
            criteria
        )
        
        self.assertTrue(all_met)
        self.assertEqual(len(unmet), 0)

    @patch('hydra.verification_system.metrics_integration.analyze_code_quality')
    def test_check_acceptance_criteria_unmet(self, mock_analyze):
        """Test checking acceptance criteria with unmet requirements"""
        mock_analyze.return_value = {
            'coverage': {'line_coverage': 40.0},  # Too low
            'documentation': {'docstring_coverage': 30.0},  # Too low
            'error_handling': {'try_except_coverage': 20.0},  # Too low
            'performance': {
                'caching': False,
                'async_operations': False,
                'connection_pooling': False
            },
            'security': {
                'secrets_in_code': True,  # Critical issue
                'input_validation': False
            }
        }
        
        criteria = [
            "Must have test coverage above 60%",
            "Should include documentation",
            "Implement error handling",
            "Add performance optimizations",
            "Ensure security measures"
        ]
        
        all_met, unmet = MetricsIntegration.check_acceptance_criteria(
            str(self.temp_dir), 
            criteria
        )
        
        self.assertFalse(all_met)
        self.assertGreater(len(unmet), 0)
        
        unmet_text = ' '.join(unmet)
        self.assertIn("coverage", unmet_text.lower())
        self.assertIn("documentation", unmet_text.lower())
        self.assertIn("error handling", unmet_text.lower())
        self.assertIn("performance", unmet_text.lower())
        self.assertIn("secrets", unmet_text.lower())

    @patch('hydra.verification_system.metrics_integration.analyze_code_quality')
    def test_generate_quality_report(self, mock_analyze):
        """Test generating quality report"""
        mock_analyze.return_value = {
            'production_ready': True,
            'overall_score': 82.5,
            'complexity': {
                'cyclomatic': 8,
                'cognitive': 12,
                'lines_of_code': 1200
            },
            'coverage': {
                'line_coverage': 85.0,
                'test_files': 15,
                'test_to_code_ratio': 1.2
            },
            'documentation': {
                'docstring_coverage': 75.0,
                'readme_exists': True,
                'api_docs_exists': False
            },
            'error_handling': {
                'try_except_coverage': 70.0,
                'error_logging': True,
                'retry_logic': False
            },
            'performance': {
                'caching': True,
                'async_operations': True,
                'connection_pooling': False
            },
            'security': {
                'sql_injection_safe': True,
                'xss_protection': True,
                'secrets_in_code': False,
                'input_validation': True
            },
            'recommendations': [
                "Add API documentation",
                "Implement connection pooling",
                "Add retry logic for network calls"
            ]
        }
        
        report = MetricsIntegration.generate_quality_report(str(self.temp_dir))
        
        self.assertIsInstance(report, str)
        self.assertIn("PRODUCTION QUALITY METRICS REPORT", report)
        self.assertIn("✅ PRODUCTION READY", report)
        self.assertIn("82.5/100", report)
        self.assertIn("Code Complexity:", report)
        self.assertIn("Test Coverage:", report)
        self.assertIn("Documentation:", report)
        self.assertIn("Error Handling:", report)
        self.assertIn("Performance Optimizations:", report)
        self.assertIn("Security:", report)
        self.assertIn("Recommendations for Improvement:", report)
        self.assertIn("Add API documentation", report)

    @patch('hydra.verification_system.metrics_integration.analyze_code_quality')
    def test_generate_quality_report_not_ready(self, mock_analyze):
        """Test generating quality report for non-production ready code"""
        mock_analyze.return_value = {
            'production_ready': False,
            'overall_score': 45.0,
            'complexity': {'cyclomatic': 25, 'lines_of_code': 2000},
            'coverage': {'line_coverage': 30.0, 'test_files': 2, 'test_to_code_ratio': 0.1},
            'documentation': {'docstring_coverage': 20.0, 'readme_exists': False, 'api_docs_exists': False},
            'error_handling': {'try_except_coverage': 15.0, 'error_logging': False, 'retry_logic': False},
            'performance': {'caching': False, 'async_operations': False, 'connection_pooling': False},
            'security': {'sql_injection_safe': False, 'xss_protection': False, 'secrets_in_code': True, 'input_validation': False},
            'recommendations': ['CRITICAL: Remove hardcoded secrets', 'Increase test coverage', 'Reduce complexity']
        }
        
        report = MetricsIntegration.generate_quality_report(str(self.temp_dir))
        
        self.assertIn("❌ NOT PRODUCTION READY", report)
        self.assertIn("45.0/100", report)
        self.assertIn("FOUND! ⚠️", report)  # Secrets warning
        self.assertIn("CRITICAL: Remove hardcoded secrets", report)


class TestVerifyWithMetrics(TestCase):
    """Test convenience function for metrics verification"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    @patch('hydra.verification_system.metrics_integration.MetricsVerifier')
    @patch('hydra.verification_system.metrics_integration.MetricsIntegration.generate_quality_report')
    def test_verify_with_metrics_verbose_pass(self, mock_report, mock_verifier):
        """Test verbose verification that passes"""
        mock_result = Mock()
        mock_result.passed = True
        mock_result.score = 85.0
        
        mock_verifier_instance = Mock()
        mock_verifier_instance.verify_project.return_value = mock_result
        mock_verifier.return_value = mock_verifier_instance
        
        mock_report.return_value = "Detailed quality report content"
        
        passed, report = verify_with_metrics(
            str(self.temp_dir),
            strict=True,
            verbose=True
        )
        
        self.assertTrue(passed)
        self.assertEqual(report, "Detailed quality report content")
        mock_verifier.assert_called_once_with(strict_mode=True)

    @patch('hydra.verification_system.metrics_integration.MetricsVerifier')
    def test_verify_with_metrics_non_verbose_pass(self, mock_verifier):
        """Test non-verbose verification that passes"""
        mock_result = Mock()
        mock_result.passed = True
        mock_result.score = 75.5
        
        mock_verifier_instance = Mock()
        mock_verifier_instance.verify_project.return_value = mock_result
        mock_verifier.return_value = mock_verifier_instance
        
        passed, report = verify_with_metrics(str(self.temp_dir), verbose=False)
        
        self.assertTrue(passed)
        self.assertEqual(report, "Quality score: 75.5/100")

    @patch('hydra.verification_system.metrics_integration.MetricsVerifier')
    def test_verify_with_metrics_fail(self, mock_verifier):
        """Test verification that fails"""
        mock_result = Mock()
        mock_result.passed = False
        mock_result.score = 40.0
        mock_result.failures = [
            "Test coverage too low: 30%",
            "CRITICAL: Hardcoded secrets found"
        ]
        
        mock_verifier_instance = Mock()
        mock_verifier_instance.verify_project.return_value = mock_result
        mock_verifier.return_value = mock_verifier_instance
        
        passed, report = verify_with_metrics(str(self.temp_dir))
        
        self.assertFalse(passed)
        self.assertIn("Verification failed:", report)
        self.assertIn("Test coverage too low", report)
        self.assertIn("CRITICAL: Hardcoded secrets", report)


class TestEdgeCases(TestCase):
    """Test edge cases and error handling"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_empty_project_verification(self):
        """Test verification of empty project"""
        # Create empty project directory
        verifier = MetricsVerifier()
        result = verifier.verify_project(str(self.temp_dir))
        
        # Should handle gracefully
        self.assertIsInstance(result, MetricsVerificationResult)
        self.assertFalse(result.passed)  # Empty project shouldn't pass

    def test_non_existent_project(self):
        """Test verification of non-existent project"""
        verifier = MetricsVerifier()
        result = verifier.verify_project("/non/existent/path")
        
        # Should handle gracefully
        self.assertIsInstance(result, MetricsVerificationResult)
        self.assertFalse(result.passed)

    def test_invalid_criteria_patterns(self):
        """Test handling of invalid acceptance criteria patterns"""
        all_met, unmet = MetricsIntegration.check_acceptance_criteria(
            str(self.temp_dir),
            ["Some random criteria that doesn't match patterns"]
        )
        
        # Should handle gracefully (criteria doesn't match known patterns)
        self.assertTrue(all_met)  # No matching patterns means no failures
        self.assertEqual(len(unmet), 0)

    @patch('hydra.verification_system.metrics_integration.analyze_code_quality')
    def test_metrics_analysis_exception(self, mock_analyze):
        """Test handling of exceptions during metrics analysis"""
        mock_analyze.side_effect = Exception("Analysis failed")
        
        # Should handle gracefully without crashing
        try:
            result = MetricsIntegration.generate_quality_report(str(self.temp_dir))
            # If it doesn't crash, that's good
        except Exception:
            self.fail("Should handle analysis exceptions gracefully")