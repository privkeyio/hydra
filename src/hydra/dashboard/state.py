"""Dashboard state management."""

import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class TicketStatus(Enum):
    """Ticket execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class TicketInfo:
    """Information about a ticket."""

    ticket_id: str
    title: str
    model: str
    status: TicketStatus
    dependencies: List[str]
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    files_changed: List[str] = field(default_factory=list)
    quality_status: Optional[str] = None


@dataclass
class ExecutionSession:
    """Execution session information."""

    session_id: str
    start_time: float
    tickets_path: str
    total_tickets: int
    completed_tickets: int
    failed_tickets: int
    current_wave: int
    total_waves: int
    workers: int


class DashboardState:
    """Manages dashboard state."""

    def __init__(self, state_dir: Optional[str] = None):
        if state_dir:
            self.state_dir = Path(state_dir)
        else:
            self.state_dir = Path.home() / ".hydra" / "dashboard"

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "state.json"

        self.tickets: Dict[str, TicketInfo] = {}
        self.session: Optional[ExecutionSession] = None
        self.lock = threading.Lock()

        self._load_state()

    def _load_state(self):
        """Load state from disk."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)

                for ticket_data in data.get("tickets", []):
                    ticket = TicketInfo(
                        ticket_id=ticket_data["ticket_id"],
                        title=ticket_data["title"],
                        model=ticket_data["model"],
                        status=TicketStatus(ticket_data["status"]),
                        dependencies=ticket_data["dependencies"],
                        start_time=ticket_data.get("start_time"),
                        end_time=ticket_data.get("end_time"),
                        error=ticket_data.get("error"),
                        logs=ticket_data.get("logs", []),
                        files_changed=ticket_data.get("files_changed", []),
                        quality_status=ticket_data.get("quality_status"),
                    )
                    self.tickets[ticket.ticket_id] = ticket

                session_data = data.get("session")
                if session_data:
                    self.session = ExecutionSession(
                        session_id=session_data["session_id"],
                        start_time=session_data["start_time"],
                        tickets_path=session_data["tickets_path"],
                        total_tickets=session_data["total_tickets"],
                        completed_tickets=session_data["completed_tickets"],
                        failed_tickets=session_data["failed_tickets"],
                        current_wave=session_data["current_wave"],
                        total_waves=session_data["total_waves"],
                        workers=session_data["workers"],
                    )

            except Exception:
                pass

    def _save_state(self):
        """Save state to disk. Assumes lock is already held."""
        data = {
            "tickets": [
                {
                    "ticket_id": t.ticket_id,
                    "title": t.title,
                    "model": t.model,
                    "status": t.status.value,
                    "dependencies": t.dependencies,
                    "start_time": t.start_time,
                    "end_time": t.end_time,
                    "error": t.error,
                    "logs": t.logs,
                    "files_changed": t.files_changed,
                    "quality_status": t.quality_status,
                }
                for t in self.tickets.values()
            ],
            "session": (
                {
                    "session_id": self.session.session_id,
                    "start_time": self.session.start_time,
                    "tickets_path": self.session.tickets_path,
                    "total_tickets": self.session.total_tickets,
                    "completed_tickets": self.session.completed_tickets,
                    "failed_tickets": self.session.failed_tickets,
                    "current_wave": self.session.current_wave,
                    "total_waves": self.session.total_waves,
                    "workers": self.session.workers,
                }
                if self.session
                else None
            ),
        }

        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def start_session(
        self,
        session_id: str,
        tickets_path: str,
        total_tickets: int,
        total_waves: int,
        workers: int,
    ):
        """Start a new execution session."""
        with self.lock:
            self.session = ExecutionSession(
                session_id=session_id,
                start_time=time.time(),
                tickets_path=tickets_path,
                total_tickets=total_tickets,
                completed_tickets=0,
                failed_tickets=0,
                current_wave=1,
                total_waves=total_waves,
                workers=workers,
            )
            self.tickets.clear()
            self._save_state()

    def add_ticket(
        self, ticket_id: str, title: str, model: str, dependencies: List[str]
    ):
        """Add a ticket to tracking."""
        with self.lock:
            self.tickets[ticket_id] = TicketInfo(
                ticket_id=ticket_id,
                title=title,
                model=model,
                status=TicketStatus.PENDING,
                dependencies=dependencies,
            )
            self._save_state()

    def update_ticket_status(
        self, ticket_id: str, status: TicketStatus, error: Optional[str] = None
    ):
        """Update ticket status."""
        with self.lock:
            if ticket_id in self.tickets:
                ticket = self.tickets[ticket_id]
                ticket.status = status

                if status == TicketStatus.RUNNING:
                    ticket.start_time = time.time()
                elif status in [TicketStatus.COMPLETED, TicketStatus.FAILED]:
                    ticket.end_time = time.time()

                    if self.session:
                        if status == TicketStatus.COMPLETED:
                            self.session.completed_tickets += 1
                        else:
                            self.session.failed_tickets += 1

                if error:
                    ticket.error = error

                self._save_state()

    def add_ticket_log(self, ticket_id: str, log_entry: str):
        """Add log entry for a ticket."""
        with self.lock:
            if ticket_id in self.tickets:
                self.tickets[ticket_id].logs.append(log_entry)
                self._save_state()

    def update_wave(self, wave_number: int):
        """Update current wave number."""
        with self.lock:
            if self.session:
                self.session.current_wave = wave_number
                self._save_state()

    def get_state(self) -> Dict:
        """Get current state as dictionary."""
        with self.lock:
            return {
                "session": (
                    {
                        "session_id": self.session.session_id,
                        "start_time": self.session.start_time,
                        "elapsed_time": time.time() - self.session.start_time,
                        "tickets_path": self.session.tickets_path,
                        "total_tickets": self.session.total_tickets,
                        "completed_tickets": self.session.completed_tickets,
                        "failed_tickets": self.session.failed_tickets,
                        "pending_tickets": self.session.total_tickets
                        - self.session.completed_tickets
                        - self.session.failed_tickets,
                        "current_wave": self.session.current_wave,
                        "total_waves": self.session.total_waves,
                        "workers": self.session.workers,
                        "progress": (
                            self.session.completed_tickets
                            / self.session.total_tickets
                            * 100
                            if self.session.total_tickets > 0
                            else 0
                        ),
                    }
                    if self.session
                    else None
                ),
                "tickets": [
                    {
                        "ticket_id": t.ticket_id,
                        "title": t.title,
                        "model": t.model,
                        "status": t.status.value,
                        "dependencies": t.dependencies,
                        "start_time": t.start_time,
                        "end_time": t.end_time,
                        "duration": (
                            t.end_time - t.start_time
                            if t.start_time and t.end_time
                            else None
                        ),
                        "error": t.error,
                        "logs": t.logs[-10:],  # Last 10 log entries
                        "files_changed": t.files_changed,
                        "quality_status": t.quality_status,
                    }
                    for t in sorted(self.tickets.values(), key=lambda x: x.ticket_id)
                ],
            }

    def clear(self):
        """Clear all state."""
        with self.lock:
            self.tickets.clear()
            self.session = None
            if self.state_file.exists():
                self.state_file.unlink()
