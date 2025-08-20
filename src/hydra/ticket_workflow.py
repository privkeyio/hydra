"""Clean ticket workflow module - delegates to refactored components.

This module provides the main entry points for ticket workflow operations
while delegating to the refactored modules in the tickets/ directory.
"""

# Import main functions from refactored modules
from hydra.tickets.generator import TicketGenerator
from hydra.tickets.ticket_database import (
    get_ticket_from_database,
    update_ticket_in_database,
)
from hydra.tickets.ticket_executor import (
    SharedWorkspace,
    execute_single_ticket,
    execute_tickets_parallel,
)
from hydra.tickets.ticket_parser import (
    get_ticket_dependencies,
    parse_ticket,
    parse_tickets_from_file,
    parse_all_tickets,
    validate_ticket_dependencies,
)
from hydra.tickets.ticket_status import (
    mark_ticket_completed,
    mark_ticket_in_progress,
    mark_ticket_quality_failed,
)
from hydra.tickets.ticket_validation import (
    check_for_ai_generated_code,
    validate_acceptance_criteria,
    validate_code_changes,
)


# Export key functions for compatibility
def generate_tickets(description: str, output_path: str) -> bool:
    """Generate tickets from description."""
    generator = TicketGenerator()
    return generator.generate_tickets_yaml(description, output_path)

# Missing functions needed by CLI
def generate_tickets_md(description: str, output_path: str = "tickets.md", project_type: str = None) -> bool:
    """Generate tickets file from project description (legacy MD format support).
    
    Args:
        description: Project description
        output_path: Output file path 
        project_type: Optional project type
        
    Returns:
        True if successful

    """
    # Convert .md to .yaml for modern format
    if output_path.endswith('.md'):
        yaml_path = output_path.replace('.md', '.yaml')
    else:
        yaml_path = output_path

    generator = TicketGenerator()
    return generator.generate_tickets_yaml(description, yaml_path, project_type)

def run_all_tickets(tickets_path: str = "tickets.md", max_parallel: int = 3, skip_preflight: bool = False):
    """Execute all tickets - delegate to ticket executor."""
    from hydra.tickets.ticket_executor import run_all_tickets as _run_all_tickets
    return _run_all_tickets(tickets_path, max_parallel, skip_preflight)

# Re-export main functions for backwards compatibility
__all__ = [
    'parse_ticket',
    'parse_tickets_from_file',
    'parse_all_tickets',
    'get_ticket_dependencies',
    'validate_ticket_dependencies',
    'execute_single_ticket',
    'execute_tickets_parallel',
    'SharedWorkspace',
    'update_ticket_in_database',
    'get_ticket_from_database',
    'mark_ticket_completed',
    'mark_ticket_in_progress',
    'mark_ticket_quality_failed',
    'validate_acceptance_criteria',
    'validate_code_changes',
    'check_for_ai_generated_code',
    'generate_tickets_md',
    'run_all_tickets',
]
