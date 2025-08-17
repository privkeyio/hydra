"""Context management commands for Hydra CLI."""

import json
from pathlib import Path


def add_context_parser(subparsers):
    """Add context management subcommands to the parser."""
    context_parser = subparsers.add_parser(
        "context", help="Manage ticket execution context and artifacts"
    )
    context_subparsers = context_parser.add_subparsers(
        dest="context_action", help="Context operations"
    )

    # Show all contexts
    context_subparsers.add_parser("show", help="Show all tracked ticket contexts")

    # Inspect specific ticket context
    inspect_parser = context_subparsers.add_parser(
        "inspect", help="Inspect detailed context for a specific ticket"
    )
    inspect_parser.add_argument("ticket_id", help="Ticket ID to inspect")

    # Clear context
    clear_parser = context_subparsers.add_parser(
        "clear", help="Clear context for a specific ticket or all tickets"
    )
    clear_parser.add_argument(
        "ticket_id", nargs="?", help="Ticket ID to clear (optional)"
    )
    clear_parser.add_argument("--all", action="store_true", help="Clear all contexts")

    # Show dependency context
    deps_parser = context_subparsers.add_parser(
        "deps", help="Show context that would be provided to a ticket"
    )
    deps_parser.add_argument("ticket_id", help="Ticket ID to show dependencies for")

    # Export contexts
    export_parser = context_subparsers.add_parser(
        "export", help="Export all ticket contexts"
    )
    export_parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Export format (default: text)",
    )

    # Preview ticket updates
    preview_parser = context_subparsers.add_parser(
        "preview-updates", help="Preview how future tickets would be updated"
    )
    preview_parser.add_argument(
        "ticket_id", help="Completed ticket ID to preview updates for"
    )


def _handle_context_show(tracker):
    """Show all tracked contexts."""
    if not tracker.ticket_contexts:
        print("No ticket contexts tracked yet.")
        return 0

    print(f"📚 Tracked Ticket Contexts ({len(tracker.ticket_contexts)} tickets)\n")

    for ticket_id in sorted(tracker.ticket_contexts.keys()):
        ctx = tracker.ticket_contexts[ticket_id]
        print(f"## Ticket {ticket_id}: {ctx.title}")
        print(f"   Status: {ctx.status}")

        if ctx.summary:
            print(f"   Summary: {ctx.summary[:100]}...")

        if ctx.artifacts:
            print(f"   Artifacts ({len(ctx.artifacts)}):")
            for artifact in ctx.artifacts[:5]:
                op_symbol = {"created": "➕", "modified": "✏️", "deleted": "➖"}.get(
                    artifact.operation, "📄"
                )
                desc = artifact.description or "File"
                print(f"     {op_symbol} {artifact.file_path} - {desc}")
            if len(ctx.artifacts) > 5:
                print(f"     ... and {len(ctx.artifacts) - 5} more")

        if ctx.acceptance_criteria_met:
            print(f"   Acceptance Criteria Met: {len(ctx.acceptance_criteria_met)}")

        print()

    return 0


def _handle_context_inspect(tracker, ticket_id):
    """Inspect a specific ticket's context."""
    if ticket_id not in tracker.ticket_contexts:
        print(f"❌ No context found for ticket {ticket_id}")
        return 1

    ctx = tracker.ticket_contexts[ticket_id]

    print(f"📋 Ticket {ticket_id}: {ctx.title}")
    print(f"{'='*60}")
    print(f"Status: {ctx.status}")

    if ctx.summary:
        print(f"\nSummary:\n{ctx.summary}")

    if ctx.artifacts:
        print(f"\nArtifacts ({len(ctx.artifacts)}):")
        for artifact in ctx.artifacts:
            op_symbol = {"created": "➕", "modified": "✏️", "deleted": "➖"}.get(
                artifact.operation, "📄"
            )
            desc = artifact.description or "File"
            print(f"  {op_symbol} {artifact.file_path}")
            print(f"     {desc}")

            if artifact.content_preview:
                print("     Preview:")
                for line in artifact.content_preview.split("\n")[:5]:
                    if line.strip():
                        print(f"       {line[:80]}")

    if ctx.acceptance_criteria_met:
        print("\nAcceptance Criteria Met:")
        for criteria in ctx.acceptance_criteria_met:
            print(f"  ✅ {criteria}")

    return 0


