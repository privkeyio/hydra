"""Complexity estimation module for ticket effort and time prediction.

This module provides intelligent estimation capabilities to predict the effort
and time required for ticket completion based on comprehensive complexity analysis.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

from ..intelligence.model_selector import ComplexityFactors, ModelSelector


class EffortCategory(Enum):
    """Effort categories for ticket complexity classification."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class TimeEstimate(Enum):
    """Time estimate categories for ticket completion."""

    THIRTY_MIN = "30min"
    ONE_HOUR = "1hr"
    TWO_HOURS = "2hr"
    FOUR_HOURS = "4hr"
    ONE_DAY = "1day"


@dataclass
class EstimationResult:
    """Complete estimation result for a ticket."""

    effort_category: EffortCategory
    time_estimate: TimeEstimate
    confidence_score: float
    complexity_factors: ComplexityFactors
    reasoning: List[str]

    @property
    def total_complexity_score(self) -> float:
        """Get the total complexity score from factors."""
        return self.complexity_factors.total_complexity


class ComplexityEstimator:
    """Intelligent complexity and effort estimator for tickets."""

    # File type complexity weights
    FILE_COMPLEXITY_WEIGHTS = {
        r"\.py$": 1.0,           # Python files - baseline
        r"\.js$|\.ts$": 1.1,     # JavaScript/TypeScript - slightly more complex
        r"\.jsx$|\.tsx$": 1.2,   # React components - more complex
        r"\.go$": 1.0,           # Go files - baseline
        r"\.rs$": 1.3,           # Rust - more complex type system
        r"\.cpp$|\.cc$": 1.4,    # C++ - high complexity
        r"\.java$": 1.1,         # Java - moderate complexity
        r"\.sql$": 1.2,          # SQL - data complexity
        r"\.proto$": 1.5,        # Protocol buffers - high complexity
        r"\.graphql$": 1.4,      # GraphQL schemas - complex
        r"migration": 1.6,       # Database migrations - highest risk
        r"dockerfile": 1.2,      # Docker configs - moderate
        r"\.yaml$|\.yml$": 0.8,  # Config files - lower complexity
        r"\.md$": 0.3,           # Documentation - lowest complexity
        r"test.*\.": 0.7,        # Test files - lower complexity
        r"spec.*\.": 0.7,        # Spec files - lower complexity
    }

    # Effort thresholds based on complexity scores
    EFFORT_THRESHOLDS = {
        EffortCategory.LARGE: 6.0,
        EffortCategory.MEDIUM: 2.5,
        EffortCategory.SMALL: 0.0,
    }

    # Time estimation based on effort and file count
    TIME_ESTIMATION_MATRIX = {
        EffortCategory.SMALL: {
            (0, 2): TimeEstimate.THIRTY_MIN,
            (2, 5): TimeEstimate.ONE_HOUR,
            (5, float("inf")): TimeEstimate.TWO_HOURS,
        },
        EffortCategory.MEDIUM: {
            (0, 3): TimeEstimate.ONE_HOUR,
            (3, 6): TimeEstimate.TWO_HOURS,
            (6, float("inf")): TimeEstimate.FOUR_HOURS,
        },
        EffortCategory.LARGE: {
            (0, 4): TimeEstimate.TWO_HOURS,
            (4, 8): TimeEstimate.FOUR_HOURS,
            (8, float("inf")): TimeEstimate.ONE_DAY,
        },
    }

    def __init__(self):
        """Initialize the complexity estimator."""
        self.model_selector = ModelSelector()

    def estimate_ticket(self, ticket: Dict) -> EstimationResult:
        """Estimate complexity, effort, and time for a ticket.

        Args:
            ticket: Dictionary containing parsed ticket information

        Returns:
            EstimationResult with complete estimation data

        """
        # Use model selector for initial complexity analysis
        complexity_factors = self.model_selector.analyze_ticket(ticket)

        # Apply additional estimation-specific adjustments
        self._adjust_complexity_for_estimation(ticket, complexity_factors)

        # Determine effort category
        effort_category = self._determine_effort_category(complexity_factors, ticket)

        # Estimate time requirement
        time_estimate = self._estimate_time_requirement(
            effort_category, complexity_factors, ticket
        )

        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(
            complexity_factors, ticket
        )

        # Generate reasoning
        reasoning = self._generate_estimation_reasoning(
            effort_category, time_estimate, complexity_factors, ticket
        )

        return EstimationResult(
            effort_category=effort_category,
            time_estimate=time_estimate,
            confidence_score=confidence_score,
            complexity_factors=complexity_factors,
            reasoning=reasoning,
        )

    def _adjust_complexity_for_estimation(
        self, ticket: Dict, factors: ComplexityFactors
    ) -> None:
        """Apply estimation-specific adjustments to complexity factors.

        Args:
            ticket: Ticket dictionary
            factors: ComplexityFactors to modify in-place

        """
        output_files = ticket.get("output_files") or []
        acceptance_criteria = ticket.get("acceptance_criteria") or []

        # Adjust for file types and operations
        file_complexity_adjustment = self._calculate_file_type_complexity(
            output_files
        )
        factors.implementation_complexity *= file_complexity_adjustment

        # Boost complexity for tickets with many acceptance criteria
        if len(acceptance_criteria) > 10:
            factors.implementation_complexity *= 1.3
        elif len(acceptance_criteria) > 7:
            factors.implementation_complexity *= 1.2

        # Adjust for specific operation types
        operation_adjustment = self._analyze_operation_complexity(ticket)
        factors.implementation_complexity *= operation_adjustment

    def _calculate_file_type_complexity(self, files: List[str]) -> float:
        """Calculate complexity adjustment based on file types.

        Args:
            files: List of file paths

        Returns:
            Complexity multiplier

        """
        if not files:
            return 1.0

        total_weight = 0.0
        for file_path in files:
            file_lower = file_path.lower()
            for pattern, weight in self.FILE_COMPLEXITY_WEIGHTS.items():
                if re.search(pattern, file_lower):
                    total_weight += weight
                    break
            else:
                # Default weight for unrecognized file types
                total_weight += 1.0

        return total_weight / len(files)

    def _analyze_operation_complexity(self, ticket: Dict) -> float:
        """Analyze the complexity of operations described in the ticket.

        Args:
            ticket: Ticket dictionary

        Returns:
            Complexity multiplier

        """
        description = (ticket.get("description") or "").lower()
        criteria = " ".join(ticket.get("acceptance_criteria") or []).lower()
        full_text = f"{description} {criteria}"

        complexity_multiplier = 1.0

        # High complexity operations
        high_complexity_ops = [
            "migrate", "refactor", "redesign", "rewrite", "optimize",
            "performance", "scale", "distributed", "concurrent"
        ]
        for op in high_complexity_ops:
            if op in full_text:
                complexity_multiplier += 0.3

        # Medium complexity operations
        medium_complexity_ops = [
            "integrate", "connect", "api", "database", "authentication",
            "authorization", "validation", "error handling"
        ]
        for op in medium_complexity_ops:
            if op in full_text:
                complexity_multiplier += 0.2

        # Simple operations (reduce complexity)
        simple_ops = [
            "format", "style", "comment", "documentation", "readme",
            "config", "setting", "parameter"
        ]
        simple_op_count = sum(1 for op in simple_ops if op in full_text)
        if simple_op_count > 2:
            complexity_multiplier *= 0.8

        return min(complexity_multiplier, 2.0)

    def _determine_effort_category(
        self, factors: ComplexityFactors, ticket: Dict
    ) -> EffortCategory:
        """Determine effort category based on complexity analysis.

        Args:
            factors: ComplexityFactors from analysis
            ticket: Original ticket dictionary

        Returns:
            EffortCategory classification

        """
        complexity_score = factors.total_complexity

        # Primary classification based on complexity score
        for effort, threshold in self.EFFORT_THRESHOLDS.items():
            if complexity_score >= threshold:
                return effort

        # Should never reach here, but fallback to SMALL
        return EffortCategory.SMALL

    def _estimate_time_requirement(
        self, effort: EffortCategory, factors: ComplexityFactors, ticket: Dict
    ) -> TimeEstimate:
        """Estimate time requirement based on effort category and file count.

        Args:
            effort: Effort category classification
            factors: ComplexityFactors from analysis
            ticket: Original ticket dictionary

        Returns:
            TimeEstimate for completion

        """
        file_count = factors.file_count
        time_matrix = self.TIME_ESTIMATION_MATRIX[effort]

        # Find appropriate time estimate based on file count
        for (min_files, max_files), time_estimate in time_matrix.items():
            if min_files <= file_count < max_files:
                base_estimate = time_estimate
                break
        else:
            # Fallback to highest estimate for the effort category
            base_estimate = list(time_matrix.values())[-1]

        # Apply adjustments for specific complexity factors
        return self._adjust_time_estimate(base_estimate, factors, ticket)

    def _adjust_time_estimate(
        self, base_estimate: TimeEstimate, factors: ComplexityFactors, ticket: Dict
    ) -> TimeEstimate:
        """Apply adjustments to base time estimate.

        Args:
            base_estimate: Base time estimate
            factors: ComplexityFactors from analysis
            ticket: Original ticket dictionary

        Returns:
            Adjusted TimeEstimate

        """
        # Define time estimate ordering for adjustments
        time_order = [
            TimeEstimate.THIRTY_MIN,
            TimeEstimate.ONE_HOUR,
            TimeEstimate.TWO_HOURS,
            TimeEstimate.FOUR_HOURS,
            TimeEstimate.ONE_DAY,
        ]

        current_index = time_order.index(base_estimate)

        # Increase estimate for high complexity factors
        if factors.has_breaking_changes:
            current_index = min(current_index + 1, len(time_order) - 1)

        if factors.requires_analysis and factors.requires_design:
            current_index = min(current_index + 1, len(time_order) - 1)

        if factors.dependency_count > 3:
            current_index = min(current_index + 1, len(time_order) - 1)

        # Decrease estimate for simple tasks
        description = (ticket.get("description") or "").lower()
        if "documentation" in description or "readme" in description:
            current_index = max(current_index - 1, 0)

        return time_order[current_index]

    def _calculate_confidence_score(
        self, factors: ComplexityFactors, ticket: Dict
    ) -> float:
        """Calculate confidence score for the estimation.

        Args:
            factors: ComplexityFactors from analysis
            ticket: Original ticket dictionary

        Returns:
            Confidence score between 0.0 and 1.0

        """
        base_confidence = 0.7

        # Increase confidence for well-defined tickets
        acceptance_criteria = ticket.get("acceptance_criteria") or []
        if len(acceptance_criteria) >= 3:
            base_confidence += 0.1

        output_files = ticket.get("output_files") or []
        if len(output_files) > 0:
            base_confidence += 0.1

        # Decrease confidence for vague or complex scenarios
        description = (ticket.get("description") or "").lower()
        vague_indicators = ["unclear", "might", "possibly", "maybe", "tbd"]
        if any(indicator in description for indicator in vague_indicators):
            base_confidence -= 0.2

        if factors.total_complexity > 10.0:
            base_confidence -= 0.1

        # Adjust for missing information
        if not output_files:
            base_confidence -= 0.1

        if len(acceptance_criteria) < 2:
            base_confidence -= 0.1

        return max(0.1, min(1.0, base_confidence))

    def _generate_estimation_reasoning(
        self,
        effort: EffortCategory,
        time_est: TimeEstimate,
        factors: ComplexityFactors,
        ticket: Dict,
    ) -> List[str]:
        """Generate human-readable reasoning for the estimation.

        Args:
            effort: Effort category
            time_est: Time estimate
            factors: ComplexityFactors
            ticket: Original ticket

        Returns:
            List of reasoning strings

        """
        reasoning = []

        # Effort reasoning
        complexity_score = factors.total_complexity
        reasoning.append(
            f"Effort: {effort.value} (complexity score: {complexity_score:.1f})"
        )

        # File count impact
        if factors.file_count > 5:
            reasoning.append(f"High file count ({factors.file_count} files)")
        elif factors.file_count > 0:
            reasoning.append(f"Moderate scope ({factors.file_count} files)")

        # Acceptance criteria impact
        if factors.acceptance_criteria_count > 7:
            reasoning.append(
                f"Many requirements ({factors.acceptance_criteria_count} criteria)"
            )

        # Complexity factor highlights
        if factors.architectural_complexity > 1.0:
            reasoning.append("Involves architectural changes")

        if factors.algorithmic_complexity > 1.0:
            reasoning.append("Contains complex algorithms")

        if factors.has_breaking_changes:
            reasoning.append("Includes breaking changes")

        if factors.requires_analysis:
            reasoning.append("Requires analysis work")

        if factors.requires_design:
            reasoning.append("Involves design decisions")

        # Time estimate reasoning
        reasoning.append(f"Estimated time: {time_est.value}")

        return reasoning

    def batch_estimate_tickets(
        self, tickets: List[Dict]
    ) -> Dict[str, EstimationResult]:
        """Estimate complexity for multiple tickets.

        Args:
            tickets: List of ticket dictionaries

        Returns:
            Dictionary mapping ticket IDs to EstimationResult

        """
        results = {}

        for ticket in tickets:
            ticket_id = ticket.get("id", ticket.get("number", "unknown"))
            estimation = self.estimate_ticket(ticket)
            results[ticket_id] = estimation

        return results

    def get_estimation_summary(self, estimation: EstimationResult) -> str:
        """Generate a concise summary of the estimation.

        Args:
            estimation: EstimationResult to summarize

        Returns:
            Summary string

        """
        if estimation.confidence_score > 0.8:
            confidence_desc = "high"
        elif estimation.confidence_score > 0.6:
            confidence_desc = "medium"
        else:
            confidence_desc = "low"

        return (
            f"{estimation.effort_category.value.title()} effort, "
            f"{estimation.time_estimate.value} estimated, "
            f"{confidence_desc} confidence "
            f"(score: {estimation.total_complexity_score:.1f})"
        )

    def compare_estimations(
        self, estimations: List[EstimationResult]
    ) -> Dict[str, any]:
        """Compare multiple estimations and provide insights.

        Args:
            estimations: List of EstimationResult objects

        Returns:
            Dictionary containing comparison insights

        """
        if not estimations:
            return {}

        effort_counts = {effort: 0 for effort in EffortCategory}
        time_counts = {time_est: 0 for time_est in TimeEstimate}
        total_complexity = 0.0
        high_confidence_count = 0

        for est in estimations:
            effort_counts[est.effort_category] += 1
            time_counts[est.time_estimate] += 1
            total_complexity += est.total_complexity_score
            if est.confidence_score > 0.8:
                high_confidence_count += 1

        return {
            "total_tickets": len(estimations),
            "effort_distribution": {k.value: v for k, v in effort_counts.items()},
            "time_distribution": {k.value: v for k, v in time_counts.items()},
            "average_complexity": total_complexity / len(estimations),
            "high_confidence_percentage": (
                high_confidence_count / len(estimations)
            ) * 100,
            "estimated_total_time": self._calculate_total_time(estimations),
        }

    def _calculate_total_time(self, estimations: List[EstimationResult]) -> str:
        """Calculate total estimated time for all tickets.

        Args:
            estimations: List of EstimationResult objects

        Returns:
            Total time estimate string

        """
        # Convert time estimates to minutes
        time_to_minutes = {
            TimeEstimate.THIRTY_MIN: 30,
            TimeEstimate.ONE_HOUR: 60,
            TimeEstimate.TWO_HOURS: 120,
            TimeEstimate.FOUR_HOURS: 240,
            TimeEstimate.ONE_DAY: 480,  # 8 hours
        }

        total_minutes = sum(
            time_to_minutes[est.time_estimate] for est in estimations
        )

        if total_minutes < 60:
            return f"{total_minutes}min"
        elif total_minutes < 480:
            hours = total_minutes / 60
            return f"{hours:.1f}hr"
        else:
            days = total_minutes / 480
            return f"{days:.1f} days"

