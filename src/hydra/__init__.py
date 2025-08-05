"""
Hydra: Self-Replicating Coding Agent System

A hierarchical AI agent system for autonomous code generation and task delegation.
"""

__version__ = "1.0.0"
__author__ = "Hydra Team"

from hydra.agents.base import CodeAgent
from hydra.workflows.engine import execute_workflow

__all__ = ["CodeAgent", "execute_workflow"]