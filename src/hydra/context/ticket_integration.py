"""Integration module for connecting context store with ticket workflow.

This module provides the bridge between the context store and the ticket
execution workflow, ensuring that context is properly shared between
dependent tickets and agents.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from hydra.context.artifact_tracker import ArtifactTracker
from hydra.context.context_store import ContextStore


class TicketContextManager:
    """Manages context flow between ticket executions."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.context_store = ContextStore(project_root)
        self.artifact_tracker = ArtifactTracker(project_root)

    def prepare_ticket_context(self, ticket_id: str, ticket_data: Dict[str, Any]) -> str:
        """Prepare comprehensive context for a ticket execution.
        
        Args:
            ticket_id: The ticket to prepare context for
            ticket_data: Parsed ticket data including dependencies
            
        Returns:
            Context string to append to the ticket prompt

        """
        dependencies = ticket_data.get('dependencies', [])

        # Get comprehensive context
        context = self.context_store.get_ticket_context(ticket_id, dependencies)

        # Build context prompt
        context_parts = []

        # Add dependency context from artifact tracker
        if dependencies:
            dep_context = self.artifact_tracker.get_dependency_context(
                ticket_id, dependencies
            )
            if dep_context:
                context_parts.append(dep_context)

        # Add applicable patterns
        if context.get('applicable_patterns'):
            context_parts.append("\n" + "=" * 60)
            context_parts.append("LEARNED PATTERNS THAT MAY HELP")
            context_parts.append("=" * 60)
            for pattern in context['applicable_patterns']:
                context_parts.append(f"\n## Pattern: {pattern['description']}")
                context_parts.append(f"Category: {pattern['category']}")
                context_parts.append(f"Success Rate: {pattern['success_rate']:.1%}")
                context_parts.append(f"Solution Template:\n{pattern['solution_template']}")
            context_parts.append("=" * 60 + "\n")

        # Add previous attempts if any
        if context.get('previous_attempts'):
            context_parts.append("\n" + "=" * 60)
            context_parts.append("PREVIOUS EXECUTION ATTEMPTS")
            context_parts.append("=" * 60)
            for attempt in context['previous_attempts']:
                status_emoji = "✅" if attempt['success'] else "❌"
                context_parts.append(
                    f"{status_emoji} {attempt['agent_type']} - {attempt['status']} "
                    f"({attempt.get('execution_time_seconds', 0):.1f}s)"
                )
                if attempt.get('error_message'):
                    context_parts.append(f"   Error: {attempt['error_message']}")
            context_parts.append("=" * 60 + "\n")

        # Add related solutions
        if context.get('related_solutions'):
            context_parts.append("\n" + "=" * 60)
            context_parts.append("SOLUTIONS FROM SIMILAR TICKETS")
            context_parts.append("=" * 60)
            for solution in context['related_solutions'][:3]:
                context_parts.append(
                    f"• {solution['problem_type']}: {solution['solution_approach']}"
                    f" (confidence: {solution['confidence_score']:.1%})"
                )
            context_parts.append("=" * 60 + "\n")

        return '\n'.join(context_parts)

    def start_ticket_execution(self, ticket_id: str, agent_type: str) -> str:
        """Start tracking a ticket execution.
        
        Args:
            ticket_id: The ticket being executed
            agent_type: Type of agent executing the ticket
            
        Returns:
            Session ID for tracking

        """
        return self.context_store.start_session(ticket_id, agent_type)

    def complete_ticket_execution(self, session_id: str, ticket_id: str,
                                 success: bool, error_message: Optional[str] = None):
        """Complete a ticket execution and record results.
        
        Args:
            session_id: The session ID
            ticket_id: The ticket that was executed
            success: Whether execution was successful
            error_message: Error message if failed

        """
        # Get file snapshot before completion
        before_snapshot = self.artifact_tracker.get_file_snapshot()

        # Discover artifacts created/modified
        artifacts = self.artifact_tracker.discover_artifacts(ticket_id, before_snapshot)

        # Complete the session
        self.context_store.complete_session(
            session_id, success, artifacts, error_message
        )

        # Record artifacts if successful
        if success and artifacts:
            # Get ticket title from tickets.md
            ticket_title = self._get_ticket_title(ticket_id)
            self.artifact_tracker.record_ticket_completion(
                ticket_id, ticket_title, artifacts
            )

            # Learn patterns from successful execution
            self._extract_and_learn_patterns(ticket_id, artifacts)

    def _get_ticket_title(self, ticket_id: str) -> str:
        """Get ticket title from tickets.md."""
        tickets_path = self.project_root / "tickets.md"
        if not tickets_path.exists():
            return f"Ticket {ticket_id}"

        try:
            with open(tickets_path, 'r') as f:
                content = f.read()

            import re
            pattern = rf'## Ticket {ticket_id}:\s*(.+?)$'
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                return match.group(1).strip()
        except Exception:
            pass

        return f"Ticket {ticket_id}"

    def _extract_and_learn_patterns(self, ticket_id: str,
                                   artifacts: List) -> None:
        """Extract and learn patterns from successful execution.
        
        Args:
            ticket_id: The ticket that was executed
            artifacts: List of artifacts created/modified

        """
        # Categorize the execution
        categories = set()

        for artifact in artifacts:
            file_path = artifact.file_path

            # Determine categories based on file types and operations
            if 'test' in file_path.lower():
                categories.add('testing')
            elif artifact.operation == 'created':
                categories.add('file_creation')
            elif artifact.operation == 'modified':
                categories.add('file_modification')

            # Check file extensions
            if file_path.endswith('.py'):
                categories.add('python_development')
            elif file_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
                categories.add('javascript_development')
            elif file_path.endswith(('.yml', '.yaml', '.json')):
                categories.add('configuration')

        # Create patterns for each category
        for category in categories:
            # Build a simple solution template
            file_list = [a.file_path for a in artifacts
                        if self._matches_category(a, category)]

            if file_list:
                solution_template = f"Files involved: {', '.join(file_list[:3])}"
                if len(file_list) > 3:
                    solution_template += f" and {len(file_list) - 3} more"

                description = f"Pattern for {category} from ticket {ticket_id}"

                self.context_store.learn_pattern(
                    ticket_id, category, description, solution_template
                )

    def _matches_category(self, artifact, category: str) -> bool:
        """Check if an artifact matches a category."""
        file_path = artifact.file_path.lower()

        category_checks = {
            'testing': lambda: 'test' in file_path,
            'file_creation': lambda: artifact.operation == 'created',
            'file_modification': lambda: artifact.operation == 'modified',
            'python_development': lambda: file_path.endswith('.py'),
            'javascript_development': lambda: any(file_path.endswith(ext)
                                                 for ext in ['.js', '.ts', '.jsx', '.tsx']),
            'configuration': lambda: any(file_path.endswith(ext)
                                        for ext in ['.yml', '.yaml', '.json'])
        }

        check = category_checks.get(category)
        return check() if check else False

    def apply_pattern(self, pattern_id: str, success: bool):
        """Record the application of a pattern.
        
        Args:
            pattern_id: The pattern that was applied
            success: Whether the application was successful

        """
        self.context_store.apply_pattern(pattern_id, success)

    def get_session_metrics(self, session_id: str) -> Dict[str, Any]:
        """Get metrics for a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            Metrics dictionary

        """
        context = self.context_store.get_session_context(session_id)
        if not context:
            return {}

        session = context['session']
        return {
            'session_id': session_id,
            'ticket_id': session['ticket_id'],
            'agent_type': session['agent_type'],
            'status': session['status'],
            'patterns_applied': len(session.get('learned_patterns', [])),
            'context_size': len(json.dumps(context))
        }

    def cleanup_stale_sessions(self, hours: int = 24) -> int:
        """Clean up stale sessions.
        
        Args:
            hours: Number of hours after which a session is considered stale
            
        Returns:
            Number of sessions cleaned up

        """
        return self.context_store.cleanup_stale_sessions(hours)

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get overall execution statistics.
        
        Returns:
            Statistics dictionary

        """
        stats = self.context_store.get_execution_stats()

        # Add artifact tracking stats
        stats['total_tracked_tickets'] = len(self.artifact_tracker.ticket_contexts)
        stats['total_artifacts'] = sum(
            len(ctx.artifacts)
            for ctx in self.artifact_tracker.ticket_contexts.values()
        )

        return stats
