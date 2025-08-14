"""Model selector with intelligent complexity analysis for optimal model assignment.

This module provides sophisticated heuristics to analyze task complexity
and recommend the most appropriate model for ticket execution.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class ModelCategory(Enum):
    """Available model categories for ticket execution."""

    SMART = "smart"  # Opus 4 - Complex reasoning and architecture
    CODER = "coder"  # Opus 4 - Complex implementation and refactoring
    BALANCED = "balanced"  # Sonnet 4 - Standard features and tests
    FAST = "fast"  # Haiku - Simple tasks and documentation


@dataclass
class ComplexityFactors:
    """Factors contributing to task complexity assessment."""

    architectural_complexity: float = 0.0
    implementation_complexity: float = 0.0
    algorithmic_complexity: float = 0.0
    integration_complexity: float = 0.0
    testing_complexity: float = 0.0
    file_count: int = 0
    acceptance_criteria_count: int = 0
    dependency_count: int = 0
    has_breaking_changes: bool = False
    requires_analysis: bool = False
    requires_design: bool = False

    @property
    def total_complexity(self) -> float:
        """Calculate weighted total complexity score."""
        base_score = (
            self.architectural_complexity * 2.0 +
            self.implementation_complexity * 1.5 +
            self.algorithmic_complexity * 2.5 +
            self.integration_complexity * 1.5 +
            self.testing_complexity * 1.0
        )

        # Adjust for scale factors
        if self.file_count > 5:
            base_score *= 1.2
        if self.acceptance_criteria_count > 7:
            base_score *= 1.3
        if self.dependency_count > 3:
            base_score *= 1.1
        if self.has_breaking_changes:
            base_score *= 1.4
        if self.requires_analysis:
            base_score *= 1.2
        if self.requires_design:
            base_score *= 1.3

        return base_score


class ModelSelector:
    """Intelligent model selection based on task complexity analysis."""

    # Keywords indicating architectural complexity
    ARCHITECTURE_KEYWORDS = {
        "architecture", "design", "system", "framework", "infrastructure",
        "microservice", "distributed", "scalable", "pattern", "abstraction",
        "interface", "api", "protocol", "schema", "database", "migration"
    }

    # Keywords indicating complex algorithms
    ALGORITHM_KEYWORDS = {
        "algorithm", "optimization", "graph", "tree", "recursive", "dynamic",
        "parallel", "concurrent", "async", "thread", "performance", "cache",
        "index", "search", "sort", "hash", "encryption", "compression"
    }

    # Keywords indicating heavy implementation work
    IMPLEMENTATION_KEYWORDS = {
        "implement", "build", "create", "develop", "construct", "establish",
        "refactor", "rewrite", "restructure", "reorganize", "migrate",
        "port", "convert", "transform", "integrate", "connect"
    }

    # Keywords indicating integration complexity
    INTEGRATION_KEYWORDS = {
        "integrate", "connect", "api", "webhook", "service", "endpoint",
        "external", "third-party", "authentication", "authorization",
        "middleware", "adapter", "bridge", "gateway", "proxy"
    }

    # Keywords indicating testing complexity
    TESTING_KEYWORDS = {
        "test", "validate", "verify", "benchmark", "performance", "load",
        "integration test", "end-to-end", "e2e", "coverage", "mock",
        "stub", "fixture", "assertion", "regression"
    }

    # Keywords suggesting analysis requirements
    ANALYSIS_KEYWORDS = {
        "analyze", "investigate", "research", "explore", "evaluate",
        "assess", "review", "audit", "profile", "debug", "diagnose",
        "troubleshoot", "identify", "discover", "understand"
    }

    # File patterns suggesting complexity
    COMPLEX_FILE_PATTERNS = {
        r"\.proto$": 1.5,  # Protocol buffers
        r"\.graphql$": 1.4,  # GraphQL schemas
        r"migration": 1.6,  # Database migrations
        r"\.sql$": 1.3,  # SQL files
        r"webpack\.": 1.3,  # Webpack configs
        r"dockerfile": 1.2,  # Docker configurations
        r"\.yaml$|\.yml$": 1.1,  # Configuration files
        r"test.*\.": 0.8,  # Test files (generally simpler)
        r"\.md$": 0.5,  # Documentation (simplest)
    }

    def __init__(self):
        """Initialize the model selector."""
        self.complexity_thresholds = {
            ModelCategory.SMART: 8.0,
            ModelCategory.CODER: 5.0,
            ModelCategory.BALANCED: 2.0,
            ModelCategory.FAST: 0.0
        }

    def analyze_ticket(self, ticket: Dict) -> ComplexityFactors:
        """Analyze a ticket to determine its complexity factors.

        Args:
            ticket: Dictionary containing parsed ticket information

        Returns:
            ComplexityFactors with calculated scores

        """
        factors = ComplexityFactors()

        # Extract ticket components with None handling
        description = (ticket.get("description") or "").lower()
        title = (ticket.get("title") or "").lower()
        criteria = ticket.get("acceptance_criteria") or []
        output_files = ticket.get("output_files") or []
        input_files = ticket.get("input_files") or []
        dependencies = ticket.get("dependencies") or []

        # Combine text for analysis
        full_text = f"{title} {description} {' '.join(criteria)}".lower()

        # Analyze architectural complexity
        factors.architectural_complexity = self._calculate_keyword_score(
            full_text, self.ARCHITECTURE_KEYWORDS
        )

        # Analyze algorithmic complexity
        factors.algorithmic_complexity = self._calculate_keyword_score(
            full_text, self.ALGORITHM_KEYWORDS
        )

        # Analyze implementation complexity
        factors.implementation_complexity = self._calculate_keyword_score(
            full_text, self.IMPLEMENTATION_KEYWORDS
        )

        # Analyze integration complexity
        factors.integration_complexity = self._calculate_keyword_score(
            full_text, self.INTEGRATION_KEYWORDS
        )

        # Analyze testing complexity
        factors.testing_complexity = self._calculate_keyword_score(
            full_text, self.TESTING_KEYWORDS
        )

        # Check for analysis requirements
        factors.requires_analysis = self._contains_keywords(
            full_text, self.ANALYSIS_KEYWORDS
        )

        # Check for design requirements
        factors.requires_design = any(
            keyword in full_text for keyword in [
                "design", "architect", "plan", "structure", "model"
            ]
        )

        # Count files and criteria
        factors.file_count = len(output_files)
        factors.acceptance_criteria_count = len(criteria)
        factors.dependency_count = len(dependencies) if dependencies != ["None"] else 0

        # Check for breaking changes
        factors.has_breaking_changes = self._detect_breaking_changes(
            full_text, output_files
        )

        # Adjust for file complexity
        file_complexity_multiplier = self._calculate_file_complexity(
            output_files + input_files
        )

        # Apply file complexity to relevant factors
        factors.implementation_complexity *= file_complexity_multiplier

        return factors

    def _calculate_keyword_score(self, text: str, keywords: Set[str]) -> float:
        """Calculate complexity score based on keyword presence.

        Args:
            text: Text to analyze
            keywords: Set of keywords to search for

        Returns:
            Complexity score (0.0 to 1.0+)

        """
        score = 0.0

        for keyword in keywords:
            if keyword in text:
                # Base score for presence
                score += 0.3

                # Additional score for frequency
                count = text.count(keyword)
                score += min(count * 0.1, 0.5)

        # Normalize to reasonable range
        return min(score / len(keywords) * 5, 2.0)

    def _contains_keywords(self, text: str, keywords: Set[str]) -> bool:
        """Check if text contains any of the keywords."""
        return any(keyword in text for keyword in keywords)

    def _detect_breaking_changes(self, text: str, output_files: List[str]) -> bool:
        """Detect if the ticket involves breaking changes.

        Args:
            text: Combined ticket text
            output_files: List of output files

        Returns:
            True if breaking changes are likely

        """
        breaking_indicators = [
            "breaking change", "migration", "deprecate", "remove",
            "refactor", "restructure", "incompatible", "major version"
        ]

        # Check text for indicators
        if any(indicator in text for indicator in breaking_indicators):
            return True

        # Check for migration files
        if any("migration" in file.lower() for file in output_files):
            return True

        return False

    def _calculate_file_complexity(self, files: List[str]) -> float:
        """Calculate complexity multiplier based on file types.

        Args:
            files: List of file paths

        Returns:
            Complexity multiplier (>= 1.0)

        """
        if not files:
            return 1.0

        total_multiplier = 0.0
        for file in files:
            file_lower = file.lower()
            for pattern, multiplier in self.COMPLEX_FILE_PATTERNS.items():
                if re.search(pattern, file_lower):
                    total_multiplier += multiplier
                    break
            else:
                # Default multiplier for unmatched files
                total_multiplier += 1.0

        return max(total_multiplier / len(files), 1.0)

    def select_model(self, ticket: Dict) -> Tuple[ModelCategory, ComplexityFactors]:
        """Select the optimal model for a ticket based on complexity analysis.

        Args:
            ticket: Dictionary containing parsed ticket information

        Returns:
            Tuple of (recommended model category, complexity factors)

        """
        factors = self.analyze_ticket(ticket)
        complexity_score = factors.total_complexity

        # Determine model based on complexity thresholds
        if complexity_score >= self.complexity_thresholds[ModelCategory.SMART]:
            return ModelCategory.SMART, factors
        elif complexity_score >= self.complexity_thresholds[ModelCategory.CODER]:
            # Distinguish between CODER and SMART based on specific factors
            if factors.architectural_complexity > 1.5 or factors.requires_design:
                return ModelCategory.SMART, factors
            else:
                return ModelCategory.CODER, factors
        elif complexity_score >= self.complexity_thresholds[ModelCategory.BALANCED]:
            return ModelCategory.BALANCED, factors
        else:
            return ModelCategory.FAST, factors

    def get_recommendation_reason(self,
                                   model: ModelCategory,
                                   factors: ComplexityFactors) -> str:
        """Generate human-readable explanation for model selection.

        Args:
            model: Selected model category
            factors: Complexity factors used in decision

        Returns:
            Explanation string

        """
        reasons = self._get_model_specific_reasons(model, factors)
        complexity_level = self._get_complexity_level(factors.total_complexity)
        reasons.append(
            f"Overall complexity: {complexity_level} ({factors.total_complexity:.1f})"
        )
        return " | ".join(reasons)

    def _get_model_specific_reasons(self,
                                     model: ModelCategory,
                                     factors: ComplexityFactors) -> List[str]:
        """Get model-specific reason list."""
        if model == ModelCategory.SMART:
            return self._get_smart_reasons(factors)
        elif model == ModelCategory.CODER:
            return self._get_coder_reasons(factors)
        elif model == ModelCategory.BALANCED:
            return self._get_balanced_reasons(factors)
        else:  # FAST
            return self._get_fast_reasons(factors)

    def _get_smart_reasons(self, factors: ComplexityFactors) -> List[str]:
        """Get reasons for SMART model selection."""
        reasons = ["Complex architectural or design work required"]
        if factors.algorithmic_complexity > 1.0:
            reasons.append("Contains complex algorithms")
        if factors.requires_analysis:
            reasons.append("Requires deep analysis")
        if factors.requires_design:
            reasons.append("Involves system design")
        return reasons

    def _get_coder_reasons(self, factors: ComplexityFactors) -> List[str]:
        """Get reasons for CODER model selection."""
        reasons = ["Substantial implementation work"]
        if factors.file_count > 3:
            reasons.append(f"Involves {factors.file_count} files")
        if factors.has_breaking_changes:
            reasons.append("Contains breaking changes")
        if factors.integration_complexity > 1.0:
            reasons.append("Complex integrations required")
        return reasons

    def _get_balanced_reasons(self, factors: ComplexityFactors) -> List[str]:
        """Get reasons for BALANCED model selection."""
        reasons = ["Standard feature implementation"]
        if factors.testing_complexity > 0.5:
            reasons.append("Includes testing requirements")
        if factors.acceptance_criteria_count > 3:
            reasons.append(
                f"Has {factors.acceptance_criteria_count} acceptance criteria"
            )
        return reasons

    def _get_fast_reasons(self, factors: ComplexityFactors) -> List[str]:
        """Get reasons for FAST model selection."""
        reasons = ["Simple or routine task"]
        if factors.file_count <= 1:
            reasons.append("Minimal file changes")
        if "documentation" in str(factors):
            reasons.append("Documentation focused")
        return reasons

    def _get_complexity_level(self, score: float) -> str:
        """Convert complexity score to human-readable level."""
        if score >= 10:
            return "Very High"
        elif score >= 7:
            return "High"
        elif score >= 4:
            return "Medium"
        elif score >= 2:
            return "Low"
        else:
            return "Very Low"

    def batch_select_models(
        self, tickets: List[Dict]
    ) -> Dict[str, Tuple[ModelCategory, str]]:
        """Select models for multiple tickets with optimization.

        Args:
            tickets: List of ticket dictionaries

        Returns:
            Dictionary mapping ticket IDs to (model, reason) tuples

        """
        results = {}

        for ticket in tickets:
            ticket_id = ticket.get("id", ticket.get("number", "unknown"))
            model, factors = self.select_model(ticket)
            reason = self.get_recommendation_reason(model, factors)
            results[ticket_id] = (model, reason)

        return results

    def validate_model_selection(self,
                                  ticket: Dict,
                                  selected_model: str) -> Tuple[bool, Optional[str]]:
        """Validate if a manually selected model is appropriate.

        Args:
            ticket: Ticket dictionary
            selected_model: Manually selected model category

        Returns:
            Tuple of (is_valid, warning_message)

        """
        recommended_model, factors = self.select_model(ticket)

        try:
            selected_category = ModelCategory(selected_model.lower())
        except ValueError:
            return False, f"Invalid model category: {selected_model}"

        # Check if selection is reasonable
        if selected_category == recommended_model:
            return True, None

        # Check for significant mismatches
        complexity = factors.total_complexity

        if selected_category == ModelCategory.FAST and complexity > 5.0:
            return (
                False,
                f"Task too complex for FAST model (complexity: {complexity:.1f})"
            )

        if selected_category == ModelCategory.BALANCED and complexity > 10.0:
            return (
                False,
                f"Task too complex for BALANCED model (complexity: {complexity:.1f})"
            )

        # Warn about potential inefficiencies
        if selected_category == ModelCategory.SMART and complexity < 3.0:
            return True, "Task may be too simple for SMART model (consider BALANCED)"

        if selected_category == ModelCategory.CODER and complexity < 2.0:
            return True, "Task may be too simple for CODER model (consider FAST)"

        return True, None


def create_enhanced_model_prompt() -> str:
    """Generate enhanced prompt text for ticket creation with model selection guidance.

    Returns:
        Enhanced prompt string for model selection

    """
    return """
