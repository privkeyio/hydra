"""Data export functionality for Hydra dashboard."""

import csv
import json
import logging
from datetime import datetime
from io import BytesIO, StringIO
from typing import Any, Dict, Optional

import orjson
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from hydra.dashboard.api import get_current_user
from hydra.dashboard.database import (
    Execution,
    Project,
    Ticket,
    User,
    get_db,
)

logger = logging.getLogger(__name__)

# Create export router
export_router = APIRouter(prefix="/api/export", tags=["Export"])


class DataExporter:
    """Handles data export in various formats."""

    def __init__(self, db: Session):
        """Initialize data exporter."""
        self.db = db

    def export_tickets_json(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> bytes:
        """Export tickets as JSON."""
        query = self.db.query(Ticket)

        if project_id:
            query = query.filter(Ticket.project_id == project_id)
        if status:
            query = query.filter(Ticket.status == status)
        if start_date:
            query = query.filter(Ticket.created_at >= start_date)
        if end_date:
            query = query.filter(Ticket.created_at <= end_date)

        tickets = query.all()

        # Convert to dictionaries
        data = []
        for ticket in tickets:
            ticket_dict = {
                "id": ticket.id,
                "project_id": ticket.project_id,
                "ticket_number": ticket.ticket_number,
                "title": ticket.title,
                "description": ticket.description,
                "status": ticket.status,
                "priority": ticket.priority,
                "complexity": ticket.complexity,
                "model": ticket.model,
                "dependencies": ticket.dependencies,
                "acceptance_criteria": ticket.acceptance_criteria,
                "artifacts": ticket.artifacts,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
                "started_at": ticket.started_at.isoformat() if ticket.started_at else None,
                "completed_at": ticket.completed_at.isoformat() if ticket.completed_at else None,
                "metadata": ticket.ticket_metadata,
            }
            data.append(ticket_dict)

        return orjson.dumps(data, option=orjson.OPT_INDENT_2)

    def export_tickets_csv(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """Export tickets as CSV."""
        query = self.db.query(Ticket)

        if project_id:
            query = query.filter(Ticket.project_id == project_id)
        if status:
            query = query.filter(Ticket.status == status)
        if start_date:
            query = query.filter(Ticket.created_at >= start_date)
        if end_date:
            query = query.filter(Ticket.created_at <= end_date)

        tickets = query.all()

        # Create CSV
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "ID", "Project ID", "Ticket Number", "Title", "Description",
            "Status", "Priority", "Complexity", "Model", "Dependencies",
            "Acceptance Criteria", "Created At", "Updated At", "Started At",
            "Completed At"
        ])

        # Write data
        for ticket in tickets:
            writer.writerow([
                ticket.id,
                ticket.project_id,
                ticket.ticket_number,
                ticket.title,
                ticket.description or "",
                ticket.status,
                ticket.priority,
                ticket.complexity or "",
                ticket.model or "",
                json.dumps(ticket.dependencies) if ticket.dependencies else "[]",
                json.dumps(ticket.acceptance_criteria) if ticket.acceptance_criteria else "[]",
                ticket.created_at.isoformat() if ticket.created_at else "",
                ticket.updated_at.isoformat() if ticket.updated_at else "",
                ticket.started_at.isoformat() if ticket.started_at else "",
                ticket.completed_at.isoformat() if ticket.completed_at else "",
            ])

        return output.getvalue()

    def export_tickets_markdown(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """Export tickets as Markdown."""
        query = self.db.query(Ticket)

        if project_id:
            query = query.filter(Ticket.project_id == project_id)
        if status:
            query = query.filter(Ticket.status == status)
        if start_date:
            query = query.filter(Ticket.created_at >= start_date)
        if end_date:
            query = query.filter(Ticket.created_at <= end_date)

        tickets = query.order_by(Ticket.priority, Ticket.created_at).all()

        # Generate Markdown
        output = []
        output.append("# Hydra Project Tickets\n")
        output.append(f"Generated: {datetime.utcnow().isoformat()}\n")

        if project_id:
            project = self.db.query(Project).filter(Project.id == project_id).first()
            if project:
                output.append(f"Project: {project.name}\n")

        output.append("\n---\n")

        for ticket in tickets:
            output.append(f"\n## Ticket {ticket.ticket_number}: {ticket.title}\n")
            output.append(f"\n**Status:** {ticket.status}")
            output.append(f"\n**Priority:** {ticket.priority}")

            if ticket.model:
                output.append(f"\n**Model:** {ticket.model}")
            if ticket.complexity:
                output.append(f"\n**Complexity:** {ticket.complexity}")

            if ticket.description:
                output.append(f"\n\n**Description:**\n{ticket.description}")

            if ticket.dependencies:
                output.append("\n\n**Dependencies:**")
                for dep in ticket.dependencies:
                    output.append(f"\n- {dep}")

            if ticket.acceptance_criteria:
                output.append("\n\n**Acceptance Criteria:**")
                for criteria in ticket.acceptance_criteria:
                    status_mark = "x" if ticket.status == "DONE" else " "
                    output.append(f"\n- [{status_mark}] {criteria}")

            if ticket.artifacts:
                output.append("\n\n**Artifacts:**")
                for artifact in ticket.artifacts:
                    output.append(f"\n- {artifact.get('name', 'Unknown')}: {artifact.get('path', '')}")

            output.append("\n\n---\n")

        return "".join(output)

    def export_executions_json(
        self,
        ticket_id: Optional[int] = None,
        session_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> bytes:
        """Export executions as JSON."""
        query = self.db.query(Execution)

        if ticket_id:
            query = query.filter(Execution.ticket_id == ticket_id)
        if session_id:
            query = query.filter(Execution.session_id == session_id)
        if start_date:
            query = query.filter(Execution.started_at >= start_date)
        if end_date:
            query = query.filter(Execution.started_at <= end_date)

        executions = query.all()

        # Convert to dictionaries
        data = []
        for execution in executions:
            exec_dict = {
                "id": execution.id,
                "ticket_id": execution.ticket_id,
                "session_id": execution.session_id,
                "status": execution.status,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "duration_seconds": execution.duration_seconds,
                "tokens_used": execution.tokens_used,
                "cost_estimate": execution.cost_estimate,
                "output": execution.output,
                "error": execution.error,
                "commands_executed": execution.commands_executed,
                "files_modified": execution.files_modified,
            }
            data.append(exec_dict)

        return orjson.dumps(data, option=orjson.OPT_INDENT_2)

    def export_project_summary(self, project_id: int) -> Dict[str, Any]:
        """Export comprehensive project summary."""
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {}

        # Get ticket statistics
        tickets = self.db.query(Ticket).filter(Ticket.project_id == project_id).all()
        ticket_stats = {
            "total": len(tickets),
            "by_status": {},
            "by_priority": {},
            "by_model": {},
        }

        for ticket in tickets:
            # Status
            status = ticket.status
            ticket_stats["by_status"][status] = ticket_stats["by_status"].get(status, 0) + 1

            # Priority
            priority = f"P{ticket.priority}"
            ticket_stats["by_priority"][priority] = ticket_stats["by_priority"].get(priority, 0) + 1

            # Model
            if ticket.model:
                ticket_stats["by_model"][ticket.model] = ticket_stats["by_model"].get(ticket.model, 0) + 1

        # Get execution statistics
        executions = (
            self.db.query(Execution)
            .join(Ticket)
            .filter(Ticket.project_id == project_id)
            .all()
        )

        execution_stats = {
            "total": len(executions),
            "successful": sum(1 for e in executions if e.status == "success"),
            "failed": sum(1 for e in executions if e.status == "failed"),
            "total_tokens": sum(e.tokens_used or 0 for e in executions),
            "total_duration_seconds": sum(e.duration_seconds or 0 for e in executions),
        }

        # Calculate cost
        total_cost = 0.0
        for execution in executions:
            if execution.cost_estimate:
                try:
                    cost = float(execution.cost_estimate.replace("$", ""))
                    total_cost += cost
                except ValueError:
                    pass

        execution_stats["estimated_cost"] = f"${total_cost:.2f}"

        # Build summary
        summary = {
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "repository_url": project.repository_url,
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                "is_active": project.is_active,
            },
            "tickets": ticket_stats,
            "executions": execution_stats,
            "sessions": {
                "total": len(project.sessions),
                "active": sum(1 for s in project.sessions if s.status == "active"),
            },
            "exported_at": datetime.utcnow().isoformat(),
        }

        return summary


# API endpoints
@export_router.get("/tickets.json")
def export_tickets_json(
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export tickets as JSON file."""
    exporter = DataExporter(db)
    data = exporter.export_tickets_json(project_id, status, start_date, end_date)

    return StreamingResponse(
        BytesIO(data),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        },
    )


@export_router.get("/tickets.csv")
def export_tickets_csv(
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export tickets as CSV file."""
    exporter = DataExporter(db)
    data = exporter.export_tickets_csv(project_id, status, start_date, end_date)

    return StreamingResponse(
        BytesIO(data.encode()),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )


@export_router.get("/tickets.md")
def export_tickets_markdown(
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export tickets as Markdown file."""
    exporter = DataExporter(db)
    data = exporter.export_tickets_markdown(project_id, status, start_date, end_date)

    return StreamingResponse(
        BytesIO(data.encode()),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename=tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
        },
    )


@export_router.get("/executions.json")
def export_executions_json(
    ticket_id: Optional[int] = Query(None),
    session_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export executions as JSON file."""
    exporter = DataExporter(db)
    data = exporter.export_executions_json(ticket_id, session_id, start_date, end_date)

    return StreamingResponse(
        BytesIO(data),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=executions_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        },
    )


@export_router.get("/project/{project_id}/summary.json")
def export_project_summary(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export comprehensive project summary."""
    exporter = DataExporter(db)
    summary = exporter.export_project_summary(project_id)

    if not summary:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    data = orjson.dumps(summary, option=orjson.OPT_INDENT_2)

    return StreamingResponse(
        BytesIO(data),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=project_{project_id}_summary_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        },
    )