def _handle_context_clear(tracker, ticket_id, clear_all):
    """Clear context for tickets."""
    if clear_all:
        response = input("Are you sure you want to clear ALL ticket contexts? (y/n): ")
        if response.lower() == "y":
            tracker.clear_context()
            print("✅ All ticket contexts cleared")
        else:
            print("Cancelled")
    elif ticket_id:
        if ticket_id in tracker.ticket_contexts:
            tracker.clear_context(ticket_id)
            print(f"✅ Context for ticket {ticket_id} cleared")
        else:
            print(f"❌ No context found for ticket {ticket_id}")
            return 1
    else:
        print("Please specify a ticket ID or use --all flag")
        return 1

    return 0


def _handle_context_deps(tracker, ticket_id, project_dir):
    """Show dependency context for a ticket."""
    from hydra.ticket_workflow import parse_ticket

    tickets_path = Path(project_dir) / "tickets.md"
    if not tickets_path.exists():
        print("❌ tickets.md not found")
        return 1

    ticket_data = parse_ticket(str(tickets_path), ticket_id)
    if not ticket_data:
        print(f"❌ Ticket {ticket_id} not found")
        return 1

    dependencies = ticket_data.get("dependencies", [])
    if not dependencies:
        print(f"Ticket {ticket_id} has no dependencies")
        return 0

    context_str = tracker.get_dependency_context(ticket_id, dependencies)

    if context_str:
        print(context_str)
    else:
        print(f"No context available from dependencies: {', '.join(dependencies)}")

    return 0


def _handle_context_export(tracker, format_type):
    """Export all ticket contexts."""
    if not tracker.ticket_contexts:
        print("No ticket contexts to export")
        return 0

    if format_type == "json":
        data = {tid: ctx.to_dict() for tid, ctx in tracker.ticket_contexts.items()}
        print(json.dumps(data, indent=2))
    else:
        # Text format
        for ticket_id in sorted(tracker.ticket_contexts.keys()):
            ctx = tracker.ticket_contexts[ticket_id]
            print(f"Ticket {ticket_id}: {ctx.title}")
            print(f"  Status: {ctx.status}")
            if ctx.artifacts:
                print(f"  Artifacts: {len(ctx.artifacts)} files")
                for a in ctx.artifacts:
                    print(f"    - {a.file_path} ({a.operation})")
            print()

    return 0


def _handle_context_preview_updates(tracker, ticket_id, project_dir):
    """Preview what ticket updates would be made."""
    from hydra.context import TicketUpdater

    updater = TicketUpdater(project_dir)

    # Check if this ticket has context
    if ticket_id not in tracker.ticket_contexts:
        print(f"❌ No context found for ticket {ticket_id}")
        print("Ticket must be completed first to preview updates")
        return 1

    ctx = tracker.ticket_contexts[ticket_id]

    if not ctx.artifacts:
        print(f"Ticket {ticket_id} created no artifacts, so no updates would be made")
        return 0

    print(f"🔍 Previewing updates for artifacts from Ticket {ticket_id}:")
    print(f"   {ctx.title}")
    print()

    # Show artifacts that would trigger updates
    print("📦 Artifacts created:")
    for artifact in ctx.artifacts:
        print(f"   - {artifact.file_path} ({artifact.description or 'File'})")
    print()

    # Get preview of updates
    proposed_updates = updater.preview_updates(ticket_id, ctx.artifacts)

    if proposed_updates:
        print("📝 Proposed updates to future tickets:")
        current_ticket = None
        for update in proposed_updates:
            if update["ticket"] != current_ticket:
                current_ticket = update["ticket"]
                print(f"\n   Ticket {current_ticket}:")
            print(f"      Before: {update['before']}")
            print("      After:  [would update with specific filename]")
    else:
        print("No future tickets reference this ticket's outputs")

    return 0


def handle_context_command(args):
    """Handle context management commands."""
    from hydra.context import ArtifactTracker

    # Default to current directory for project path
    project_dir = getattr(args, "dir", ".")
    tracker = ArtifactTracker(project_dir)

    if args.context_action == "show":
        return _handle_context_show(tracker)
    elif args.context_action == "inspect":
        return _handle_context_inspect(tracker, args.ticket_id)
    elif args.context_action == "clear":
        ticket_id = getattr(args, "ticket_id", None)
        clear_all = getattr(args, "all", False)
        return _handle_context_clear(tracker, ticket_id, clear_all)
    elif args.context_action == "deps":
        return _handle_context_deps(tracker, args.ticket_id, project_dir)
    elif args.context_action == "export":
        format_type = getattr(args, "format", "text")
        return _handle_context_export(tracker, format_type)
    elif args.context_action == "preview-updates":
        return _handle_context_preview_updates(tracker, args.ticket_id, project_dir)
    else:
        print("Unknown context action")
        return 1
