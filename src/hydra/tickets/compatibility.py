"""Compatibility layer for MD and YAML ticket formats."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from hydra.tickets.yaml_handler import TicketYAMLHandler


class TicketFormatHandler:
    """Handles both MD and YAML ticket formats transparently."""

    def __init__(self):
        self.yaml_handler = TicketYAMLHandler(strict_mode=False)

    def detect_format(self, file_path: str) -> str:
        """Detect ticket file format.

        Args:
            file_path: Path to ticket file

        Returns:
            'yaml', 'md', or 'unknown'

        """
        path = Path(file_path)

        if not path.exists():
            if path.suffix in [".yml", ".yaml"]:
                return "yaml"
            elif path.suffix == ".md":
                return "md"
            else:
                return "yaml"

        # First check file extension - more reliable
        if path.suffix in [".yml", ".yaml"]:
            return "yaml"
        elif path.suffix == ".md":
            return "md"
        
        # If no clear extension, check content
        with open(path, "r", encoding="utf-8") as f:
            content = f.read(500)  # Read first 500 chars
            
        # Skip comment lines for detection
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # First non-comment line
            if line.startswith("version:") or line.startswith("tickets:") or line.startswith("project:"):
                return "yaml"
            elif line.startswith("##"):
                return "md"
            break
        
        # Try to parse as YAML as fallback
        try:
            import yaml
            with open(path, "r") as f:
                yaml.safe_load(f)
            return "yaml"
        except:
            return "md"

    def parse_ticket(self, file_path: str, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Parse a single ticket from either format.

        Args:
            file_path: Path to ticket file
            ticket_id: ID of ticket to parse

        Returns:
            Ticket dictionary or None

        """
        format_type = self.detect_format(file_path)

        if format_type == "yaml":
            try:
                data = self.yaml_handler.load_tickets(file_path)
                return self.yaml_handler.parse_single_ticket(data, ticket_id)
            except Exception as e:
                print(f"YAML parse failed, trying MD: {e}")
                format_type = "md"

        if format_type == "md":
            # Use legacy MD parser directly to avoid circular import
            from hydra.tickets.ticket_parser import parse_ticket_md_legacy

            return parse_ticket_md_legacy(file_path, ticket_id)

        return None

    def get_ticket_ids(self, file_path: str) -> list:
        """Get all ticket IDs from either format.

        Args:
            file_path: Path to ticket file

        Returns:
            List of ticket IDs

        """
        format_type = self.detect_format(file_path)

        if format_type == "yaml":
            try:
                import yaml

                with open(file_path, "r") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and "tickets" in data:
                    return [str(t.get("id", "")) for t in data["tickets"]]
                return []
            except Exception as e:
                print(f"YAML load failed, trying MD: {e}")
                format_type = "md"

        if format_type == "md":
            import re

            with open(file_path, "r") as f:
                content = f.read()

            ticket_patterns = [
                r"## Ticket (\d+):",
                r"## TICKET-(\d+):",
                r"## Ticket-(\d+):",
                r"## \w+-(\d+):",
                r"### TICKET-(\d+):",
                r"## #(\d+):",
                r"## (\d+):",
            ]

            for pattern in ticket_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    return matches

        return []

    def get_all_tickets(self, file_path: str) -> Dict[str, Dict[str, Any]]:
        """Get all tickets from either format.

        Args:
            file_path: Path to ticket file

        Returns:
            Dictionary of tickets keyed by ID

        """
        format_type = self.detect_format(file_path)

        if format_type == "yaml":
            try:
                return self.yaml_handler.get_all_tickets(file_path)
            except Exception as e:
                print(f"YAML load failed, trying MD: {e}")
                format_type = "md"

        if format_type == "md":
            result = {}
            with open(file_path, "r") as f:
                content = f.read()

            import re

            ticket_ids = re.findall(
                r"## (?:Ticket |TICKET-)?(\d{3}):", content, re.IGNORECASE
            )

            for ticket_id in ticket_ids:
                from hydra.tickets.ticket_parser import parse_ticket_md_legacy

                ticket = parse_ticket_md_legacy(file_path, ticket_id)
                if ticket:
                    result[ticket_id] = ticket

            return result

        return {}

    def parse_all_tickets(self, file_path: str) -> list:
        """Parse all tickets from either format as a list.

        Args:
            file_path: Path to ticket file

        Returns:
            List of ticket dictionaries

        """
        all_tickets = self.get_all_tickets(file_path)
        return list(all_tickets.values())

    def update_ticket_status(self, file_path: str, ticket_id: str, status: str) -> None:
        """Update ticket status in either format.

        Args:
            file_path: Path to ticket file
            ticket_id: ID of ticket to update
            status: New status

        """
        format_type = self.detect_format(file_path)

        if format_type == "yaml":
            self.yaml_handler.update_ticket_status(file_path, ticket_id, status)
        else:
            if status == "DONE":
                from hydra.tickets.ticket_status import mark_ticket_completed

                mark_ticket_completed(file_path, ticket_id)
            elif status == "IN_PROGRESS":
                from hydra.tickets.ticket_status import mark_ticket_in_progress

                mark_ticket_in_progress(file_path, ticket_id)

    def convert_md_to_yaml(self, md_path: str, yaml_path: str) -> bool:
        """Convert MD tickets to YAML format.

        Args:
            md_path: Path to MD file
            yaml_path: Path to save YAML file

        Returns:
            True if successful

        """
        try:
            tickets_dict = self.get_all_tickets(md_path)

            tickets_list = []
            for ticket_id, ticket in sorted(tickets_dict.items()):
                yaml_ticket = {
                    "id": ticket_id,
                    "title": ticket.get("title", ""),
                    "status": ticket.get("status", "TODO"),
                    "priority": ticket.get("priority", 5),
                    "model": ticket.get("model", "balanced"),
                    "description": ticket.get("description", ""),
                    "acceptance_criteria": ticket.get("acceptance_criteria", []),
                    "dependencies": ticket.get("dependencies", []),
                }
                tickets_list.append(yaml_ticket)

            data = {
                "version": "1.0",
                "project": {
                    "name": Path(md_path).parent.name,
                    "path": str(Path(md_path).parent.absolute()),
                    "created_at": datetime.now().isoformat(),
                },
                "tickets": tickets_list,
            }

            self.yaml_handler.save_tickets(data, yaml_path)
            return True

        except Exception as e:
            print(f"Conversion failed: {e}")
            return False
