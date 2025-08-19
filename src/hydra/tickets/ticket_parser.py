"""Ticket parsing module - extracts and processes ticket information from various formats."""

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from hydra.caching import get_cache_key, get_file_meta_cache
from hydra.tickets.compatibility import TicketFormatHandler


def parse_ticket(tickets_path: str, ticket_identifier: str) -> Optional[dict]:
    """Parse specific ticket from tickets file.
    
    Args:
        tickets_path: Path to the tickets file (YAML or MD)
        ticket_identifier: ID of the ticket to parse (e.g., '001')
        
    Returns:
        Dictionary containing parsed ticket data or None if not found

    """
    handler = TicketFormatHandler()
    ticket = handler.parse_ticket(tickets_path, ticket_identifier)

    if ticket:
        # Cache the result
        cache = get_file_meta_cache()
        cache_key = get_cache_key(tickets_path, ticket_identifier)
        cache.set(cache_key, ticket, tickets_path)

    return ticket


def parse_tickets_from_file(tickets_path: str) -> List[dict]:
    """Parse all tickets from a tickets file.
    
    Args:
        tickets_path: Path to the tickets file (YAML or MD)
        
    Returns:
        List of dictionaries containing parsed ticket data
    
    """
    handler = TicketFormatHandler()
    # This function needs to be implemented in the handler
    return handler.parse_all_tickets(tickets_path)


def get_ticket_dependencies(tickets_path: str, ticket_identifier: str) -> List[str]:
    """Get dependencies for a specific ticket.
    
    Args:
        tickets_path: Path to the tickets file
        ticket_identifier: ID of the ticket
        
    Returns:
        List of ticket IDs that this ticket depends on
    
    """
    ticket = parse_ticket(tickets_path, ticket_identifier)
    if ticket:
        return ticket.get('dependencies', [])
    return []


def validate_ticket_dependencies(tickets_path: str) -> bool:
    """Validate that all ticket dependencies exist.
    
    Args:
        tickets_path: Path to the tickets file
        
    Returns:
        True if all dependencies are valid, False otherwise
    
    """
    tickets = parse_tickets_from_file(tickets_path)
    ticket_ids = set(ticket.get('id', ticket.get('ticket_number', '')) for ticket in tickets)
    
    for ticket in tickets:
        dependencies = ticket.get('dependencies', [])
        for dep in dependencies:
            if dep not in ticket_ids:
                print(f"❌ Ticket {ticket.get('id', 'unknown')} has invalid dependency: {dep}")
                return False
    return True


