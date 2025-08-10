"""Distributed execution support for Hydra.

This module provides coordination and synchronization for running Hydra tasks
across multiple instances with distributed state management.
"""

from .coordinator import DistributedCoordinator, InstanceInfo, DistributedState

__all__ = ['DistributedCoordinator', 'InstanceInfo', 'DistributedState']