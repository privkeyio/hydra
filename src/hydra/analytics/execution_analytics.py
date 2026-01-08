"""Execution analytics system for measuring ticket performance and model effectiveness.

This module provides comprehensive analytics capabilities to track actual vs
estimated completion times, measure model performance by ticket type, and
identify failure patterns.
"""

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..estimation.complexity_estimator import (
    EffortCategory,
    EstimationResult,
    TimeEstimate,
)
from ..intelligence.model_selector import ModelCategory
from ..tracking.progress_tracker import ProgressStage, TicketProgress


class FailureCategory(Enum):
    """Categories for ticket execution failures."""

    TIMEOUT = "timeout"
    COMPLEXITY_UNDERESTIMATED = "complexity_underestimated"
    MODEL_MISMATCH = "model_mismatch"
    DEPENDENCY_ISSUE = "dependency_issue"
    TECHNICAL_ERROR = "technical_error"
    RESOURCE_CONSTRAINT = "resource_constraint"
    EXTERNAL_SERVICE = "external_service"
    UNKNOWN = "unknown"


@dataclass
class ModelPerformance:
    """Performance metrics for a specific model category."""

    model_category: ModelCategory
    total_tickets: int = 0
    completed_tickets: int = 0
    failed_tickets: int = 0
    average_completion_time: float = 0.0
    accuracy_vs_estimates: float = 0.0
    complexity_handling_score: float = 0.0
    failure_rate: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_tickets == 0:
            return 0.0
        return (self.completed_tickets / self.total_tickets) * 100

    @property
    def performance_score(self) -> float:
        """Calculate overall performance score (0-100)."""
        if self.total_tickets == 0:
            return 0.0

        success_weight = 0.4
        accuracy_weight = 0.3
        complexity_weight = 0.3

        return (
            self.success_rate * success_weight
            + self.accuracy_vs_estimates * accuracy_weight
            + self.complexity_handling_score * complexity_weight
        )


