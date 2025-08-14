"""
Hydra Evolution System - Self-improvement through evolutionary algorithms.

This module implements autonomous code evolution capabilities inspired by goose-evolve,
enabling Hydra to continuously improve its own codebase through genetic algorithms,
fitness evaluation, and safe mutation strategies.
"""

from hydra.evolution.core import (
    HydraEvolutionEngine,
    CodeVariant,
    EvolutionConfig,
    EvolutionResult,
)
from hydra.evolution.fitness import (
    HydraFitnessEvaluator,
    FitnessObjective,
    FitnessResult,
)
from hydra.evolution.mutations import (
    CodeMutator,
    MutationStrategy,
    MutationType,
)
from hydra.evolution.sandbox import (
    EvolutionSandbox,
    SandboxConfig,
    TestResult,
)
from hydra.evolution.supervisor import (
    EvolutionSupervisor,
    ValidationResult,
    SupervisorConfig,
)

__all__ = [
    # Core
    "HydraEvolutionEngine",
    "CodeVariant",
    "EvolutionConfig",
    "EvolutionResult",
    # Fitness
    "HydraFitnessEvaluator",
    "FitnessObjective",
    "FitnessResult",
    # Mutations
    "CodeMutator",
    "MutationStrategy",
    "MutationType",
    # Sandbox
    "EvolutionSandbox",
    "SandboxConfig",
    "TestResult",
    # Supervisor
    "EvolutionSupervisor",
    "ValidationResult",
    "SupervisorConfig",
]

__version__ = "0.1.0"