"""Analytics package for measuring and improving ticket execution performance.

This package provides comprehensive analytics capabilities for ticket execution,
including performance tracking, model effectiveness analysis, and failure
pattern detection.
"""

from .execution_analytics import (
    AnalyticsMetrics,
    ExecutionAnalytics,
    ModelPerformance,
)
from .performance_report import PerformanceReport, ReportGenerator

__all__ = [
    "ExecutionAnalytics",
    "AnalyticsMetrics",
    "ModelPerformance",
    "PerformanceReport",
    "ReportGenerator",
]
