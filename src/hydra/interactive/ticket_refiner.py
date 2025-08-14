"""Ticket refinement logic for interactive ticket modification."""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from hydra.templates.project_templates import ProjectTemplateManager
from hydra.validation.dependency_validator import DependencyValidator


class RefinementAction(str, Enum):
    """Available refinement actions."""

    ADJUST_MODEL = "adjust_model"
    SPLIT_TICKET = "split_ticket"
    ADD_DEPENDENCY = "add_dependency"
    REMOVE_DEPENDENCY = "remove_dependency"
    VALIDATE_FLOWS = "validate_flows"
    UPDATE_CRITERIA = "update_criteria"
    CANCEL = "cancel"


@dataclass
class TicketData:
    """Parsed ticket data structure."""

    id: str
    title: str
    status: str
    model: str
    dependencies: List[str]
    description: str
    required_input_files: List[str]
    output_files: List[str]
    acceptance_criteria: List[str]
    progress: str = "started"


@dataclass
class RefinementSuggestion:
    """A suggestion for ticket refinement."""

    action: RefinementAction
    description: str
    reason: str
    target_ticket: Optional[str] = None
    suggested_value: Optional[str] = None


class TicketRefiner:
    """Interactive ticket refinement system."""

    def __init__(self, tickets_path: str):
        """Initialize the refiner with a tickets file."""
        self.tickets_path = Path(tickets_path)
        self.validator = DependencyValidator()
        self.template_manager = ProjectTemplateManager()
        self.tickets: Dict[str, TicketData] = {}
        self._load_tickets()

    def _load_tickets(self) -> None:
        """Load and parse all tickets from the file."""
        if not self.tickets_path.exists():
            raise FileNotFoundError(f"Tickets file not found: {self.tickets_path}")

        with open(self.tickets_path, 'r') as f:
            content = f.read()

        # Find all ticket sections
        ticket_pattern = r'## Ticket (\d+):(.*?)(?=## Ticket|\Z)'
        matches = re.finditer(ticket_pattern, content, re.DOTALL | re.IGNORECASE)

        for match in matches:
            ticket_id = match.group(1).strip()
            ticket_content = match.group(2).strip()

            ticket_data = self._parse_ticket_content(ticket_id, ticket_content)
            self.tickets[ticket_id] = ticket_data

    def _parse_ticket_content(self, ticket_id: str, content: str) -> TicketData:
        """Parse individual ticket content into structured data."""
        lines = content.split('\n')

        # Initialize with defaults
        data = TicketData(
            id=ticket_id,
            title=lines[0].strip() if lines else f"Ticket {ticket_id}",
            status="TODO",
            model="balanced",
            dependencies=[],
            description="",
            required_input_files=[],
            output_files=[],
            acceptance_criteria=[],
            progress="started"
        )

        current_section = None

        for line in lines[1:]:  # Skip title line
            line = line.strip()

            # Parse metadata fields
            if line.startswith('**Status:**'):
                data.status = line.replace('**Status:**', '').strip()
            elif line.startswith('**Model:**'):
                data.model = line.replace('**Model:**', '').strip()
            elif line.startswith('**Dependencies:**'):
                deps_text = line.replace('**Dependencies:**', '').strip()
                if deps_text and deps_text.lower() != 'none':
                    data.dependencies = [d.strip() for d in deps_text.split(',')]
            elif line.startswith('**Description:**'):
                data.description = line.replace('**Description:**', '').strip()
                current_section = 'description'
            elif line.startswith('**Progress:**'):
                data.progress = line.replace('**Progress:**', '').strip()

            # Parse section headers
            elif line.startswith('**Required Input Files:**'):
                current_section = 'required_input_files'
            elif line.startswith('**Output Files:**'):
                current_section = 'output_files'
            elif line.startswith('**Acceptance Criteria:**'):
                current_section = 'acceptance_criteria'
            elif line.startswith('**'):
                current_section = None

            # Parse list items
            elif line.startswith('- '):
                item = line[2:].strip()
                if not item or item.lower() == 'none':
                    continue

                if current_section == 'required_input_files':
                    data.required_input_files.append(item)
                elif current_section == 'output_files':
                    data.output_files.append(item)
                elif current_section == 'acceptance_criteria':
                    # Handle checkboxes
                    if item.startswith('[ ]') or item.startswith('[x]') or item.startswith('[X]'):
                        criteria = item[3:].strip()
                        if criteria:
                            data.acceptance_criteria.append(criteria)
                    else:
                        data.acceptance_criteria.append(item)

            # Handle standalone checkboxes
            elif line.startswith('- [ ]') or line.startswith('- [x]') or line.startswith('- [X]'):
                criteria = line[5:].strip()
                if criteria:
                    data.acceptance_criteria.append(criteria)

            # Continue description on multiple lines
            elif current_section == 'description' and line and not line.startswith('**'):
                data.description += ' ' + line

        return data

    def get_refinement_suggestions(self, ticket_id: str) -> List[RefinementSuggestion]:
        """Generate refinement suggestions for a ticket."""
        if ticket_id not in self.tickets:
            return []

        ticket = self.tickets[ticket_id]
        suggestions = []

        # Check model appropriateness
        model_suggestion = self._suggest_model_adjustment(ticket)
        if model_suggestion:
            suggestions.append(model_suggestion)

        # Check if ticket should be split
        split_suggestion = self._suggest_ticket_split(ticket)
        if split_suggestion:
            suggestions.append(split_suggestion)

        # Check dependency issues
        dep_suggestions = self._suggest_dependency_fixes(ticket)
        suggestions.extend(dep_suggestions)

        # Check file flow validation
        flow_suggestion = self._suggest_file_flow_validation(ticket)
        if flow_suggestion:
            suggestions.append(flow_suggestion)

        return suggestions

    def _suggest_model_adjustment(self, ticket: TicketData) -> Optional[RefinementSuggestion]:
        """Suggest model adjustments based on ticket complexity."""
        criteria_count = len(ticket.acceptance_criteria)
        output_files_count = len(ticket.output_files)

        # Suggest smart model for complex tickets
        if criteria_count >= 6 or output_files_count >= 3:
            if ticket.model != 'smart':
                return RefinementSuggestion(
                    action=RefinementAction.ADJUST_MODEL,
                    description=f"Consider using 'smart' model for Ticket {ticket.id}",
                    reason=f"High complexity: {criteria_count} criteria, {output_files_count} output files",
                    target_ticket=ticket.id,
                    suggested_value='smart'
                )

        # Suggest coder model for implementation-heavy tickets
        if any('implement' in criteria.lower() or 'create' in criteria.lower()
               for criteria in ticket.acceptance_criteria):
            if ticket.model != 'coder':
                return RefinementSuggestion(
                    action=RefinementAction.ADJUST_MODEL,
                    description=f"Consider using 'coder' model for Ticket {ticket.id}",
                    reason="Heavy implementation requirements detected",
                    target_ticket=ticket.id,
                    suggested_value='coder'
                )

        return None

    def _suggest_ticket_split(self, ticket: TicketData) -> Optional[RefinementSuggestion]:
        """Suggest splitting large tickets."""
        criteria_count = len(ticket.acceptance_criteria)
        output_files_count = len(ticket.output_files)

        if criteria_count > 8 or output_files_count > 4:
            return RefinementSuggestion(
                action=RefinementAction.SPLIT_TICKET,
                description=f"Consider splitting Ticket {ticket.id} into smaller tickets",
                reason=f"Large scope: {criteria_count} criteria, {output_files_count} output files",
                target_ticket=ticket.id
            )

        return None

    def _suggest_dependency_fixes(self, ticket: TicketData) -> List[RefinementSuggestion]:
        """Suggest dependency-related fixes."""
        suggestions = []

        # Check for missing dependencies based on required input files
        for input_file in ticket.required_input_files:
            if '(from Ticket ' in input_file:
                # Extract source ticket from input file reference
                match = re.search(r'\(from Ticket (\d+)\)', input_file)
                if match:
                    source_ticket = match.group(1)
                    if source_ticket not in ticket.dependencies:
                        suggestions.append(RefinementSuggestion(
                            action=RefinementAction.ADD_DEPENDENCY,
                            description=f"Add missing dependency on Ticket {source_ticket}",
                            reason=f"Ticket {ticket.id} requires file from Ticket {source_ticket}",
                            target_ticket=ticket.id,
                            suggested_value=source_ticket
                        ))

        # Check for circular dependencies
        circular_deps = self._detect_circular_dependencies(ticket.id)
        if circular_deps:
            suggestions.append(RefinementSuggestion(
                action=RefinementAction.REMOVE_DEPENDENCY,
                description=f"Remove circular dependency in Ticket {ticket.id}",
                reason=f"Circular dependency detected: {' -> '.join(circular_deps)}",
                target_ticket=ticket.id
            ))

        return suggestions

    def _suggest_file_flow_validation(self, ticket: TicketData) -> Optional[RefinementSuggestion]:
        """Suggest file flow validation."""
        if ticket.required_input_files or ticket.dependencies:
            return RefinementSuggestion(
                action=RefinementAction.VALIDATE_FLOWS,
                description=f"Validate file flows for Ticket {ticket.id}",
                reason="Ticket has dependencies or required input files",
                target_ticket=ticket.id
            )

        return None

    def _detect_circular_dependencies(self, ticket_id: str, visited: Optional[Set[str]] = None) -> Optional[List[str]]:
        """Detect circular dependencies starting from a ticket."""
        if visited is None:
            visited = set()

        if ticket_id in visited:
            return [ticket_id]

        if ticket_id not in self.tickets:
            return None

        visited.add(ticket_id)
        ticket = self.tickets[ticket_id]

        for dep in ticket.dependencies:
            cycle = self._detect_circular_dependencies(dep, visited.copy())
            if cycle:
                return [ticket_id] + cycle

        return None

    def adjust_model(self, ticket_id: str, new_model: str) -> bool:
        """Adjust the model for a ticket."""
        valid_models = ['smart', 'balanced', 'coder', 'fast']
        if new_model not in valid_models:
            return False

        if ticket_id not in self.tickets:
            return False

        self.tickets[ticket_id].model = new_model
        return True

    def add_dependency(self, ticket_id: str, dependency: str) -> bool:
        """Add a dependency to a ticket."""
        if ticket_id not in self.tickets:
            return False

        if dependency not in self.tickets[ticket_id].dependencies:
            self.tickets[ticket_id].dependencies.append(dependency)

        return True

    def remove_dependency(self, ticket_id: str, dependency: str) -> bool:
        """Remove a dependency from a ticket."""
        if ticket_id not in self.tickets:
            return False

        if dependency in self.tickets[ticket_id].dependencies:
            self.tickets[ticket_id].dependencies.remove(dependency)

        return True

    def split_ticket(self, ticket_id: str, split_criteria: List[int]) -> Tuple[str, str]:
        """Split a ticket into two tickets based on criteria indices."""
        if ticket_id not in self.tickets:
            raise ValueError(f"Ticket {ticket_id} not found")

        original = self.tickets[ticket_id]

        # Create two new ticket IDs
        next_id = str(max(int(tid) for tid in self.tickets.keys()) + 1)
        new_ticket_id = str(int(next_id))

        # Split acceptance criteria
        original_criteria = []
        new_criteria = []

        for i, criteria in enumerate(original.acceptance_criteria):
            if i in split_criteria:
                new_criteria.append(criteria)
            else:
                original_criteria.append(criteria)

        # Update original ticket
        original.acceptance_criteria = original_criteria
        original.title = f"{original.title} (Part 1)"

        # Create new ticket
        new_ticket = TicketData(
            id=new_ticket_id,
            title=f"{original.title.replace(' (Part 1)', '')} (Part 2)",
            status=original.status,
            model=original.model,
            dependencies=original.dependencies.copy(),
            description=original.description,
            required_input_files=original.required_input_files.copy(),
            output_files=[],  # To be specified by user
            acceptance_criteria=new_criteria
        )

        # Add dependency from new ticket to original
        new_ticket.dependencies.append(ticket_id)

        self.tickets[new_ticket_id] = new_ticket

        return ticket_id, new_ticket_id

    def validate_file_flows(self, ticket_id: str) -> Dict[str, any]:
        """Validate file flows for a specific ticket using dependency validator."""
        validation_result = self.validator.validate_ticket_dependencies(str(self.tickets_path))

        # Filter results for the specific ticket
        ticket_issues = [
            issue for issue in validation_result.issues
            if issue.ticket_id == ticket_id
        ]

        ticket_flows = [
            flow for flow in validation_result.file_flows
            if flow.target_ticket == ticket_id or flow.source_ticket == ticket_id
        ]

        return {
            'valid': len(ticket_issues) == 0,
            'issues': ticket_issues,
            'flows': ticket_flows,
            'suggestions': [
                issue.suggested_fix for issue in ticket_issues
                if issue.suggested_fix
            ]
        }

    def save_changes(self) -> bool:
        """Save all changes back to the tickets file."""
        try:
            # Read the original file to preserve formatting
            with open(self.tickets_path, 'r') as f:
                content = f.read()

            # Update each ticket section
            for ticket_id, ticket_data in self.tickets.items():
                updated_section = self._format_ticket_section(ticket_data)

                # Find and replace the ticket section
                pattern = rf'(## Ticket {ticket_id}:.*?)(?=## Ticket|\Z)'
                content = re.sub(pattern, updated_section, content, flags=re.DOTALL)

            # Write back to file
            with open(self.tickets_path, 'w') as f:
                f.write(content)

            return True

        except Exception:
            return False

    def _format_ticket_section(self, ticket: TicketData) -> str:
        """Format a ticket into markdown section."""
        lines = [f"## Ticket {ticket.id}: {ticket.title}"]
        lines.append(f"**Status:** {ticket.status}")
        lines.append(f"**Model:** {ticket.model}")

        deps_str = ','.join(ticket.dependencies) if ticket.dependencies else 'None'
        lines.append(f"**Dependencies:** {deps_str}")
        lines.append(f"**Description:** {ticket.description}")
        lines.append(f"**Progress:** {ticket.progress}")
        lines.append("")

        lines.append("**Required Input Files:**")
        if ticket.required_input_files:
            for file in ticket.required_input_files:
                lines.append(f"- {file}")
        else:
            lines.append("- None")
        lines.append("")

        lines.append("**Output Files:**")
        if ticket.output_files:
            for file in ticket.output_files:
                lines.append(f"- {file}")
        else:
            lines.append("- None")
        lines.append("")

        lines.append("**Acceptance Criteria:**")
        if ticket.acceptance_criteria:
            for criteria in ticket.acceptance_criteria:
                lines.append(f"- [ ] {criteria}")
        else:
            lines.append("- None")

        return '\n'.join(lines) + '\n\n---\n'

    def get_ticket_list(self) -> List[Tuple[str, str, str]]:
        """Get list of all tickets with id, title, and status."""
        return [
            (ticket.id, ticket.title, ticket.status)
            for ticket in self.tickets.values()
        ]

    def get_ticket_details(self, ticket_id: str) -> Optional[TicketData]:
        """Get detailed information about a specific ticket."""
        return self.tickets.get(ticket_id)
