"""Ticket database module - handles all database operations for tickets."""

import os
from datetime import datetime
from typing import Any, Dict, Optional


def update_ticket_in_database(
    ticket_identifier: str,
    status: str,
    project_path: Optional[str] = None,
    ticket_info: Optional[Dict[str, Any]] = None,
):
    """Update ticket status in the dashboard database.
    
    Args:
        ticket_identifier: Ticket ID (e.g., '001')
        status: New status (TODO, IN_PROGRESS, DONE)
        project_path: Path to the project (defaults to current directory)
        ticket_info: Optional dict with ticket details (title, description, etc.)

    """
    try:
        from hydra.dashboard.database import Execution, Project, Ticket, get_db_manager

        # Set database URL to project-specific location if we're in a project
        if project_path and os.path.exists(os.path.join(project_path, "tickets.yaml")):
            db_url = f"sqlite:///{project_path}/.hydra/dashboard/hydra.db"
            os.environ["DATABASE_URL"] = db_url
            
            # Ensure the directory structure exists
            db_path = f"{project_path}/.hydra/dashboard/hydra.db"
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)

        # Get database manager and ensure tables are created
        db_manager = get_db_manager()

        # Normalize ticket ID
        if ticket_identifier.isdigit():
            ticket_identifier = ticket_identifier.zfill(3)

        # Get project path
        if project_path is None:
            project_path = os.getcwd()

        with db_manager.get_session() as db:
            # Find or create project
            project = (
                db.query(Project).filter(Project.repository_url == project_path).first()
            )

            if not project:
                project_name = os.path.basename(project_path) or "Current Project"
                project = Project(
                    name=project_name,
                    description=f"Project at {project_path}",
                    repository_url=project_path,
                    created_at=datetime.now(),
                )
                db.add(project)
                db.commit()

            # Find or create ticket
            ticket = (
                db.query(Ticket)
                .filter(
                    Ticket.ticket_number == ticket_identifier,
                    Ticket.project_id == project.id,
                )
                .first()
            )

            if ticket:
                # Update existing ticket
                ticket.status = status
                ticket.updated_at = datetime.now()

                if status == "IN_PROGRESS" and not ticket.started_at:
                    ticket.started_at = datetime.now()
                elif status == "DONE" and not ticket.completed_at:
                    ticket.completed_at = datetime.now()
            else:
                # Create new ticket
                ticket = Ticket(
                    ticket_number=ticket_identifier,
                    title=(
                        ticket_info.get("title", f"Ticket {ticket_identifier}")
                        if ticket_info
                        else f"Ticket {ticket_identifier}"
                    ),
                    description=(
                        ticket_info.get("description", "") if ticket_info else ""
                    ),
                    status=status,
                    priority=(
                        ticket_info.get("priority", "medium") if ticket_info else "medium"
                    ),
                    model=ticket_info.get("model", "balanced") if ticket_info else "balanced",
                    project_id=project.id,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                if status == "IN_PROGRESS":
                    ticket.started_at = datetime.now()
                elif status == "DONE":
                    ticket.completed_at = datetime.now()

                db.add(ticket)
                db.flush()  # Ensure ticket gets an ID before creating execution

            # Create execution record for status changes
            execution = Execution(
                ticket_id=ticket.id,
                status="success" if status == "DONE" else "running",
                started_at=datetime.now(),
                completed_at=datetime.now() if status == "DONE" else None,
            )
            db.add(execution)

            db.commit()
            print(f"📊 Updated database: Ticket {ticket_identifier} -> {status}")

    except ImportError:
        # Dashboard module not available
        print(f"⚠️  Dashboard database not available (ticket {ticket_identifier} -> {status})")
    except Exception as e:
        # Don't fail ticket execution if database update fails
        print(f"⚠️  Database update failed (non-critical): {e}")


def get_ticket_from_database(
    ticket_identifier: str,
    project_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get ticket information from the database.
    
    Args:
        ticket_identifier: Ticket ID (e.g., '001')
        project_path: Path to the project (defaults to current directory)
        
    Returns:
        Dictionary with ticket information or None if not found

    """
    try:
        from hydra.dashboard.database import Project, Ticket, get_db_manager

        # Set database URL to project-specific location if we're in a project
        if project_path and os.path.exists(os.path.join(project_path, "tickets.yaml")):
            db_url = f"sqlite:///{project_path}/.hydra/dashboard/hydra.db"
            os.environ["DATABASE_URL"] = db_url
            
            # Ensure the directory structure exists
            db_path = f"{project_path}/.hydra/dashboard/hydra.db"
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)

        # Get database manager and ensure tables are created
        db_manager = get_db_manager()

        # Normalize ticket ID
        if ticket_identifier.isdigit():
            ticket_identifier = ticket_identifier.zfill(3)

        # Get project path
        if project_path is None:
            project_path = os.getcwd()

        with db_manager.get_session() as db:
            # Find project
            project = (
                db.query(Project).filter(Project.repository_url == project_path).first()
            )

            if not project:
                return None

            # Find ticket
            ticket = (
                db.query(Ticket)
                .filter(
                    Ticket.ticket_number == ticket_identifier,
                    Ticket.project_id == project.id,
                )
                .first()
            )

            if ticket:
                return {
                    "id": ticket.ticket_number,
                    "title": ticket.title,
                    "description": ticket.description,
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "model": ticket.model,
                    "created_at": ticket.created_at,
                    "started_at": ticket.started_at,
                    "completed_at": ticket.completed_at,
                    "updated_at": ticket.updated_at,
                }

            return None

    except ImportError:
        # Dashboard module not available
        return None
    except Exception:
        # Don't fail if database read fails
        return None


def sync_tickets_to_database(
    tickets_path: str,
    project_path: Optional[str] = None
):
    """Sync all tickets from file to database.
    
    Args:
        tickets_path: Path to the tickets file
        project_path: Path to the project (defaults to tickets file directory)

    """
    try:
        from hydra.dashboard.database import Project, Ticket, get_db_manager
        from hydra.tickets.ticket_parser import parse_all_tickets

        # Get project path
        if project_path is None:
            project_path = os.path.dirname(os.path.abspath(tickets_path))

        # Set database URL to project-specific location
        if os.path.exists(os.path.join(project_path, "tickets.yaml")):
            db_url = f"sqlite:///{project_path}/.hydra/dashboard/hydra.db"
            os.environ["DATABASE_URL"] = db_url
            
            # Ensure the directory structure exists
            db_path = f"{project_path}/.hydra/dashboard/hydra.db"
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)

        # Parse all tickets
        tickets = parse_all_tickets(tickets_path)
        if not tickets:
            print("⚠️  No tickets found to sync")
            return

        # Get database manager
        db_manager = get_db_manager()

        with db_manager.get_session() as db:
            # Find or create project
            project = (
                db.query(Project).filter(Project.repository_url == project_path).first()
            )

            if not project:
                project_name = os.path.basename(project_path) or "Current Project"
                project = Project(
                    name=project_name,
                    description=f"Project at {project_path}",
                    repository_url=project_path,
                    created_at=datetime.now(),
                )
                db.add(project)
                db.commit()

            # Sync each ticket
            synced_count = 0
            for ticket_id, ticket_data in tickets.items():
                # Normalize ticket ID
                if ticket_id.isdigit():
                    ticket_id = ticket_id.zfill(3)

                # Find or create ticket
                ticket = (
                    db.query(Ticket)
                    .filter(
                        Ticket.ticket_number == ticket_id,
                        Ticket.project_id == project.id,
                    )
                    .first()
                )

                # Determine status
                status = ticket_data.get("status", "TODO").upper()
                if ticket_data.get("completed") or status == "DONE":
                    status = "DONE"
                elif ticket_data.get("quality_failed"):
                    status = "QUALITY_FAILED"

                if ticket:
                    # Update existing ticket
                    ticket.title = ticket_data.get("title", f"Ticket {ticket_id}")
                    ticket.description = ticket_data.get("description", "")
                    ticket.status = status
                    ticket.priority = ticket_data.get("priority", "medium")
                    ticket.model = ticket_data.get("model", "balanced")
                    ticket.updated_at = datetime.now()

                    if status == "DONE" and not ticket.completed_at:
                        ticket.completed_at = datetime.now()
                else:
                    # Create new ticket
                    ticket = Ticket(
                        ticket_number=ticket_id,
                        title=ticket_data.get("title", f"Ticket {ticket_id}"),
                        description=ticket_data.get("description", ""),
                        status=status,
                        priority=ticket_data.get("priority", "medium"),
                        model=ticket_data.get("model", "balanced"),
                        project_id=project.id,
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                    )

                    if status == "DONE":
                        ticket.completed_at = datetime.now()

                    db.add(ticket)

                synced_count += 1

            db.commit()
            print(f"📊 Synced {synced_count} tickets to database")

    except ImportError:
        # Dashboard module not available
        print("⚠️  Dashboard database not available for sync")
    except Exception as e:
        # Don't fail if database sync fails
        print(f"⚠️  Database sync failed (non-critical): {e}")


def get_project_summary(project_path: Optional[str] = None) -> Dict[str, Any]:
    """Get project summary from database.
    
    Args:
        project_path: Path to the project (defaults to current directory)
        
    Returns:
        Dictionary with project summary information

    """
    try:
        from hydra.dashboard.database import Project, Ticket, get_db_manager

        # Get project path
        if project_path is None:
            project_path = os.getcwd()

        # Set database URL to project-specific location
        if os.path.exists(os.path.join(project_path, "tickets.yaml")):
            db_url = f"sqlite:///{project_path}/.hydra/dashboard/hydra.db"
            os.environ["DATABASE_URL"] = db_url
            
            # Ensure the directory structure exists
            db_path = f"{project_path}/.hydra/dashboard/hydra.db"
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)

        # Get database manager
        db_manager = get_db_manager()

        with db_manager.get_session() as db:
            # Find project
            project = (
                db.query(Project).filter(Project.repository_url == project_path).first()
            )

            if not project:
                return {
                    "project_name": os.path.basename(project_path),
                    "total_tickets": 0,
                    "completed": 0,
                    "in_progress": 0,
                    "todo": 0,
                    "quality_failed": 0,
                }

            # Get ticket counts
            tickets = db.query(Ticket).filter(Ticket.project_id == project.id).all()

            summary = {
                "project_name": project.name,
                "project_description": project.description,
                "total_tickets": len(tickets),
                "completed": 0,
                "in_progress": 0,
                "todo": 0,
                "quality_failed": 0,
                "created_at": project.created_at,
            }

            for ticket in tickets:
                if ticket.status == "DONE":
                    summary["completed"] += 1
                elif ticket.status == "IN_PROGRESS":
                    summary["in_progress"] += 1
                elif ticket.status == "QUALITY_FAILED":
                    summary["quality_failed"] += 1
                else:
                    summary["todo"] += 1

            return summary

    except ImportError:
        # Dashboard module not available
        return {
            "project_name": os.path.basename(project_path or os.getcwd()),
            "total_tickets": 0,
            "completed": 0,
            "in_progress": 0,
            "todo": 0,
            "quality_failed": 0,
        }
    except Exception:
        # Don't fail if database read fails
        return {
            "project_name": os.path.basename(project_path or os.getcwd()),
            "total_tickets": 0,
            "completed": 0,
            "in_progress": 0,
            "todo": 0,
            "quality_failed": 0,
        }
