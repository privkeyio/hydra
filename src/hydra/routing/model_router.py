"""Model Router module."""

import json
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from hydra.providers.model_mapper import ModelCategory, get_model_mapper, map_model


class ComplexityLevel(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    CRITICAL = "critical"


@dataclass
class CostInfo:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class RoutingDecision:
    selected_model: str  # Provider-specific model identifier
    confidence: float
    complexity: ComplexityLevel
    reasoning: str
    estimated_cost: float
    manual_override: bool = False


@dataclass
class RoutingMetrics:
    total_requests: int = 0
    fast_requests: int = 0
    balanced_requests: int = 0
    smart_requests: int = 0
    total_cost: float = 0.0
    cost_savings: float = 0.0
    accuracy_score: float = 0.0
    manual_overrides: int = 0


class TaskComplexityAnalyzer:
    def __init__(self):
        self.complexity_keywords = {
            ComplexityLevel.SIMPLE: {
                "keywords": [
                    "read",
                    "list",
                    "show",
                    "display",
                    "print",
                    "format",
                    "simple",
                    "basic",
                    "quick",
                    "check",
                    "validate",
                ],
                "patterns": [
                    r"\b(get|fetch|retrieve)\s+\w+",
                    r"\b(list|show)\s+(files?|directories?)",
                    r"\bprint\s+\w+",
                ],
            },
            ComplexityLevel.MODERATE: {
                "keywords": [
                    "create",
                    "write",
                    "modify",
                    "update",
                    "refactor",
                    "implement",
                    "add",
                    "remove",
                    "fix",
                    "test",
                ],
                "patterns": [
                    r"\b(create|write|implement)\s+\w+",
                    r"\b(add|modify|update)\s+\w+",
                    r"\bfix\s+(bug|issue|error)",
                ],
            },
            ComplexityLevel.COMPLEX: {
                "keywords": [
                    "architecture",
                    "design",
                    "optimize",
                    "performance",
                    "algorithm",
                    "database",
                    "integration",
                    "system",
                    "concurrent",
                    "parallel",
                    "async",
                    "distributed",
                ],
                "patterns": [
                    r"\b(design|architect)\s+\w+",
                    r"\boptimize\s+(for|performance)",
                    r"\b(integrate|connect)\s+with",
                ],
            },
            ComplexityLevel.CRITICAL: {
                "keywords": [
                    "security",
                    "production",
                    "deployment",
                    "migration",
                    "critical",
                    "urgent",
                    "emergency",
                    "backup",
                    "recovery",
                    "scale",
                    "enterprise",
                ],
                "patterns": [
                    r"\b(security|auth|authentication)",
                    r"\b(production|deploy|release)",
                    r"\b(critical|urgent|emergency)",
                ],
            },
        }

    def _score_keywords(self, text: str, scores: Dict[ComplexityLevel, int]):
        """Score based on keyword matches."""
        for level, rules in self.complexity_keywords.items():
            for keyword in rules["keywords"]:
                if keyword in text:
                    scores[level] += 2

    def _score_patterns(self, text: str, scores: Dict[ComplexityLevel, int]):
        """Score based on pattern matches."""
        for level, rules in self.complexity_keywords.items():
            for pattern in rules["patterns"]:
                if re.search(pattern, text):
                    scores[level] += 3

    def _score_context(self, context: Dict, scores: Dict[ComplexityLevel, int]):
        """Score based on context information."""
        if not context:
            return

        if context.get("file_count", 0) > 10:
            scores[ComplexityLevel.COMPLEX] += 2
        if context.get("has_tests", False):
            scores[ComplexityLevel.MODERATE] += 1
        if context.get("involves_database", False):
            scores[ComplexityLevel.COMPLEX] += 2

    def analyze_task(
        self, task_description: str, context: Dict = None
    ) -> ComplexityLevel:
        if not task_description:
            return ComplexityLevel.SIMPLE

        text = task_description.lower()
        scores = {level: 0 for level in ComplexityLevel}

        self._score_keywords(text, scores)
        self._score_patterns(text, scores)
        self._score_context(context, scores)

        max_score = max(scores.values())
        if max_score == 0:
            return ComplexityLevel.SIMPLE

        return max(scores, key=scores.get)


class CostEstimator:
    def __init__(self):
        # Use relative costs from model mapper
        self.model_mapper = get_model_mapper()
        # Base costs per 1k tokens (relative to baseline)
        self.base_input_cost = 0.003
        self.base_output_cost = 0.015

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()) * 1.3)

    def estimate_cost(
        self, model: str, input_text: str, expected_output_tokens: int = 500
    ) -> float:
        input_tokens = self.estimate_tokens(input_text)

        # Get relative cost for model
        relative_cost = 1.0  # Default
        category = self.model_mapper.get_model_category(model)
        if category:
            # Get provider from environment
            provider = os.getenv("LLM_PROVIDER", "claude_tmux").lower()
            provider_models = self.model_mapper.provider_mappings.get(provider, {})
            mapping = provider_models.get(category)
            if mapping:
                relative_cost = mapping.relative_cost

        input_cost = (input_tokens / 1000) * self.base_input_cost * relative_cost
        output_cost = (
            (expected_output_tokens / 1000) * self.base_output_cost * relative_cost
        )

        return input_cost + output_cost


