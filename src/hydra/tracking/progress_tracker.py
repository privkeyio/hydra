"""Progress tracking system for enhanced ticket execution monitoring.

This module provides comprehensive progress tracking capabilities for ticket execution,
including stage management, real-time updates, and history storage.
"""

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ProgressStage(Enum):
    """Execution stages for ticket progress tracking."""

    STARTED = "started"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def emoji(self) -> str:
        """Get emoji representation for the stage."""
        return {
            ProgressStage.STARTED: "🚀",
            ProgressStage.IMPLEMENTATION: "⚙️",
            ProgressStage.TESTING: "🧪",
            ProgressStage.REVIEW: "👀",
            ProgressStage.COMPLETED: "✅",
            ProgressStage.FAILED: "❌",
        }[self]

    @property
    def description(self) -> str:
        """Get human-readable description for the stage."""
        return {
            ProgressStage.STARTED: "Started",
            ProgressStage.IMPLEMENTATION: "Implementation",
            ProgressStage.TESTING: "Testing",
            ProgressStage.REVIEW: "Review",
            ProgressStage.COMPLETED: "Completed",
            ProgressStage.FAILED: "Failed",
        }[self]

    @property
    def percentage(self) -> float:
        """Get progress percentage for the stage."""
        return {
            ProgressStage.STARTED: 10.0,
            ProgressStage.IMPLEMENTATION: 50.0,
            ProgressStage.TESTING: 80.0,
            ProgressStage.REVIEW: 95.0,
            ProgressStage.COMPLETED: 100.0,
            ProgressStage.FAILED: 0.0,
        }[self]


@dataclass
class ProgressUpdate:
    """Represents a single progress update event."""

    ticket_id: str
    stage: ProgressStage
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    update_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert update to dictionary format."""
        return {
            "update_id": self.update_id,
            "ticket_id": self.ticket_id,
            "stage": self.stage.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressUpdate":
        """Create update from dictionary format."""
        return cls(
            ticket_id=data["ticket_id"],
            stage=ProgressStage(data["stage"]),
            message=data.get("message", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
            update_id=data.get("update_id", str(uuid.uuid4())),
        )


@dataclass
class TicketProgress:
    """Tracks progress for a single ticket."""

    ticket_id: str
    current_stage: ProgressStage = ProgressStage.STARTED
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    updates: List[ProgressUpdate] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Get execution duration in seconds."""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def is_completed(self) -> bool:
        """Check if ticket execution is completed."""
        return self.current_stage in [ProgressStage.COMPLETED, ProgressStage.FAILED]

    @property
    def progress_percentage(self) -> float:
        """Get current progress percentage."""
        return self.current_stage.percentage

    def add_update(self, update: ProgressUpdate) -> None:
        """Add a progress update."""
        self.updates.append(update)
        self.current_stage = update.stage
        if update.stage in [ProgressStage.COMPLETED, ProgressStage.FAILED]:
            self.end_time = update.timestamp

    def get_latest_update(self) -> Optional[ProgressUpdate]:
        """Get the most recent progress update."""
        return self.updates[-1] if self.updates else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "ticket_id": self.ticket_id,
            "current_stage": self.current_stage.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "progress_percentage": self.progress_percentage,
            "is_completed": self.is_completed,
            "updates": [update.to_dict() for update in self.updates],
            "metadata": self.metadata,
        }


