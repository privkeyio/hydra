"""Refactored Ticket Workflow module - delegates to specialized modules."""

#!/usr/bin/env python3
"""Kyle's ticket-based development workflow integrated into Hydra - Refactored."""

from typing import Optional

from hydra.tickets.ticket_database import (
    get_project_summary,
    get_ticket_from_database,
    sync_tickets_to_database,
    update_ticket_in_database,
)
from hydra.tickets.ticket_executor import (
    SharedWorkspace,
    execute_single_ticket,
    execute_ticket_worker,
    get_quality_summary,
    get_shared_workspace,
    print_quality_summary,
    run_all_tickets,
)

# Import from new specialized modules
from hydra.tickets.ticket_parser import (
    build_dependency_graph,
    detect_project_context,
    get_executable_tickets,
    parse_all_tickets,
    parse_ticket,
    parse_ticket_md_legacy,
)
from hydra.tickets.ticket_status import (
    mark_ticket_completed,
    mark_ticket_in_progress,
    mark_ticket_quality_failed,
)
from hydra.tickets.ticket_validation import (
    check_for_ai_generated_code,
    run_node_validation,
    run_validation_commands,
    validate_acceptance_criteria,
    validate_code_changes,
)


def generate_tickets_md(
    project_description: str,
    output_path: str = "tickets.md",
    project_type: Optional[str] = None
):
    """Generate tickets file from project description.
    
    Args:
        project_description: Description of the project
        output_path: Path to output file
        project_type: Type of project (optional)
        
    Returns:
        Path to generated tickets file

    """
    from pathlib import Path

    from hydra.tickets.generator import TicketGenerator

    if Path(output_path).suffix not in [".yml", ".yaml"]:
        output_path = output_path.replace(".md", ".yaml")

    generator = TicketGenerator()
    return generator.generate_tickets_yaml(
        project_description, output_path, project_type
    )


# Re-export all the main functions for backward compatibility
__all__ = [
    # Parser functions
    "parse_ticket",
    "parse_ticket_md_legacy",
    "parse_all_tickets",
    "build_dependency_graph",
    "get_executable_tickets",
    "detect_project_context",

    # Executor functions
    "SharedWorkspace",
    "get_shared_workspace",
    "execute_single_ticket",
    "execute_ticket_worker",
    "run_all_tickets",
    "get_quality_summary",
    "print_quality_summary",

    # Database functions
    "update_ticket_in_database",
    "get_ticket_from_database",
    "sync_tickets_to_database",
    "get_project_summary",

    # Status functions
    "mark_ticket_in_progress",
    "mark_ticket_completed",
    "mark_ticket_quality_failed",

    # Validation functions
    "validate_acceptance_criteria",
    "validate_code_changes",
    "check_for_ai_generated_code",
    "run_validation_commands",
    "run_node_validation",

    # Generator function
    "generate_tickets_md",
]


# Convenience function for backward compatibility
def main():
    """Main entry point for ticket workflow."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: ticket_workflow.py <command> [args...]")
        print("Commands:")
        print("  execute <tickets_file> <ticket_id> - Execute a single ticket")
        print("  run-all <tickets_file> [--workers N] - Run all tickets")
        print("  generate <description> [output_file] - Generate tickets file")
        print("  sync <tickets_file> - Sync tickets to database")
        return

    command = sys.argv[1]

    if command == "execute":
        if len(sys.argv) < 4:
            print("Usage: ticket_workflow.py execute <tickets_file> <ticket_id>")
            return
        tickets_file = sys.argv[2]
        ticket_id = sys.argv[3]
        success = execute_single_ticket(tickets_file, ticket_id)
        sys.exit(0 if success else 1)

    elif command == "run-all":
        if len(sys.argv) < 3:
            print("Usage: ticket_workflow.py run-all <tickets_file> [--workers N]")
            return
        tickets_file = sys.argv[2]
        workers = 3
        if "--workers" in sys.argv:
            idx = sys.argv.index("--workers")
            if idx + 1 < len(sys.argv):
                workers = int(sys.argv[idx + 1])
        run_all_tickets(tickets_file, max_parallel=workers)

    elif command == "generate":
        if len(sys.argv) < 3:
            print("Usage: ticket_workflow.py generate <description> [output_file]")
            return
        description = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else "tickets.yaml"
        generate_tickets_md(description, output_file)

    elif command == "sync":
        if len(sys.argv) < 3:
            print("Usage: ticket_workflow.py sync <tickets_file>")
            return
        tickets_file = sys.argv[2]
        sync_tickets_to_database(tickets_file)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