def parse_ticket_md_legacy(tickets_path: str, ticket_identifier: str) -> Optional[dict]:
    """Legacy MD parser kept for backward compatibility.
    
    Args:
        tickets_path: Path to the markdown tickets file
        ticket_identifier: ID of the ticket to parse
        
    Returns:
        Dictionary containing parsed ticket data or None if not found

    """
    if not os.path.exists(tickets_path):
        print(f"❌ {tickets_path} not found")
        return None

    # Check cache first
    cache = get_file_meta_cache()
    cache_key = get_cache_key(tickets_path, ticket_identifier)
    cached_result = cache.get(cache_key, tickets_path)

    if cached_result is not None:
        return cached_result

    with open(tickets_path, "r") as f:
        content = f.read()

    # Normalize identifier - add TICKET- prefix if just a number
    if ticket_identifier.isdigit():
        # Try with TICKET- prefix first for numbered identifiers
        patterns = [
            rf"### TICKET-{ticket_identifier}:(.*?)(?=### TICKET-|\Z)",
            rf"## TICKET-{ticket_identifier}:(.*?)(?=## TICKET-|\Z)",
            rf"## Ticket-{ticket_identifier}:(.*?)(?=## Ticket-|\Z)",
            rf"## Ticket {ticket_identifier}:(.*?)(?=## Ticket|\Z)",
            rf"## #{ticket_identifier}:(.*?)(?=## #|\Z)",
            rf"## {ticket_identifier}:(.*?)(?=## |\Z)",
        ]
    else:
        # Already has prefix, use as-is
        patterns = [
            rf"### {ticket_identifier}:(.*?)(?=### TICKET-|\Z)",
            rf"## {ticket_identifier}:(.*?)(?=## TICKET-|\Z)",
        ]

    match = None

    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            break

    if not match:
        print(f"❌ Ticket {ticket_identifier} not found")
        print("📋 Available ticket patterns found:")
        # Show available tickets for debugging
        ticket_headers = re.findall(
            r"##+ (TICKET-\d+|Ticket-\d+|Ticket \d+|#\d+|\d+):", content, re.IGNORECASE
        )
        for header in ticket_headers[:10]:  # Show first 10
            print(f"   - {header}")
        if len(ticket_headers) > 10:
            print(f"   ... and {len(ticket_headers) - 10} more")
        return None

    ticket_content = match.group(1).strip()
    lines = ticket_content.split("\n")

    ticket = {
        "number": ticket_identifier,
        "title": lines[0].strip(),
        "description": "",
        "status": "TODO",  # Default status
        "model": "balanced",  # Default to balanced model
        "acceptance_criteria": [],
        "dependencies": [],
        "completed": False,
    }

    # Check if ticket is already completed
    if "✅ COMPLETED" in ticket["title"] or "COMPLETED" in ticket["title"]:
        ticket["completed"] = True

    in_criteria = False
    unchecked_criteria = 0
    checked_criteria = 0

    for line in lines[1:]:
        line = line.strip()
        # Check for status line (markdown bold syntax: **Status**:)
        if len(line) >= 11 and line[:11] == "**Status**:":
            status_text = line.replace("**Status**:", "").strip().upper()
            ticket["status"] = status_text
            # Mark as completed if status is DONE
            if status_text == "DONE":
                ticket["completed"] = True
            # Don't mark as completed if quality failed
            elif status_text == "QUALITY_FAILED":
                ticket["completed"] = False
                ticket["quality_failed"] = True
        elif len(line) >= 10 and line[:10] == "**Model:**":
            # Use model mapper to handle both legacy and new model categories
            from hydra.providers.model_mapper import get_model_mapper

            mapper = get_model_mapper()
            model_text = line.replace("**Model:**", "").strip().lower()

            # Map to model category (fast, balanced, smart, coder)
            category = mapper.get_model_category(model_text)
            if category:
                ticket["model"] = category.value
            else:
                # Default to balanced if unknown
                ticket["model"] = "balanced"
        elif len(line) >= 17 and line[:17] == "**Dependencies:**":
            # Parse simplified dependency format: "001,002,003" or "None"
            deps_text = line.replace("**Dependencies:**", "").strip()
            if deps_text.lower() not in ["none", "n/a", "-", ""]:
                # Split by comma and normalize to 3 digits
                deps = deps_text.split(",")
                for dep in deps:
                    dep = dep.strip()
                    if dep.isdigit():
                        ticket["dependencies"].append(dep.zfill(3))
        elif line.startswith("**Description:**"):
            # Capture single-line description
            ticket["description"] = line.replace("**Description:**", "").strip()
        elif len(line) >= 24 and line[:24] == "**Acceptance Criteria:**":
            in_criteria = True
        elif line.startswith("- [ ]"):
            criteria = line.replace("- [ ]", "").strip()
            ticket["acceptance_criteria"].append(criteria)
            unchecked_criteria += 1
        elif line.startswith("- [x]"):
            # Already completed criteria - still add to list but mark as done
            criteria = line.replace("- [x]", "").strip()
            ticket["acceptance_criteria"].append(f"✅ {criteria}")
            checked_criteria += 1
        elif line.startswith("##"):
            # Stop parsing if we hit another section header
            break
        elif (
            not in_criteria
            and line
            and not line.startswith("**")
            and not ticket["description"]
        ):
            # Only capture additional description if we don't have one yet
            ticket["description"] = line

    # Mark ticket as completed if all acceptance criteria are checked
    if unchecked_criteria == 0 and checked_criteria > 0:
        ticket["completed"] = True
        print(
            f"✅ Ticket {ticket_identifier} is already completed (all {checked_criteria} criteria checked)"
        )

    # Cache the parsed ticket
    cache.set(cache_key, ticket, tickets_path)

    return ticket


def parse_all_tickets(tickets_path: str) -> Dict[str, dict]:
    """Parse all tickets and return as dictionary with consistent internal IDs.
    
    Args:
        tickets_path: Path to the tickets file
        
    Returns:
        Dictionary mapping ticket IDs to ticket data

    """
    if not os.path.exists(tickets_path):
        return {}

    # Check cache first
    cache = get_file_meta_cache()
    cache_key = get_cache_key("parse_all_tickets", tickets_path)
    cached_result = cache.get(cache_key, tickets_path)

    if cached_result is not None:
        return cached_result

    # Use the unified TicketFormatHandler for both YAML and MD
    handler = TicketFormatHandler()

    # Get all ticket IDs
    ticket_ids = handler.get_ticket_ids(tickets_path)

    tickets = {}
    for ticket_id in ticket_ids:
        ticket = handler.parse_ticket(tickets_path, ticket_id)
        if ticket:
            # Store with normalized 3-digit key
            normalized_id = ticket_id.zfill(3)
            tickets[normalized_id] = ticket
            # Store the original format for execution
            tickets[normalized_id]["raw_id"] = ticket_id

    # Cache the parsed tickets
    cache.set(cache_key, tickets, tickets_path)

    return tickets


