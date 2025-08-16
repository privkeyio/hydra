"""Backward compatibility layer for ticket operations.

This module provides wrapper functions that maintain the existing API
while transparently using the database when available.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

# Flag to control whether to use database or markdown
USE_DATABASE = os.getenv("HYDRA_USE_DATABASE", "auto").lower()


def _should_use_database(tickets_path: str = None) -> bool:
    """Determine whether to use database or markdown.
    
    Args:
        tickets_path: Optional path to tickets file
        
    Returns:
        True if database should be used

    """
    if USE_DATABASE == "true":
        return True
    elif USE_DATABASE == "false":
        return False
    else:  # auto mode
        # Check if database is initialized
        try:
            from hydra.dashboard.database import get_db_manager
            db_manager = get_db_manager()
            with db_manager.get_session() as session:
                # Try a simple query to check if database is accessible
                from hydra.dashboard.database import Project
                session.query(Project).first()
                return True
        except Exception:
            return False


def _get_project_name(tickets_path: str) -> str:
    """Extract project name from tickets path.
    
    Args:
        tickets_path: Path to tickets.md file
        
    Returns:
        Project name

    """
    return Path(tickets_path).parent.name


def parse_ticket_compat(tickets_path: str, ticket_identifier: str) -> Optional[Dict[str, Any]]:
    """Parse a single ticket with database fallback.
    
    Args:
        tickets_path: Path to tickets.md file
        ticket_identifier: Ticket number/ID
        
    Returns:
        Ticket data dictionary or None

    """
    if _should_use_database(tickets_path):
        try:
            from hydra.database.ticket_service import TicketDatabaseService

            service = TicketDatabaseService()
            project_name = _get_project_name(tickets_path)

            # Ensure tickets are imported to database
            if os.path.exists(tickets_path):
                service.import_from_markdown(tickets_path, project_name)

            # Get ticket from database
            ticket = service.get_ticket(project_name, ticket_identifier)
            if ticket:
                return ticket
        except Exception as e:
            # Fall back to markdown parsing if database fails
            import sys
            print(f"Database access failed, falling back to markdown: {e}", file=sys.stderr)

    # Use original markdown parsing
    from hydra.ticket_workflow import parse_ticket
    return parse_ticket(tickets_path, ticket_identifier)


def parse_all_tickets_compat(tickets_path: str) -> Dict[str, Dict[str, Any]]:
    """Parse all tickets with database fallback.
    
    Args:
        tickets_path: Path to tickets.md file
        
    Returns:
        Dictionary of tickets keyed by ticket number

    """
    if _should_use_database(tickets_path):
        try:
            from hydra.database.ticket_service import TicketDatabaseService

            service = TicketDatabaseService()
            project_name = _get_project_name(tickets_path)

            # Ensure tickets are imported to database
            if os.path.exists(tickets_path):
                service.import_from_markdown(tickets_path, project_name)

            # Get all tickets from database
            tickets = service.get_all_tickets(project_name)
            if tickets:
                return tickets
        except Exception as e:
            # Fall back to markdown parsing if database fails
            import sys
            print(f"Database access failed, falling back to markdown: {e}", file=sys.stderr)

    # Use original markdown parsing
    from hydra.ticket_workflow import parse_all_tickets
    return parse_all_tickets(tickets_path)


def mark_ticket_completed_compat(tickets_path: str, ticket_identifier: str) -> bool:
    """Mark ticket as completed with database support.
    
    Args:
        tickets_path: Path to tickets.md file
        ticket_identifier: Ticket number/ID
        
    Returns:
        True if marked successfully

    """
    success = False

    # Always update markdown file for visibility
    from hydra.ticket_workflow import mark_ticket_completed
    mark_ticket_completed(tickets_path, ticket_identifier)
    success = True

    # Also update database if available
    if _should_use_database(tickets_path):
        try:
            from hydra.database.ticket_service import TicketDatabaseService

            service = TicketDatabaseService()
            project_name = _get_project_name(tickets_path)

            # Update status in database
            service.update_ticket_status(project_name, ticket_identifier,
                                        "DONE", update_criteria=True)
        except Exception:
            pass  # Database update is optional

    return success


def mark_ticket_in_progress_compat(tickets_path: str, ticket_identifier: str) -> bool:
    """Mark ticket as in progress with database support.
    
    Args:
        tickets_path: Path to tickets.md file
        ticket_identifier: Ticket number/ID
        
    Returns:
        True if marked successfully

    """
    success = False

    # Always update markdown file for visibility
    from hydra.ticket_workflow import mark_ticket_in_progress
    mark_ticket_in_progress(tickets_path, ticket_identifier)
    success = True

    # Also update database if available
    if _should_use_database(tickets_path):
        try:
            from hydra.database.ticket_service import TicketDatabaseService

            service = TicketDatabaseService()
            project_name = _get_project_name(tickets_path)

            # Update status in database
            service.update_ticket_status(project_name, ticket_identifier, "IN_PROGRESS")
        except Exception:
            pass  # Database update is optional

    return success


def mark_ticket_quality_failed_compat(tickets_path: str, ticket_identifier: str,
                                     quality_report: Any = None) -> bool:
    """Mark ticket as quality failed with database support.
    
    Args:
        tickets_path: Path to tickets.md file
        ticket_identifier: Ticket number/ID
        quality_report: Optional quality report
        
    Returns:
        True if marked successfully

    """
    success = False

    # Always update markdown file for visibility
    from hydra.ticket_workflow import mark_ticket_quality_failed
    mark_ticket_quality_failed(tickets_path, ticket_identifier, quality_report)
    success = True

    # Also update database if available
    if _should_use_database(tickets_path):
        try:
            from hydra.database.ticket_service import TicketDatabaseService

            service = TicketDatabaseService()
            project_name = _get_project_name(tickets_path)

            # Update status in database
            service.update_ticket_status(project_name, ticket_identifier, "QUALITY_FAILED")
        except Exception:
            pass  # Database update is optional

    return success


def add_ticket_artifact_compat(tickets_path: str, ticket_identifier: str,
                              artifact_name: str, artifact_type: str,
                              path: Optional[str] = None,
                              content: Optional[str] = None) -> bool:
    """Add artifact to ticket with database support.
    
    Args:
        tickets_path: Path to tickets.md file
        ticket_identifier: Ticket number/ID
        artifact_name: Name of the artifact
        artifact_type: Type of artifact
        path: Optional file path
        content: Optional content
        
    Returns:
        True if added successfully

    """
    if _should_use_database(tickets_path):
        try:
            from hydra.database.ticket_service import TicketDatabaseService

            service = TicketDatabaseService()
            project_name = _get_project_name(tickets_path)

            # Add artifact to database
            return service.add_ticket_artifact(
                project_name, ticket_identifier,
                artifact_name, artifact_type,
                path, content
            )
        except Exception:
            pass  # Fall through to return False

    return False


def build_dependency_graph_compat(tickets: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build dependency graphs with database support.
    
    Args:
        tickets: Dictionary of tickets
        
    Returns:
        Tuple of (dependencies dict, reverse dependencies dict)

    """
    # Check if we have a project context
    if tickets and USE_DATABASE != "false":
        # Try to get from database first
        first_ticket = next(iter(tickets.values()))
        if 'project_name' in first_ticket:
            try:
                from hydra.database.ticket_service import TicketDatabaseService

                service = TicketDatabaseService()
                return service.get_dependency_graph(first_ticket['project_name'])
            except Exception:
                pass  # Fall back to in-memory calculation

    # Use original implementation
    from hydra.ticket_workflow import build_dependency_graph
    return build_dependency_graph(tickets)


def sync_markdown_to_database(tickets_path: str, force: bool = False) -> int:
    """Sync markdown tickets to database.
    
    Args:
        tickets_path: Path to tickets.md file
        force: Force re-import even if already synced
        
    Returns:
        Number of tickets synced

    """
    try:
        from hydra.database.ticket_service import TicketDatabaseService

        service = TicketDatabaseService()
        project_name = _get_project_name(tickets_path)

        # Check if already synced
        if not force:
            existing = service.get_all_tickets(project_name)
            if existing:
                return len(existing)

        # Import from markdown
        return service.import_from_markdown(tickets_path, project_name)
    except Exception as e:
        import sys
        print(f"Failed to sync to database: {e}", file=sys.stderr)
        return 0


def sync_database_to_markdown(project_name: str, output_path: Optional[str] = None) -> str:
    """Export database tickets to markdown.
    
    Args:
        project_name: Name of the project
        output_path: Optional output path
        
    Returns:
        Path to exported file

    """
    try:
        from hydra.database.ticket_service import TicketDatabaseService

        service = TicketDatabaseService()
        return service.export_to_markdown(project_name, output_path)
    except Exception as e:
        raise RuntimeError(f"Failed to export from database: {e}")
