"""CLI commands for managing ticket context and artifacts."""

import json
from pathlib import Path
from typing import Optional

import click

from hydra.context import ArtifactTracker


@click.group()
def context():
    """Manage ticket execution context and artifacts."""
    pass


@context.command()
@click.option('--project', default='.', help='Project directory')
def show(project: str):
    """Show all tracked ticket contexts and artifacts."""
    tracker = ArtifactTracker(project)

    if not tracker.ticket_contexts:
        click.echo("No ticket contexts tracked yet.")
        return

    click.echo(f"📚 Tracked Ticket Contexts ({len(tracker.ticket_contexts)} tickets)\n")

    for ticket_id in sorted(tracker.ticket_contexts.keys()):
        ctx = tracker.ticket_contexts[ticket_id]
        click.echo(f"## Ticket {ticket_id}: {ctx.title}")
        click.echo(f"   Status: {ctx.status}")

        if ctx.summary:
            click.echo(f"   Summary: {ctx.summary[:100]}...")

        if ctx.artifacts:
            click.echo(f"   Artifacts ({len(ctx.artifacts)}):")
            for artifact in ctx.artifacts[:5]:
                op_symbol = {
                    'created': '➕',
                    'modified': '✏️',
                    'deleted': '➖'
                }.get(artifact.operation, '📄')
                desc = artifact.description or 'File'
                click.echo(f"     {op_symbol} {artifact.file_path} - {desc}")
            if len(ctx.artifacts) > 5:
                click.echo(f"     ... and {len(ctx.artifacts) - 5} more")

        if ctx.acceptance_criteria_met:
            click.echo(f"   Acceptance Criteria Met: {len(ctx.acceptance_criteria_met)}")

        click.echo()


@context.command()
@click.argument('ticket_id')
@click.option('--project', default='.', help='Project directory')
def inspect(ticket_id: str, project: str):
    """Inspect detailed context for a specific ticket."""
    tracker = ArtifactTracker(project)

    if ticket_id not in tracker.ticket_contexts:
        click.echo(f"❌ No context found for ticket {ticket_id}")
        return

    ctx = tracker.ticket_contexts[ticket_id]

    click.echo(f"📋 Ticket {ticket_id}: {ctx.title}")
    click.echo(f"{'='*60}")
    click.echo(f"Status: {ctx.status}")

    if ctx.summary:
        click.echo(f"\nSummary:\n{ctx.summary}")

    if ctx.artifacts:
        click.echo(f"\nArtifacts ({len(ctx.artifacts)}):")
        for artifact in ctx.artifacts:
            op_symbol = {
                'created': '➕',
                'modified': '✏️',
                'deleted': '➖'
            }.get(artifact.operation, '📄')
            desc = artifact.description or 'File'
            click.echo(f"  {op_symbol} {artifact.file_path}")
            click.echo(f"     {desc}")

            if artifact.content_preview:
                click.echo("     Preview:")
                for line in artifact.content_preview.split('\n')[:5]:
                    if line.strip():
                        click.echo(f"       {line[:80]}")

    if ctx.acceptance_criteria_met:
        click.echo("\nAcceptance Criteria Met:")
        for criteria in ctx.acceptance_criteria_met:
            click.echo(f"  ✅ {criteria}")


@context.command()
@click.argument('ticket_id', required=False)
@click.option('--project', default='.', help='Project directory')
@click.option('--all', 'clear_all', is_flag=True, help='Clear all contexts')
def clear(ticket_id: Optional[str], project: str, clear_all: bool):
    """Clear context for a specific ticket or all tickets."""
    tracker = ArtifactTracker(project)

    if clear_all:
        if click.confirm("Are you sure you want to clear ALL ticket contexts?"):
            tracker.clear_context()
            click.echo("✅ All ticket contexts cleared")
    elif ticket_id:
        if ticket_id in tracker.ticket_contexts:
            tracker.clear_context(ticket_id)
            click.echo(f"✅ Context for ticket {ticket_id} cleared")
        else:
            click.echo(f"❌ No context found for ticket {ticket_id}")
    else:
        click.echo("Please specify a ticket ID or use --all flag")


@context.command()
@click.argument('ticket_id')
@click.option('--project', default='.', help='Project directory')
def deps(ticket_id: str, project: str):
    """Show what context would be provided to a ticket based on its dependencies."""
    # Parse tickets.md to find dependencies
    tickets_path = Path(project) / "tickets.md"
    if not tickets_path.exists():
        click.echo("❌ tickets.md not found")
        return

    from hydra.ticket_workflow import parse_ticket

    ticket_data = parse_ticket(str(tickets_path), ticket_id)
    if not ticket_data:
        click.echo(f"❌ Ticket {ticket_id} not found")
        return

    dependencies = ticket_data.get('dependencies', [])
    if not dependencies:
        click.echo(f"Ticket {ticket_id} has no dependencies")
        return

    tracker = ArtifactTracker(project)
    context_str = tracker.get_dependency_context(ticket_id, dependencies)

    if context_str:
        click.echo(context_str)
    else:
        click.echo(f"No context available from dependencies: {', '.join(dependencies)}")


@context.command()
@click.option('--project', default='.', help='Project directory')
@click.option('--format', type=click.Choice(['json', 'text']), default='text')
def export(project: str, format: str):
    """Export all ticket contexts."""
    tracker = ArtifactTracker(project)

    if not tracker.ticket_contexts:
        click.echo("No ticket contexts to export")
        return

    if format == 'json':
        data = {
            tid: ctx.to_dict()
            for tid, ctx in tracker.ticket_contexts.items()
        }
        click.echo(json.dumps(data, indent=2))
    else:
        # Text format
        for ticket_id in sorted(tracker.ticket_contexts.keys()):
            ctx = tracker.ticket_contexts[ticket_id]
            click.echo(f"Ticket {ticket_id}: {ctx.title}")
            click.echo(f"  Status: {ctx.status}")
            if ctx.artifacts:
                click.echo(f"  Artifacts: {len(ctx.artifacts)} files")
                for a in ctx.artifacts:
                    click.echo(f"    - {a.file_path} ({a.operation})")
            click.echo()


if __name__ == '__main__':
    context()