def build_dependency_graph(
    tickets: Dict[str, dict],
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build dependency and reverse dependency graphs.
    
    Args:
        tickets: Dictionary of parsed tickets
        
    Returns:
        Tuple of (dependencies dict, reverse dependencies dict)

    """
    deps = defaultdict(set)
    reverse_deps = defaultdict(set)

    for ticket_id, ticket_data in tickets.items():
        normalized_id = ticket_id.zfill(3)
        for dep in ticket_data.get("dependencies", []):
            normalized_dep = dep.zfill(3)
            deps[normalized_id].add(normalized_dep)
            reverse_deps[normalized_dep].add(normalized_id)

    return dict(deps), dict(reverse_deps)


def get_executable_tickets(tickets: Dict[str, dict], completed: Set[str]) -> List[str]:
    """Get tickets that can be executed based on dependency status.
    
    Args:
        tickets: Dictionary of all tickets
        completed: Set of completed ticket IDs
        
    Returns:
        List of ticket IDs that can be executed

    """
    executable = []
    for ticket_id, ticket_data in tickets.items():
        # Skip already completed tickets
        if ticket_id in completed:
            continue

        # Check if all dependencies are satisfied
        deps_satisfied = True
        for dep in ticket_data.get("dependencies", []):
            normalized_dep = dep.zfill(3)
            if normalized_dep not in completed:
                deps_satisfied = False
                break

        if deps_satisfied:
            executable.append(ticket_id)

    return executable


def detect_project_context(tickets_path: str) -> dict:
    """Detect project context from directory structure.
    
    Args:
        tickets_path: Path to the tickets file
        
    Returns:
        Dictionary containing project context information

    """
    # Get the directory containing the tickets file
    project_dir = os.path.dirname(os.path.abspath(tickets_path))

    context = {
        "language": "unknown",
        "framework": None,
        "build_tool": None,
        "test_framework": None,
        "dependencies": [],
        "project_type": "unknown",
    }

    # Check for language/framework indicators
    if os.path.exists(os.path.join(project_dir, "package.json")):
        context["language"] = "javascript"
        context["build_tool"] = "npm"

        # Try to detect framework from package.json
        try:
            import json
            with open(os.path.join(project_dir, "package.json"), "r") as f:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

                if "react" in deps:
                    context["framework"] = "react"
                    context["project_type"] = "react_app"
                elif "vue" in deps:
                    context["framework"] = "vue"
                    context["project_type"] = "vue_app"
                elif "express" in deps:
                    context["framework"] = "express"
                    context["project_type"] = "node_server"
                elif "@angular/core" in deps:
                    context["framework"] = "angular"
                    context["project_type"] = "angular_app"

                if "jest" in deps:
                    context["test_framework"] = "jest"
                elif "mocha" in deps:
                    context["test_framework"] = "mocha"
                elif "vitest" in deps:
                    context["test_framework"] = "vitest"

                context["dependencies"] = list(deps.keys())
        except Exception as e:
            print(f"Warning: Could not parse package.json: {e}")

    elif os.path.exists(os.path.join(project_dir, "requirements.txt")) or os.path.exists(
        os.path.join(project_dir, "setup.py")
    ):
        context["language"] = "python"
        context["build_tool"] = "pip"

        # Check for common Python frameworks
        req_file = os.path.join(project_dir, "requirements.txt")
        if os.path.exists(req_file):
            try:
                with open(req_file, "r") as f:
                    requirements = f.read().lower()
                    if "django" in requirements:
                        context["framework"] = "django"
                        context["project_type"] = "django_app"
                    elif "flask" in requirements:
                        context["framework"] = "flask"
                        context["project_type"] = "flask_app"
                    elif "fastapi" in requirements:
                        context["framework"] = "fastapi"
                        context["project_type"] = "fastapi_app"

                    if "pytest" in requirements:
                        context["test_framework"] = "pytest"
                    elif "unittest" in requirements:
                        context["test_framework"] = "unittest"
            except Exception as e:
                print(f"Warning: Could not parse requirements.txt: {e}")

    elif os.path.exists(os.path.join(project_dir, "Cargo.toml")):
        context["language"] = "rust"
        context["build_tool"] = "cargo"
        context["test_framework"] = "cargo_test"
        context["project_type"] = "rust_project"

    elif os.path.exists(os.path.join(project_dir, "go.mod")):
        context["language"] = "go"
        context["build_tool"] = "go"
        context["test_framework"] = "go_test"
        context["project_type"] = "go_project"

    return context
