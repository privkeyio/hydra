"""Integration module for quality metrics with verification system

This module provides the glue between the quality metrics analyzer and the
verification engine, allowing the verification system to use production quality
metrics as part of its decision-making process.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from hydra.metrics.config import MetricsConfig, get_metrics_config
from hydra.metrics.quality_metrics import (
    QualityMetricsAnalyzer,
    analyze_code_quality,
    get_quality_metrics_for_verification,
)

logger = logging.getLogger(__name__)


@dataclass
class MetricsVerificationResult:
    """Result of metrics-based verification"""

    passed: bool
    score: float
    failures: List[str]
    warnings: List[str]
    metrics: Dict[str, Any]
    recommendations: List[str]


class MetricsVerifier:
    """Verifier that uses quality metrics for verification decisions"""

    def __init__(self, strict_mode: bool = False, config: Optional[MetricsConfig] = None):
        """Initialize metrics verifier
        
        Args:
            strict_mode: If True, apply stricter thresholds
            config: Custom metrics configuration

        """
        self.strict_mode = strict_mode
        self.analyzer = QualityMetricsAnalyzer()

        # Load configuration
        if config:
            self.config = config
        else:
            environment = 'strict' if strict_mode else None
            self.config = get_metrics_config(environment)

        # Define thresholds from config
        self.thresholds = {
            'min_overall_score': self.config.quality_gates.min_overall_score,
            'min_coverage': self.config.coverage.min_line_coverage,
            'max_complexity': self.config.complexity.max_cyclomatic_complexity,
            'min_documentation': self.config.documentation.min_docstring_coverage,
            'min_error_handling': self.config.error_handling.min_try_except_coverage,
            'required_security': True
        }

    def verify_project(self, project_path: str) -> MetricsVerificationResult:
        """Verify project using quality metrics
        
        Args:
            project_path: Path to project to verify
            
        Returns:
            MetricsVerificationResult with verification outcome

        """
        failures = []
        warnings = []

        # Get quality metrics
        passed, metrics = get_quality_metrics_for_verification(
            project_path,
            self.strict_mode
        )

        # Check individual criteria
        if metrics['overall_score'] < self.thresholds['min_overall_score']:
            failures.append(
                f"Overall quality score too low: {metrics['overall_score']:.1f} "
                f"(minimum: {self.thresholds['min_overall_score']})"
            )

        if metrics['coverage']['line_coverage'] < self.thresholds['min_coverage']:
            failures.append(
                f"Test coverage insufficient: {metrics['coverage']['line_coverage']:.1f}% "
                f"(minimum: {self.thresholds['min_coverage']}%)"
            )

        if metrics['complexity']['cyclomatic'] > self.thresholds['max_complexity']:
            failures.append(
                f"Code too complex: cyclomatic complexity {metrics['complexity']['cyclomatic']} "
                f"(maximum: {self.thresholds['max_complexity']})"
            )

        if metrics['documentation']['docstring_coverage'] < self.thresholds['min_documentation']:
            warnings.append(
                f"Documentation incomplete: {metrics['documentation']['docstring_coverage']:.1f}% "
                f"(recommended: {self.thresholds['min_documentation']}%)"
            )

        if metrics['error_handling']['try_except_coverage'] < self.thresholds['min_error_handling']:
            warnings.append(
                f"Error handling insufficient: {metrics['error_handling']['try_except_coverage']:.1f}% "
                f"(recommended: {self.thresholds['min_error_handling']}%)"
            )

        # Security is critical
        if self.thresholds['required_security']:
            if metrics['security']['secrets_in_code']:
                failures.append("CRITICAL: Hardcoded secrets detected in code")
            if not metrics['security']['sql_injection_safe']:
                failures.append("CRITICAL: SQL injection vulnerabilities detected")
            if not metrics['security']['input_validation']:
                warnings.append("Security: Input validation missing")

        # Final decision
        final_passed = len(failures) == 0 and passed

        return MetricsVerificationResult(
            passed=final_passed,
            score=metrics['overall_score'],
            failures=failures,
            warnings=warnings,
            metrics=metrics,
            recommendations=metrics.get('recommendations', [])
        )

    def verify_ticket_completion(self,
                                ticket_path: str,
                                ticket_id: str,
                                project_path: str) -> MetricsVerificationResult:
        """Verify ticket completion using quality metrics
        
        Args:
            ticket_path: Path to ticket file
            ticket_id: ID of ticket to verify
            project_path: Path to project with implementation
            
        Returns:
            MetricsVerificationResult with verification outcome

        """
        # For ticket-specific verification, we might want to be less strict
        # about overall project metrics and focus on the changes
        result = self.verify_project(project_path)

        # Add ticket-specific context
        if not result.passed:
            result.failures.insert(0, f"Ticket {ticket_id} verification failed")

        return result


class MetricsIntegration:
    """Integration point for metrics with verification system"""

    @staticmethod
    def get_metrics_for_verification(project_path: str,
                                    strict_mode: bool = False) -> Dict[str, Any]:
        """Get metrics formatted for verification system
        
        Args:
            project_path: Path to analyze
            strict_mode: Whether to use strict thresholds
            
        Returns:
            Dictionary with metrics suitable for verification

        """
        passed, metrics = get_quality_metrics_for_verification(project_path, strict_mode)

        return {
            'passed': passed,
            'metrics': metrics,
            'score': metrics['overall_score'],
            'production_ready': metrics['production_ready'],
            'summary': {
                'complexity': f"Cyclomatic: {metrics['complexity']['cyclomatic']}, "
                             f"LOC: {metrics['complexity']['lines_of_code']}",
                'coverage': f"{metrics['coverage']['line_coverage']:.1f}%",
                'documentation': f"{metrics['documentation']['docstring_coverage']:.1f}%",
                'security': "FAIL" if metrics['security']['secrets_in_code'] else "PASS"
            }
        }

    @staticmethod
    def check_acceptance_criteria(project_path: str,
                                 criteria: List[str]) -> Tuple[bool, List[str]]:
        """Check if quality metrics meet acceptance criteria
        
        Args:
            project_path: Path to project
            criteria: List of acceptance criteria strings
            
        Returns:
            Tuple of (all_met, unmet_criteria)

        """
        metrics = analyze_code_quality(project_path)
        unmet = []

        for criterion in criteria:
            criterion_lower = criterion.lower()

            # Check for quality-related criteria
            if 'test coverage' in criterion_lower:
                if metrics['coverage']['line_coverage'] < 60:
                    unmet.append(f"{criterion} - Coverage: {metrics['coverage']['line_coverage']:.1f}%")

            elif 'documentation' in criterion_lower:
                if metrics['documentation']['docstring_coverage'] < 50:
                    unmet.append(f"{criterion} - Docstrings: {metrics['documentation']['docstring_coverage']:.1f}%")

            elif 'error handling' in criterion_lower:
                if metrics['error_handling']['try_except_coverage'] < 40:
                    unmet.append(f"{criterion} - Error handling: {metrics['error_handling']['try_except_coverage']:.1f}%")

            elif 'performance' in criterion_lower:
                if not any([
                    metrics['performance']['caching'],
                    metrics['performance']['async_operations'],
                    metrics['performance']['connection_pooling']
                ]):
                    unmet.append(f"{criterion} - No performance optimizations found")

            elif 'security' in criterion_lower:
                if metrics['security']['secrets_in_code']:
                    unmet.append(f"{criterion} - Hardcoded secrets found")
                elif not metrics['security']['input_validation']:
                    unmet.append(f"{criterion} - Input validation missing")

        return len(unmet) == 0, unmet

    @staticmethod
    def generate_quality_report(project_path: str) -> str:
        """Generate human-readable quality report
        
        Args:
            project_path: Path to project
            
        Returns:
            Formatted report string

        """
        try:
            metrics = analyze_code_quality(project_path)
        except Exception as e:
            # Return a basic error report if analysis fails
            return f"Failed to generate quality report: {str(e)}"

        report = []
        report.append("=" * 60)
        report.append("PRODUCTION QUALITY METRICS REPORT")
        report.append("=" * 60)
        report.append("")

        # Overall status
        status = "✅ PRODUCTION READY" if metrics['production_ready'] else "❌ NOT PRODUCTION READY"
        report.append(f"Status: {status}")
        report.append(f"Overall Score: {metrics['overall_score']:.1f}/100")
        report.append("")

        # Complexity metrics
        report.append("Code Complexity:")
        report.append(f"  - Cyclomatic Complexity: {metrics['complexity']['cyclomatic']}")
        report.append(f"  - Cognitive Complexity: {metrics['complexity'].get('cognitive', 'N/A')}")
        report.append(f"  - Lines of Code: {metrics['complexity']['lines_of_code']}")
        report.append("")

        # Coverage metrics
        report.append("Test Coverage:")
        report.append(f"  - Line Coverage: {metrics['coverage']['line_coverage']:.1f}%")
        report.append(f"  - Test Files: {metrics['coverage']['test_files']}")
        report.append(f"  - Test-to-Code Ratio: {metrics['coverage']['test_to_code_ratio']:.2f}")
        report.append("")

        # Documentation metrics
        report.append("Documentation:")
        report.append(f"  - Docstring Coverage: {metrics['documentation']['docstring_coverage']:.1f}%")
        report.append(f"  - README Exists: {'Yes' if metrics['documentation']['readme_exists'] else 'No'}")
        report.append(f"  - API Docs: {'Yes' if metrics['documentation']['api_docs_exists'] else 'No'}")
        report.append("")

        # Error handling metrics
        report.append("Error Handling:")
        report.append(f"  - Try/Except Coverage: {metrics['error_handling']['try_except_coverage']:.1f}%")
        report.append(f"  - Error Logging: {'Yes' if metrics['error_handling']['error_logging'] else 'No'}")
        report.append(f"  - Retry Logic: {'Yes' if metrics['error_handling']['retry_logic'] else 'No'}")
        report.append("")

        # Performance metrics
        report.append("Performance Optimizations:")
        report.append(f"  - Caching: {'Yes' if metrics['performance']['caching'] else 'No'}")
        report.append(f"  - Async Operations: {'Yes' if metrics['performance']['async_operations'] else 'No'}")
        report.append(f"  - Connection Pooling: {'Yes' if metrics['performance']['connection_pooling'] else 'No'}")
        report.append("")

        # Security metrics
        report.append("Security:")
        report.append(f"  - SQL Injection Safe: {'Yes' if metrics['security']['sql_injection_safe'] else 'No'}")
        report.append(f"  - XSS Protection: {'Yes' if metrics['security']['xss_protection'] else 'No'}")
        report.append(f"  - Secrets in Code: {'FOUND! ⚠️' if metrics['security']['secrets_in_code'] else 'None'}")
        report.append(f"  - Input Validation: {'Yes' if metrics['security']['input_validation'] else 'No'}")
        report.append("")

        # Recommendations
        if metrics['recommendations']:
            report.append("Recommendations for Improvement:")
            for i, rec in enumerate(metrics['recommendations'], 1):
                report.append(f"  {i}. {rec}")
            report.append("")

        report.append("=" * 60)

        return "\n".join(report)


# Convenience function for boss agent integration
def verify_with_metrics(project_path: str,
                       strict: bool = True,
                       verbose: bool = False) -> Tuple[bool, str]:
    """Verify project with metrics for boss agent
    
    Args:
        project_path: Path to project
        strict: Use strict mode
        verbose: Generate verbose report
        
    Returns:
        Tuple of (passed, report_or_reason)

    """
    verifier = MetricsVerifier(strict_mode=strict)
    result = verifier.verify_project(project_path)

    if verbose:
        report = MetricsIntegration.generate_quality_report(project_path)
        return result.passed, report
    else:
        if result.passed:
            return True, f"Quality score: {result.score:.1f}/100"
        else:
            reasons = "\n".join(result.failures)
            return False, f"Verification failed:\n{reasons}"
