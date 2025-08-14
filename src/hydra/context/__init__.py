"""Context management for Hydra ticket execution.

This package provides comprehensive context management for ticket execution,
including artifact tracking, session management, and pattern learning.
"""

from .artifact_tracker import ArtifactTracker, TicketArtifact, TicketContext
from .context_store import ContextStore, ExecutionPattern, SessionState
from .ticket_integration import TicketContextManager
from .ticket_updater import TicketUpdater

__all__ = [
    'ArtifactTracker',
    'TicketArtifact',
    'TicketContext',
    'ContextStore',
    'ExecutionPattern',
    'SessionState',
    'TicketContextManager',
    'TicketUpdater',
]