class ProgressTracker:
    """Enhanced progress tracking system for ticket execution."""

    def __init__(self, history_file: Optional[str] = None):
        """Initialize the progress tracker.

        Args:
            history_file: Path to file for storing progress history

        """
        self.tickets: Dict[str, TicketProgress] = {}
        self.history_file = Path(history_file) if history_file else None
        self.webhooks: List[str] = []
        self.update_callbacks: List[Callable[[ProgressUpdate], None]] = []
        self._lock = threading.Lock()
        self._load_history()

    def _load_history(self) -> None:
        """Load progress history from file."""
        if not self.history_file or not self.history_file.exists():
            return

        try:
            with open(self.history_file, "r") as f:
                data = json.load(f)

            for ticket_data in data.get("tickets", []):
                ticket_id = ticket_data["ticket_id"]
                progress = TicketProgress(
                    ticket_id=ticket_id,
                    current_stage=ProgressStage(ticket_data["current_stage"]),
                    start_time=datetime.fromisoformat(ticket_data["start_time"]),
                    end_time=(
                        datetime.fromisoformat(ticket_data["end_time"])
                        if ticket_data.get("end_time")
                        else None
                    ),
                    metadata=ticket_data.get("metadata", {}),
                )

                for update_data in ticket_data.get("updates", []):
                    update = ProgressUpdate.from_dict(update_data)
                    progress.updates.append(update)

                self.tickets[ticket_id] = progress

        except (json.JSONDecodeError, KeyError, ValueError):
            # If history file is corrupted, start fresh
            pass

    def _save_history(self) -> None:
        """Save progress history to file."""
        if not self.history_file:
            return

        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "last_updated": datetime.now().isoformat(),
                "tickets": [progress.to_dict() for progress in self.tickets.values()],
            }

            with open(self.history_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception:
            # Silently fail if we can't save history
            pass

    def start_ticket(
        self,
        ticket_id: str,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Start tracking a ticket.

        Args:
            ticket_id: Unique identifier for the ticket
            message: Optional message for the start event
            metadata: Optional metadata to store with the ticket

        """
        with self._lock:
            if ticket_id in self.tickets:
                # Reset if ticket was already tracked
                self.tickets[ticket_id] = TicketProgress(ticket_id=ticket_id)
            else:
                self.tickets[ticket_id] = TicketProgress(ticket_id=ticket_id)

            if metadata:
                self.tickets[ticket_id].metadata.update(metadata)

            update = ProgressUpdate(
                ticket_id=ticket_id,
                stage=ProgressStage.STARTED,
                message=message or f"Started execution of ticket {ticket_id}",
                metadata=metadata or {},
            )

            self.tickets[ticket_id].add_update(update)
            self._notify_update(update)
            self._save_history()

    def update_progress(
        self,
        ticket_id: str,
        stage: ProgressStage,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update progress for a ticket.

        Args:
            ticket_id: Ticket identifier
            stage: New progress stage
            message: Optional message describing the update
            metadata: Optional metadata for the update

        """
        with self._lock:
            if ticket_id not in self.tickets:
                raise ValueError(
                    f"Ticket {ticket_id} not found. Call start_ticket() first."
                )

            update = ProgressUpdate(
                ticket_id=ticket_id,
                stage=stage,
                message=message or f"Moved to {stage.description}",
                metadata=metadata or {},
            )

            self.tickets[ticket_id].add_update(update)
            self._notify_update(update)
            self._save_history()

    def complete_ticket(
        self,
        ticket_id: str,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a ticket as completed.

        Args:
            ticket_id: Ticket identifier
            message: Optional completion message
            metadata: Optional metadata for the completion

        """
        self.update_progress(
            ticket_id=ticket_id,
            stage=ProgressStage.COMPLETED,
            message=message or f"Ticket {ticket_id} completed successfully",
            metadata=metadata,
        )

    def fail_ticket(
        self,
        ticket_id: str,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a ticket as failed.

        Args:
            ticket_id: Ticket identifier
            message: Optional failure message
            metadata: Optional metadata for the failure

        """
        self.update_progress(
            ticket_id=ticket_id,
            stage=ProgressStage.FAILED,
            message=message or f"Ticket {ticket_id} failed",
            metadata=metadata,
        )

    def get_ticket_progress(self, ticket_id: str) -> Optional[TicketProgress]:
        """Get progress information for a ticket.

        Args:
            ticket_id: Ticket identifier

        Returns:
            TicketProgress object or None if not found

        """
        return self.tickets.get(ticket_id)

    def get_all_tickets(self) -> Dict[str, TicketProgress]:
        """Get progress information for all tickets.

        Returns:
            Dictionary mapping ticket IDs to TicketProgress objects

        """
        return self.tickets.copy()

    def get_active_tickets(self) -> Dict[str, TicketProgress]:
        """Get progress for tickets that are still in progress.

        Returns:
            Dictionary of active tickets

        """
        return {
            ticket_id: progress
            for ticket_id, progress in self.tickets.items()
            if not progress.is_completed
        }

    def get_completed_tickets(self) -> Dict[str, TicketProgress]:
        """Get progress for completed tickets.

        Returns:
            Dictionary of completed tickets

        """
        return {
            ticket_id: progress
            for ticket_id, progress in self.tickets.items()
            if progress.is_completed
        }

    def add_webhook(self, webhook_url: str) -> None:
        """Add a webhook URL for progress notifications.

        Args:
            webhook_url: URL to send progress updates to

        """
        if webhook_url and webhook_url not in self.webhooks:
            # Basic URL validation
            try:
                parsed = urlparse(webhook_url)
                if parsed.scheme in ["http", "https"] and parsed.netloc:
                    self.webhooks.append(webhook_url)
            except Exception:
                pass

    def remove_webhook(self, webhook_url: str) -> None:
        """Remove a webhook URL.

        Args:
            webhook_url: URL to remove

        """
        if webhook_url in self.webhooks:
            self.webhooks.remove(webhook_url)

    def add_callback(self, callback: Callable[[ProgressUpdate], None]) -> None:
        """Add a callback function for progress updates.

        Args:
            callback: Function to call on each update

        """
        if callback not in self.update_callbacks:
            self.update_callbacks.append(callback)

    def remove_callback(self, callback: Callable[[ProgressUpdate], None]) -> None:
        """Remove a callback function.

        Args:
            callback: Function to remove

        """
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)

    def _notify_update(self, update: ProgressUpdate) -> None:
        """Send notifications for a progress update.

        Args:
            update: ProgressUpdate to notify about

        """
        # Call registered callbacks
        for callback in self.update_callbacks:
            try:
                callback(update)
            except Exception:
                # Silently ignore callback errors
                pass

        # Send webhooks in background thread
        if self.webhooks:
            threading.Thread(
                target=self._send_webhooks, args=(update,), daemon=True
            ).start()

    def _send_webhooks(self, update: ProgressUpdate) -> None:
        """Send webhook notifications for an update.

        Args:
            update: ProgressUpdate to send

        """
        payload = json.dumps(update.to_dict()).encode("utf-8")

        for webhook_url in self.webhooks:
            try:
                req = Request(
                    webhook_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )

                with urlopen(req, timeout=5):
                    # Successfully sent webhook
                    pass

            except Exception:
                # Silently ignore webhook errors
                pass

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all tracked tickets.

        Returns:
            Dictionary with summary statistics

        """
        total_tickets = len(self.tickets)
        active_tickets = len(self.get_active_tickets())
        completed_tickets = len(
            [
                t
                for t in self.tickets.values()
                if t.current_stage == ProgressStage.COMPLETED
            ]
        )
        failed_tickets = len(
            [
                t
                for t in self.tickets.values()
                if t.current_stage == ProgressStage.FAILED
            ]
        )

        stage_counts = {}
        for stage in ProgressStage:
            stage_counts[stage.value] = len(
                [t for t in self.tickets.values() if t.current_stage == stage]
            )

        total_duration = sum(t.duration for t in self.tickets.values())
        avg_duration = total_duration / total_tickets if total_tickets > 0 else 0

        return {
            "total_tickets": total_tickets,
            "active_tickets": active_tickets,
            "completed_tickets": completed_tickets,
            "failed_tickets": failed_tickets,
            "stage_counts": stage_counts,
            "total_duration": total_duration,
            "average_duration": avg_duration,
            "last_updated": datetime.now().isoformat(),
        }

    def clear_history(self) -> None:
        """Clear all progress history."""
        with self._lock:
            self.tickets.clear()
            if self.history_file and self.history_file.exists():
                self.history_file.unlink()

    def export_progress(self, format: str = "json") -> str:
        """Export progress data in specified format.

        Args:
            format: Export format ('json' or 'csv')

        Returns:
            Formatted progress data

        """
        if format == "json":
            return json.dumps(
                {
                    "summary": self.get_summary(),
                    "tickets": [
                        progress.to_dict() for progress in self.tickets.values()
                    ],
                },
                indent=2,
            )
        elif format == "csv":
            lines = ["ticket_id,stage,start_time,end_time,duration,progress_percentage"]
            for progress in self.tickets.values():
                lines.append(
                    f"{progress.ticket_id},{progress.current_stage.value},"
                    f"{progress.start_time.isoformat()},"
                    f"{progress.end_time.isoformat() if progress.end_time else ''},"
                    f"{progress.duration:.2f},{progress.progress_percentage:.1f}"
                )
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format}")
