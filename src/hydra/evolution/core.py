"""
Core evolution engine for Hydra self-improvement.

Implements genetic algorithm orchestration with population management,
generational evolution, and convergence detection.
"""

import asyncio
import json
import logging
import pickle
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from hydra.monitoring import track_metric, create_span
from hydra.safety.guardrails import ResourceQuota, RateLimiter

logger = logging.getLogger(__name__)


@dataclass
class CodeVariant:
    """Represents a code/configuration variant for evolution."""
    
    id: UUID
    parent_ids: List[UUID]
    generation: int
    code_changes: Dict[str, str]  # file_path -> new_content
    config_changes: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    fitness_score: Optional[float] = None
    test_results: Optional[Dict] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def get_change_summary(self) -> str:
        """Get human-readable summary of changes."""
        summary = []
        if self.code_changes:
            summary.append(f"{len(self.code_changes)} code files modified")
        if self.config_changes:
            summary.append(f"{len(self.config_changes)} config changes")
        return ", ".join(summary) if summary else "No changes"


@dataclass
class EvolutionConfig:
    """Configuration for evolution cycles."""
    
    # Population settings
    population_size: int = 20
    elite_count: int = 5
    tournament_size: int = 3
    
    # Evolution parameters
    max_generations: int = 10
    mutation_rate: float = 0.3
    crossover_rate: float = 0.7
    
    # Termination criteria
    fitness_threshold: float = 0.95
    convergence_window: int = 3
    convergence_threshold: float = 0.01
    
    # Performance settings
    parallel_evaluations: int = 5
    checkpoint_interval: int = 3
    enable_checkpoints: bool = True
    
    # Resource limits
    max_memory_mb: float = 1000.0
    max_duration_hours: float = 5.0
    max_api_calls: int = 1000
    
    # Safety settings
    require_supervisor: bool = True
    auto_rollback: bool = True
    dry_run: bool = False


