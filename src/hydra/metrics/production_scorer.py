"""Production Quality Scoring System

Comprehensive scoring system to measure and score production readiness
of generated code with configurable thresholds for pass/fail decisions.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .quality_metrics import (
    ComplexityMetrics,
    CoverageMetrics,
    DocumentationMetrics,
    ErrorHandlingMetrics,
    PerformanceMetrics,
    QualityMetricsAnalyzer,
    QualityReport,
    SecurityMetrics,
)

logger = logging.getLogger(__name__)


class ScoreCategory(Enum):
    """Categories for scoring different aspects."""
    
    COMPLEXITY = "complexity"
    COVERAGE = "coverage"
    DOCUMENTATION = "documentation"
    ERROR_HANDLING = "error_handling"
    PERFORMANCE = "performance"
    SECURITY = "security"
    OVERALL = "overall"


@dataclass
class CategoryScore:
    """Score for a specific category."""
    
    category: ScoreCategory
    score: float  # 0-10 scale
    weight: float  # Weight in overall score
    passed: bool  # Whether it meets minimum threshold
    details: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class ProductionReadinessScore:
    """Complete production readiness scoring."""
    
    overall_score: float  # 0-10 scale
    production_ready: bool
    category_scores: Dict[ScoreCategory, CategoryScore]
    passed_categories: List[ScoreCategory]
    failed_categories: List[ScoreCategory]
    critical_issues: List[str]
    recommendations: List[str]
    threshold_met: bool
    detailed_report: Optional[str] = None


class ProductionScorer:
    """Scores production readiness of code."""
    
    # Default weights for each category (must sum to 1.0)
    DEFAULT_WEIGHTS = {
        ScoreCategory.COMPLEXITY: 0.15,
        ScoreCategory.COVERAGE: 0.25,
        ScoreCategory.DOCUMENTATION: 0.15,
        ScoreCategory.ERROR_HANDLING: 0.20,
        ScoreCategory.PERFORMANCE: 0.10,
        ScoreCategory.SECURITY: 0.15,
    }
    
    # Default minimum thresholds for each category (0-10 scale)
    DEFAULT_THRESHOLDS = {
        ScoreCategory.COMPLEXITY: 6.0,
        ScoreCategory.COVERAGE: 7.0,
        ScoreCategory.DOCUMENTATION: 6.0,
        ScoreCategory.ERROR_HANDLING: 7.0,
        ScoreCategory.PERFORMANCE: 5.0,
        ScoreCategory.SECURITY: 8.0,
        ScoreCategory.OVERALL: 7.0,  # Overall threshold for production readiness
    }
    
    def __init__(
        self,
        weights: Optional[Dict[ScoreCategory, float]] = None,
        thresholds: Optional[Dict[ScoreCategory, float]] = None,
        strict_mode: bool = False
    ):
        """Initialize production scorer.
        
        Args:
            weights: Custom weights for categories
            thresholds: Custom thresholds for categories
            strict_mode: If True, all categories must pass
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.thresholds = thresholds or self.DEFAULT_THRESHOLDS
        self.strict_mode = strict_mode
        self.analyzer = QualityMetricsAnalyzer()
        
        # Validate weights sum to 1.0
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")
    
    def score_project(self, project_path: str) -> ProductionReadinessScore:
        """Score a project's production readiness.
        
        Args:
            project_path: Path to project directory
            
        Returns:
            ProductionReadinessScore with detailed scoring
        """
        # Analyze project quality
        quality_report = self.analyzer.analyze_project(project_path)
        
        # Score each category
        category_scores = {}
        
        # Complexity scoring
        complexity_score = self._score_complexity(quality_report.complexity)
        category_scores[ScoreCategory.COMPLEXITY] = complexity_score
        
        # Coverage scoring
        coverage_score = self._score_coverage(quality_report.coverage)
        category_scores[ScoreCategory.COVERAGE] = coverage_score
        
        # Documentation scoring
        documentation_score = self._score_documentation(quality_report.documentation)
        category_scores[ScoreCategory.DOCUMENTATION] = documentation_score
        
        # Error handling scoring
        error_handling_score = self._score_error_handling(quality_report.error_handling)
        category_scores[ScoreCategory.ERROR_HANDLING] = error_handling_score
        
        # Performance scoring
        performance_score = self._score_performance(quality_report.performance)
        category_scores[ScoreCategory.PERFORMANCE] = performance_score
        
        # Security scoring
        security_score = self._score_security(quality_report.security)
        category_scores[ScoreCategory.SECURITY] = security_score
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(category_scores)
        
        # Determine pass/fail status
        passed_categories = []
        failed_categories = []
        critical_issues = []
        
        for category, score in category_scores.items():
            if score.passed:
                passed_categories.append(category)
            else:
                failed_categories.append(category)
                if score.score < 5.0:  # Critical if below 5
                    critical_issues.append(
                        f"{category.value}: Score {score.score:.1f} is critically low"
                    )
        
        # Check if production ready
        production_ready = self._is_production_ready(
            overall_score, category_scores, critical_issues
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(category_scores, quality_report)
        
        # Generate detailed report
        detailed_report = self._generate_detailed_report(
            category_scores, overall_score, quality_report
        )
        
        return ProductionReadinessScore(
            overall_score=overall_score,
            production_ready=production_ready,
            category_scores=category_scores,
            passed_categories=passed_categories,
            failed_categories=failed_categories,
            critical_issues=critical_issues,
            recommendations=recommendations,
            threshold_met=overall_score >= self.thresholds[ScoreCategory.OVERALL],
            detailed_report=detailed_report
        )
    
    def _score_complexity(self, metrics: ComplexityMetrics) -> CategoryScore:
        """Score code complexity metrics."""
        score = 10.0
        details = {}
        recommendations = []
        
        # Cyclomatic complexity (lower is better)
        if metrics.cyclomatic_complexity > 20:
            score -= 3.0
            recommendations.append("Reduce cyclomatic complexity in complex functions")
        elif metrics.cyclomatic_complexity > 10:
            score -= 1.5
        details["cyclomatic_complexity"] = metrics.cyclomatic_complexity
        
        # Cognitive complexity (lower is better)
        if metrics.cognitive_complexity > 15:
            score -= 2.0
            recommendations.append("Simplify complex logic to reduce cognitive load")
        elif metrics.cognitive_complexity > 8:
            score -= 1.0
        details["cognitive_complexity"] = metrics.cognitive_complexity
        
        # Nesting depth (lower is better)
        if metrics.nesting_depth > 4:
            score -= 2.0
            recommendations.append("Reduce nesting depth for better readability")
        elif metrics.nesting_depth > 3:
            score -= 1.0
        details["nesting_depth"] = metrics.nesting_depth
        
        # Function length
        if metrics.max_function_length > 50:
            score -= 1.5
            recommendations.append("Break down long functions into smaller ones")
        elif metrics.max_function_length > 30:
            score -= 0.5
        details["max_function_length"] = metrics.max_function_length
        
        # Duplicate code
        if metrics.duplicate_code_ratio > 0.15:
            score -= 2.0
            recommendations.append("Eliminate duplicate code through refactoring")
        elif metrics.duplicate_code_ratio > 0.05:
            score -= 1.0
        details["duplicate_code_ratio"] = metrics.duplicate_code_ratio
        
        score = max(0, score)  # Ensure non-negative
        
        return CategoryScore(
            category=ScoreCategory.COMPLEXITY,
            score=score,
            weight=self.weights[ScoreCategory.COMPLEXITY],
            passed=score >= self.thresholds[ScoreCategory.COMPLEXITY],
            details=details,
            recommendations=recommendations
        )
    
    def _score_coverage(self, metrics: CoverageMetrics) -> CategoryScore:
        """Score test coverage metrics."""
        # Direct percentage to 10-scale conversion
        line_coverage_score = (metrics.line_coverage / 100) * 10
        branch_coverage_score = (metrics.branch_coverage / 100) * 10
        
        # Weighted average (line coverage more important)
        score = (line_coverage_score * 0.6) + (branch_coverage_score * 0.4)
        
        details = {
            "line_coverage": metrics.line_coverage,
            "branch_coverage": metrics.branch_coverage,
            "test_to_code_ratio": metrics.test_to_code_ratio
        }
        
        recommendations = []
        if metrics.line_coverage < 80:
            recommendations.append(f"Increase line coverage from {metrics.line_coverage}% to at least 80%")
        if metrics.branch_coverage < 70:
            recommendations.append(f"Increase branch coverage from {metrics.branch_coverage}% to at least 70%")
        if metrics.test_to_code_ratio < 0.5:
            recommendations.append("Add more tests - aim for 1:2 test-to-code ratio")
        
        return CategoryScore(
            category=ScoreCategory.COVERAGE,
            score=score,
            weight=self.weights[ScoreCategory.COVERAGE],
            passed=score >= self.thresholds[ScoreCategory.COVERAGE],
            details=details,
            recommendations=recommendations
        )
    
    def _score_documentation(self, metrics: DocumentationMetrics) -> CategoryScore:
        """Score documentation completeness."""
        score = 0.0
        
        # Docstring coverage (40% of score)
        docstring_score = (metrics.docstring_coverage / 100) * 4.0
        score += docstring_score
        
        # Public API documentation (30% of score)
        api_doc_score = (metrics.public_api_documented / 100) * 3.0
        score += api_doc_score
        
        # README and docs (30% of score)
        if metrics.readme_exists:
            score += 1.5
        if metrics.api_docs_exists:
            score += 1.0
        if metrics.examples_provided:
            score += 0.5
        
        details = {
            "docstring_coverage": metrics.docstring_coverage,
            "public_api_documented": metrics.public_api_documented,
            "readme_exists": metrics.readme_exists,
            "api_docs_exists": metrics.api_docs_exists
        }
        
        recommendations = []
        if metrics.docstring_coverage < 70:
            recommendations.append("Add docstrings to all public functions and classes")
        if not metrics.readme_exists:
            recommendations.append("Create a comprehensive README file")
        if not metrics.examples_provided:
            recommendations.append("Add usage examples to documentation")
        
        return CategoryScore(
            category=ScoreCategory.DOCUMENTATION,
            score=min(10, score),  # Cap at 10
            weight=self.weights[ScoreCategory.DOCUMENTATION],
            passed=score >= self.thresholds[ScoreCategory.DOCUMENTATION],
            details=details,
            recommendations=recommendations
        )
    
    def _score_error_handling(self, metrics: ErrorHandlingMetrics) -> CategoryScore:
        """Score error handling implementation."""
        score = 5.0  # Start at middle
        
        # Try-except coverage
        if metrics.try_except_coverage > 0.3:
            score += 2.0
        elif metrics.try_except_coverage > 0.1:
            score += 1.0
        
        # Custom exceptions
        if metrics.custom_exceptions_defined:
            score += 1.0
        
        # Error logging
        if metrics.error_logging_present:
            score += 1.0
        
        # Input validation
        if metrics.input_sanitization:
            score += 1.0
        
        # Retry logic
        if metrics.retry_logic_present:
            score += 0.5
        
        # Circuit breaker
        if metrics.circuit_breaker_present:
            score += 0.5
        
        # Penalize unhandled exceptions
        score -= len(metrics.unhandled_exceptions) * 0.5
        
        details = {
            "try_except_coverage": metrics.try_except_coverage,
            "error_logging": metrics.error_logging_present,
            "unhandled_exceptions": len(metrics.unhandled_exceptions)
        }
        
        recommendations = []
        if not metrics.error_logging_present:
            recommendations.append("Add comprehensive error logging")
        if not metrics.custom_exceptions_defined:
            recommendations.append("Define custom exception classes")
        if metrics.unhandled_exceptions:
            recommendations.append(f"Handle {len(metrics.unhandled_exceptions)} unhandled exception(s)")
        
        return CategoryScore(
            category=ScoreCategory.ERROR_HANDLING,
            score=min(10, max(0, score)),
            weight=self.weights[ScoreCategory.ERROR_HANDLING],
            passed=score >= self.thresholds[ScoreCategory.ERROR_HANDLING],
            details=details,
            recommendations=recommendations
        )
    
    def _score_performance(self, metrics: PerformanceMetrics) -> CategoryScore:
        """Score performance optimizations."""
        score = 5.0  # Start at middle
        
        # Response time
        if metrics.p95_response_time < 100:  # < 100ms
            score += 2.0
        elif metrics.p95_response_time < 500:  # < 500ms
            score += 1.0
        
        # Caching
        if metrics.caching_implemented:
            score += 1.0
        
        # Async operations
        if metrics.async_operations_used:
            score += 1.0
        
        # Batch processing
        if metrics.batch_processing_used:
            score += 0.5
        
        # Connection pooling
        if metrics.connection_pooling:
            score += 0.5
        
        details = {
            "p95_response_time": metrics.p95_response_time,
            "caching": metrics.caching_implemented,
            "async_operations": metrics.async_operations_used
        }
        
        recommendations = []
        if not metrics.caching_implemented:
            recommendations.append("Implement caching for frequently accessed data")
        if not metrics.async_operations_used:
            recommendations.append("Use async operations for I/O-bound tasks")
        if metrics.p95_response_time > 500:
            recommendations.append("Optimize response time - target < 500ms p95")
        
        return CategoryScore(
            category=ScoreCategory.PERFORMANCE,
            score=min(10, score),
            weight=self.weights[ScoreCategory.PERFORMANCE],
            passed=score >= self.thresholds[ScoreCategory.PERFORMANCE],
            details=details,
            recommendations=recommendations
        )
    
    def _score_security(self, metrics: SecurityMetrics) -> CategoryScore:
        """Score security best practices."""
        score = 10.0  # Start high, deduct for issues
        
        # Critical: Secrets in code
        if metrics.secrets_in_code:
            score -= 5.0  # Major deduction
        
        # SQL injection vulnerabilities
        if not metrics.sql_injection_safe:
            score -= 3.0
        
        # Input validation
        if not metrics.input_validation:
            score -= 2.0
        
        # Authentication
        if not metrics.authentication_present:
            score -= 1.5
        
        # Authorization
        if not metrics.authorization_present:
            score -= 1.5
        
        # Encryption
        if not metrics.encryption_used:
            score -= 1.0
        
        # Outdated dependencies
        if metrics.outdated_dependencies > 5:
            score -= 2.0
        elif metrics.outdated_dependencies > 0:
            score -= 1.0
        
        details = {
            "secrets_in_code": metrics.secrets_in_code,
            "sql_injection_safe": metrics.sql_injection_safe,
            "outdated_dependencies": metrics.outdated_dependencies
        }
        
        recommendations = []
        if metrics.secrets_in_code:
            recommendations.append("CRITICAL: Remove secrets from code immediately!")
        if not metrics.sql_injection_safe:
            recommendations.append("CRITICAL: Fix SQL injection vulnerabilities")
        if not metrics.input_validation:
            recommendations.append("Add input validation for all user inputs")
        if metrics.outdated_dependencies > 0:
            recommendations.append(f"Update {metrics.outdated_dependencies} outdated dependencies")
        
        return CategoryScore(
            category=ScoreCategory.SECURITY,
            score=max(0, score),
            weight=self.weights[ScoreCategory.SECURITY],
            passed=score >= self.thresholds[ScoreCategory.SECURITY],
            details=details,
            recommendations=recommendations
        )
    
    def _calculate_overall_score(self, category_scores: Dict[ScoreCategory, CategoryScore]) -> float:
        """Calculate weighted overall score."""
        total_score = 0.0
        
        for category, score in category_scores.items():
            total_score += score.score * score.weight
        
        return round(total_score, 2)
    
    def _is_production_ready(
        self,
        overall_score: float,
        category_scores: Dict[ScoreCategory, CategoryScore],
        critical_issues: List[str]
    ) -> bool:
        """Determine if code is production ready."""
        # Critical issues = not production ready
        if critical_issues:
            return False
        
        # Check overall threshold
        if overall_score < self.thresholds[ScoreCategory.OVERALL]:
            return False
        
        # In strict mode, all categories must pass
        if self.strict_mode:
            for score in category_scores.values():
                if not score.passed:
                    return False
        
        # Security must always pass
        if not category_scores[ScoreCategory.SECURITY].passed:
            return False
        
        # Coverage must always pass
        if not category_scores[ScoreCategory.COVERAGE].passed:
            return False
        
        return True
    
    def _generate_recommendations(
        self,
        category_scores: Dict[ScoreCategory, CategoryScore],
        quality_report: QualityReport
    ) -> List[str]:
        """Generate prioritized recommendations."""
        all_recommendations = []
        
        # Collect all recommendations with priority
        for category, score in category_scores.items():
            if not score.passed:
                # High priority for failed categories
                for rec in score.recommendations:
                    all_recommendations.append((1, rec))
            else:
                # Low priority for passed categories
                for rec in score.recommendations:
                    all_recommendations.append((2, rec))
        
        # Sort by priority and deduplicate
        all_recommendations.sort(key=lambda x: x[0])
        seen = set()
        final_recommendations = []
        
        for _, rec in all_recommendations:
            if rec not in seen:
                seen.add(rec)
                final_recommendations.append(rec)
        
        return final_recommendations[:10]  # Top 10 recommendations
    
    def _generate_detailed_report(
        self,
        category_scores: Dict[ScoreCategory, CategoryScore],
        overall_score: float,
        quality_report: QualityReport
    ) -> str:
        """Generate detailed scoring report."""
        lines = []
        lines.append("=" * 60)
        lines.append("PRODUCTION READINESS SCORE REPORT")
        lines.append("=" * 60)
        lines.append(f"\nOverall Score: {overall_score:.1f}/10")
        lines.append(f"Threshold: {self.thresholds[ScoreCategory.OVERALL]:.1f}/10")
        lines.append(f"Status: {'✅ PRODUCTION READY' if overall_score >= self.thresholds[ScoreCategory.OVERALL] else '❌ NOT PRODUCTION READY'}")
        
        lines.append("\n" + "-" * 60)
        lines.append("CATEGORY SCORES")
        lines.append("-" * 60)
        
        for category in ScoreCategory:
            if category == ScoreCategory.OVERALL:
                continue
            
            score = category_scores[category]
            status = "✅" if score.passed else "❌"
            lines.append(
                f"{status} {category.value.replace('_', ' ').title():20} "
                f"{score.score:4.1f}/10 "
                f"(threshold: {self.thresholds[category]:.1f})"
            )
        
        lines.append("\n" + "-" * 60)
        lines.append("CRITICAL METRICS")
        lines.append("-" * 60)
        
        lines.append(f"Line Coverage: {quality_report.coverage.line_coverage:.1f}%")
        lines.append(f"Cyclomatic Complexity: {quality_report.complexity.cyclomatic_complexity}")
        lines.append(f"Security Issues: {len(quality_report.security.vulnerabilities)}")
        lines.append(f"Unhandled Exceptions: {len(quality_report.error_handling.unhandled_exceptions)}")
        
        return "\n".join(lines)


# Convenience functions
def score_production_readiness(
    project_path: str,
    strict: bool = False,
    custom_thresholds: Optional[Dict[str, float]] = None
) -> Tuple[float, bool, str]:
    """Score production readiness of a project.
    
    Args:
        project_path: Path to project
        strict: If True, all categories must pass
        custom_thresholds: Custom scoring thresholds
        
    Returns:
        Tuple of (score, is_production_ready, report)
    """
    scorer = ProductionScorer(
        thresholds=custom_thresholds,
        strict_mode=strict
    )
    
    result = scorer.score_project(project_path)
    
    return result.overall_score, result.production_ready, result.detailed_report


def get_production_score(project_path: str) -> float:
    """Get simple production readiness score.
    
    Args:
        project_path: Path to project
        
    Returns:
        Score from 0-10
    """
    scorer = ProductionScorer()
    result = scorer.score_project(project_path)
    return result.overall_score