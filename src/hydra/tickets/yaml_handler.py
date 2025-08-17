"""YAML ticket format handler."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class TicketYAMLHandler:
    """Handles reading and writing tickets in YAML format."""

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode

    def load_tickets(self, file_path: str) -> Dict[str, Any]:
        """Load tickets from YAML file.

        Args:
            file_path: Path to YAML file

        Returns:
            Dictionary containing tickets data

        Raises:
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If YAML is invalid
            ValueError: If required fields are missing

        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Tickets file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if self.strict_mode:
            self._validate_structure(data)

        return data

    def save_tickets(self, data: Dict[str, Any], file_path: str) -> None:
        """Save tickets to YAML file.

        Args:
            data: Tickets data dictionary
            file_path: Path to save YAML file

        Raises:
            ValueError: If data validation fails

        """
        if self.strict_mode:
            self._validate_structure(data)

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=1000,
                line_break=None,
            )

    def parse_single_ticket(
        self, data: Dict[str, Any], ticket_id: str
    ) -> Optional[Dict[str, Any]]:
        """Extract a single ticket from loaded data.

        Args:
            data: Full tickets data
            ticket_id: ID of ticket to extract

        Returns:
            Ticket dictionary or None if not found

        """
        tickets = data.get("tickets", [])
        for ticket in tickets:
            if str(ticket.get("id")) == str(ticket_id):
                return self._normalize_ticket(ticket)
        return None

    def _normalize_ticket(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize ticket to expected format.

        Args:
            ticket: Raw ticket data

        Returns:
            Normalized ticket dictionary

        """
        normalized = {
            "number": str(ticket.get("id", "")),
            "title": ticket.get("title", ""),
            "description": ticket.get("description", ""),
            "status": ticket.get("status", "TODO"),
            "model": ticket.get("model", "balanced"),
            "priority": ticket.get("priority", 5),
            "dependencies": [],
            "acceptance_criteria": [],
            "completed": ticket.get("status") == "DONE",
        }

        deps = ticket.get("dependencies", [])
        if isinstance(deps, list):
            if deps and isinstance(deps[0], dict):
                normalized["dependencies"] = [str(d.get("ticket_id", "")) for d in deps]
            else:
                normalized["dependencies"] = [str(d) for d in deps]

        criteria = ticket.get("acceptance_criteria", [])
        if isinstance(criteria, list):
            if criteria and isinstance(criteria[0], dict):
                normalized["acceptance_criteria"] = [
                    c.get("criterion", "") if isinstance(c, dict) else str(c)
                    for c in criteria
                ]
            else:
                normalized["acceptance_criteria"] = [str(c) for c in criteria]

        return normalized

    def _validate_structure(self, data: Dict[str, Any]) -> None:
        """Validate YAML structure.

        Args:
            data: Data to validate

        Raises:
            ValueError: If validation fails

        """
        if not isinstance(data, dict):
            raise ValueError("Root must be a dictionary")

        if "tickets" not in data:
            raise ValueError("Missing 'tickets' field")

        tickets = data["tickets"]
        if not isinstance(tickets, list):
            raise ValueError("'tickets' must be a list")

        for i, ticket in enumerate(tickets):
            if not isinstance(ticket, dict):
                raise ValueError(f"Ticket {i} must be a dictionary")

            required = ["id", "title", "status"]
            for field in required:
                if field not in ticket:
                    raise ValueError(f"Ticket {i} missing required field: {field}")

    def update_ticket_status(self, file_path: str, ticket_id: str, status: str) -> None:
        """Update status of a specific ticket.

        Args:
            file_path: Path to YAML file
            ticket_id: ID of ticket to update
            status: New status value

        Raises:
            ValueError: If ticket not found

        """
        data = self.load_tickets(file_path)
        tickets = data.get("tickets", [])

        found = False
        for ticket in tickets:
            if str(ticket.get("id")) == str(ticket_id):
                ticket["status"] = status
                if status == "DONE":
                    ticket["completed_at"] = datetime.now().isoformat()
                elif status == "IN_PROGRESS" and not ticket.get("started_at"):
                    ticket["started_at"] = datetime.now().isoformat()
                found = True
                break

        if not found:
            raise ValueError(f"Ticket {ticket_id} not found")

        self.save_tickets(data, file_path)

    def add_ticket(self, file_path: str, ticket: Dict[str, Any]) -> None:
        """Add a new ticket to the file.

        Args:
            file_path: Path to YAML file
            ticket: Ticket data to add

        """
        if Path(file_path).exists():
            data = self.load_tickets(file_path)
        else:
            data = {"version": "1.0", "tickets": []}

        data["tickets"].append(ticket)
        self.save_tickets(data, file_path)

    def get_all_tickets(self, file_path: str) -> Dict[str, Dict[str, Any]]:
        """Get all tickets as a dictionary keyed by ID.

        Args:
            file_path: Path to YAML file

        Returns:
            Dictionary of tickets keyed by ticket ID

        """
        data = self.load_tickets(file_path)
        result = {}

        for ticket in data.get("tickets", []):
            ticket_id = str(ticket.get("id", ""))
            if ticket_id:
                result[ticket_id] = self._normalize_ticket(ticket)

        return result
