import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class ModelType(Enum):
    SONNET = "claude-sonnet-4-20250514"
    OPUS = "claude-3-opus-20240229"


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
    selected_model: ModelType
    confidence: float
    complexity: ComplexityLevel
    reasoning: str
    estimated_cost: float
    manual_override: bool = False


@dataclass
class RoutingMetrics:
    total_requests: int = 0
    sonnet_requests: int = 0
    opus_requests: int = 0
    total_cost: float = 0.0
    cost_savings: float = 0.0
    accuracy_score: float = 0.0
    manual_overrides: int = 0


class TaskComplexityAnalyzer:
    def __init__(self):
        self.complexity_keywords = {
            ComplexityLevel.SIMPLE: {
                'keywords': [
                    'read', 'list', 'show', 'display', 'print', 'format',
                    'simple', 'basic', 'quick', 'check', 'validate'
                ],
                'patterns': [
                    r'\b(get|fetch|retrieve)\s+\w+',
                    r'\b(list|show)\s+(files?|directories?)',
                    r'\bprint\s+\w+'
                ]
            },
            ComplexityLevel.MODERATE: {
                'keywords': [
                    'create', 'write', 'modify', 'update', 'refactor',
                    'implement', 'add', 'remove', 'fix', 'test'
                ],
                'patterns': [
                    r'\b(create|write|implement)\s+\w+',
                    r'\b(add|modify|update)\s+\w+',
                    r'\bfix\s+(bug|issue|error)'
                ]
            },
            ComplexityLevel.COMPLEX: {
                'keywords': [
                    'architecture', 'design', 'optimize', 'performance',
                    'algorithm', 'database', 'integration', 'system',
                    'concurrent', 'parallel', 'async', 'distributed'
                ],
                'patterns': [
                    r'\b(design|architect)\s+\w+',
                    r'\boptimize\s+(for|performance)',
                    r'\b(integrate|connect)\s+with'
                ]
            },
            ComplexityLevel.CRITICAL: {
                'keywords': [
                    'security', 'production', 'deployment', 'migration',
                    'critical', 'urgent', 'emergency', 'backup',
                    'recovery', 'scale', 'enterprise'
                ],
                'patterns': [
                    r'\b(security|auth|authentication)',
                    r'\b(production|deploy|release)',
                    r'\b(critical|urgent|emergency)'
                ]
            }
        }

    def analyze_task(
        self, task_description: str, context: Dict = None
    ) -> ComplexityLevel:
        if not task_description:
            return ComplexityLevel.SIMPLE

        text = task_description.lower()
        scores = {level: 0 for level in ComplexityLevel}

        for level, rules in self.complexity_keywords.items():
            for keyword in rules['keywords']:
                if keyword in text:
                    scores[level] += 2

            for pattern in rules['patterns']:
                if re.search(pattern, text):
                    scores[level] += 3

        if context:
            if context.get('file_count', 0) > 10:
                scores[ComplexityLevel.COMPLEX] += 2
            if context.get('has_tests', False):
                scores[ComplexityLevel.MODERATE] += 1
            if context.get('involves_database', False):
                scores[ComplexityLevel.COMPLEX] += 2

        max_score = max(scores.values())
        if max_score == 0:
            return ComplexityLevel.SIMPLE

        return max(scores, key=scores.get)


class CostEstimator:
    def __init__(self):
        self.model_costs = {
            ModelType.SONNET: {
                'input_per_1k': 0.003,
                'output_per_1k': 0.015
            },
            ModelType.OPUS: {
                'input_per_1k': 0.015,
                'output_per_1k': 0.075
            }
        }

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()) * 1.3)

    def estimate_cost(
        self, model: ModelType, input_text: str, expected_output_tokens: int = 500
    ) -> float:
        input_tokens = self.estimate_tokens(input_text)
        costs = self.model_costs[model]

        input_cost = (input_tokens / 1000) * costs['input_per_1k']
        output_cost = (expected_output_tokens / 1000) * costs['output_per_1k']

        return input_cost + output_cost