@dataclass
class AnalyticsMetrics:
    """Comprehensive analytics metrics for ticket execution."""

    total_tickets: int = 0
    completed_tickets: int = 0
    failed_tickets: int = 0
    average_execution_time: float = 0.0
    estimation_accuracy: float = 0.0
    model_performance: Dict[str, ModelPerformance] = field(default_factory=dict)
    failure_patterns: Dict[str, int] = field(default_factory=dict)
    complexity_trends: Dict[str, List[float]] = field(default_factory=dict)
    time_analysis: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    @property
    def overall_success_rate(self) -> float:
        """Calculate overall success rate percentage."""
        if self.total_tickets == 0:
            return 0.0
        return (self.completed_tickets / self.total_tickets) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary format."""
        return {
            "total_tickets": self.total_tickets,
            "completed_tickets": self.completed_tickets,
            "failed_tickets": self.failed_tickets,
            "overall_success_rate": self.overall_success_rate,
            "average_execution_time": self.average_execution_time,
            "estimation_accuracy": self.estimation_accuracy,
            "model_performance": {
                k: {
                    "model_category": v.model_category.value,
                    "total_tickets": v.total_tickets,
                    "success_rate": v.success_rate,
                    "performance_score": v.performance_score,
                    "average_completion_time": v.average_completion_time,
                    "accuracy_vs_estimates": v.accuracy_vs_estimates,
                    "complexity_handling_score": v.complexity_handling_score,
                    "failure_rate": v.failure_rate,
                }
                for k, v in self.model_performance.items()
            },
            "failure_patterns": self.failure_patterns,
            "complexity_trends": self.complexity_trends,
            "time_analysis": self.time_analysis,
            "recommendations": self.recommendations,
        }


@dataclass
class TicketAnalyticsData:
    """Analytics data for a single ticket execution."""

    ticket_id: str
    model_used: Optional[ModelCategory] = None
    estimated_effort: Optional[EffortCategory] = None
    estimated_time: Optional[TimeEstimate] = None
    actual_duration: Optional[float] = None
    completion_status: Optional[ProgressStage] = None
    complexity_score: Optional[float] = None
    failure_category: Optional[FailureCategory] = None
    execution_metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "ticket_id": self.ticket_id,
            "model_used": self.model_used.value if self.model_used else None,
            "estimated_effort": (
                self.estimated_effort.value if self.estimated_effort else None
            ),
            "estimated_time": (
                self.estimated_time.value if self.estimated_time else None
            ),
            "actual_duration": self.actual_duration,
            "completion_status": (
                self.completion_status.value if self.completion_status else None
            ),
            "complexity_score": self.complexity_score,
            "failure_category": (
                self.failure_category.value if self.failure_category else None
            ),
            "execution_metadata": self.execution_metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TicketAnalyticsData":
        """Create from dictionary format."""
        return cls(
            ticket_id=data["ticket_id"],
            model_used=(
                ModelCategory(data["model_used"]) if data.get("model_used") else None
            ),
            estimated_effort=(
                EffortCategory(data["estimated_effort"])
                if data.get("estimated_effort")
                else None
            ),
            estimated_time=(
                TimeEstimate(data["estimated_time"])
                if data.get("estimated_time")
                else None
            ),
            actual_duration=data.get("actual_duration"),
            completion_status=(
                ProgressStage(data["completion_status"])
                if data.get("completion_status")
                else None
            ),
            complexity_score=data.get("complexity_score"),
            failure_category=(
                FailureCategory(data["failure_category"])
                if data.get("failure_category")
                else None
            ),
            execution_metadata=data.get("execution_metadata", {}),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if data.get("timestamp")
                else datetime.now()
            ),
        )


class ExecutionAnalytics:
    """Analytics system for tracking and analyzing ticket execution performance."""

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize the execution analytics system.

        Args:
            storage_path: Path to store analytics data

        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.ticket_data: Dict[str, TicketAnalyticsData] = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load existing analytics data from storage."""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            for ticket_data in data.get("tickets", []):
                analytics_data = TicketAnalyticsData.from_dict(ticket_data)
                self.ticket_data[analytics_data.ticket_id] = analytics_data

        except (json.JSONDecodeError, KeyError, ValueError):
            # If data file is corrupted, start fresh
            pass

    def _save_data(self) -> None:
        """Save analytics data to storage."""
        if not self.storage_path:
            return

        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "last_updated": datetime.now().isoformat(),
                "tickets": [ticket.to_dict() for ticket in self.ticket_data.values()],
            }

            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)

        except Exception:
            # Silently fail if we can't save data
            pass

    def record_ticket_execution(
        self,
        ticket_id: str,
        estimation_result: Optional[EstimationResult] = None,
        model_used: Optional[ModelCategory] = None,
        execution_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record the start of ticket execution.

        Args:
            ticket_id: Unique identifier for the ticket
            estimation_result: Initial estimation data
            model_used: Model category assigned for execution
            execution_metadata: Additional metadata about execution

        """
        analytics_data = TicketAnalyticsData(
            ticket_id=ticket_id,
            model_used=model_used,
            execution_metadata=execution_metadata or {},
        )

        if estimation_result:
            analytics_data.estimated_effort = estimation_result.effort_category
            analytics_data.estimated_time = estimation_result.time_estimate
            analytics_data.complexity_score = estimation_result.total_complexity_score

        self.ticket_data[ticket_id] = analytics_data
        self._save_data()

    def update_ticket_completion(
        self,
        ticket_id: str,
        progress: TicketProgress,
        failure_category: Optional[FailureCategory] = None,
    ) -> None:
        """Update ticket completion data.

        Args:
            ticket_id: Ticket identifier
            progress: TicketProgress object with completion data
            failure_category: Category of failure if ticket failed

        """
        if ticket_id not in self.ticket_data:
            # Create basic analytics data if not found
            self.ticket_data[ticket_id] = TicketAnalyticsData(ticket_id=ticket_id)

        analytics_data = self.ticket_data[ticket_id]
        analytics_data.actual_duration = progress.duration
        analytics_data.completion_status = progress.current_stage

        if failure_category:
            analytics_data.failure_category = failure_category

        self._save_data()

    def analyze_actual_vs_estimated_times(self) -> Dict[str, Any]:
        """Analyze accuracy of time estimations.

        Returns:
            Dictionary with timing analysis results

        """
        estimates_vs_actual = []
        time_estimate_to_minutes = {
            TimeEstimate.THIRTY_MIN: 30,
            TimeEstimate.ONE_HOUR: 60,
            TimeEstimate.TWO_HOURS: 120,
            TimeEstimate.FOUR_HOURS: 240,
            TimeEstimate.ONE_DAY: 480,
        }

        for ticket in self.ticket_data.values():
            if (
                ticket.estimated_time
                and ticket.actual_duration
                and ticket.completion_status == ProgressStage.COMPLETED
            ):

                estimated_minutes = time_estimate_to_minutes[ticket.estimated_time]
                actual_minutes = ticket.actual_duration / 60

                max_time = max(estimated_minutes, actual_minutes)
                accuracy = 1.0 - abs(estimated_minutes - actual_minutes) / max_time
                estimates_vs_actual.append(
                    {
                        "ticket_id": ticket.ticket_id,
                        "estimated_minutes": estimated_minutes,
                        "actual_minutes": actual_minutes,
                        "accuracy": max(0.0, accuracy),
                        "ratio": (
                            actual_minutes / estimated_minutes
                            if estimated_minutes > 0
                            else 0
                        ),
                    }
                )

        if not estimates_vs_actual:
            return {"average_accuracy": 0.0, "total_comparisons": 0, "details": []}

        average_accuracy = statistics.mean(
            [item["accuracy"] for item in estimates_vs_actual]
        )

        return {
            "average_accuracy": average_accuracy * 100,  # Convert to percentage
            "total_comparisons": len(estimates_vs_actual),
            "underestimated_count": len(
                [item for item in estimates_vs_actual if item["ratio"] > 1.2]
            ),
            "overestimated_count": len(
                [item for item in estimates_vs_actual if item["ratio"] < 0.8]
            ),
            "accurate_count": len(
                [item for item in estimates_vs_actual if 0.8 <= item["ratio"] <= 1.2]
            ),
            "details": estimates_vs_actual,
        }

    def measure_model_performance_by_type(self) -> Dict[str, ModelPerformance]:
        """Measure performance of each model category.

        Returns:
            Dictionary mapping model categories to performance metrics

        """
        model_metrics = {}

        for model_category in ModelCategory:
            model_tickets = [
                ticket
                for ticket in self.ticket_data.values()
                if ticket.model_used == model_category
            ]

            if not model_tickets:
                model_metrics[model_category.value] = ModelPerformance(model_category)
                continue

            completed_tickets = [
                ticket
                for ticket in model_tickets
                if ticket.completion_status == ProgressStage.COMPLETED
            ]

            failed_tickets = [
                ticket
                for ticket in model_tickets
                if ticket.completion_status == ProgressStage.FAILED
            ]

            # Calculate average completion time for completed tickets
            completion_times = [
                ticket.actual_duration
                for ticket in completed_tickets
                if ticket.actual_duration is not None
            ]
            avg_completion_time = (
                statistics.mean(completion_times) if completion_times else 0.0
            )

            # Calculate estimation accuracy for this model
            accuracy_scores = []
            for ticket in completed_tickets:
                if ticket.estimated_time and ticket.actual_duration:
                    time_estimate_to_minutes = {
                        TimeEstimate.THIRTY_MIN: 30,
                        TimeEstimate.ONE_HOUR: 60,
                        TimeEstimate.TWO_HOURS: 120,
                        TimeEstimate.FOUR_HOURS: 240,
                        TimeEstimate.ONE_DAY: 480,
                    }
                    estimated_minutes = time_estimate_to_minutes[ticket.estimated_time]
                    actual_minutes = ticket.actual_duration / 60
                    max_time = max(estimated_minutes, actual_minutes)
                    accuracy = 1.0 - abs(estimated_minutes - actual_minutes) / max_time
                    accuracy_scores.append(max(0.0, accuracy))

            avg_accuracy = (
                statistics.mean(accuracy_scores) * 100 if accuracy_scores else 0.0
            )

            # Calculate complexity handling score
            complexity_scores = [
                ticket.complexity_score
                for ticket in completed_tickets
                if ticket.complexity_score is not None
            ]
            avg_complexity = (
                statistics.mean(complexity_scores) if complexity_scores else 0.0
            )

            # Normalize complexity handling score
            complexity_handling_score = (
                min(avg_complexity * 10, 100) if avg_complexity > 0 else 0.0
            )

            model_metrics[model_category.value] = ModelPerformance(
                model_category=model_category,
                total_tickets=len(model_tickets),
                completed_tickets=len(completed_tickets),
                failed_tickets=len(failed_tickets),
                average_completion_time=avg_completion_time,
                accuracy_vs_estimates=avg_accuracy,
                complexity_handling_score=complexity_handling_score,
                failure_rate=(
                    (len(failed_tickets) / len(model_tickets)) * 100
                    if model_tickets
                    else 0.0
                ),
            )

        return model_metrics

    def identify_common_failure_patterns(self) -> Dict[str, Any]:
        """Identify common patterns in ticket failures.

        Returns:
            Dictionary with failure pattern analysis

        """
        failed_tickets = [
            ticket
            for ticket in self.ticket_data.values()
            if ticket.completion_status == ProgressStage.FAILED
        ]

        if not failed_tickets:
            return {"total_failures": 0, "patterns": {}}

        # Count failure categories
        failure_counts = {}
        for failure_category in FailureCategory:
            failure_counts[failure_category.value] = len(
                [
                    ticket
                    for ticket in failed_tickets
                    if ticket.failure_category == failure_category
                ]
            )

        # Analyze failure patterns by model
        model_failure_patterns = {}
        for model_category in ModelCategory:
            model_failures = [
                ticket
                for ticket in failed_tickets
                if ticket.model_used == model_category
            ]

            if model_failures:
                model_failure_counts = {}
                for failure_category in FailureCategory:
                    count = len(
                        [
                            ticket
                            for ticket in model_failures
                            if ticket.failure_category == failure_category
                        ]
                    )
                    if count > 0:
                        model_failure_counts[failure_category.value] = count

                model_failure_patterns[model_category.value] = model_failure_counts

        # Analyze failure patterns by complexity
        complexity_failure_patterns = {
            "low_complexity": 0,
            "medium_complexity": 0,
            "high_complexity": 0,
        }

        for ticket in failed_tickets:
            if ticket.complexity_score is not None:
                if ticket.complexity_score < 3.0:
                    complexity_failure_patterns["low_complexity"] += 1
                elif ticket.complexity_score < 7.0:
                    complexity_failure_patterns["medium_complexity"] += 1
                else:
                    complexity_failure_patterns["high_complexity"] += 1

        return {
            "total_failures": len(failed_tickets),
            "failure_rate": (
                (len(failed_tickets) / len(self.ticket_data)) * 100
                if self.ticket_data
                else 0.0
            ),
            "failure_categories": failure_counts,
            "model_failure_patterns": model_failure_patterns,
            "complexity_failure_patterns": complexity_failure_patterns,
        }

    def generate_performance_improvement_recommendations(self) -> List[str]:
        """Generate recommendations for improving ticket execution performance.

        Returns:
            List of recommendation strings

        """
        recommendations = []

        # Analyze timing accuracy
        timing_analysis = self.analyze_actual_vs_estimated_times()
        if timing_analysis["total_comparisons"] > 0:
            accuracy = timing_analysis["average_accuracy"]
            if accuracy < 70:
                recommendations.append(
                    f"Estimation accuracy is low ({accuracy:.1f}%). "
                    "Consider refining complexity estimation algorithms."
                )

            underestimated_ratio = (
                timing_analysis["underestimated_count"]
                / timing_analysis["total_comparisons"]
            )
            if underestimated_ratio > 0.3:
                recommendations.append(
                    f"High underestimation rate ({underestimated_ratio * 100:.1f}%). "
                    "Consider adding buffer time or improving complexity detection."
                )

        # Analyze model performance
        model_performance = self.measure_model_performance_by_type()
        for model_name, performance in model_performance.items():
            # Only analyze models with sufficient data
            if performance.total_tickets > 5:
                if performance.failure_rate > 20:
                    recommendations.append(
                        f"{model_name} model has high failure rate "
                        f"({performance.failure_rate:.1f}%). "
                        "Review task assignment criteria."
                    )

                if performance.performance_score < 60:
                    recommendations.append(
                        f"{model_name} model has low performance score "
                        f"({performance.performance_score:.1f}). "
                        "Consider training or configuration improvements."
                    )

        # Analyze failure patterns
        failure_patterns = self.identify_common_failure_patterns()
        if failure_patterns.get("failure_rate", 0) > 15:
            recommendations.append(
                f"Overall failure rate is high "
                f"({failure_patterns['failure_rate']:.1f}%). "
                "Focus on improving system reliability."
            )

        # Check for specific failure categories
        failure_categories = failure_patterns.get("failure_categories", {})
        if failure_categories.get("complexity_underestimated", 0) > 2:
            recommendations.append(
                "Multiple tickets failed due to underestimated complexity. "
                "Improve complexity analysis or add safety margins."
            )

        if failure_categories.get("model_mismatch", 0) > 2:
            recommendations.append(
                "Multiple tickets failed due to model mismatch. "
                "Review model selection criteria and thresholds."
            )

        # Default recommendation if no issues found
        if not recommendations:
            recommendations.append(
                "System performance looks good. Continue monitoring for trends."
            )

        return recommendations

    def get_comprehensive_metrics(self) -> AnalyticsMetrics:
        """Get comprehensive analytics metrics.

        Returns:
            AnalyticsMetrics object with all calculated metrics

        """
        total_tickets = len(self.ticket_data)
        completed_tickets = len(
            [
                ticket
                for ticket in self.ticket_data.values()
                if ticket.completion_status == ProgressStage.COMPLETED
            ]
        )
        failed_tickets = len(
            [
                ticket
                for ticket in self.ticket_data.values()
                if ticket.completion_status == ProgressStage.FAILED
            ]
        )

        # Calculate average execution time
        completion_times = [
            ticket.actual_duration
            for ticket in self.ticket_data.values()
            if (
                ticket.actual_duration is not None
                and ticket.completion_status == ProgressStage.COMPLETED
            )
        ]
        avg_execution_time = (
            statistics.mean(completion_times) if completion_times else 0.0
        )

        # Get timing analysis and model performance
        timing_analysis = self.analyze_actual_vs_estimated_times()
        model_performance = self.measure_model_performance_by_type()
        failure_patterns = self.identify_common_failure_patterns()
        recommendations = self.generate_performance_improvement_recommendations()

        # Calculate complexity trends
        complexity_trends = {}
        for effort_category in EffortCategory:
            category_tickets = [
                ticket
                for ticket in self.ticket_data.values()
                if (
                    ticket.estimated_effort == effort_category
                    and ticket.complexity_score is not None
                )
            ]
            complexity_trends[effort_category.value] = [
                ticket.complexity_score for ticket in category_tickets
            ]

        return AnalyticsMetrics(
            total_tickets=total_tickets,
            completed_tickets=completed_tickets,
            failed_tickets=failed_tickets,
            average_execution_time=avg_execution_time,
            estimation_accuracy=timing_analysis.get("average_accuracy", 0.0),
            model_performance=model_performance,
            failure_patterns=failure_patterns.get("failure_categories", {}),
            complexity_trends=complexity_trends,
            time_analysis=timing_analysis,
            recommendations=recommendations,
        )

    def export_analytics_data(self, format: str = "json") -> str:
        """Export analytics data in specified format.

        Args:
            format: Export format ('json' or 'csv')

        Returns:
            Formatted analytics data

        """
        metrics = self.get_comprehensive_metrics()

        if format == "json":
            return json.dumps(metrics.to_dict(), indent=2)
        elif format == "csv":
            lines = [
                "ticket_id,model_used,estimated_effort,estimated_time,actual_duration,"
                "completion_status,complexity_score,failure_category"
            ]

            for ticket in self.ticket_data.values():
                lines.append(
                    f"{ticket.ticket_id},"
                    f"{ticket.model_used.value if ticket.model_used else ''},"
                    f"{ticket.estimated_effort.value if ticket.estimated_effort else ''},"
                    f"{ticket.estimated_time.value if ticket.estimated_time else ''},"
                    f"{ticket.actual_duration or ''},"
                    f"{ticket.completion_status.value if ticket.completion_status else ''},"
                    f"{ticket.complexity_score or ''},"
                    f"{ticket.failure_category.value if ticket.failure_category else ''}"
                    ""
                )

            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def clear_analytics_data(self) -> None:
        """Clear all analytics data."""
        self.ticket_data.clear()
        if self.storage_path and self.storage_path.exists():
            self.storage_path.unlink()
