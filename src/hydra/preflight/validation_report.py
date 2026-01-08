"""Validation report generation for pre-flight checks.

This module provides structured reporting capabilities for validation results,
enabling detailed tracking and presentation of pre-flight check outcomes.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class ValidationLevel(Enum):
    """Severity levels for validation checks."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def emoji(self) -> str:
        """Get emoji representation for the level."""
        return {
            ValidationLevel.INFO: "ℹ️",
            ValidationLevel.WARNING: "⚠️",
            ValidationLevel.ERROR: "❌",
            ValidationLevel.CRITICAL: "🚨",
        }[self]

    @property
    def priority(self) -> int:
        """Get numeric priority for sorting (higher = more severe)."""
        return {
            ValidationLevel.INFO: 0,
            ValidationLevel.WARNING: 1,
            ValidationLevel.ERROR: 2,
            ValidationLevel.CRITICAL: 3,
        }[self]


@dataclass
class ValidationCheck:
    """Represents a single validation check result."""

    name: str
    description: str
    level: ValidationLevel
    passed: bool = False
    message: str = ""
    details: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def status_emoji(self) -> str:
        """Get emoji for the check status."""
        return "✅" if self.passed else self.level.emoji

    def to_dict(self) -> Dict:
        """Convert check to dictionary format."""
        return {
            "name": self.name,
            "description": self.description,
            "level": self.level.value,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }

    def format_summary(self) -> str:
        """Format check as a summary line."""
        status = "PASS" if self.passed else "FAIL"
        return f"{self.status_emoji} [{status}] {self.description}: {self.message}"

    def format_detailed(self) -> str:
        """Format check with full details."""
        lines = [self.format_summary()]
        if self.details:
            for detail in self.details:
                lines.append(f"    {detail}")
        return "\n".join(lines)


