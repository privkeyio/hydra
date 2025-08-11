"""Artifact Tracking and Context Discovery for Dependent Tickets.

This module tracks what files and artifacts each ticket creates, modifies, or deletes,
and provides this context to dependent tickets so they can build upon previous work.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class TicketArtifact:
    """Represents an artifact created or modified by a ticket."""

    file_path: str
    operation: str  # created, modified, deleted
    description: Optional[str] = None
    content_preview: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'file_path': self.file_path,
            'operation': self.operation,
            'description': self.description,
            'content_preview': self.content_preview
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TicketArtifact':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class TicketContext:
    """Context information about a completed ticket."""

    ticket_id: str
    title: str
    status: str
    artifacts: List[TicketArtifact] = field(default_factory=list)
    summary: Optional[str] = None
    acceptance_criteria_met: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'ticket_id': self.ticket_id,
            'title': self.title,
            'status': self.status,
            'artifacts': [a.to_dict() for a in self.artifacts],
            'summary': self.summary,
            'acceptance_criteria_met': self.acceptance_criteria_met
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TicketContext':
        """Create from dictionary."""
        artifacts = [TicketArtifact.from_dict(a) for a in data.get('artifacts', [])]
        return cls(
            ticket_id=data['ticket_id'],
            title=data['title'],
            status=data['status'],
            artifacts=artifacts,
            summary=data.get('summary'),
            acceptance_criteria_met=data.get('acceptance_criteria_met', [])
        )


class ArtifactTracker:
    """Tracks artifacts created by tickets and provides context to dependent tickets."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.context_file = self.project_root / ".hydra" / "ticket_context.json"
        self.context_file.parent.mkdir(parents=True, exist_ok=True)
        self.ticket_contexts: Dict[str, TicketContext] = self._load_contexts()

    def _load_contexts(self) -> Dict[str, TicketContext]:
        """Load existing ticket contexts from file."""
        if self.context_file.exists():
            try:
                with open(self.context_file, 'r') as f:
                    data = json.load(f)
                    return {
                        tid: TicketContext.from_dict(ctx)
                        for tid, ctx in data.items()
                    }
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    def _save_contexts(self):
        """Save ticket contexts to file."""
        data = {
            tid: ctx.to_dict()
            for tid, ctx in self.ticket_contexts.items()
        }
        with open(self.context_file, 'w') as f:
            json.dump(data, f, indent=2)

    def discover_artifacts(self, ticket_id: str, before_snapshot: Set[str]) -> List[TicketArtifact]:
        """Discover artifacts created/modified by a ticket.
        
        Args:
            ticket_id: The ticket that was executed
            before_snapshot: Set of file paths that existed before ticket execution
            
        Returns:
            List of artifacts created or modified

        """
        artifacts = []

        # Get current git status
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue

                    # Parse git status line
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) < 2:
                        continue

                    status_code = parts[0]
                    file_path = parts[1]

                    # Skip tickets.md and .hydra files
                    if 'tickets.md' in file_path or '.hydra/' in file_path:
                        continue

                    # Determine operation type
                    operation = None
                    if status_code in ['??', 'A']:
                        operation = 'created'
                    elif status_code == 'M':
                        operation = 'modified'
                    elif status_code == 'D':
                        operation = 'deleted'

                    if operation:
                        # Get file description from content or name
                        description = self._infer_file_description(file_path)

                        # Get content preview for created/modified files
                        content_preview = None
                        if operation != 'deleted':
                            content_preview = self._get_content_preview(file_path)

                        artifact = TicketArtifact(
                            file_path=file_path,
                            operation=operation,
                            description=description,
                            content_preview=content_preview
                        )
                        artifacts.append(artifact)

        except subprocess.CalledProcessError:
            pass

        # Also check for new files not in git
        try:
            current_files = set()
            for path in Path(self.project_root).rglob('*'):
                if path.is_file():
                    rel_path = str(path.relative_to(self.project_root))
                    if not rel_path.startswith('.hydra/'):
                        current_files.add(rel_path)

            # Find new files
            new_files = current_files - before_snapshot
            for file_path in new_files:
                # Check if already tracked
                if not any(a.file_path == file_path for a in artifacts):
                    artifact = TicketArtifact(
                        file_path=file_path,
                        operation='created',
                        description=self._infer_file_description(file_path),
                        content_preview=self._get_content_preview(file_path)
                    )
                    artifacts.append(artifact)

        except Exception:
            pass

        return artifacts

    def _infer_file_description(self, file_path: str) -> str:
        """Infer a description of the file from its path and name."""
        path = Path(file_path)
        name = path.stem
        ext = path.suffix

        # Common file type descriptions
        descriptions = {
            '.py': 'Python module',
            '.js': 'JavaScript module',
            '.ts': 'TypeScript module',
            '.jsx': 'React component',
            '.tsx': 'React TypeScript component',
            '.html': 'HTML page',
            '.css': 'Stylesheet',
            '.json': 'Configuration file',
            '.yaml': 'Configuration file',
            '.yml': 'Configuration file',
            '.md': 'Documentation',
            '.txt': 'Text file',
            '.sh': 'Shell script',
        }

        base_desc = descriptions.get(ext, 'File')

        # Add context from filename
        if 'test' in name.lower():
            return f"Test {base_desc.lower()}"
        elif 'config' in name.lower():
            return "Configuration file"
        elif 'spec' in name.lower():
            return "Specification file"
        elif 'audit' in name.lower():
            return "Audit report"
        elif 'report' in name.lower():
            return "Report document"
        elif '__init__' in name:
            return "Package initialization"

        return base_desc

    def _get_content_preview(self, file_path: str) -> Optional[str]:
        """Get a preview of file content (first few lines)."""
        try:
            full_path = self.project_root / file_path
            if full_path.exists() and full_path.is_file():
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= 10:  # First 10 lines
                            break
                        lines.append(line.rstrip())

                    if lines:
                        preview = '\n'.join(lines)
                        if len(preview) > 500:
                            preview = preview[:500] + '...'
                        return preview
        except Exception:
            pass

        return None

    def record_ticket_completion(
        self,
        ticket_id: str,
        title: str,
        artifacts: List[TicketArtifact],
        acceptance_criteria_met: Optional[List[str]] = None
    ):
        """Record the completion of a ticket and its artifacts.
        
        Args:
            ticket_id: The completed ticket ID
            title: Ticket title
            artifacts: List of artifacts created/modified
            acceptance_criteria_met: List of met acceptance criteria

        """
        # Parse ticket content for summary
        summary = self._extract_ticket_summary(ticket_id)

        context = TicketContext(
            ticket_id=ticket_id,
            title=title,
            status='completed',
            artifacts=artifacts,
            summary=summary,
            acceptance_criteria_met=acceptance_criteria_met or []
        )

        self.ticket_contexts[ticket_id] = context
        self._save_contexts()

    def _extract_ticket_summary(self, ticket_id: str) -> Optional[str]:
        """Extract a summary from the ticket description."""
        tickets_path = self.project_root / "tickets.md"
        if not tickets_path.exists():
            return None

        try:
            with open(tickets_path, 'r') as f:
                content = f.read()

            # Find ticket section
            pattern = rf'## Ticket {ticket_id}:.*?(?=## Ticket \d+:|$)'
            match = re.search(pattern, content, re.DOTALL)

            if match:
                ticket_content = match.group(0)
                # Extract description
                desc_match = re.search(r'\*\*Description:\*\*\s*(.+?)(?=\n\*\*|\n##|$)',
                                      ticket_content, re.DOTALL)
                if desc_match:
                    summary = desc_match.group(1).strip()
                    # Limit to first paragraph
                    if '\n\n' in summary:
                        summary = summary.split('\n\n')[0]
                    return summary

        except Exception:
            pass

        return None

    def get_dependency_context(self, ticket_id: str, dependencies: List[str]) -> str:
        """Get context from dependent tickets for inclusion in prompt.
        
        Args:
            ticket_id: The ticket about to be executed
            dependencies: List of ticket IDs this ticket depends on
            
        Returns:
            Context string to include in the prompt

        """
        if not dependencies:
            return ""

        context_parts = []
        context_parts.append("=" * 60)
        context_parts.append("CONTEXT FROM DEPENDENT TICKETS")
        context_parts.append("=" * 60)
        context_parts.append(
            f"This ticket ({ticket_id}) depends on the following completed tickets. "
            "Please review their outputs and build upon their work:"
        )
        context_parts.append("")

        for dep_id in dependencies:
            if dep_id in self.ticket_contexts:
                ctx = self.ticket_contexts[dep_id]

                context_parts.append(f"## Ticket {dep_id}: {ctx.title}")
                context_parts.append(f"Status: {ctx.status}")

                if ctx.summary:
                    context_parts.append(f"Summary: {ctx.summary}")

                if ctx.artifacts:
                    context_parts.append("")
                    context_parts.append("Artifacts created/modified:")
                    for artifact in ctx.artifacts:
                        op_symbol = {
                            'created': '➕',
                            'modified': '✏️',
                            'deleted': '➖'
                        }.get(artifact.operation, '📄')

                        context_parts.append(
                            f"  {op_symbol} {artifact.file_path} - {artifact.description or 'File'}"
                        )

                        # Include preview for key files
                        if artifact.content_preview and artifact.operation == 'created':
                            # Only show preview for important files
                            if any(key in artifact.file_path.lower()
                                   for key in ['report', 'audit', 'spec', 'design', 'api']):
                                context_parts.append("    Preview:")
                                for line in artifact.content_preview.split('\n')[:5]:
                                    if line.strip():
                                        context_parts.append(f"      {line[:80]}")

                if ctx.acceptance_criteria_met:
                    context_parts.append("")
                    context_parts.append("Acceptance criteria met:")
                    for criteria in ctx.acceptance_criteria_met:
                        context_parts.append(f"  ✅ {criteria}")

                context_parts.append("")
                context_parts.append("-" * 40)
                context_parts.append("")

        context_parts.append("=" * 60)
        context_parts.append(
            "IMPORTANT: Review the files created by dependent tickets before starting your work. "
            "Use the Read tool to examine any relevant files mentioned above."
        )
        context_parts.append("=" * 60)
        context_parts.append("")

        return '\n'.join(context_parts)

    def get_file_snapshot(self) -> Set[str]:
        """Get a snapshot of current files in the project.
        
        Returns:
            Set of relative file paths

        """
        files = set()
        try:
            for path in Path(self.project_root).rglob('*'):
                if path.is_file():
                    rel_path = str(path.relative_to(self.project_root))
                    if not rel_path.startswith('.hydra/'):
                        files.add(rel_path)
        except Exception:
            pass

        return files

    def clear_context(self, ticket_id: Optional[str] = None):
        """Clear context for a specific ticket or all tickets.
        
        Args:
            ticket_id: Specific ticket to clear, or None for all

        """
        if ticket_id:
            if ticket_id in self.ticket_contexts:
                del self.ticket_contexts[ticket_id]
        else:
            self.ticket_contexts.clear()

        self._save_contexts()
