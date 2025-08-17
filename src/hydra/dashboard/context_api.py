"""Context visualization API endpoints for the Hydra dashboard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from hydra.context import TicketContextManager

# Create router for context endpoints
router = APIRouter(prefix="/api/context", tags=["context"])


class PatternResponse(BaseModel):
    """Pattern response schema."""

    pattern_id: str
    category: str
    description: str
    solution_template: str
    success_rate: float
    usage_count: int
    created_at: str
    last_used: Optional[str]


class SessionResponse(BaseModel):
    """Session response schema."""

    session_id: str
    ticket_id: str
    agent_type: str
    status: str
    started_at: str
    last_activity: str
    patterns_applied: List[str]
    context_size_kb: float


class ArtifactResponse(BaseModel):
    """Artifact response schema."""

    ticket_id: str
    file_path: str
    operation: str
    description: Optional[str]


class ExecutionHistoryResponse(BaseModel):
    """Execution history response schema."""

    ticket_id: str
    session_id: Optional[str]
    agent_type: Optional[str]
    started_at: str
    completed_at: Optional[str]
    status: str
    success: bool
    error_message: Optional[str]
    execution_time_seconds: Optional[float]
    artifacts_created: int


class ContextStatsResponse(BaseModel):
    """Context statistics response schema."""

    total_executions: int
    successful_executions: int
    success_rate: float
    avg_execution_time: float
    unique_tickets: int
    total_patterns: int
    active_sessions: int
    total_tracked_tickets: int
    total_artifacts: int


class TicketContextResponse(BaseModel):
    """Ticket context response schema."""

    ticket_id: str
    dependencies: List[str]
    dependency_artifacts: List[ArtifactResponse]
    applicable_patterns: List[PatternResponse]
    previous_attempts: List[ExecutionHistoryResponse]
    related_solutions: List[Dict[str, Any]]


def get_context_manager(project: str = ".") -> TicketContextManager:
    """Get context manager instance."""
    return TicketContextManager(project)


@router.get("/stats", response_model=ContextStatsResponse)
async def get_context_stats(
    project: str = Query(".", description="Project directory"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Get overall context statistics."""
    stats = manager.get_execution_stats()
    return ContextStatsResponse(**stats)


