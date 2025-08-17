"""Performance report generation system for analytics data visualization and export.

This module provides comprehensive report generation capabilities to create formatted
performance reports, charts, and export analytics data for external tools.
"""

import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from .execution_analytics import (
    ExecutionAnalytics,
)


@dataclass
class ReportSection:
    """Represents a section in a performance report."""

    title: str
    content: str
    charts: List[Dict[str, Any]] = None
    tables: List[Dict[str, Any]] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        """Initialize empty collections if None."""
        if self.charts is None:
            self.charts = []
        if self.tables is None:
            self.tables = []
        if self.metadata is None:
            self.metadata = {}


class PerformanceReport:
    """Comprehensive performance report with analytics data and visualizations."""

    def __init__(
        self,
        analytics: ExecutionAnalytics,
        report_title: str = "Hydra Analytics Report",
    ):
        """Initialize the performance report.

        Args:
            analytics: ExecutionAnalytics instance with data
            report_title: Title for the report

        """
        self.analytics = analytics
        self.title = report_title
        self.generated_at = datetime.now()
        self.sections: List[ReportSection] = []
        self.metrics = analytics.get_comprehensive_metrics()

    def add_section(self, section: ReportSection) -> None:
        """Add a section to the report.

        Args:
            section: ReportSection to add

        """
        self.sections.append(section)

    def generate_executive_summary(self) -> ReportSection:
        """Generate executive summary section.

        Returns:
            ReportSection with executive summary

        """
        metrics = self.metrics

        summary_stats = [
            f"Total Tickets Processed: {metrics.total_tickets}",
            f"Overall Success Rate: {metrics.overall_success_rate:.1f}%",
            f"Average Execution Time: {metrics.average_execution_time / 60:.1f} min",
            f"Estimation Accuracy: {metrics.estimation_accuracy:.1f}%",
        ]

        # Key insights
        insights = []
        if metrics.overall_success_rate >= 90:
            insights.append("✅ Excellent success rate maintained")
        elif metrics.overall_success_rate >= 75:
            insights.append("⚠️ Good success rate with room for improvement")
        else:
            insights.append("❌ Success rate needs attention")

        if metrics.estimation_accuracy >= 80:
            insights.append("✅ High estimation accuracy")
        elif metrics.estimation_accuracy >= 60:
            insights.append("⚠️ Moderate estimation accuracy")
        else:
            insights.append("❌ Estimation accuracy needs improvement")

        # Top recommendation
        top_recommendation = (
            metrics.recommendations[0]
            if metrics.recommendations
            else "No specific recommendations at this time."
        )

        content = f"""
## Key Metrics
{chr(10).join(summary_stats)}

## Key Insights
{chr(10).join(insights)}

## Priority Recommendation
{top_recommendation}

## Report Period
Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}
Data covers {metrics.total_tickets} tickets processed to date.
"""

        return ReportSection(
            title="Executive Summary",
            content=content.strip(),
            metadata={"priority": "high", "section_type": "summary"},
        )

    def generate_timing_analysis_section(self) -> ReportSection:
        """Generate timing analysis section.

        Returns:
            ReportSection with timing analysis

        """
        time_analysis = self.metrics.time_analysis

        if time_analysis.get("total_comparisons", 0) == 0:
            content = "No timing comparison data available yet."
            return ReportSection(title="Timing Analysis", content=content)

        accuracy = time_analysis["average_accuracy"]
        total_comparisons = time_analysis["total_comparisons"]
        underestimated = time_analysis["underestimated_count"]
        overestimated = time_analysis["overestimated_count"]
        accurate = time_analysis["accurate_count"]

        content = f"""
## Estimation vs Actual Performance

**Overall Accuracy**: {accuracy:.1f}%
**Total Comparisons**: {total_comparisons}

### Estimation Distribution
- **Accurate Estimates** (±20%): {accurate} ({(accurate/total_comparisons)*100:.1f}%)
- **Underestimated** (>20% over): {underestimated} \
  ({(underestimated/total_comparisons)*100:.1f}%)
- **Overestimated** (>20% under): {overestimated} \
  ({(overestimated/total_comparisons)*100:.1f}%)

### Analysis
"""

        if accuracy >= 80:
            content += "- ✅ Excellent estimation accuracy"
        elif accuracy >= 60:
            content += "- ⚠️ Good estimation accuracy with room for improvement"
        else:
            content += "- ❌ Estimation accuracy needs significant improvement"

        if underestimated > overestimated:
            content += "\n- ⚠️ Tendency to underestimate completion time"
        elif overestimated > underestimated:
            content += "\n- ℹ️ Tendency to overestimate completion time"
        else:
            content += "\n- ✅ Balanced estimation pattern"

        # Create chart data for timing distribution
        chart_data = {
            "type": "pie",
            "title": "Estimation Accuracy Distribution",
            "data": {
                "labels": ["Accurate", "Underestimated", "Overestimated"],
                "values": [accurate, underestimated, overestimated],
                "colors": ["#28a745", "#ffc107", "#dc3545"],
            },
        }

        return ReportSection(
            title="Timing Analysis",
            content=content.strip(),
            charts=[chart_data],
            metadata={"accuracy_score": accuracy},
        )

    def generate_model_performance_section(self) -> ReportSection:
        """Generate model performance analysis section.

        Returns:
            ReportSection with model performance analysis

        """
        model_performance = self.metrics.model_performance

        if not model_performance:
            return ReportSection(
                title="Model Performance",
                content="No model performance data available yet.",
            )

        content = "## Model Performance Comparison\n\n"

        # Performance table data
        table_rows = []
        chart_labels = []
        chart_success_rates = []
        chart_performance_scores = []

        for model_name, performance in model_performance.items():
            if performance.total_tickets > 0:
                table_rows.append(
                    {
                        "Model": model_name.title(),
                        "Total Tickets": performance.total_tickets,
                        "Success Rate": f"{performance.success_rate:.1f}%",
                        "Avg Time (min)": f"{performance.average_completion_time / 60:.1f}",
                        "Estimation Accuracy": f"{performance.accuracy_vs_estimates:.1f}%",
                        "Performance Score": f"{performance.performance_score:.1f}",
                    }
                )

                chart_labels.append(model_name.title())
                chart_success_rates.append(performance.success_rate)
                chart_performance_scores.append(performance.performance_score)

        # Sort by performance score
        table_rows.sort(key=lambda x: float(x["Performance Score"]), reverse=True)

        # Analysis
        if table_rows:
            best_model = table_rows[0]["Model"]
            best_score = table_rows[0]["Performance Score"]
            content += (
                f"**Best Performing Model**: {best_model} " f"(Score: {best_score})\n\n"
            )

            # Identify trends
            high_performers = [
                row for row in table_rows if float(row["Performance Score"]) >= 80
            ]
            if high_performers:
                high_models = ", ".join([row["Model"] for row in high_performers])
                content += f"**High Performers** (≥80): {high_models}\n\n"

            low_performers = [
                row for row in table_rows if float(row["Performance Score"]) < 60
            ]
            if low_performers:
                models_list = ", ".join([row["Model"] for row in low_performers])
                content += f"**Needs Improvement** (<60): {models_list}\n\n"

        # Create charts
        charts = []
        if chart_labels:
            charts.append(
                {
                    "type": "bar",
                    "title": "Model Success Rates",
                    "data": {
                        "labels": chart_labels,
                        "values": chart_success_rates,
                        "color": "#007bff",
                    },
                }
            )

            charts.append(
                {
                    "type": "bar",
                    "title": "Model Performance Scores",
                    "data": {
                        "labels": chart_labels,
                        "values": chart_performance_scores,
                        "color": "#28a745",
                    },
                }
            )

        # Create table
        table = {
            "title": "Model Performance Summary",
            "headers": [
                "Model",
                "Total Tickets",
                "Success Rate",
                "Avg Time (min)",
                "Estimation Accuracy",
                "Performance Score",
            ],
            "rows": table_rows,
        }

        return ReportSection(
            title="Model Performance",
            content=content.strip(),
            charts=charts,
            tables=[table],
            metadata={"best_model": best_model if table_rows else None},
        )

    def generate_failure_analysis_section(self) -> ReportSection:
        """Generate failure pattern analysis section.

        Returns:
            ReportSection with failure analysis

        """
        failure_patterns = self.analytics.identify_common_failure_patterns()

        if failure_patterns["total_failures"] == 0:
            return ReportSection(
                title="Failure Analysis",
                content="No failures recorded - excellent system reliability! ✅",
            )

        total_failures = failure_patterns["total_failures"]
        failure_rate = failure_patterns["failure_rate"]
        failure_categories = failure_patterns["failure_categories"]

        content = f"""
## Failure Pattern Analysis

**Total Failures**: {total_failures}
**Overall Failure Rate**: {failure_rate:.1f}%

### Failure Categories
"""

        # Add failure category breakdown
        for category, count in failure_categories.items():
            if count > 0:
                percentage = (count / total_failures) * 100
                cat_name = category.replace("_", " ").title()
                content += f"- **{cat_name}**: {count} ({percentage:.1f}%)\n"

        # Analysis and recommendations
        content += "\n### Analysis\n"

        if failure_rate <= 5:
            content += "- ✅ Low failure rate indicates good system stability"
        elif failure_rate <= 15:
            content += "- ⚠️ Moderate failure rate - monitor trends"
        else:
            content += "- ❌ High failure rate requires immediate attention"

        # Identify top failure causes
        sorted_failures = sorted(
            failure_categories.items(), key=lambda x: x[1], reverse=True
        )
        if sorted_failures and sorted_failures[0][1] > 0:
            top_cause = sorted_failures[0][0].replace("_", " ").title()
            content += f"\n- Primary failure cause: {top_cause}"

        # Create chart for failure distribution
        chart_data = {
            "type": "pie",
            "title": "Failure Category Distribution",
            "data": {
                "labels": [
                    cat.replace("_", " ").title()
                    for cat, count in failure_categories.items()
                    if count > 0
                ],
                "values": [count for count in failure_categories.values() if count > 0],
                "colors": [
                    "#dc3545",
                    "#fd7e14",
                    "#ffc107",
                    "#6f42c1",
                    "#e83e8c",
                    "#20c997",
                ],
            },
        }

        charts = [chart_data] if any(failure_categories.values()) else []

        return ReportSection(
            title="Failure Analysis",
            content=content.strip(),
            charts=charts,
            metadata={"failure_rate": failure_rate, "total_failures": total_failures},
        )

    def generate_recommendations_section(self) -> ReportSection:
        """Generate recommendations section.

        Returns:
            ReportSection with actionable recommendations

        """
        recommendations = self.metrics.recommendations

        content = "## Performance Improvement Recommendations\n\n"

        if not recommendations:
            content += (
                "No specific recommendations at this time. "
                "System performance appears optimal."
            )
            return ReportSection(title="Recommendations", content=content)

        # Prioritize recommendations
        priority_keywords = {
            "high": ["failure rate", "accuracy", "underestimated", "mismatch"],
            "medium": ["performance", "review", "improve"],
            "low": ["monitor", "continue", "consider"],
        }

        high_priority = []
        medium_priority = []
        low_priority = []

        for rec in recommendations:
            rec_lower = rec.lower()
            if any(keyword in rec_lower for keyword in priority_keywords["high"]):
                high_priority.append(rec)
            elif any(keyword in rec_lower for keyword in priority_keywords["medium"]):
                medium_priority.append(rec)
            else:
                low_priority.append(rec)

        # Add prioritized recommendations
        if high_priority:
            content += "### 🔴 High Priority\n"
            for i, rec in enumerate(high_priority, 1):
                content += f"{i}. {rec}\n"
            content += "\n"

        if medium_priority:
            content += "### 🟡 Medium Priority\n"
            for i, rec in enumerate(medium_priority, 1):
                content += f"{i}. {rec}\n"
            content += "\n"

        if low_priority:
            content += "### 🟢 Low Priority\n"
            for i, rec in enumerate(low_priority, 1):
                content += f"{i}. {rec}\n"

        return ReportSection(
            title="Recommendations",
            content=content.strip(),
            metadata={
                "total_recommendations": len(recommendations),
                "high_priority_count": len(high_priority),
            },
        )

    def generate_complexity_trends_section(self) -> ReportSection:
        """Generate complexity trends analysis section.

        Returns:
            ReportSection with complexity analysis

        """
        complexity_trends = self.metrics.complexity_trends

        if not any(complexity_trends.values()):
            return ReportSection(
                title="Complexity Trends",
                content="No complexity trend data available yet.",
            )

        content = "## Complexity Distribution Analysis\n\n"

        # Calculate statistics for each effort category
        trend_stats = {}
        chart_labels = []
        chart_averages = []

        for effort_category, scores in complexity_trends.items():
            if scores:
                avg_score = statistics.mean(scores)
                min_score = min(scores)
                max_score = max(scores)
                count = len(scores)

                trend_stats[effort_category] = {
                    "average": avg_score,
                    "min": min_score,
                    "max": max_score,
                    "count": count,
                }

                chart_labels.append(effort_category.title())
                chart_averages.append(avg_score)

                content += f"### {effort_category.title()} Effort Tickets\n"
                content += f"- Count: {count}\n"
                content += f"- Average Complexity: {avg_score:.1f}\n"
                content += f"- Range: {min_score:.1f} - {max_score:.1f}\n\n"

        # Analysis
        if trend_stats:
            content += "### Insights\n"

            # Find highest complexity category
            highest_complexity = max(trend_stats.items(), key=lambda x: x[1]["average"])
            cat_name = highest_complexity[0].title()
            avg_score = highest_complexity[1]["average"]
            content += f"- Highest average complexity: {cat_name} ({avg_score:.1f})\n"

            # Check for outliers
            for category, stats in trend_stats.items():
                if stats["max"] > stats["average"] * 2:
                    cat_name = category.title()
                    max_score = stats["max"]
                    content += (
                        f"- {cat_name} category has complexity outliers "
                        f"(max: {max_score:.1f})\n"
                    )

        # Create chart
        chart_data = {
            "type": "bar",
            "title": "Average Complexity by Effort Category",
            "data": {
                "labels": chart_labels,
                "values": chart_averages,
                "color": "#6f42c1",
            },
        }

        charts = [chart_data] if chart_labels else []

        return ReportSection(
            title="Complexity Trends",
            content=content.strip(),
            charts=charts,
            metadata={"trend_stats": trend_stats},
        )

    def generate_full_report(self) -> "PerformanceReport":
        """Generate a complete performance report with all sections.

        Returns:
            Complete PerformanceReport instance

        """
        # Clear existing sections and regenerate
        self.sections = []

        # Add all sections
        self.add_section(self.generate_executive_summary())
        self.add_section(self.generate_timing_analysis_section())
        self.add_section(self.generate_model_performance_section())
        self.add_section(self.generate_failure_analysis_section())
        self.add_section(self.generate_complexity_trends_section())
        self.add_section(self.generate_recommendations_section())

        return self

    def to_markdown(self) -> str:
        """Export report as markdown format.

        Returns:
            Markdown formatted report

        """
        lines = [
            f"# {self.title}",
            "",
            f"**Generated**: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total Tickets**: {self.metrics.total_tickets}",
            f"**Success Rate**: {self.metrics.overall_success_rate:.1f}%",
            "",
        ]

        for section in self.sections:
            lines.append(f"## {section.title}")
            lines.append("")
            lines.append(section.content)
            lines.append("")

            # Add tables if present
            if section.tables:
                for table in section.tables:
                    lines.append(f"### {table['title']}")
                    lines.append("")

                    # Create markdown table
                    headers = table["headers"]
                    lines.append("| " + " | ".join(headers) + " |")
                    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

                    for row in table["rows"]:
                        row_values = [str(row.get(header, "")) for header in headers]
                        lines.append("| " + " | ".join(row_values) + " |")
                    lines.append("")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Export report as JSON format.

        Returns:
            JSON formatted report

        """
        report_data = {
            "title": self.title,
            "generated_at": self.generated_at.isoformat(),
            "metrics": self.metrics.to_dict(),
            "sections": [
                {
                    "title": section.title,
                    "content": section.content,
                    "charts": section.charts,
                    "tables": section.tables,
                    "metadata": section.metadata,
                }
                for section in self.sections
            ],
        }

        return json.dumps(report_data, indent=2)


class ReportGenerator:
    """Factory class for generating various types of performance reports."""

    def __init__(self, analytics: ExecutionAnalytics):
        """Initialize the report generator.

        Args:
            analytics: ExecutionAnalytics instance

        """
        self.analytics = analytics

    def generate_daily_report(self, date: datetime = None) -> PerformanceReport:
        """Generate a daily performance report.

        Args:
            date: Date for the report (defaults to today)

        Returns:
            PerformanceReport for the specified date

        """
        if date is None:
            date = datetime.now()

        # Filter analytics data for the specific date
        # Note: This is a simplified implementation
        # In production, you'd want to filter the analytics data by date range

        report = PerformanceReport(
            self.analytics, f"Daily Performance Report - {date.strftime('%Y-%m-%d')}"
        )

        return report.generate_full_report()

    def generate_weekly_report(self, week_start: datetime = None) -> PerformanceReport:
        """Generate a weekly performance report.

        Args:
            week_start: Start date of the week (defaults to current week)

        Returns:
            PerformanceReport for the specified week

        """
        if week_start is None:
            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())

        week_end = week_start + timedelta(days=6)

        report = PerformanceReport(
            self.analytics,
            f"Weekly Performance Report - {week_start.strftime('%Y-%m-%d')} "
            f"to {week_end.strftime('%Y-%m-%d')}",
        )

        return report.generate_full_report()

    def generate_model_comparison_report(self) -> PerformanceReport:
        """Generate a report focused on model performance comparison.

        Returns:
            PerformanceReport with detailed model analysis

        """
        report = PerformanceReport(
            self.analytics, "Model Performance Comparison Report"
        )

        # Add only model-related sections
        report.add_section(report.generate_executive_summary())
        report.add_section(report.generate_model_performance_section())
        report.add_section(report.generate_failure_analysis_section())
        report.add_section(report.generate_recommendations_section())

        return report

    def generate_executive_dashboard_report(self) -> PerformanceReport:
        """Generate a high-level executive dashboard report.

        Returns:
            PerformanceReport with executive summary focus

        """
        report = PerformanceReport(
            self.analytics, "Executive Dashboard - Performance Overview"
        )

        # Add executive-focused sections
        report.add_section(report.generate_executive_summary())
        report.add_section(report.generate_timing_analysis_section())
        report.add_section(report.generate_recommendations_section())

        return report

    def export_to_file(
        self, report: PerformanceReport, file_path: str, format: str = "markdown"
    ) -> None:
        """Export report to file.

        Args:
            report: PerformanceReport to export
            file_path: Path to save the file
            format: Export format ('markdown' or 'json')

        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format.lower() == "markdown":
            content = report.to_markdown()
        elif format.lower() == "json":
            content = report.to_json()
        else:
            raise ValueError(f"Unsupported export format: {format}")

        with open(path, "w") as f:
            f.write(content)
