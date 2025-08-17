"""Shared context store for ticket execution and agent collaboration.

This module provides a centralized context store that enables:
- Sharing artifacts and learnings between dependent tickets
- Maintaining execution history and patterns
- Standardizing session management across agents
- Persisting learned solutions for future use
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from hydra.context.artifact_tracker import (
    ArtifactTracker,
    TicketArtifact,
)


@dataclass
class ExecutionPattern:
    """Represents a learned execution pattern from successful tickets."""

    pattern_id: str
    category: str  # e.g., "file_modification", "testing", "refactoring"
    description: str
    solution_template: str
    success_rate: float = 0.0
    usage_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None
    applicable_conditions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "pattern_id": self.pattern_id,
            "category": self.category,
            "description": self.description,
            "solution_template": self.solution_template,
            "success_rate": self.success_rate,
            "usage_count": self.usage_count,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "applicable_conditions": self.applicable_conditions,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ExecutionPattern":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class SessionState:
    """Represents the state of an agent session."""

    session_id: str
    ticket_id: str
    agent_type: str  # e.g., "venice", "claude", "openai"
    status: str  # "active", "paused", "completed", "failed"
    started_at: str
    last_activity: str
    context_data: Dict[str, Any] = field(default_factory=dict)
    learned_patterns: List[str] = field(default_factory=list)  # Pattern IDs

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "ticket_id": self.ticket_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "started_at": self.started_at,
            "last_activity": self.last_activity,
            "context_data": self.context_data,
            "learned_patterns": self.learned_patterns,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SessionState":
        """Create from dictionary."""
        return cls(**data)


class ContextStore:
    """Centralized context store for ticket execution and agent collaboration."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.context_dir = self.project_root / ".hydra" / "context"
        self.context_dir.mkdir(parents=True, exist_ok=True)

        # Storage paths
        self.patterns_file = self.context_dir / "learned_patterns.json"
        self.sessions_file = self.context_dir / "active_sessions.json"
        self.history_db = self.context_dir / "execution_history.db"
        self.artifacts_cache = self.context_dir / "artifacts_cache.pkl"

        # Initialize components
        self.artifact_tracker = ArtifactTracker(project_root)
        self.patterns: Dict[str, ExecutionPattern] = self._load_patterns()
        self.sessions: Dict[str, SessionState] = self._load_sessions()
        self._init_history_db()

    def _load_patterns(self) -> Dict[str, ExecutionPattern]:
        """Load learned execution patterns from file."""
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, "r") as f:
                    data = json.load(f)
                    return {
                        pid: ExecutionPattern.from_dict(pattern)
                        for pid, pattern in data.items()
                    }
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    def _save_patterns(self):
        """Save learned execution patterns to file."""
        data = {pid: pattern.to_dict() for pid, pattern in self.patterns.items()}
        with open(self.patterns_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_sessions(self) -> Dict[str, SessionState]:
        """Load active session states from file."""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file, "r") as f:
                    data = json.load(f)
                    return {
                        sid: SessionState.from_dict(session)
                        for sid, session in data.items()
                    }
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    def _save_sessions(self):
        """Save active session states to file."""
        data = {sid: session.to_dict() for sid, session in self.sessions.items()}
        with open(self.sessions_file, "w") as f:
            json.dump(data, f, indent=2)

    def _init_history_db(self):
        """Initialize the execution history database."""
        conn = sqlite3.connect(self.history_db)
        cursor = conn.cursor()

        # Create tables if they don't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                session_id TEXT,
                agent_type TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                success BOOLEAN,
                error_message TEXT,
                artifacts_created INTEGER DEFAULT 0,
                patterns_applied TEXT,
                execution_time_seconds REAL,
                context_size_bytes INTEGER
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS learned_solutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                problem_type TEXT NOT NULL,
                solution_approach TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                timestamp TEXT NOT NULL,
                confidence_score REAL DEFAULT 0.5
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ticket_history ON execution_history(ticket_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_history ON execution_history(session_id)
        """
        )

        conn.commit()
        conn.close()

    def get_ticket_context(
        self, ticket_id: str, dependencies: List[str]
    ) -> Dict[str, Any]:
        """Get comprehensive context for a ticket including dependencies.

        Args:
            ticket_id: The ticket about to be executed
            dependencies: List of dependent ticket IDs

        Returns:
            Dictionary containing all relevant context

        """
        context = {
            "ticket_id": ticket_id,
            "dependencies": dependencies,
            "dependency_artifacts": [],
            "applicable_patterns": [],
            "previous_attempts": [],
            "related_solutions": [],
        }

        # Get dependency context from artifact tracker
        if dependencies:
            dependency_context = self.artifact_tracker.get_dependency_context(
                ticket_id, dependencies
            )
            context["dependency_context_text"] = dependency_context

            # Collect artifacts from dependencies
            for dep_id in dependencies:
                if dep_id in self.artifact_tracker.ticket_contexts:
                    dep_ctx = self.artifact_tracker.ticket_contexts[dep_id]
                    for artifact in dep_ctx.artifacts:
                        context["dependency_artifacts"].append(
                            {
                                "ticket_id": dep_id,
                                "file_path": artifact.file_path,
                                "operation": artifact.operation,
                                "description": artifact.description,
                            }
                        )

        # Find applicable patterns
        context["applicable_patterns"] = self._find_applicable_patterns(ticket_id)

        # Get previous execution attempts
        context["previous_attempts"] = self._get_execution_history(ticket_id)

        # Find related solutions
        context["related_solutions"] = self._find_related_solutions(ticket_id)

        return context

    def _find_applicable_patterns(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Find patterns that might be applicable to this ticket."""
        applicable = []

        # Simple heuristic: patterns used in similar tickets
        # In production, this would use ML or more sophisticated matching
        for pattern_id, pattern in self.patterns.items():
            if pattern.success_rate > 0.7 and pattern.usage_count > 2:
                applicable.append(
                    {
                        "pattern_id": pattern_id,
                        "category": pattern.category,
                        "description": pattern.description,
                        "success_rate": pattern.success_rate,
                        "solution_template": pattern.solution_template,
                    }
                )

        return applicable[:5]  # Return top 5 patterns

    def _get_execution_history(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Get previous execution attempts for a ticket."""
        conn = sqlite3.connect(self.history_db)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT session_id, agent_type, started_at, status, success, 
                   error_message, execution_time_seconds
            FROM execution_history
            WHERE ticket_id = ?
            ORDER BY started_at DESC
            LIMIT 5
        """,
            (ticket_id,),
        )

        history = []
        for row in cursor.fetchall():
            history.append(
                {
                    "session_id": row[0],
                    "agent_type": row[1],
                    "started_at": row[2],
                    "status": row[3],
                    "success": bool(row[4]),
                    "error_message": row[5],
                    "execution_time_seconds": row[6],
                }
            )

        conn.close()
        return history

    def _find_related_solutions(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Find solutions from similar tickets."""
        conn = sqlite3.connect(self.history_db)
        cursor = conn.cursor()

        # For now, just get recent successful solutions
        cursor.execute(
            """
            SELECT ticket_id, problem_type, solution_approach, confidence_score
            FROM learned_solutions
            WHERE success = 1
            ORDER BY timestamp DESC
            LIMIT 10
        """
        )

        solutions = []
        for row in cursor.fetchall():
            solutions.append(
                {
                    "ticket_id": row[0],
                    "problem_type": row[1],
                    "solution_approach": row[2],
                    "confidence_score": row[3],
                }
            )

        conn.close()
        return solutions

    def start_session(self, ticket_id: str, agent_type: str) -> str:
        """Start a new agent session for a ticket.

        Args:
            ticket_id: The ticket being executed
            agent_type: Type of agent (venice, claude, etc.)

        Returns:
            Session ID

        """
        session_id = (
            f"{ticket_id}_{agent_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

        session = SessionState(
            session_id=session_id,
            ticket_id=ticket_id,
            agent_type=agent_type,
            status="active",
            started_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat(),
        )

        self.sessions[session_id] = session
        self._save_sessions()

        # Record in history
        conn = sqlite3.connect(self.history_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO execution_history 
            (ticket_id, session_id, agent_type, started_at, status)
            VALUES (?, ?, ?, ?, ?)
        """,
            (ticket_id, session_id, agent_type, session.started_at, "active"),
        )
        conn.commit()
        conn.close()

        return session_id

    def update_session(self, session_id: str, **updates):
        """Update session state.

        Args:
            session_id: The session to update
            **updates: Fields to update

        """
        if session_id not in self.sessions:
            return

        session = self.sessions[session_id]
        for key, value in updates.items():
            if hasattr(session, key):
                setattr(session, key, value)

        session.last_activity = datetime.now().isoformat()
        self._save_sessions()

    def complete_session(
        self,
        session_id: str,
        success: bool,
        artifacts: Optional[List[TicketArtifact]] = None,
        error_message: Optional[str] = None,
    ):
        """Mark a session as completed.

        Args:
            session_id: The session to complete
            success: Whether the execution was successful
            artifacts: List of artifacts created/modified
            error_message: Error message if failed

        """
        if session_id not in self.sessions:
            return

        session = self.sessions[session_id]
        session.status = "completed" if success else "failed"

        # Calculate execution time
        started = datetime.fromisoformat(session.started_at)
        completed = datetime.now()
        execution_time = (completed - started).total_seconds()

        # Update history
        conn = sqlite3.connect(self.history_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE execution_history
            SET completed_at = ?, status = ?, success = ?, 
                error_message = ?, artifacts_created = ?, 
                execution_time_seconds = ?
            WHERE session_id = ?
        """,
            (
                completed.isoformat(),
                session.status,
                success,
                error_message,
                len(artifacts) if artifacts else 0,
                execution_time,
                session_id,
            ),
        )
        conn.commit()
        conn.close()

        # Clean up completed session
        del self.sessions[session_id]
        self._save_sessions()

    def learn_pattern(
        self, ticket_id: str, category: str, description: str, solution_template: str
    ) -> str:
        """Learn a new execution pattern from a successful ticket.

        Args:
            ticket_id: The ticket this pattern came from
            category: Category of the pattern
            description: Description of what this pattern does
            solution_template: Template for applying this solution

        Returns:
            Pattern ID

        """
        pattern_id = f"pattern_{category}_{len(self.patterns) + 1}"

        pattern = ExecutionPattern(
            pattern_id=pattern_id,
            category=category,
            description=description,
            solution_template=solution_template,
            success_rate=1.0,  # Start optimistic
            usage_count=1,
        )

        self.patterns[pattern_id] = pattern
        self._save_patterns()

        return pattern_id

    def apply_pattern(self, pattern_id: str, success: bool):
        """Record the application of a pattern.

        Args:
            pattern_id: The pattern that was applied
            success: Whether the application was successful

        """
        if pattern_id not in self.patterns:
            return

        pattern = self.patterns[pattern_id]
        pattern.usage_count += 1
        pattern.last_used = datetime.now().isoformat()

        # Update success rate with exponential moving average
        alpha = 0.3  # Weight for new observation
        pattern.success_rate = (
            alpha * (1.0 if success else 0.0) + (1 - alpha) * pattern.success_rate
        )

        self._save_patterns()

    def record_solution(
        self,
        ticket_id: str,
        problem_type: str,
        solution_approach: str,
        success: bool,
        confidence_score: float = 0.5,
    ):
        """Record a solution approach for future reference.

        Args:
            ticket_id: The ticket this solution was for
            problem_type: Type of problem solved
            solution_approach: Description of the solution
            success: Whether the solution worked
            confidence_score: Confidence in this solution (0-1)

        """
        conn = sqlite3.connect(self.history_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO learned_solutions
            (ticket_id, problem_type, solution_approach, success, 
             timestamp, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                ticket_id,
                problem_type,
                solution_approach,
                success,
                datetime.now().isoformat(),
                confidence_score,
            ),
        )
        conn.commit()
        conn.close()

    def get_session_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the full context for a session.

        Args:
            session_id: The session ID

        Returns:
            Session context or None if not found

        """
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]

        # Get ticket context
        ticket_context = self.get_ticket_context(
            session.ticket_id, []  # Dependencies would be fetched from ticket data
        )

        return {
            "session": session.to_dict(),
            "ticket_context": ticket_context,
            "active_patterns": [
                self.patterns[pid].to_dict()
                for pid in session.learned_patterns
                if pid in self.patterns
            ],
        }

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get overall execution statistics."""
        conn = sqlite3.connect(self.history_db)
        cursor = conn.cursor()

        # Get overall stats
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_executions,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                AVG(execution_time_seconds) as avg_execution_time,
                COUNT(DISTINCT ticket_id) as unique_tickets
            FROM execution_history
            WHERE completed_at IS NOT NULL
        """
        )

        row = cursor.fetchone()
        stats = {
            "total_executions": row[0] or 0,
            "successful": row[1] or 0,
            "avg_execution_time": row[2] or 0,
            "unique_tickets": row[3] or 0,
        }

        stats["success_rate"] = (
            stats["successful"] / stats["total_executions"]
            if stats["total_executions"] > 0
            else 0
        )

        # Get pattern stats
        stats["total_patterns"] = len(self.patterns)
        stats["active_sessions"] = len(self.sessions)

        conn.close()
        return stats

    def cleanup_stale_sessions(self, hours: int = 24):
        """Clean up sessions older than specified hours.

        Args:
            hours: Number of hours after which a session is considered stale

        """
        cutoff = datetime.now() - timedelta(hours=hours)

        stale_sessions = []
        for session_id, session in self.sessions.items():
            last_activity = datetime.fromisoformat(session.last_activity)
            if last_activity < cutoff:
                stale_sessions.append(session_id)

        for session_id in stale_sessions:
            self.complete_session(session_id, False, error_message="Session timed out")

        return len(stale_sessions)