class ValidationReport:
    """Comprehensive validation report for pre-flight checks."""

    def __init__(self):
        """Initialize an empty validation report."""
        self.checks: List[ValidationCheck] = []
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.metadata: Dict = {}

    def add_check(self, check: ValidationCheck) -> None:
        """Add a validation check to the report.

        Args:
            check: ValidationCheck to add

        """
        self.checks.append(check)

    def finalize(self) -> None:
        """Mark the report as complete."""
        self.end_time = datetime.now()

    @property
    def duration(self) -> float:
        """Get validation duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def total_checks(self) -> int:
        """Get total number of checks performed."""
        return len(self.checks)

    @property
    def passed_checks(self) -> int:
        """Get number of passed checks."""
        return sum(1 for check in self.checks if check.passed)

    @property
    def failed_checks(self) -> int:
        """Get number of failed checks."""
        return sum(1 for check in self.checks if not check.passed)

    @property
    def pass_rate(self) -> float:
        """Get percentage of passed checks."""
        if self.total_checks == 0:
            return 100.0
        return (self.passed_checks / self.total_checks) * 100

    def has_critical_issues(self) -> bool:
        """Check if there are any critical issues.

        Returns:
            True if any critical checks failed

        """
        return any(
            check.level == ValidationLevel.CRITICAL and not check.passed
            for check in self.checks
        )

    def has_errors(self) -> bool:
        """Check if there are any errors.

        Returns:
            True if any error-level checks failed

        """
        return any(
            check.level == ValidationLevel.ERROR and not check.passed
            for check in self.checks
        )

    def has_warnings(self) -> bool:
        """Check if there are any warnings.

        Returns:
            True if any warning-level checks failed

        """
        return any(
            check.level == ValidationLevel.WARNING and not check.passed
            for check in self.checks
        )

    def get_failed_checks(self) -> List[ValidationCheck]:
        """Get all failed validation checks.

        Returns:
            List of failed checks sorted by severity

        """
        failed = [check for check in self.checks if not check.passed]
        return sorted(failed, key=lambda c: c.level.priority, reverse=True)

    def get_critical_issues(self) -> List[ValidationCheck]:
        """Get all critical issues.

        Returns:
            List of critical checks that failed

        """
        return [
            check
            for check in self.checks
            if check.level == ValidationLevel.CRITICAL and not check.passed
        ]

    def get_checks_by_level(self, level: ValidationLevel) -> List[ValidationCheck]:
        """Get all checks of a specific level.

        Args:
            level: ValidationLevel to filter by

        Returns:
            List of checks matching the level

        """
        return [check for check in self.checks if check.level == level]

    def get_summary(self) -> str:
        """Generate a human-readable summary of the validation report.

        Returns:
            Formatted summary string

        """
        lines = [
            "=" * 60,
            "PRE-FLIGHT VALIDATION REPORT",
            "=" * 60,
            f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if self.end_time:
            lines.append(f"Completed: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"Duration: {self.duration:.2f} seconds")

        lines.extend(
            [
                "",
                f"Total Checks: {self.total_checks}",
                f"Passed: {self.passed_checks} ({self.pass_rate:.1f}%)",
                f"Failed: {self.failed_checks}",
                "",
            ]
        )

        # Overall status
        if self.has_critical_issues():
            lines.append("🚨 CRITICAL ISSUES FOUND - EXECUTION BLOCKED")
        elif self.has_errors():
            lines.append("❌ ERRORS FOUND - EXECUTION NOT RECOMMENDED")
        elif self.has_warnings():
            lines.append("⚠️  WARNINGS FOUND - REVIEW BEFORE PROCEEDING")
        else:
            lines.append("✅ ALL CHECKS PASSED - READY FOR EXECUTION")

        lines.append("")

        # Group checks by level
        for level in [
            ValidationLevel.CRITICAL,
            ValidationLevel.ERROR,
            ValidationLevel.WARNING,
            ValidationLevel.INFO,
        ]:
            level_checks = self.get_checks_by_level(level)
            if level_checks:
                lines.append(f"\n{level.emoji} {level.value.upper()} CHECKS:")
                lines.append("-" * 40)
                for check in level_checks:
                    lines.append(check.format_summary())

        return "\n".join(lines)

    def get_detailed_report(self) -> str:
        """Generate a detailed validation report with all information.

        Returns:
            Detailed formatted report string

        """
        lines = [
            "=" * 60,
            "DETAILED PRE-FLIGHT VALIDATION REPORT",
            "=" * 60,
            f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if self.end_time:
            lines.append(f"Completed: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"Duration: {self.duration:.2f} seconds")

        lines.extend(
            [
                "",
                "SUMMARY",
                "-" * 40,
                f"Total Checks: {self.total_checks}",
                f"Passed: {self.passed_checks} ({self.pass_rate:.1f}%)",
                f"Failed: {self.failed_checks}",
                "",
            ]
        )

        # Overall status
        if self.has_critical_issues():
            lines.append("🚨 CRITICAL ISSUES FOUND - EXECUTION BLOCKED")
        elif self.has_errors():
            lines.append("❌ ERRORS FOUND - EXECUTION NOT RECOMMENDED")
        elif self.has_warnings():
            lines.append("⚠️  WARNINGS FOUND - REVIEW BEFORE PROCEEDING")
        else:
            lines.append("✅ ALL CHECKS PASSED - READY FOR EXECUTION")

        lines.extend(
            [
                "",
                "DETAILED CHECK RESULTS",
                "=" * 60,
            ]
        )

        # Sort checks by severity and status
        sorted_checks = sorted(
            self.checks,
            key=lambda c: (not c.passed, c.level.priority),
            reverse=True,
        )

        for i, check in enumerate(sorted_checks, 1):
            lines.append(f"\n[{i}/{self.total_checks}] {check.name}")
            lines.append("-" * 40)
            lines.append(check.format_detailed())

        if self.metadata:
            lines.extend(
                [
                    "",
                    "METADATA",
                    "-" * 40,
                ]
            )
            for key, value in self.metadata.items():
                lines.append(f"{key}: {value}")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Export report as JSON string.

        Returns:
            JSON representation of the report

        """
        data = {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "summary": {
                "total_checks": self.total_checks,
                "passed": self.passed_checks,
                "failed": self.failed_checks,
                "pass_rate": self.pass_rate,
                "has_critical": self.has_critical_issues(),
                "has_errors": self.has_errors(),
                "has_warnings": self.has_warnings(),
            },
            "checks": [check.to_dict() for check in self.checks],
            "metadata": self.metadata,
        }
        return json.dumps(data, indent=2)

    def save_to_file(self, filepath: str, format: str = "text") -> None:
        """Save report to a file.

        Args:
            filepath: Path to save the report
            format: Format to save in ('text', 'detailed', 'json')

        """
        if format == "json":
            content = self.to_json()
        elif format == "detailed":
            content = self.get_detailed_report()
        else:
            content = self.get_summary()

        with open(filepath, "w") as f:
            f.write(content)

    def print_summary(self) -> None:
        """Print the summary to console."""
        print(self.get_summary())

    def get_recommendations(self) -> List[str]:
        """Generate recommendations based on validation results.

        Returns:
            List of recommended actions

        """
        recommendations = []

        if self.has_critical_issues():
            recommendations.append(
                "Fix all critical issues before attempting execution"
            )
            critical = self.get_critical_issues()
            for check in critical[:3]:  # Show top 3 critical issues
                recommendations.append(f"  - Fix: {check.message}")

        if self.has_errors():
            recommendations.append(
                "Resolve error-level issues to ensure smooth execution"
            )

        # Check for specific issue patterns
        failed = self.get_failed_checks()
        check_names = [check.name for check in failed]

        if "dependency_validation" in check_names:
            recommendations.append(
                "Review and fix ticket dependencies using dependency validator"
            )

        if "input_files_exist" in check_names:
            recommendations.append(
                "Ensure all required input files are present before execution"
            )

        if "file_conflicts" in check_names:
            recommendations.append(
                "Resolve file write conflicts or adjust parallel execution groups"
            )

        if "model_configuration" in check_names:
            recommendations.append(
                "Configure required AI models or update ticket model assignments"
            )

        if not recommendations and self.has_warnings():
            recommendations.append(
                "Review warnings and assess if they impact your use case"
            )

        if not recommendations:
            recommendations.append("System is ready for ticket execution")

        return recommendations

    def can_execute_with_skip(self) -> List[str]:
        """Determine which checks could be skipped for forced execution.

        Returns:
            List of check names that could be skipped

        """
        skippable = []

        for check in self.get_failed_checks():
            # Never skip critical dependency issues
            if (
                check.name == "dependency_validation"
                and check.level == ValidationLevel.CRITICAL
            ):
                continue

            # Warning level checks are generally skippable
            if check.level == ValidationLevel.WARNING:
                skippable.append(check.name)

            # Some error checks might be skippable
            if check.level == ValidationLevel.ERROR:
                if check.name in ["model_configuration", "resource_availability"]:
                    skippable.append(check.name)

        return skippable
