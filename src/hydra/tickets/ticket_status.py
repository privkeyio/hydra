"""Ticket status management module - handles ticket status updates in files."""

import os
import re
from typing import Optional

import yaml


# Valid ticket statuses
class TicketStatus:
    """Valid ticket status values."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    PARTIAL = "PARTIAL"  # Work done but criteria not fully met
    DONE = "DONE"
    QUALITY_FAILED = "QUALITY_FAILED"
    BLOCKED = "BLOCKED"


def mark_ticket_in_progress(tickets_path: str, ticket_identifier: str):
    """Mark ticket as IN_PROGRESS in tickets file (YAML or MD).
    
    Args:
        tickets_path: Path to the tickets file
        ticket_identifier: ID of the ticket to mark as in progress

    """
    if not os.path.exists(tickets_path):
        return

    # Check if it's YAML format
    if tickets_path.endswith((".yaml", ".yml")):
        with open(tickets_path, "r") as f:
            data = yaml.safe_load(f)

        # Update ticket status
        for ticket in data.get("tickets", []):
            if str(ticket.get("id", "")) == str(ticket_identifier):
                ticket["status"] = "IN_PROGRESS"
                break

        # Write back
        with open(tickets_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        return

    # Legacy MD format handling
    # Normalize ticket ID to 3 digits if it's numeric
    if ticket_identifier.isdigit():
        ticket_identifier = ticket_identifier.zfill(3)

    with open(tickets_path, "r") as f:
        content = f.read()

    # Try multiple ticket header patterns
    patterns = [
        rf"(## Ticket {ticket_identifier}:.*?)(?=## Ticket|\Z)",
        rf"(## TICKET-{ticket_identifier}:.*?)(?=## TICKET-|\Z)",
        rf"(## Ticket-{ticket_identifier}:.*?)(?=## Ticket-|\Z)",
        rf"(## #{ticket_identifier}:.*?)(?=## #|\Z)",
        rf"(## {ticket_identifier}:.*?)(?=## |\Z)",
    ]

    updated_content = content
    ticket_found = False

    for pattern in patterns:
        def replace_ticket(match):
            ticket_content = match.group(1)
            # Update Status field to IN_PROGRESS
            updated_content = re.sub(
                r"\*\*Status:\*\*\s*\w+", "**Status:** IN_PROGRESS", ticket_content
            )
            return updated_content

        flags = re.DOTALL | re.IGNORECASE
        new_content = re.sub(pattern, replace_ticket, updated_content, flags=flags)
        if new_content != updated_content:
            updated_content = new_content
            ticket_found = True
            break

    if ticket_found:
        with open(tickets_path, "w") as f:
            f.write(updated_content)
        print(f"📝 Updated ticket {ticket_identifier} status to IN_PROGRESS")
    else:
        print(f"⚠️  Could not find ticket {ticket_identifier} to update status")


def mark_ticket_completed(tickets_path: str, ticket_identifier: str):
    """Mark ticket as completed in tickets file.
    
    Args:
        tickets_path: Path to the tickets file
        ticket_identifier: ID of the ticket to mark as completed

    """
    from hydra.tickets.ticket_database import update_ticket_in_database

    if not os.path.exists(tickets_path):
        return

    # Update database
    project_path = os.path.dirname(os.path.abspath(tickets_path))
    update_ticket_in_database(ticket_identifier, "DONE", project_path)

    # Check if it's YAML format
    if tickets_path.endswith((".yaml", ".yml")):
        with open(tickets_path, "r") as f:
            data = yaml.safe_load(f)

        # Update ticket status
        for ticket in data.get("tickets", []):
            if str(ticket.get("id", "")) == str(ticket_identifier):
                ticket["status"] = "DONE"
                break

        # Write back
        with open(tickets_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        print(f"✅ Marked ticket {ticket_identifier} as DONE in {tickets_path}")
        return

    # Legacy MD format handling
    # Normalize ticket ID to 3 digits if it's numeric
    if ticket_identifier.isdigit():
        ticket_identifier = ticket_identifier.zfill(3)

    with open(tickets_path, "r") as f:
        content = f.read()

    # Try multiple ticket header patterns
    patterns = [
        rf"(## Ticket {ticket_identifier}:.*?)(?=## Ticket|\Z)",
        rf"(## TICKET-{ticket_identifier}:.*?)(?=## TICKET-|\Z)",
        rf"(## Ticket-{ticket_identifier}:.*?)(?=## Ticket-|\Z)",
        rf"(## #{ticket_identifier}:.*?)(?=## #|\Z)",
        rf"(## {ticket_identifier}:.*?)(?=## |\Z)",
    ]

    updated_content = content
    ticket_found = False

    for pattern in patterns:
        def replace_ticket(match):
            ticket_content = match.group(1)
            # Update Status field to DONE
            updated_content = re.sub(
                r"\*\*Status:\*\*\s*\w+", "**Status:** DONE", ticket_content
            )
            # Also check all criteria boxes
            updated_content = re.sub(r"- \[ \]", "- [x]", updated_content)
            return updated_content

        flags = re.DOTALL | re.IGNORECASE
        new_content = re.sub(pattern, replace_ticket, updated_content, flags=flags)
        if new_content != updated_content:
            updated_content = new_content
            ticket_found = True
            break

    if ticket_found:
        with open(tickets_path, "w") as f:
            f.write(updated_content)
        print(f"✅ Marked ticket {ticket_identifier} as DONE in {tickets_path}")
    else:
        print(f"⚠️  Could not find ticket {ticket_identifier} to mark as completed")


def mark_ticket_quality_failed(
    tickets_path: str,
    ticket_identifier: str,
    quality_report: Optional[dict] = None
):
    """Mark ticket as quality failed.
    
    Args:
        tickets_path: Path to the tickets file
        ticket_identifier: ID of the ticket to mark as quality failed
        quality_report: Optional quality report details

    """
    from hydra.tickets.ticket_database import update_ticket_in_database

    if not os.path.exists(tickets_path):
        return

    # Update database
    project_path = os.path.dirname(os.path.abspath(tickets_path))
    update_ticket_in_database(ticket_identifier, "QUALITY_FAILED", project_path)

    # Check if it's YAML format
    if tickets_path.endswith((".yaml", ".yml")):
        with open(tickets_path, "r") as f:
            data = yaml.safe_load(f)

        # Update ticket status
        for ticket in data.get("tickets", []):
            if str(ticket.get("id", "")) == str(ticket_identifier):
                ticket["status"] = "QUALITY_FAILED"
                if quality_report:
                    ticket["quality_notes"] = str(quality_report)
                break

        # Write back
        with open(tickets_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        print(f"❌ Marked ticket {ticket_identifier} as QUALITY_FAILED in {tickets_path}")
        return

    # Legacy MD format handling
    # Normalize ticket ID to 3 digits if it's numeric
    if ticket_identifier.isdigit():
        ticket_identifier = ticket_identifier.zfill(3)

    with open(tickets_path, "r") as f:
        content = f.read()

    # Try multiple ticket header patterns
    patterns = [
        rf"(## Ticket {ticket_identifier}:.*?)(?=## Ticket|\Z)",
        rf"(## TICKET-{ticket_identifier}:.*?)(?=## TICKET-|\Z)",
        rf"(## Ticket-{ticket_identifier}:.*?)(?=## Ticket-|\Z)",
        rf"(## #{ticket_identifier}:.*?)(?=## #|\Z)",
        rf"(## {ticket_identifier}:.*?)(?=## |\Z)",
    ]

    updated_content = content
    ticket_found = False

    for pattern in patterns:
        def replace_ticket(match):
            ticket_content = match.group(1)
            # Update Status field to QUALITY_FAILED
            updated_content = re.sub(
                r"\*\*Status:\*\*\s*\w+", "**Status:** QUALITY_FAILED", ticket_content
            )

            # Add quality failure note if not already present
            if "**Quality Issues:**" not in updated_content and quality_report:
                # Insert quality issues after status line
                lines = updated_content.split("\n")
                for i, line in enumerate(lines):
                    if "**Status:** QUALITY_FAILED" in line:
                        lines.insert(
                            i + 1, "**Quality Issues:** See quality report for details"
                        )
                        break
                updated_content = "\n".join(lines)

            return updated_content

        flags = re.DOTALL | re.IGNORECASE
        new_content = re.sub(pattern, replace_ticket, updated_content, flags=flags)
        if new_content != updated_content:
            updated_content = new_content
            ticket_found = True
            break

    if ticket_found:
        with open(tickets_path, "w") as f:
            f.write(updated_content)
        print(f"❌ Marked ticket {ticket_identifier} as QUALITY_FAILED in {tickets_path}")
    else:
        print(f"⚠️  Could not find ticket {ticket_identifier} to mark as quality failed")


def update_ticket_status(tickets_path: str, ticket_identifier: str, status: str):
    """Update ticket status to any valid status.
    
    Args:
        tickets_path: Path to the tickets file
        ticket_identifier: ID of the ticket to update
        status: New status (TODO, IN_PROGRESS, PARTIAL, DONE, QUALITY_FAILED, BLOCKED)
    
    """
    # Validate status
    valid_statuses = [
        TicketStatus.TODO,
        TicketStatus.IN_PROGRESS,
        TicketStatus.PARTIAL,
        TicketStatus.DONE,
        TicketStatus.QUALITY_FAILED,
        TicketStatus.BLOCKED
    ]

    if status not in valid_statuses:
        print(f"⚠️  Invalid status '{status}'. Valid statuses: {', '.join(valid_statuses)}")
        return

    if not os.path.exists(tickets_path):
        return

    # Check if it's YAML format
    if tickets_path.endswith((".yaml", ".yml")):
        with open(tickets_path, "r") as f:
            data = yaml.safe_load(f)

        # Update ticket status
        for ticket in data.get("tickets", []):
            if str(ticket.get("id", "")) == str(ticket_identifier):
                ticket["status"] = status
                # Add completed flag for DONE status
                if status == TicketStatus.DONE:
                    ticket["completed"] = True
                elif status == TicketStatus.PARTIAL:
                    ticket["completed"] = False
                    ticket["partial_completion"] = True
                else:
                    ticket["completed"] = False
                break

        # Write back
        with open(tickets_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        status_emoji = {
            TicketStatus.TODO: "📝",
            TicketStatus.IN_PROGRESS: "🔄",
            TicketStatus.PARTIAL: "⚠️",
            TicketStatus.DONE: "✅",
            TicketStatus.QUALITY_FAILED: "❌",
            TicketStatus.BLOCKED: "🚫"
        }

        print(f"{status_emoji.get(status, '📌')} Updated ticket {ticket_identifier} status to {status}")
        return

    # Legacy MD format handling
    # Normalize ticket ID to 3 digits if it's numeric
    if ticket_identifier.isdigit():
        ticket_identifier = ticket_identifier.zfill(3)

    with open(tickets_path, "r") as f:
        content = f.read()

    # Try multiple ticket header patterns
    patterns = [
        rf"(## Ticket {ticket_identifier}:.*?)(?=## Ticket|\Z)",
        rf"(## TICKET-{ticket_identifier}:.*?)(?=## TICKET-|\Z)",
        rf"(## Ticket-{ticket_identifier}:.*?)(?=## Ticket-|\Z)",
        rf"(## #{ticket_identifier}:.*?)(?=## #|\Z)",
        rf"(## {ticket_identifier}:.*?)(?=## |\Z)",
    ]

    updated_content = content
    ticket_found = False

    for pattern in patterns:
        def replace_ticket(match):
            ticket_content = match.group(1)
            # Update Status field
            updated_content = re.sub(
                r"\*\*Status:\*\*\s*\w+", f"**Status:** {status}", ticket_content
            )
            return updated_content

        new_content, replacements = re.subn(
            pattern, replace_ticket, updated_content, flags=re.DOTALL
        )

        if replacements > 0:
            updated_content = new_content
            ticket_found = True
            break

    if ticket_found:
        with open(tickets_path, "w") as f:
            f.write(updated_content)
        print(f"📝 Updated ticket {ticket_identifier} status to {status}")
    else:
        print(f"⚠️  Could not find ticket {ticket_identifier} to update status")