Model Selection Guidelines (Enhanced):

Choose the model based on task complexity analysis:

**smart** (Opus 4) - Use for:
- Complex architectural design and system planning
- Tasks requiring deep analysis and reasoning
- Algorithm design and optimization
- Critical business logic implementation
- Tasks with multiple integration points
- Breaking changes and migrations
- Complexity indicators: architecture, design patterns, algorithms, analysis

**coder** (Opus 4) - Use for:
- Large-scale implementation work
- Complex refactoring tasks
- Multi-file changes (>3 files)
- Tasks with many acceptance criteria (>5)
- Performance-critical code
- Complex data transformations
- Complexity indicators: heavy implementation, refactoring, multiple files

**balanced** (Sonnet 4) - Use for:
- Standard feature implementation
- Test writing and validation
- Documentation with code examples
- Moderate complexity tasks
- Single service modifications
- Configuration changes
- Complexity indicators: standard features, testing, moderate scope

**fast** (Haiku) - Use for:
- Simple file updates
- Basic documentation
- Configuration tweaks
- Formatting and style fixes
- Simple utility functions
- Tasks with 1-2 acceptance criteria
- Complexity indicators: minimal changes, documentation, simple scope

Consider these factors when selecting:
1. Number of files affected
2. Architectural impact
3. Integration requirements
4. Testing complexity
5. Breaking change potential
6. Analysis requirements
"""