class ModelRouter:
    def __init__(self, config_path: Optional[str] = None):
        self.analyzer = TaskComplexityAnalyzer()
        self.cost_estimator = CostEstimator()
        self.metrics = RoutingMetrics()
        self.routing_history = []
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: Optional[str]) -> Dict:
        default_config = {
            'routing_rules': {
                ComplexityLevel.SIMPLE.value: ModelType.SONNET.value,
                ComplexityLevel.MODERATE.value: ModelType.SONNET.value,
                ComplexityLevel.COMPLEX.value: ModelType.OPUS.value,
                ComplexityLevel.CRITICAL.value: ModelType.OPUS.value
            },
            'confidence_threshold': 0.7,
            'cost_optimization_enabled': True,
            'fallback_model': ModelType.SONNET.value
        }

        if config_path and Path(config_path).exists():
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception:
                pass

        return default_config

    def route_task(
        self,
        task_description: str,
        context: Optional[Dict] = None,
        manual_model: Optional[ModelType] = None,
        expected_output_tokens: int = 500
    ) -> RoutingDecision:

        self.metrics.total_requests += 1

        if manual_model:
            self.metrics.manual_overrides += 1
            complexity = self.analyzer.analyze_task(task_description, context)
            estimated_cost = self.cost_estimator.estimate_cost(
                manual_model, task_description, expected_output_tokens
            )

            decision = RoutingDecision(
                selected_model=manual_model,
                confidence=1.0,
                complexity=complexity,
                reasoning="Manual override",
                estimated_cost=estimated_cost,
                manual_override=True
            )
        else:
            complexity = self.analyzer.analyze_task(task_description, context)
            selected_model_str = self.config['routing_rules'][complexity.value]
            selected_model = ModelType(selected_model_str)

            confidence = self._calculate_confidence(task_description, complexity)

            if confidence < self.config['confidence_threshold']:
                fallback_model_str = self.config['fallback_model']
                selected_model = ModelType(fallback_model_str)

            estimated_cost = self.cost_estimator.estimate_cost(
                selected_model, task_description, expected_output_tokens
            )

            reasoning = f"Complexity: {complexity.value}, Confidence: {confidence:.2f}"
            if self.config['cost_optimization_enabled']:
                reasoning += f", Estimated cost: ${estimated_cost:.4f}"

            decision = RoutingDecision(
                selected_model=selected_model,
                confidence=confidence,
                complexity=complexity,
                reasoning=reasoning,
                estimated_cost=estimated_cost
            )

        if decision.selected_model == ModelType.SONNET:
            self.metrics.sonnet_requests += 1
        else:
            self.metrics.opus_requests += 1

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
        for keyword in rules.get('keywords', []):
            total_keywords += 1
            if keyword in text:
                keyword_matches += 1

        for pattern in rules.get('patterns', []):
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

        opus_cost_total = sum(
            self.cost_estimator.estimate_cost(ModelType.OPUS, "dummy", 500)
            for _ in self.routing_history
        )

        actual_cost = sum(decision.estimated_cost for decision in self.routing_history)
        self.metrics.cost_savings = max(0, opus_cost_total - actual_cost)

    def record_actual_cost(self, task_id: str, cost_info: CostInfo):
        pass

    def get_routing_stats(self) -> Dict:
        total = self.metrics.total_requests
        if total == 0:
            return {'no_data': True}

        return {
            'total_requests': total,
            'sonnet_percentage': (self.metrics.sonnet_requests / total) * 100,
            'opus_percentage': (self.metrics.opus_requests / total) * 100,
            'estimated_total_cost': self.metrics.total_cost,
            'estimated_cost_savings': self.metrics.cost_savings,
            'manual_override_percentage': (self.metrics.manual_overrides / total) * 100,
            'average_cost_per_request': self.metrics.total_cost / total
        }

    def update_routing_accuracy(self, task_id: str, was_correct: bool):
        pass

    def export_config(self, file_path: str):
        with open(file_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def get_model_recommendations(
        self, task_descriptions: List[str]
    ) -> List[RoutingDecision]:
        return [self.route_task(desc) for desc in task_descriptions]
