"""Database service layer for ticket operations."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from sqlalchemy.orm import Session, joinedload

from hydra.dashboard.database import (
    DatabaseManager,
    Project,
    Ticket,
    TicketArtifact,
    TicketDependency,
    get_db_manager,
)


class TicketDatabaseService:
    """Service for managing tickets in the database."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """Initialize the ticket database service.

        Args:
            db_manager: Optional database manager instance

        """
        self.db_manager = db_manager or get_db_manager()

    def get_or_create_project(
        self, session: Session, project_name: str, project_path: Optional[str] = None
    ) -> Project:
        """Get or create a project.

        Args:
            session: Database session
            project_name: Name of the project
            project_path: Optional path to the project

        Returns:
            Project instance

        """
        project = session.query(Project).filter_by(name=project_name).first()
        if not project:
            project = Project(
                name=project_name,
                description=f"Project: {project_name}",
                repository_url=project_path,
                is_active=True,
            )
            session.add(project)
            session.commit()
        return project

    def import_from_markdown(
        self, markdown_path: str, project_name: Optional[str] = None
    ) -> int:
        """Import tickets from markdown file to database.

        Args:
            markdown_path: Path to tickets.md file
            project_name: Optional project name (defaults to directory name)

        Returns:
            Number of tickets imported

        """
        from hydra.ticket_workflow import parse_all_tickets

        if not os.path.exists(markdown_path):
            raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

        # Determine project name
        if not project_name:
            project_name = Path(markdown_path).parent.name

        # Parse all tickets from markdown
        tickets_dict = parse_all_tickets(markdown_path)

        with self.db_manager.get_session() as session:
            # Get or create project
            project = self.get_or_create_project(
                session, project_name, os.path.dirname(markdown_path)
            )

            imported_count = 0
            ticket_id_map = {}  # Map markdown IDs to database IDs

            # First pass: Create all tickets without dependencies
            for ticket_num, ticket_data in tickets_dict.items():
                # Check if ticket already exists
                existing = (
                    session.query(Ticket)
                    .filter_by(project_id=project.id, ticket_number=ticket_num)
                    .first()
                )

                if existing:
                    # Update existing ticket
                    db_ticket = existing
                    db_ticket.title = ticket_data.get("title", "")
                    db_ticket.description = ticket_data.get("description", "")
                    db_ticket.status = ticket_data.get("status", "TODO")
                    db_ticket.model = ticket_data.get("model", "balanced")
                    db_ticket.acceptance_criteria = ticket_data.get(
                        "acceptance_criteria", []
                    )
                else:
                    # Create new ticket
                    db_ticket = Ticket(
                        project_id=project.id,
                        ticket_number=ticket_num,
                        title=ticket_data.get("title", ""),
                        description=ticket_data.get("description", ""),
                        status=ticket_data.get("status", "TODO"),
                        priority=5,  # Default priority
                        model=ticket_data.get("model", "balanced"),
                        acceptance_criteria=ticket_data.get("acceptance_criteria", []),
                        dependencies=[],  # Will be set in second pass
                        artifacts=[],
                    )

                    # Set timestamps based on status
                    if ticket_data.get("status") == "IN_PROGRESS":
                        db_ticket.started_at = datetime.utcnow()
                    elif ticket_data.get("status") == "DONE":
                        db_ticket.completed_at = datetime.utcnow()

                    session.add(db_ticket)
                    imported_count += 1

                session.flush()  # Get IDs without committing
                ticket_id_map[ticket_num] = db_ticket.id

            # Second pass: Create dependencies
            for ticket_num, ticket_data in tickets_dict.items():
                if ticket_data.get("dependencies"):
                    parent_id = ticket_id_map[ticket_num]

                    for dep_num in ticket_data["dependencies"]:
                        # Normalize dependency ID
                        dep_num_normalized = (
                            dep_num.zfill(3) if dep_num.isdigit() else dep_num
                        )

                        if dep_num_normalized in ticket_id_map:
                            depends_on_id = ticket_id_map[dep_num_normalized]

                            # Check if dependency already exists
                            existing_dep = (
                                session.query(TicketDependency)
                                .filter_by(
                                    parent_ticket_id=parent_id,
                                    depends_on_ticket_id=depends_on_id,
                                )
                                .first()
                            )

                            if not existing_dep:
                                dependency = TicketDependency(
                                    parent_ticket_id=parent_id,
                                    depends_on_ticket_id=depends_on_id,
                                    dependency_type="blocks",
                                )
                                session.add(dependency)

            session.commit()

        return imported_count

    def export_to_markdown(
        self, project_name: str, output_path: Optional[str] = None
    ) -> str:
        """Export tickets from database to markdown format.

        Args:
            project_name: Name of the project to export
            output_path: Optional output path (defaults to tickets_export.md)

        Returns:
            Path to the exported file

        """
        if not output_path:
            output_path = "tickets_export.md"

        with self.db_manager.get_session() as session:
            # Get project
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                raise ValueError(f"Project not found: {project_name}")

            # Get all tickets with dependencies eagerly loaded
            tickets = (
                session.query(Ticket)
                .filter_by(project_id=project.id)
                .options(
                    joinedload(Ticket.dependencies_as_parent),
                    joinedload(Ticket.ticket_artifacts),
                )
                .order_by(Ticket.ticket_number)
                .all()
            )

            # Build markdown content
            lines = [f"# Project Tickets - {project_name}", ""]

            for ticket in tickets:
                # Format ticket number with padding
                ticket_num = (
                    ticket.ticket_number.zfill(3)
                    if ticket.ticket_number.isdigit()
                    else ticket.ticket_number
                )

                lines.append(f"## Ticket {ticket_num}: {ticket.title}")
                lines.append("")
                lines.append(f"**Status:** {ticket.status}")
                lines.append(f"**Model:** {ticket.model or 'balanced'}")

                # Format dependencies
                deps = []
                for dep_rel in ticket.dependencies_as_parent:
                    dep_ticket = session.query(Ticket).get(dep_rel.depends_on_ticket_id)
                    if dep_ticket:
                        deps.append(dep_ticket.ticket_number)

                if deps:
                    lines.append(f"**Dependencies:** {','.join(deps)}")
                else:
                    lines.append("**Dependencies:** None")

                lines.append(
                    f"**Description:** {ticket.description or 'No description'}"
                )
                lines.append(
                    f"**Progress:** {'completed' if ticket.status == 'DONE' else 'started'}"
                )
                lines.append("")
                lines.append("**Acceptance Criteria:**")

                # Format acceptance criteria
                for criterion in ticket.acceptance_criteria:
                    # Check if criterion is already marked as completed
                    if criterion.startswith("✅"):
                        lines.append(f"- [x] {criterion.replace('✅ ', '')}")
                    else:
                        checkbox = "- [x]" if ticket.status == "DONE" else "- [ ]"
                        lines.append(f"{checkbox} {criterion}")

                # Add artifacts if any
                if ticket.ticket_artifacts:
                    lines.append("")
                    lines.append("**Artifacts:**")
                    for artifact in ticket.ticket_artifacts:
                        lines.append(f"- {artifact.name} ({artifact.artifact_type})")
                        if artifact.path:
                            lines.append(f"  Path: {artifact.path}")

                lines.append("")

        # Write to file
        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        return output_path

    def get_ticket(
        self, project_name: str, ticket_number: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single ticket by number.

        Args:
            project_name: Name of the project
            ticket_number: Ticket number/ID

        Returns:
            Ticket data dictionary or None if not found

        """
        with self.db_manager.get_session() as session:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return None

            ticket = (
                session.query(Ticket)
                .filter_by(project_id=project.id, ticket_number=ticket_number)
                .first()
            )

            if not ticket:
                return None

            # Convert to dictionary format compatible with existing code
            deps = []
            for dep_rel in ticket.dependencies_as_parent:
                dep_ticket = session.query(Ticket).get(dep_rel.depends_on_ticket_id)
                if dep_ticket:
                    deps.append(dep_ticket.ticket_number)

            return {
                "number": ticket.ticket_number,
                "title": ticket.title,
                "description": ticket.description,
                "status": ticket.status,
                "model": ticket.model or "balanced",
                "acceptance_criteria": ticket.acceptance_criteria,
                "dependencies": deps,
                "completed": ticket.status == "DONE",
                "id": ticket.id,
                "artifacts": [
                    {"name": a.name, "type": a.artifact_type, "path": a.path}
                    for a in ticket.ticket_artifacts
                ],
            }

    def get_all_tickets(self, project_name: str) -> Dict[str, Dict[str, Any]]:
        """Get all tickets for a project.

        Args:
            project_name: Name of the project

        Returns:
            Dictionary of tickets keyed by ticket number

        """
        with self.db_manager.get_session() as session:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return {}

            tickets = (
                session.query(Ticket)
                .filter_by(project_id=project.id)
                .options(
                    joinedload(Ticket.dependencies_as_parent),
                    joinedload(Ticket.ticket_artifacts),
                )
                .all()
            )

            result = {}
            for ticket in tickets:
                # Normalize ticket number
                ticket_num = (
                    ticket.ticket_number.zfill(3)
                    if ticket.ticket_number.isdigit()
                    else ticket.ticket_number
                )

                # Get dependencies
                deps = []
                for dep_rel in ticket.dependencies_as_parent:
                    dep_ticket = session.query(Ticket).get(dep_rel.depends_on_ticket_id)
                    if dep_ticket:
                        deps.append(dep_ticket.ticket_number.zfill(3))

                result[ticket_num] = {
                    "number": ticket.ticket_number,
                    "title": ticket.title,
                    "description": ticket.description,
                    "status": ticket.status,
                    "model": ticket.model or "balanced",
                    "acceptance_criteria": ticket.acceptance_criteria,
                    "dependencies": deps,
                    "completed": ticket.status == "DONE",
                    "raw_id": ticket.ticket_number,  # For compatibility
                    "id": ticket.id,
                }

            return result

    def update_ticket_status(
        self,
        project_name: str,
        ticket_number: str,
        status: str,
        update_criteria: bool = False,
    ) -> bool:
        """Update ticket status in database.

        Args:
            project_name: Name of the project
            ticket_number: Ticket number/ID
            status: New status (TODO, IN_PROGRESS, DONE, QUALITY_FAILED)
            update_criteria: Whether to mark acceptance criteria as completed

        Returns:
            True if updated successfully

        """
        with self.db_manager.get_session() as session:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return False

            ticket = (
                session.query(Ticket)
                .filter_by(project_id=project.id, ticket_number=ticket_number)
                .first()
            )

            if not ticket:
                return False

            # Update status
            ticket.status = status

            # Update timestamps
            if status == "IN_PROGRESS" and not ticket.started_at:
                ticket.started_at = datetime.utcnow()
            elif status == "DONE":
                ticket.completed_at = datetime.utcnow()

                # Mark all acceptance criteria as completed if requested
                if update_criteria and ticket.acceptance_criteria:
                    updated_criteria = []
                    for criterion in ticket.acceptance_criteria:
                        if not criterion.startswith("✅"):
                            updated_criteria.append(f"✅ {criterion}")
                        else:
                            updated_criteria.append(criterion)
                    ticket.acceptance_criteria = updated_criteria

            ticket.updated_at = datetime.utcnow()
            session.commit()

            return True

    def add_ticket_artifact(
        self,
        project_name: str,
        ticket_number: str,
        artifact_name: str,
        artifact_type: str,
        path: Optional[str] = None,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add an artifact to a ticket.

        Args:
            project_name: Name of the project
            ticket_number: Ticket number/ID
            artifact_name: Name of the artifact
            artifact_type: Type of artifact (file, document, config, data)
            path: Optional file path or URL
            content: Optional inline content
            metadata: Optional metadata dictionary

        Returns:
            True if added successfully

        """
        with self.db_manager.get_session() as session:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return False

            ticket = (
                session.query(Ticket)
                .filter_by(project_id=project.id, ticket_number=ticket_number)
                .first()
            )

            if not ticket:
                return False

            # Check if artifact already exists
            existing = (
                session.query(TicketArtifact)
                .filter_by(ticket_id=ticket.id, name=artifact_name)
                .first()
            )

            if existing:
                # Update existing artifact
                existing.artifact_type = artifact_type
                existing.path = path
                existing.content = content
                existing.metadata = metadata or {}
                existing.updated_at = datetime.utcnow()
            else:
                # Create new artifact
                artifact = TicketArtifact(
                    ticket_id=ticket.id,
                    artifact_type=artifact_type,
                    name=artifact_name,
                    path=path,
                    content=content,
                    metadata=metadata or {},
                )
                session.add(artifact)

            session.commit()
            return True

    def get_dependency_graph(
        self, project_name: str
    ) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
        """Build dependency and reverse dependency graphs.

        Args:
            project_name: Name of the project

        Returns:
            Tuple of (dependencies dict, reverse dependencies dict)

        """
        with self.db_manager.get_session() as session:
            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                return {}, {}

            # Get all dependencies
            dependencies = (
                session.query(TicketDependency)
                .join(Ticket, TicketDependency.parent_ticket_id == Ticket.id)
                .filter(Ticket.project_id == project.id)
                .all()
            )

            deps = {}
            reverse_deps = {}

            for dep in dependencies:
                # Get ticket numbers
                parent_ticket = session.query(Ticket).get(dep.parent_ticket_id)
                depends_on_ticket = session.query(Ticket).get(dep.depends_on_ticket_id)

                if parent_ticket and depends_on_ticket:
                    parent_num = parent_ticket.ticket_number.zfill(3)
                    dep_num = depends_on_ticket.ticket_number.zfill(3)

                    if parent_num not in deps:
                        deps[parent_num] = set()
                    deps[parent_num].add(dep_num)

                    if dep_num not in reverse_deps:
                        reverse_deps[dep_num] = set()
                    reverse_deps[dep_num].add(parent_num)

            return deps, reverse_deps

    def run_migration(self) -> bool:
        """Run database migrations using Alembic.

        Returns:
            True if migrations ran successfully

        """
        try:
            import subprocess

            result = subprocess.run(
                ["alembic", "upgrade", "head"], capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception:
            # If Alembic not available, create tables directly
            self.db_manager.create_tables()
            return True
