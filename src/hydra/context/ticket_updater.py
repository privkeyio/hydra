"""Automatic Ticket Updater for Forward References.

This module updates future tickets in tickets.md to replace generic references
like "doc created by ticket X" with actual filenames once those files are created.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from hydra.context import ArtifactTracker, TicketArtifact
from hydra.ticket_workflow import parse_ticket


class TicketUpdater:
    """Updates future tickets with actual artifact names from completed tickets."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.tickets_path = self.project_root / "tickets.md"
        self.artifact_tracker = ArtifactTracker(project_root)

        # Patterns to match generic references
        self.reference_patterns = [
            # "doc/document/file/report created by ticket X"
            (r'(doc|document|file|report|spec|design|schema|config|audit)\s+(?:created|generated|produced|from)\s+(?:by\s+)?[Tt]icket\s+(\d+)',
             'file_reference'),
            # "outputs from ticket X"
            (r'outputs?\s+(?:from|of)\s+[Tt]icket\s+(\d+)', 'outputs_reference'),
            # "artifacts from ticket X"
            (r'artifacts?\s+(?:from|of)\s+[Tt]icket\s+(\d+)', 'artifacts_reference'),
            # "ticket X's file/doc/etc"
            (r'[Tt]icket\s+(\d+)(?:\'s?|\s+)\s*(file|doc|document|report|spec|design|schema|config|audit)',
             'possessive_reference'),
            # Generic "from Ticket X" that might need updating
            (r'\(from [Tt]icket (\d+)\)', 'parenthetical_reference'),
        ]

    def update_future_tickets(self, completed_ticket_id: str, artifacts: List[TicketArtifact]) -> int:
        """Update all future tickets that reference this completed ticket's artifacts.
        
        Args:
            completed_ticket_id: The ticket that just completed
            artifacts: List of artifacts created by the completed ticket
            
        Returns:
            Number of updates made

        """
        if not self.tickets_path.exists():
            return 0

        if not artifacts:
            return 0

        # Read current tickets.md
        with open(self.tickets_path, 'r') as f:
            content = f.read()

        original_content = content
        updates_made = 0

        # Find all tickets that depend on this completed ticket
        dependent_tickets = self._find_dependent_tickets(completed_ticket_id)

        if dependent_tickets:
            print(f"🔄 Found {len(dependent_tickets)} tickets that depend on Ticket {completed_ticket_id}")

            # Create artifact mappings for easy reference
            artifact_map = self._create_artifact_map(artifacts)

            # Update each dependent ticket section
            for dep_ticket_id in dependent_tickets:
                ticket_updates = self._update_ticket_section(
                    content, dep_ticket_id, completed_ticket_id, artifact_map
                )
                if ticket_updates:
                    content = ticket_updates
                    updates_made += 1
                    print(f"   ✏️ Updated Ticket {dep_ticket_id} with specific file references")

        # Also update any tickets that might reference this ticket without formal dependency
        content, informal_updates = self._update_informal_references(
            content, completed_ticket_id, artifacts
        )
        updates_made += informal_updates

        # Save if changes were made
        if content != original_content:
            with open(self.tickets_path, 'w') as f:
                f.write(content)
            print(f"✅ Updated {updates_made} ticket sections with specific artifact references")

        return updates_made

    def _find_dependent_tickets(self, ticket_id: str) -> List[str]:
        """Find all tickets that list this ticket as a dependency."""
        dependent_tickets = []

        with open(self.tickets_path, 'r') as f:
            content = f.read()

        # Find all ticket IDs first
        ticket_pattern = r'## Ticket (\d+):'
        all_tickets = re.findall(ticket_pattern, content)

        # Check each ticket's dependencies
        for check_ticket_id in all_tickets:
            ticket_data = parse_ticket(str(self.tickets_path), check_ticket_id)
            if ticket_data:
                dependencies = ticket_data.get('dependencies', [])
                if ticket_id in dependencies:
                    dependent_tickets.append(check_ticket_id)

        return dependent_tickets

    def _create_artifact_map(self, artifacts: List[TicketArtifact]) -> Dict[str, TicketArtifact]:
        """Create a map of artifact types to artifacts for easy lookup."""
        artifact_map = {
            'doc': [],
            'document': [],
            'file': [],
            'report': [],
            'spec': [],
            'design': [],
            'schema': [],
            'config': [],
            'audit': [],
            'api': [],
            'test': [],
            'script': [],
            'module': [],
        }

        # Categorize artifacts by type
        for artifact in artifacts:
            if artifact.operation == 'deleted':
                continue

            file_lower = artifact.file_path.lower()
            desc_lower = (artifact.description or '').lower()

            # Categorize based on filename and description
            if 'report' in file_lower or 'report' in desc_lower:
                artifact_map['report'].append(artifact)
                artifact_map['doc'].append(artifact)
                artifact_map['document'].append(artifact)
            elif 'audit' in file_lower or 'audit' in desc_lower:
                artifact_map['audit'].append(artifact)
                artifact_map['report'].append(artifact)
                artifact_map['doc'].append(artifact)
            elif 'spec' in file_lower or 'specification' in desc_lower:
                artifact_map['spec'].append(artifact)
                artifact_map['doc'].append(artifact)
            elif 'design' in file_lower or 'design' in desc_lower:
                artifact_map['design'].append(artifact)
                artifact_map['doc'].append(artifact)
            elif 'schema' in file_lower or 'schema' in desc_lower:
                artifact_map['schema'].append(artifact)
                artifact_map['file'].append(artifact)
            elif 'config' in file_lower or 'configuration' in desc_lower:
                artifact_map['config'].append(artifact)
                artifact_map['file'].append(artifact)
            elif 'api' in file_lower or 'endpoint' in desc_lower:
                artifact_map['api'].append(artifact)
                artifact_map['file'].append(artifact)
            elif 'test' in file_lower or 'test' in desc_lower:
                artifact_map['test'].append(artifact)
                artifact_map['file'].append(artifact)
            elif file_lower.endswith('.py'):
                artifact_map['module'].append(artifact)
                artifact_map['file'].append(artifact)
            elif file_lower.endswith('.js') or file_lower.endswith('.ts'):
                artifact_map['script'].append(artifact)
                artifact_map['file'].append(artifact)
            elif file_lower.endswith('.md'):
                artifact_map['doc'].append(artifact)
                artifact_map['document'].append(artifact)
            else:
                # Generic file
                artifact_map['file'].append(artifact)

        # Remove duplicates from each category
        for key in artifact_map:
            seen = set()
            unique = []
            for artifact in artifact_map[key]:
                if artifact.file_path not in seen:
                    seen.add(artifact.file_path)
                    unique.append(artifact)
            artifact_map[key] = unique

        return artifact_map

    def _update_ticket_section(
        self,
        content: str,
        ticket_id: str,
        referenced_ticket: str,
        artifact_map: Dict[str, List[TicketArtifact]]
    ) -> Optional[str]:
        """Update a specific ticket section with actual file references.
        
        Args:
            content: The full tickets.md content
            ticket_id: The ticket to update
            referenced_ticket: The ticket being referenced
            artifact_map: Map of artifact types to artifacts
            
        Returns:
            Updated content or None if no updates made

        """
        # Find the ticket section
        pattern = rf'(## Ticket {ticket_id}:.*?)(?=## Ticket \d+:|$)'
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            return None

        ticket_section = match.group(1)
        original_section = ticket_section

        # Apply reference updates
        for pattern, ref_type in self.reference_patterns:
            # Look for references to the completed ticket
            if ref_type == 'file_reference':
                # Pattern captures: (file_type, ticket_number)
                for match in re.finditer(pattern, ticket_section, re.IGNORECASE):
                    file_type = match.group(1).lower()
                    ticket_num = match.group(2)

                    if ticket_num == referenced_ticket:
                        # Get matching artifacts
                        matching_artifacts = artifact_map.get(file_type, [])
                        if matching_artifacts:
                            # Use the first/most relevant artifact
                            artifact = matching_artifacts[0]
                            replacement = f"{artifact.file_path} (from Ticket {referenced_ticket})"
                            ticket_section = ticket_section.replace(match.group(0), replacement)

            elif ref_type == 'possessive_reference':
                # Pattern captures: (ticket_number, file_type)
                for match in re.finditer(pattern, ticket_section, re.IGNORECASE):
                    ticket_num = match.group(1)
                    file_type = match.group(2).lower()

                    if ticket_num == referenced_ticket:
                        matching_artifacts = artifact_map.get(file_type, [])
                        if matching_artifacts:
                            artifact = matching_artifacts[0]
                            replacement = f"{artifact.file_path} (Ticket {referenced_ticket}'s {file_type})"
                            ticket_section = ticket_section.replace(match.group(0), replacement)

            elif ref_type == 'parenthetical_reference':
                # Update generic "(from Ticket X)" to include file list
                pattern_specific = rf'\(from [Tt]icket {referenced_ticket}\)'
                matches = list(re.finditer(pattern_specific, ticket_section))

                for match in matches:
                    # Check what's before the parenthetical to determine context
                    before_text = ticket_section[:match.start()].split('\n')[-1]

                    # If it's in a list item about a file, try to be more specific
                    if '- ' in before_text and not any(
                        artifact.file_path in before_text
                        for artifacts in artifact_map.values()
                        for artifact in artifacts
                    ):
                        # This is likely a generic reference that needs updating
                        all_artifacts = [a for artifacts in artifact_map.values() for a in artifacts]
                        if all_artifacts:
                            # Create a brief list of main artifacts
                            main_files = [a.file_path for a in all_artifacts[:3]]
                            if len(all_artifacts) > 3:
                                file_list = ', '.join(main_files) + f" and {len(all_artifacts)-3} more"
                            else:
                                file_list = ', '.join(main_files)
                            replacement = f"(from Ticket {referenced_ticket}: {file_list})"
                            ticket_section = ticket_section.replace(match.group(0), replacement)

        # Update "Required Input Files" section if it exists
        ticket_section = self._update_required_files_section(
            ticket_section, referenced_ticket, artifact_map
        )

        if ticket_section != original_section:
            # Replace the section in the full content
            content = content.replace(original_section, ticket_section)
            return content

        return None

    def _update_required_files_section(
        self,
        section: str,
        referenced_ticket: str,
        artifact_map: Dict[str, List[TicketArtifact]]
    ) -> str:
        """Update the Required Input Files section with actual filenames."""
        # Find Required Input Files section
        files_pattern = r'(\*\*Required Input Files:\*\*.*?)(?=\*\*|\n##|$)'
        match = re.search(files_pattern, section, re.DOTALL)

        if match:
            files_section = match.group(1)
            original_files = files_section

            # Look for generic references in this section
            lines = files_section.split('\n')
            updated_lines = []

            for line in lines:
                if f"from Ticket {referenced_ticket}" in line:
                    # This line references our completed ticket
                    updated_line = line

                    # Try to identify what type of file is being referenced
                    for file_type, artifacts in artifact_map.items():
                        if file_type in line.lower() and artifacts:
                            # Replace generic reference with specific file
                            artifact = artifacts[0]
                            # Check if line already has a specific filename
                            if not any(a.file_path in line for a in artifacts):
                                # Replace generic description with specific file
                                if ' - ' in line:
                                    # It's a list item with description
                                    updated_line = f"- {artifact.file_path} (from Ticket {referenced_ticket}) - {artifact.description or 'File'}"
                                else:
                                    updated_line = f"- {artifact.file_path} (from Ticket {referenced_ticket})"
                            break

                    updated_lines.append(updated_line)
                else:
                    updated_lines.append(line)

            updated_files = '\n'.join(updated_lines)
            if updated_files != original_files:
                section = section.replace(original_files, updated_files)

        return section

    def _update_informal_references(
        self,
        content: str,
        completed_ticket: str,
        artifacts: List[TicketArtifact]
    ) -> Tuple[str, int]:
        """Update any informal references to this ticket throughout the document.
        
        Returns:
            Tuple of (updated_content, number_of_updates)

        """
        updates = 0

        if not artifacts:
            return content, updates

        # Create a simple mapping of likely references
        artifact_map = self._create_artifact_map(artifacts)

        # Look for informal references outside of dependency declarations
        # For example: "Use the audit from ticket 001"
        informal_patterns = [
            rf'(?:the|a)\s+(audit|report|design|spec|schema|config|doc|document)\s+from\s+[Tt]icket\s+{completed_ticket}',
            rf'[Tt]icket\s+{completed_ticket}\'s\s+(audit|report|design|spec|schema|config|doc|document)',
            rf'(audit|report|design|spec|schema|config|doc|document)\s+(?:created|generated)\s+in\s+[Tt]icket\s+{completed_ticket}',
        ]

        for pattern in informal_patterns:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            for match in matches:
                file_type = match.group(1).lower()
                matching_artifacts = artifact_map.get(file_type, [])

                if matching_artifacts:
                    artifact = matching_artifacts[0]
                    # Create a more specific reference
                    replacement = f"{artifact.file_path} (the {file_type} from Ticket {completed_ticket})"
                    content = content.replace(match.group(0), replacement)
                    updates += 1

        return content, updates

    def preview_updates(
        self,
        completed_ticket_id: str,
        artifacts: List[TicketArtifact]
    ) -> List[Dict[str, str]]:
        """Preview what updates would be made without actually making them.
        
        Returns:
            List of proposed updates with before/after text

        """
        proposed_updates = []

        if not self.tickets_path.exists() or not artifacts:
            return proposed_updates

        with open(self.tickets_path, 'r') as f:
            content = f.read()

        dependent_tickets = self._find_dependent_tickets(completed_ticket_id)
        artifact_map = self._create_artifact_map(artifacts)

        for dep_ticket_id in dependent_tickets:
            # Find references in this ticket
            pattern = rf'(## Ticket {dep_ticket_id}:.*?)(?=## Ticket \d+:|$)'
            match = re.search(pattern, content, re.DOTALL)

            if match:
                section = match.group(1)

                # Look for updatable references
                for ref_pattern, ref_type in self.reference_patterns:
                    for match in re.finditer(ref_pattern, section, re.IGNORECASE):
                        if completed_ticket_id in match.group(0):
                            # This would be updated
                            proposed_updates.append({
                                'ticket': dep_ticket_id,
                                'before': match.group(0),
                                'after': "[would be updated with specific file reference]",
                                'type': ref_type
                            })

        return proposed_updates
