"""
Fitness evaluation for code evolution.

Implements multi-objective fitness functions for evaluating
code quality, performance, and other metrics.
"""

import asyncio
import subprocess
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hydra.evolution.core import CodeVariant
from hydra.monitoring import track_metric

import logging

logger = logging.getLogger(__name__)


@dataclass
class FitnessObjective:
    """Configuration for a fitness objective."""
    
    name: str
    weight: float = 1.0
    target_value: Optional[float] = None
    minimize: bool = False
    
    def normalize_score(self, score: float) -> float:
        """Normalize score to [0, 1] range."""
        if self.target_value is not None:
            if self.minimize:
                # Lower is better
                if score <= self.target_value:
                    return 1.0
                return max(0.0, 1.0 - (score - self.target_value) / self.target_value)
            else:
                # Higher is better
                if score >= self.target_value:
                    return 1.0
                return max(0.0, score / self.target_value)
        return max(0.0, min(1.0, score))


@dataclass
class FitnessResult:
    """Result of fitness evaluation."""
    
    overall_score: float
    objective_scores: Dict[str, float]
    normalized_scores: Dict[str, float]
    metadata: Dict[str, Any]


class HydraFitnessEvaluator:
    """
    Evaluates code quality across multiple objectives.
    
    Implements weighted multi-objective fitness evaluation
    for code evolution.
    """
    
    def __init__(self):
        self.objectives = self._initialize_objectives()
        self._baseline_metrics: Dict[str, float] = {}
        
    def _initialize_objectives(self) -> Dict[str, FitnessObjective]:
        """Initialize default fitness objectives."""
        return {
            "test_coverage": FitnessObjective(
                name="Test Coverage",
                weight=0.3,
                target_value=0.9,
                minimize=False,
            ),
            "performance": FitnessObjective(
                name="Performance",
                weight=0.3,
                target_value=1.0,
                minimize=True,
            ),
            "code_quality": FitnessObjective(
                name="Code Quality",
                weight=0.2,
                target_value=8.0,
                minimize=False,
            ),
            "documentation": FitnessObjective(
                name="Documentation",
                weight=0.1,
                target_value=0.8,
                minimize=False,
            ),
            "security": FitnessObjective(
                name="Security",
                weight=0.1,
                target_value=0.0,
                minimize=True,
            ),
        }
    
    async def evaluate(
        self,
        variant: CodeVariant,
        target_metrics: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Evaluate fitness of a code variant.
        
        Args:
            variant: Code variant to evaluate
            target_metrics: Optional target metrics to achieve
            
        Returns:
            Overall fitness score between 0 and 1
        """
        objective_scores = {}
        normalized_scores = {}
        metadata = {}
        
        # Evaluate each objective
        for name, objective in self.objectives.items():
            try:
                # Get raw score
                score = await self._evaluate_objective(name, variant)
                objective_scores[name] = score
                
                # Override target if specified
                if target_metrics and name in target_metrics:
                    objective.target_value = target_metrics[name]
                
                # Normalize score
                normalized = objective.normalize_score(score)
                normalized_scores[name] = normalized
                
                logger.debug(
                    f"Objective {name}: raw={score:.3f}, normalized={normalized:.3f}"
                )
                
            except Exception as e:
                logger.warning(f"Failed to evaluate {name}: {e}")
                objective_scores[name] = 0.0
                normalized_scores[name] = 0.0
        
        # Calculate weighted overall score
        total_score = 0.0
        total_weight = 0.0
        
        for name, objective in self.objectives.items():
            if name in normalized_scores:
                total_score += normalized_scores[name] * objective.weight
                total_weight += objective.weight
        
        overall_score = total_score / total_weight if total_weight > 0 else 0.0
        
        # Track metrics
        track_metric("evolution.fitness.overall", overall_score)
        for name, score in objective_scores.items():
            track_metric(f"evolution.fitness.{name}", score)
        
        # Store result in variant
        variant.fitness_score = overall_score
        
        return overall_score
    
    async def _evaluate_objective(
        self,
        objective_name: str,
        variant: CodeVariant,
    ) -> float:
        """Evaluate a specific fitness objective."""
        if objective_name == "test_coverage":
            return await self._evaluate_test_coverage(variant)
        elif objective_name == "performance":
            return await self._evaluate_performance(variant)
        elif objective_name == "code_quality":
            return await self._evaluate_code_quality(variant)
        elif objective_name == "documentation":
            return await self._evaluate_documentation(variant)
        elif objective_name == "security":
            return await self._evaluate_security(variant)
        else:
            return 0.0
    
    async def _evaluate_test_coverage(self, variant: CodeVariant) -> float:
        """
        Evaluate test coverage of variant.
        
        Returns coverage percentage (0-1).
        """
        if not variant.test_results:
            return 0.0
        
        # Extract coverage from test results
        coverage = variant.test_results.get("coverage", 0.0)
        
        # If no coverage data, try to calculate
        if coverage == 0.0 and variant.code_changes:
            try:
                # Run coverage analysis
                result = subprocess.run(
                    ["pytest", "--cov", "--cov-report=json", "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                
                if result.returncode == 0:
                    # Parse coverage report
                    import json
                    coverage_file = Path(".coverage.json")
                    if coverage_file.exists():
                        with open(coverage_file) as f:
                            data = json.load(f)
                            coverage = data.get("totals", {}).get("percent_covered", 0) / 100
                
            except Exception as e:
                logger.warning(f"Coverage evaluation failed: {e}")
        
        return coverage
    
    async def _evaluate_performance(self, variant: CodeVariant) -> float:
        """
        Evaluate performance of variant.
        
        Returns relative performance score (lower is better).
        """
        if not variant.test_results:
            return 1.0
        
        # Extract performance metrics
        perf_data = variant.test_results.get("performance", {})
        
        # Calculate composite performance score
        scores = []
        
        # Response time (normalized)
        if "response_time" in perf_data:
            baseline = self._baseline_metrics.get("response_time", 1.0)
            score = perf_data["response_time"] / baseline
            scores.append(score)
        
        # Memory usage (normalized)
        if "memory_usage" in perf_data:
            baseline = self._baseline_metrics.get("memory_usage", 100.0)
            score = perf_data["memory_usage"] / baseline
            scores.append(score)
        
        # CPU usage (normalized)
        if "cpu_usage" in perf_data:
            baseline = self._baseline_metrics.get("cpu_usage", 50.0)
            score = perf_data["cpu_usage"] / baseline
            scores.append(score)
        
        return statistics.mean(scores) if scores else 1.0
    
    async def _evaluate_code_quality(self, variant: CodeVariant) -> float:
        """
        Evaluate code quality of variant.
        
        Returns quality score (0-10).
        """
        if not variant.code_changes:
            return 5.0  # Neutral score for no changes
        
        quality_scores = []
        
        for file_path, code in variant.code_changes.items():
            try:
                # Run static analysis
                # Complexity analysis
                complexity = await self._analyze_complexity(code)
                quality_scores.append(10 - min(complexity, 10))
                
                # Linting score
                lint_score = await self._run_linter(file_path, code)
                quality_scores.append(lint_score)
                
            except Exception as e:
                logger.warning(f"Quality analysis failed for {file_path}: {e}")
                quality_scores.append(5.0)
        
        return statistics.mean(quality_scores) if quality_scores else 5.0
    
    async def _evaluate_documentation(self, variant: CodeVariant) -> float:
        """
        Evaluate documentation quality of variant.
        
        Returns documentation score (0-1).
        """
        if not variant.code_changes:
            return 0.5
        
        doc_scores = []
        
        for code in variant.code_changes.values():
            # Count docstrings
            import ast
            try:
                tree = ast.parse(code)
                
                total_items = 0
                documented_items = 0
                
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        total_items += 1
                        if ast.get_docstring(node):
                            documented_items += 1
                
                if total_items > 0:
                    doc_scores.append(documented_items / total_items)
                    
            except Exception:
                doc_scores.append(0.0)
        
        return statistics.mean(doc_scores) if doc_scores else 0.0
    
    async def _evaluate_security(self, variant: CodeVariant) -> float:
        """
        Evaluate security of variant.
        
        Returns security issue count (lower is better).
        """
        if not variant.code_changes:
            return 0.0
        
        issue_count = 0
        
        # Check for common security issues
        security_patterns = [
            (r"eval\s*\(", "eval() usage"),
            (r"exec\s*\(", "exec() usage"),
            (r"pickle\.loads", "pickle.loads() usage"),
            (r"subprocess.*shell=True", "shell=True in subprocess"),
            (r"os\.system", "os.system() usage"),
        ]
        
        import re
        for code in variant.code_changes.values():
            for pattern, issue_name in security_patterns:
                if re.search(pattern, code):
                    issue_count += 1
                    logger.warning(f"Security issue found: {issue_name}")
        
        return issue_count
    
    async def _analyze_complexity(self, code: str) -> float:
        """Analyze cyclomatic complexity of code."""
        try:
            import ast
            tree = ast.parse(code)
            
            # Simple complexity calculation
            complexity = 1  # Base complexity
            
            for node in ast.walk(tree):
                # Each branch adds complexity
                if isinstance(node, (ast.If, ast.While, ast.For)):
                    complexity += 1
                elif isinstance(node, ast.ExceptHandler):
                    complexity += 1
                elif isinstance(node, ast.BoolOp):
                    complexity += len(node.values) - 1
            
            return complexity
            
        except Exception:
            return 10.0  # High complexity on parse error
    
    async def _run_linter(self, file_path: str, code: str) -> float:
        """Run linter and return score."""
        try:
            # Save temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            # Run pylint or flake8
            result = subprocess.run(
                ["flake8", "--count", "--exit-zero", temp_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            # Count issues
            issue_count = len(result.stdout.strip().split("\n")) if result.stdout else 0
            
            # Convert to score (fewer issues = higher score)
            score = max(0, 10 - issue_count)
            
            # Cleanup
            Path(temp_path).unlink()
            
            return score
            
        except Exception:
            return 5.0  # Neutral score on error
    
    def set_baseline_metrics(self, metrics: Dict[str, float]) -> None:
        """Set baseline metrics for relative scoring."""
        self._baseline_metrics = metrics.copy()
        logger.info(f"Set baseline metrics: {metrics}")
    
    def calculate_pareto_frontier(
        self,
        population: List[CodeVariant],
    ) -> List[CodeVariant]:
        """
        Calculate Pareto frontier for multi-objective optimization.
        
        Returns list of non-dominated solutions.
        """
        if not population:
            return []
        
        pareto_front = []
        
        for i, variant1 in enumerate(population):
            is_dominated = False
            
            for j, variant2 in enumerate(population):
                if i == j:
                    continue
                
                # Check if variant1 is dominated by variant2
                if self._dominates(variant2, variant1):
                    is_dominated = True
                    break
            
            if not is_dominated:
                pareto_front.append(variant1)
        
        logger.info(f"Pareto frontier: {len(pareto_front)} non-dominated solutions")
        return pareto_front
    
    def _dominates(self, v1: CodeVariant, v2: CodeVariant) -> bool:
        """Check if v1 dominates v2 in objective space."""
        if not v1.test_results or not v2.test_results:
            return False
        
        # For each objective, v1 must be at least as good as v2
        # and strictly better in at least one
        at_least_as_good = True
        strictly_better = False
        
        for name, objective in self.objectives.items():
            score1 = v1.test_results.get(name, 0.0)
            score2 = v2.test_results.get(name, 0.0)
            
            if objective.minimize:
                if score1 > score2:
                    at_least_as_good = False
                    break
                if score1 < score2:
                    strictly_better = True
            else:
                if score1 < score2:
                    at_least_as_good = False
                    break
                if score1 > score2:
                    strictly_better = True
        
        return at_least_as_good and strictly_better