class ModelRouter:
    def __init__(self, config_path: Optional[str] = None):
        self.analyzer = TaskComplexityAnalyzer()
        self.cost_estimator = CostEstimator()
        self.metrics = RoutingMetrics()
        self.routing_history = []
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: Optional[str]) -> Dict:
        # Get provider from environment
        provider = os.getenv("LLM_PROVIDER", "claude_tmux").lower()
        mapper = get_model_mapper()

        # Map complexity to model categories and then to provider models
        default_config = {
            "routing_rules": {
                ComplexityLevel.SIMPLE.value: mapper.suggest_model_for_task(
                    "simple", provider
                ),
                ComplexityLevel.MODERATE.value: mapper.suggest_model_for_task(
                    "moderate", provider
                ),
                ComplexityLevel.COMPLEX.value: mapper.suggest_model_for_task(
                    "complex", provider
                ),
                ComplexityLevel.CRITICAL.value: mapper.suggest_model_for_task(
                    "critical", provider
                ),
            },
            "confidence_threshold": 0.7,
            "cost_optimization_enabled": True,
            "fallback_model": mapper.suggest_model_for_task("moderate", provider),
            "provider": provider,
        }

        if config_path and Path(config_path).exists():
            try:
                with open(config_path, "r") as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception:
                pass

        return default_config

    def route_task(
        self,
        task_description: str,
        context: Optional[Dict] = None,
        manual_model: Optional[str] = None,
        expected_output_tokens: int = 500,
    ) -> RoutingDecision:

        self.metrics.total_requests += 1
        mapper = get_model_mapper()

        if manual_model:
            self.metrics.manual_overrides += 1
            complexity = self.analyzer.analyze_task(task_description, context)

            # Map the manual model if needed
            selected_model = map_model(manual_model, self.config.get("provider"))
            if not selected_model:
                selected_model = manual_model  # Use as-is if mapping fails

            estimated_cost = self.cost_estimator.estimate_cost(
                selected_model, task_description, expected_output_tokens
            )

            decision = RoutingDecision(
                selected_model=selected_model,
                confidence=1.0,
                complexity=complexity,
                reasoning="Manual override",
                estimated_cost=estimated_cost,
                manual_override=True,
            )
        else:
            complexity = self.analyzer.analyze_task(task_description, context)
            selected_model = self.config["routing_rules"][complexity.value]

            confidence = self._calculate_confidence(task_description, complexity)

            if confidence < self.config["confidence_threshold"]:
                selected_model = self.config["fallback_model"]

            # Fallback to default model if still None
            if not selected_model:
                selected_model = "claude-3-5-sonnet-20241022"

            # Only estimate cost if we have a valid model
            if selected_model:
                estimated_cost = self.cost_estimator.estimate_cost(
                    selected_model, task_description, expected_output_tokens
                )
            else:
                estimated_cost = 0.0

            reasoning = f"Complexity: {complexity.value}, Confidence: {confidence:.2f}"
            if self.config["cost_optimization_enabled"]:
                reasoning += f", Estimated cost: ${estimated_cost:.4f}"

            decision = RoutingDecision(
                selected_model=selected_model,
                confidence=confidence,
                complexity=complexity,
                reasoning=reasoning,
                estimated_cost=estimated_cost,
            )

        # Update metrics based on model category
        category = mapper.get_model_category(decision.selected_model)
        if category == ModelCategory.FAST:
            self.metrics.fast_requests += 1
        elif category == ModelCategory.BALANCED:
            self.metrics.balanced_requests += 1
        elif category == ModelCategory.SMART:
            self.metrics.smart_requests += 1

        self.metrics.total_cost += decision.estimated_cost
        self.routing_history.append(decision)
        self._calculate_cost_savings()

        return decision

    def _calculate_confidence(
        self, task_description: str, complexity: ComplexityLevel
    ) -> float:
        text = task_description.lower()

        keyword_matches = 0
        total_keywords = 0

        rules = self.analyzer.complexity_keywords.get(complexity, {})
        for keyword in rules.get("keywords", []):
            total_keywords += 1
            if keyword in text:
                keyword_matches += 1

        for pattern in rules.get("patterns", []):
            total_keywords += 1
            if re.search(pattern, text):
                keyword_matches += 1

        if total_keywords == 0:
            return 0.5

        base_confidence = keyword_matches / total_keywords
        length_factor = min(1.0, len(text.split()) / 20)

        return min(1.0, base_confidence * 0.7 + length_factor * 0.3)

    def _calculate_cost_savings(self):
        if not self.routing_history:
            return

        # Calculate what it would cost to use the most expensive model for everything
        mapper = get_model_mapper()
        smart_model = mapper.suggest_model_for_task(
            "critical", self.config.get("provider")
        )

        max_cost_total = sum(
            self.cost_estimator.estimate_cost(smart_model, "dummy", 500)
            for _ in self.routing_history
        )

        actual_cost = sum(decision.estimated_cost for decision in self.routing_history)
        self.metrics.cost_savings = max(0, max_cost_total - actual_cost)

    def record_actual_cost(self, task_id: str, cost_info: CostInfo):
        pass

    def get_routing_stats(self) -> Dict:
        total = self.metrics.total_requests
        if total == 0:
            return {"no_data": True}

        return {
            "total_requests": total,
            "fast_percentage": (self.metrics.fast_requests / total) * 100,
            "balanced_percentage": (self.metrics.balanced_requests / total) * 100,
            "smart_percentage": (self.metrics.smart_requests / total) * 100,
            "estimated_total_cost": self.metrics.total_cost,
            "estimated_cost_savings": self.metrics.cost_savings,
            "manual_override_percentage": (self.metrics.manual_overrides / total) * 100,
            "average_cost_per_request": self.metrics.total_cost / total,
        }

    def update_routing_accuracy(self, task_id: str, was_correct: bool):
        pass

    def export_config(self, file_path: str):
        with open(file_path, "w") as f:
            json.dump(self.config, f, indent=2)

    def get_model_recommendations(
        self, task_descriptions: List[str]
    ) -> List[RoutingDecision]:
        return [self.route_task(desc) for desc in task_descriptions]
