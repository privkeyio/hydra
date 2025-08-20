"""Learning module for Hydra - intelligent failure analysis and improvement."""

from .failure_analyzer import (
    FailureAnalyzer,
    FailureCategory,
    FailureContext,
    FailurePattern,
    FailureSolution,
    analyze_failure,
    get_retry_feedback,
)

__all__ = [
    "FailureAnalyzer",
    "FailureCategory",
    "FailureContext",
    "FailurePattern",
    "FailureSolution",
    "analyze_failure",
    "get_retry_feedback",
]
