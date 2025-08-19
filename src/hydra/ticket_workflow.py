"""Clean ticket workflow module - delegates to refactored components.

This module provides the main entry points for ticket workflow operations
while delegating to the refactored modules in the tickets/ directory.
"""

# Import main functions from refactored modules
from hydra.tickets.ticket_parser import (
    parse_ticket,
    parse_tickets_from_file,
    get_ticket_dependencies,
    validate_ticket_dependencies,
)

from hydra.tickets.ticket_executor import (
    execute_single_ticket,
    execute_tickets_parallel,
    SharedWorkspace,
)

from hydra.tickets.ticket_database import (
    update_ticket_in_database,
    get_ticket_from_database,
)

from hydra.tickets.ticket_status import (
    mark_ticket_completed,
    mark_ticket_in_progress,
    mark_ticket_quality_failed,
)

from hydra.tickets.ticket_validation import (
    validate_acceptance_criteria,
    validate_code_changes,
    check_for_ai_generated_code,
)

# Re-export main functions for backwards compatibility
__all__ = [
    'parse_ticket',
    'parse_tickets_from_file', 
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
]

# Legacy function aliases for backwards compatibility
def run_all_tickets(tickets_path: str, max_workers: int = 4, **kwargs):
    """Legacy alias for execute_tickets_parallel."""
    return execute_tickets_parallel(tickets_path, max_workers, **kwargs)

def validate_tickets(tickets_path: str, **kwargs):
    """Legacy alias for ticket validation."""
    from hydra.tickets.ticket_validation import validate_all_tickets
    return validate_all_tickets(tickets_path, **kwargs)