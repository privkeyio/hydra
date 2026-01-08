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
    parse_all_tickets,
    parse_ticket,
    parse_tickets_from_file,
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
    from pathlib import Path
    
    # Convert .md to .yaml for internal generation
    if output_path.endswith('.md'):
        yaml_path = output_path.replace('.md', '.yaml')
    else:
        yaml_path = output_path
        
    generator = TicketGenerator()
    success = generator.generate_tickets_yaml(
        project_description=description,
        output_path=yaml_path,
        project_type=project_type
    )
    
    # If requested .md file, create a simple markdown version from YAML
    if success and output_path.endswith('.md'):
        try:
            yaml_file = Path(yaml_path)
            md_file = Path(output_path)
            
            if yaml_file.exists():
                # Parse YAML and create basic MD format
                import yaml
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                
                md_content = f"# {data.get('project', {}).get('name', 'Project')} Tickets\n\n"
                
                tickets = data.get('tickets', [])
                for ticket in tickets:
                    md_content += f"## Ticket {ticket.get('id', '???')}: {ticket.get('title', 'Untitled')}\n\n"
                    md_content += f"**Status:** {ticket.get('status', 'TODO')}\n"
                    md_content += f"**Priority**: {ticket.get('priority', 1)}\n"
                    md_content += f"**Model**: {ticket.get('model', 'balanced')}\n"
                    md_content += f"**Description**: {ticket.get('description', '')}\n\n"
                    
                    criteria = ticket.get('acceptance_criteria', [])
                    if criteria:
                        md_content += "**Acceptance Criteria:**\n"
                        for criterion in criteria:
                            md_content += f"- [ ] {criterion}\n"
                        md_content += "\n"
                    
                    deps = ticket.get('dependencies', [])
                    if deps:
                        md_content += f"**Dependencies**: {', '.join(deps)}\n\n"
                
                md_file.write_text(md_content)
        except Exception as e:
            print(f"Warning: Could not create MD file: {e}")
    
    return success

def run_all_tickets(tickets_path: str = "tickets.md", max_parallel: int = 3, skip_preflight: bool = False):
    """Execute all tickets - delegate to ticket executor."""
    from hydra.tickets.ticket_executor import run_all_tickets as _run_all_tickets
    return _run_all_tickets(tickets_path, max_parallel, skip_preflight)


def build_dependency_graph(tickets: list) -> tuple:
    """Build dependency graph for tickets.
    
    Args:
        tickets: List of ticket dictionaries or ticket IDs
        
    Returns:
        Tuple of (graph, reverse_graph) dictionaries
    """
    graph = {}
    reverse_graph = {}
    
    # Handle both ticket dictionaries and ticket IDs
    for ticket in tickets:
        if isinstance(ticket, dict):
            ticket_id = ticket.get('id', '')
            dependencies = ticket.get('dependencies', [])
        else:
            # If ticket is just a string ID, assume no dependencies
            ticket_id = str(ticket)
            dependencies = []
            
        graph[ticket_id] = dependencies
        
        # Build reverse graph (dependents)
        if ticket_id not in reverse_graph:
            reverse_graph[ticket_id] = []
        for dep in dependencies:
            if dep not in reverse_graph:
                reverse_graph[dep] = []
            reverse_graph[dep].append(ticket_id)
    
    return graph, reverse_graph


def get_quality_summary(tickets_file: str) -> dict:
    """Get quality summary for tickets file.
    
    Args:
        tickets_file: Path to tickets file
        
    Returns:
        Dictionary with quality metrics
    """
    try:
        tickets = parse_all_tickets(tickets_file)
        total = len(tickets)
        completed = sum(1 for t in tickets if t.get('status') == 'DONE')
        
        return {
            "total_tickets": total,
            "completed_tickets": completed,
            "completion_rate": completed / total if total > 0 else 0,
            "quality_score": 85.0,  # Mock quality score
            "issues_found": 0
        }
    except Exception as e:
        return {
            "total_tickets": 0,
            "completed_tickets": 0,
            "completion_rate": 0,
            "quality_score": 0,
            "issues_found": 1,
            "error": str(e)
        }

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
    'build_dependency_graph',
    'get_quality_summary',
]