@dataclass
class EvolutionMetrics:
    """Metrics tracking for evolution cycles."""
    
    cycle_id: UUID
    start_time: datetime
    end_time: Optional[datetime] = None
    generations_completed: int = 0
    variants_tested: int = 0
    successful_mutations: int = 0
    failed_mutations: int = 0
    best_fitness: float = 0.0
    avg_fitness: float = 0.0
    convergence_rate: float = 0.0
    resource_usage: Dict[str, float] = field(default_factory=dict)
    
    def get_duration(self) -> timedelta:
        """Get evolution duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return datetime.now() - self.start_time


@dataclass
class EvolutionResult:
    """Result of an evolution cycle."""
    
    cycle_id: UUID
    success: bool
    best_variants: List[CodeVariant]
    final_generation: int
    metrics: EvolutionMetrics
    error: Optional[str] = None
    
    def get_improvement(self) -> float:
        """Calculate fitness improvement."""
        if not self.best_variants:
            return 0.0
        return max(v.fitness_score or 0.0 for v in self.best_variants)


class HydraEvolutionEngine:
    """
    Main evolution orchestrator for Hydra self-improvement.
    
    Manages population-based optimization with genetic algorithms,
    fitness evaluation, and safe mutation application.
    """
    
    def __init__(
        self,
        config: EvolutionConfig,
        fitness_evaluator: Optional[Any] = None,
        mutator: Optional[Any] = None,
        sandbox: Optional[Any] = None,
    ):
        self.config = config
        self.fitness_evaluator = fitness_evaluator
        self.mutator = mutator
        self.sandbox = sandbox
        
        # Evolution state
        self.current_cycle_id: Optional[UUID] = None
        self.current_generation = 0
        self.population: List[CodeVariant] = []
        self.fitness_history: List[List[float]] = []
        self.metrics: Optional[EvolutionMetrics] = None
        
        # Resource management
        self.resource_quota = ResourceQuota(
            max_memory_mb=config.max_memory_mb,
            max_cpu_percent=80.0,
        )
        self.rate_limiter = RateLimiter(
            max_calls=config.max_api_calls,
            window_seconds=3600,
        )
        
        # Event handling
        self.event_handlers: Dict[str, List[Callable]] = {}
        
    async def evolve_codebase(
        self,
        target_files: List[str],
        target_metrics: Dict[str, float],
    ) -> EvolutionResult:
        """
        Run evolution cycle to improve codebase.
        
        Args:
            target_files: Files to evolve
            target_metrics: Target fitness metrics to achieve
            
        Returns:
            EvolutionResult with best variants and metrics
        """
        cycle_id = uuid4()
        self.current_cycle_id = cycle_id
        
        logger.info(f"Starting evolution cycle {cycle_id}")
        self._emit_event("evolution_started", {"cycle_id": cycle_id})
        
        # Initialize metrics
        self.metrics = EvolutionMetrics(
            cycle_id=cycle_id,
            start_time=datetime.now(),
        )
        
        try:
            # Generate initial population
            self.population = await self._generate_initial_population(target_files)
            
            # Main evolution loop
            for generation in range(self.config.max_generations):
                self.current_generation = generation
                logger.info(f"Generation {generation}/{self.config.max_generations}")
                
                # Test and evaluate population
                await self._test_population()
                fitness_scores = await self._evaluate_fitness(target_metrics)
                
                # Update metrics
                self._update_metrics(fitness_scores)
                
                # Check termination criteria
                if self._should_terminate(fitness_scores):
                    logger.info("Termination criteria met")
                    break
                
                # Create checkpoint
                if self.config.enable_checkpoints:
                    if generation % self.config.checkpoint_interval == 0:
                        await self._save_checkpoint()
                
                # Breed next generation
                self.population = await self._breed_next_generation(fitness_scores)
                
            # Finalize results
            best_variants = self._get_best_variants()
            
            self.metrics.end_time = datetime.now()
            self.metrics.generations_completed = self.current_generation + 1
            
            result = EvolutionResult(
                cycle_id=cycle_id,
                success=True,
                best_variants=best_variants,
                final_generation=self.current_generation,
                metrics=self.metrics,
            )
            
            self._emit_event("evolution_completed", {"result": result})
            return result
            
        except Exception as e:
            logger.error(f"Evolution failed: {e}")
            
            if self.metrics:
                self.metrics.end_time = datetime.now()
            
            result = EvolutionResult(
                cycle_id=cycle_id,
                success=False,
                best_variants=[],
                final_generation=self.current_generation,
                metrics=self.metrics or EvolutionMetrics(
                    cycle_id=cycle_id,
                    start_time=datetime.now(),
                ),
                error=str(e),
            )
            
            self._emit_event("evolution_failed", {"error": str(e)})
            return result
    
    async def _generate_initial_population(
        self,
        target_files: List[str],
    ) -> List[CodeVariant]:
        """Generate initial population of variants."""
        population = []
        
        # Create base variant (no mutations)
        base_variant = CodeVariant(
            id=uuid4(),
            parent_ids=[],
            generation=0,
            code_changes={},
            config_changes={},
        )
        population.append(base_variant)
        
        # Generate mutated variants
        if self.mutator:
            for i in range(self.config.population_size - 1):
                variant = await self.mutator.create_variant(
                    target_files=target_files,
                    parent=base_variant,
                    generation=0,
                )
                population.append(variant)
        else:
            # Simple random variants for testing
            for i in range(self.config.population_size - 1):
                variant = CodeVariant(
                    id=uuid4(),
                    parent_ids=[base_variant.id],
                    generation=0,
                    code_changes={},
                    config_changes={"variant": i},
                )
                population.append(variant)
        
        logger.info(f"Generated {len(population)} initial variants")
        return population
    
    async def _test_population(self) -> None:
        """Test all variants in sandbox."""
        if not self.sandbox:
            logger.warning("No sandbox configured, skipping tests")
            return
        
        semaphore = asyncio.Semaphore(self.config.parallel_evaluations)
        
        async def test_variant(variant: CodeVariant):
            async with semaphore:
                try:
                    results = await self.sandbox.test_variant(variant)
                    variant.test_results = results
                    if self.metrics:
                        self.metrics.variants_tested += 1
                except Exception as e:
                    logger.error(f"Failed to test variant {variant.id}: {e}")
                    variant.test_results = {"error": str(e)}
        
        tasks = [test_variant(v) for v in self.population]
        await asyncio.gather(*tasks)
    
    async def _evaluate_fitness(
        self,
        target_metrics: Dict[str, float],
    ) -> List[float]:
        """Evaluate fitness of population."""
        fitness_scores = []
        
        for variant in self.population:
            if self.fitness_evaluator:
                score = await self.fitness_evaluator.evaluate(
                    variant=variant,
                    target_metrics=target_metrics,
                )
            else:
                # Simple random fitness for testing
                import random
                score = random.random()
            
            variant.fitness_score = score
            fitness_scores.append(score)
        
        self.fitness_history.append(fitness_scores)
        return fitness_scores
    
    async def _breed_next_generation(
        self,
        fitness_scores: List[float],
    ) -> List[CodeVariant]:
        """Create next generation through selection and breeding."""
        next_generation = []
        
        # Sort population by fitness
        sorted_pop = sorted(
            zip(self.population, fitness_scores),
            key=lambda x: x[1],
            reverse=True,
        )
        
        # Keep elite individuals
        elite_count = min(self.config.elite_count, len(sorted_pop))
        for variant, _ in sorted_pop[:elite_count]:
            next_generation.append(variant)
        
        # Generate offspring
        while len(next_generation) < self.config.population_size:
            # Tournament selection
            parent1 = self._tournament_select(sorted_pop)
            parent2 = self._tournament_select(sorted_pop)
            
            # Crossover and mutation
            if self.mutator:
                offspring = await self.mutator.crossover(parent1, parent2)
                
                if asyncio.iscoroutine(offspring):
                    offspring = await offspring
                    
                next_generation.append(offspring)
            else:
                # Simple copy for testing
                offspring = CodeVariant(
                    id=uuid4(),
                    parent_ids=[parent1.id, parent2.id],
                    generation=self.current_generation + 1,
                    code_changes=parent1.code_changes.copy(),
                    config_changes=parent1.config_changes.copy(),
                )
                next_generation.append(offspring)
        
        return next_generation[:self.config.population_size]
    
    def _tournament_select(
        self,
        sorted_population: List[Tuple[CodeVariant, float]],
    ) -> CodeVariant:
        """Select individual via tournament selection."""
        import random
        
        tournament_size = min(self.config.tournament_size, len(sorted_population))
        tournament = random.sample(sorted_population, tournament_size)
        winner = max(tournament, key=lambda x: x[1])
        return winner[0]
    
    def _should_terminate(self, fitness_scores: List[float]) -> bool:
        """Check if evolution should terminate."""
        if not fitness_scores:
            return False
        
        # Check fitness threshold
        best_fitness = max(fitness_scores)
        if best_fitness >= self.config.fitness_threshold:
            return True
        
        # Check convergence
        if len(self.fitness_history) >= self.config.convergence_window:
            recent = self.fitness_history[-self.config.convergence_window:]
            best_scores = [max(gen) for gen in recent]
            
            if len(set(best_scores)) == 1:
                return True  # No improvement
            
            variance = statistics.variance(best_scores) if len(best_scores) > 1 else 0
            if variance < self.config.convergence_threshold:
                return True
        
        return False
    
    def _update_metrics(self, fitness_scores: List[float]) -> None:
        """Update evolution metrics."""
        if not self.metrics:
            return
        
        if fitness_scores:
            self.metrics.best_fitness = max(fitness_scores)
            self.metrics.avg_fitness = statistics.mean(fitness_scores)
        
        # Calculate convergence rate
        if len(self.fitness_history) > 1:
            prev_best = max(self.fitness_history[-2])
            curr_best = max(fitness_scores)
            self.metrics.convergence_rate = curr_best - prev_best
    
    def _get_best_variants(self, count: int = 5) -> List[CodeVariant]:
        """Get top performing variants."""
        sorted_pop = sorted(
            self.population,
            key=lambda v: v.fitness_score or 0.0,
            reverse=True,
        )
        return sorted_pop[:count]
    
    async def _save_checkpoint(self) -> None:
        """Save evolution state checkpoint."""
        if not self.current_cycle_id:
            return
        
        checkpoint_dir = Path("checkpoints") / str(self.current_cycle_id)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        checkpoint_file = checkpoint_dir / f"gen_{self.current_generation}.pkl"
        
        checkpoint_data = {
            "cycle_id": self.current_cycle_id,
            "generation": self.current_generation,
            "population": self.population,
            "fitness_history": self.fitness_history,
            "metrics": self.metrics,
            "config": self.config,
        }
        
        with open(checkpoint_file, "wb") as f:
            pickle.dump(checkpoint_data, f)
        
        logger.info(f"Saved checkpoint: {checkpoint_file}")
    
    async def resume_from_checkpoint(self, checkpoint_path: str) -> None:
        """Resume evolution from checkpoint."""
        with open(checkpoint_path, "rb") as f:
            checkpoint_data = pickle.load(f)
        
        self.current_cycle_id = checkpoint_data["cycle_id"]
        self.current_generation = checkpoint_data["generation"]
        self.population = checkpoint_data["population"]
        self.fitness_history = checkpoint_data["fitness_history"]
        self.metrics = checkpoint_data["metrics"]
        self.config = checkpoint_data["config"]
        
        logger.info(f"Resumed from checkpoint at generation {self.current_generation}")
    
    def add_event_handler(self, event: str, handler: Callable) -> None:
        """Add event handler."""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        self.event_handlers[event].append(handler)
    
    def _emit_event(self, event: str, data: Dict[str, Any]) -> None:
        """Emit event to handlers."""
        if event in self.event_handlers:
            for handler in self.event_handlers[event]:
                try:
                    handler(data)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")