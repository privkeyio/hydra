"""Hydra: Self-Replicating Coding Agent System.

A hierarchical AI agent system for autonomous code generation and task delegation.
"""

__version__ = "1.0.0"
__author__ = "Hydra Team"

from hydra.agents.base import CodeAgent


# Import execute_workflow lazily to avoid dependency issues
def execute_workflow(*args, **kwargs):
    from hydra.workflows.engine import execute_workflow as _execute_workflow
    return _execute_workflow(*args, **kwargs)

__all__ = ["CodeAgent", "execute_workflow"]
