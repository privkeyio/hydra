"""Database package for Hydra ticket management."""

from hydra.database.ticket_compatibility import (
    add_ticket_artifact_compat,
    build_dependency_graph_compat,
    mark_ticket_completed_compat,
    mark_ticket_in_progress_compat,
    mark_ticket_quality_failed_compat,
    parse_all_tickets_compat,
    parse_ticket_compat,
    sync_database_to_markdown,
    sync_markdown_to_database,
)
from hydra.database.ticket_service import TicketDatabaseService

__all__ = [
    "TicketDatabaseService",
    "parse_ticket_compat",
    "parse_all_tickets_compat",
    "mark_ticket_completed_compat",
    "mark_ticket_in_progress_compat",
    "mark_ticket_quality_failed_compat",
    "add_ticket_artifact_compat",
    "build_dependency_graph_compat",
    "sync_markdown_to_database",
    "sync_database_to_markdown",
]