@router.get("/patterns", response_model=List[PatternResponse])
async def get_patterns(
    project: str = Query(".", description="Project directory"),
    category: Optional[str] = Query(None, description="Filter by category"),
    min_success_rate: float = Query(0.0, description="Minimum success rate"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Get learned execution patterns."""
    patterns = []

    for pattern_id, pattern in manager.context_store.patterns.items():
        if category and pattern.category != category:
            continue
        if pattern.success_rate < min_success_rate:
            continue

        patterns.append(
            PatternResponse(
                pattern_id=pattern.pattern_id,
                category=pattern.category,
                description=pattern.description,
                solution_template=pattern.solution_template,
                success_rate=pattern.success_rate,
                usage_count=pattern.usage_count,
                created_at=pattern.created_at,
                last_used=pattern.last_used,
            )
        )

    # Sort by success rate and usage count
    patterns.sort(key=lambda p: (p.success_rate, p.usage_count), reverse=True)
    return patterns


@router.get("/sessions", response_model=List[SessionResponse])
async def get_active_sessions(
    project: str = Query(".", description="Project directory"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Get active execution sessions."""
    sessions = []

    for session_id, session in manager.context_store.sessions.items():
        context_size = len(str(session.context_data)) / 1024  # KB

        sessions.append(
            SessionResponse(
                session_id=session.session_id,
                ticket_id=session.ticket_id,
                agent_type=session.agent_type,
                status=session.status,
                started_at=session.started_at,
                last_activity=session.last_activity,
                patterns_applied=session.learned_patterns,
                context_size_kb=round(context_size, 2),
            )
        )

    # Sort by last activity
    sessions.sort(key=lambda s: s.last_activity, reverse=True)
    return sessions


@router.get("/ticket/{ticket_id}/context", response_model=TicketContextResponse)
async def get_ticket_context(
    ticket_id: str,
    project: str = Query(".", description="Project directory"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Get comprehensive context for a specific ticket."""
    # For demonstration, using empty dependencies
    # In production, this would fetch from ticket data
    context = manager.context_store.get_ticket_context(ticket_id, [])

    # Transform to response model
    dependency_artifacts = [
        ArtifactResponse(**artifact)
        for artifact in context.get("dependency_artifacts", [])
    ]

    applicable_patterns = [
        PatternResponse(
            pattern_id=p["pattern_id"],
            category=p["category"],
            description=p["description"],
            solution_template=p["solution_template"],
            success_rate=p["success_rate"],
            usage_count=0,  # Not included in simplified response
            created_at=datetime.now().isoformat(),
            last_used=None,
        )
        for p in context.get("applicable_patterns", [])
    ]

    previous_attempts = [
        ExecutionHistoryResponse(
            ticket_id=ticket_id,
            session_id=a.get("session_id"),
            agent_type=a.get("agent_type"),
            started_at=a.get("started_at", ""),
            completed_at=None,
            status=a.get("status", ""),
            success=a.get("success", False),
            error_message=a.get("error_message"),
            execution_time_seconds=a.get("execution_time_seconds"),
            artifacts_created=0,
        )
        for a in context.get("previous_attempts", [])
    ]

    return TicketContextResponse(
        ticket_id=ticket_id,
        dependencies=context.get("dependencies", []),
        dependency_artifacts=dependency_artifacts,
        applicable_patterns=applicable_patterns,
        previous_attempts=previous_attempts,
        related_solutions=context.get("related_solutions", []),
    )


@router.get("/artifacts", response_model=List[ArtifactResponse])
async def get_artifacts(
    project: str = Query(".", description="Project directory"),
    ticket_id: Optional[str] = Query(None, description="Filter by ticket ID"),
    operation: Optional[str] = Query(None, description="Filter by operation"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Get tracked artifacts."""
    artifacts = []

    for tid, ticket_context in manager.artifact_tracker.ticket_contexts.items():
        if ticket_id and tid != ticket_id:
            continue

        for artifact in ticket_context.artifacts:
            if operation and artifact.operation != operation:
                continue

            artifacts.append(
                ArtifactResponse(
                    ticket_id=tid,
                    file_path=artifact.file_path,
                    operation=artifact.operation,
                    description=artifact.description,
                )
            )

    return artifacts


@router.get("/history", response_model=List[ExecutionHistoryResponse])
async def get_execution_history(
    project: str = Query(".", description="Project directory"),
    ticket_id: Optional[str] = Query(None, description="Filter by ticket ID"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    limit: int = Query(100, description="Maximum results"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Get execution history."""
    import sqlite3

    conn = sqlite3.connect(manager.context_store.history_db)
    cursor = conn.cursor()

    # Build query
    query = """
        SELECT ticket_id, session_id, agent_type, started_at, completed_at,
               status, success, error_message, execution_time_seconds, 
               artifacts_created
        FROM execution_history
        WHERE 1=1
    """
    params = []

    if ticket_id:
        query += " AND ticket_id = ?"
        params.append(ticket_id)

    if agent_type:
        query += " AND agent_type = ?"
        params.append(agent_type)

    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)

    history = []
    for row in cursor.fetchall():
        history.append(
            ExecutionHistoryResponse(
                ticket_id=row[0],
                session_id=row[1],
                agent_type=row[2],
                started_at=row[3],
                completed_at=row[4],
                status=row[5],
                success=bool(row[6]) if row[6] is not None else False,
                error_message=row[7],
                execution_time_seconds=row[8],
                artifacts_created=row[9] or 0,
            )
        )

    conn.close()
    return history


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    success: bool,
    error_message: Optional[str] = None,
    project: str = Query(".", description="Project directory"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Mark a session as completed."""
    if session_id not in manager.context_store.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = manager.context_store.sessions[session_id]
    manager.complete_ticket_execution(
        session_id, session.ticket_id, success, error_message
    )

    return {"message": "Session completed successfully"}


@router.post("/cleanup")
async def cleanup_stale_sessions(
    hours: int = Query(24, description="Hours after which sessions are stale"),
    project: str = Query(".", description="Project directory"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Clean up stale sessions."""
    cleaned = manager.cleanup_stale_sessions(hours)
    return {"cleaned_sessions": cleaned}


@router.get("/visualization/dependency-graph")
async def get_dependency_graph(
    project: str = Query(".", description="Project directory"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Get ticket dependency graph data for visualization."""
    nodes = []
    edges = []

    # Build nodes from tracked tickets
    for ticket_id, context in manager.artifact_tracker.ticket_contexts.items():
        nodes.append(
            {
                "id": ticket_id,
                "label": f"Ticket {ticket_id}",
                "title": context.title,
                "status": context.status,
                "artifacts": len(context.artifacts),
            }
        )

    # Parse tickets.md for dependencies (simplified)
    from pathlib import Path

    tickets_path = Path(project) / "tickets.md"
    if tickets_path.exists():
        import re

        with open(tickets_path, "r") as f:
            content = f.read()

        # Find all ticket dependencies
        pattern = r"## Ticket (\d+):.*?\*\*Dependencies:\*\*\s*([^\n]+)"
        matches = re.findall(pattern, content, re.DOTALL)

        for ticket_id, deps_str in matches:
            if deps_str.strip() and deps_str.strip() != "None":
                deps = [d.strip() for d in deps_str.split(",")]
                for dep in deps:
                    if dep and dep != "None":
                        edges.append(
                            {"from": dep, "to": ticket_id, "label": "depends on"}
                        )

    return {"nodes": nodes, "edges": edges}


@router.get("/visualization/timeline")
async def get_execution_timeline(
    project: str = Query(".", description="Project directory"),
    days: int = Query(7, description="Number of days to include"),
    manager: TicketContextManager = Depends(get_context_manager),
):
    """Get execution timeline data for visualization."""
    import sqlite3
    from datetime import datetime, timedelta

    conn = sqlite3.connect(manager.context_store.history_db)
    cursor = conn.cursor()

    # Get executions from last N days
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    cursor.execute(
        """
        SELECT ticket_id, agent_type, started_at, completed_at, success,
               execution_time_seconds
        FROM execution_history
        WHERE started_at >= ?
        ORDER BY started_at
    """,
        (cutoff,),
    )

    timeline = []
    for row in cursor.fetchall():
        timeline.append(
            {
                "ticket_id": row[0],
                "agent_type": row[1],
                "started_at": row[2],
                "completed_at": row[3],
                "success": bool(row[4]) if row[4] is not None else False,
                "duration_seconds": row[5],
            }
        )

    conn.close()
    return timeline
