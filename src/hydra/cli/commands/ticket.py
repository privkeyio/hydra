"""Ticket workflow commands for Hydra CLI."""

import os
from pathlib import Path

from hydra.ticket_workflow import (
    execute_single_ticket,
    generate_tickets_md,
    run_all_tickets,
)


def add_ticket_parser(subparsers):
    """Add ticket workflow subcommands to the parser."""
    ticket_parser = subparsers.add_parser(
        "ticket",
        help="Ticket workflow operations - create, execute, and manage tickets"
    )
    ticket_subparsers = ticket_parser.add_subparsers(
        dest="ticket_action",
        help="Ticket operations"
    )

    # Create tickets command
    create_tickets_parser = ticket_subparsers.add_parser(
        "create",
        help="Generate tickets.md file from project description"
    )
    create_tickets_parser.add_argument(
        "description",
        help="Project description to generate tickets from"
    )
    create_tickets_parser.add_argument(
        "--output", "-o",
        default="tickets.md",
        help="Output file path (default: tickets.md)"
    )
    create_tickets_parser.add_argument(
        "--project-type",
        choices=["feature", "refactor", "bugfix", "research"],
        help="Type of project for ticket generation"
    )
    create_tickets_parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Enable interactive ticket refinement after generation"
    )

    # Execute single ticket
    execute_ticket_parser = ticket_subparsers.add_parser(
        "execute",
        help="Execute a single ticket by identifier"
    )
    execute_ticket_parser.add_argument(
        "tickets",
        help="Path to tickets.md file"
    )
    execute_ticket_parser.add_argument(
        "identifier",
        help="Ticket identifier to execute (e.g., 001, 002)"
    )
    execute_ticket_parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight checks and proceed directly with execution"
    )
    execute_ticket_parser.add_argument(
        "--context", "-c",
        action="store_true",
        help="Include context from dependent tickets in execution"
    )

    # Run all tickets
    run_tickets_parser = ticket_subparsers.add_parser(
        "run-all",
        help="Execute all tickets in order with dependency resolution"
    )
    run_tickets_parser.add_argument(
        "tickets",
        help="Path to tickets.md file"
    )
    run_tickets_parser.add_argument(
        "--max-parallel", "-p",
        type=int,
        default=1,
        help="Maximum number of parallel agents (default: 1)"
    )
    run_tickets_parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight checks for all tickets"
    )

    # Auto workflow command
    auto_parser = ticket_subparsers.add_parser(
        "auto",
        help="Automated workflow with dependency-aware parallel execution"
    )
    auto_parser.add_argument(
        "tickets",
        help="Path to tickets.md file"
    )
    auto_parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=3,
        help="Maximum parallel agents (default: 3)"
    )
    auto_parser.add_argument(
        "--dir", "-d",
        help="Project directory to execute in (default: current directory)"
    )
    auto_parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight checks for faster execution"
    )

    # Parallel execution command
    parallel_parser = ticket_subparsers.add_parser(
        "parallel",
        help="Execute tickets in parallel with dependency resolution"
    )
    parallel_parser.add_argument(
        "tickets",
        help="Path to tickets.md file"
    )
    parallel_parser.add_argument(
        "--workers", "-w",
        type=int,
        default=3,
        help="Number of parallel workers (default: 3)"
    )
    parallel_parser.add_argument(
        "--save-log", "-l",
        action="store_true",
        help="Save execution log to file"
    )
    parallel_parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight validation checks"
    )
    parallel_parser.add_argument(
        "--async",
        action="store_true",
        dest="async_mode",
        help="Use async execution mode for better concurrency"
    )

    # Verify parallel execution results
    verify_parallel_parser = ticket_subparsers.add_parser(
        "verify-parallel",
        help="Verify results from parallel ticket execution and check acceptance criteria"
    )
    verify_parallel_parser.add_argument(
        "tickets",
        help="Path to tickets.md file to verify against"
    )
    verify_parallel_parser.add_argument(
        "--workers", "-w",
        type=int,
        default=3,
        help="Number of parallel verification workers (default: 3)"
    )
    verify_parallel_parser.add_argument(
        "--check-ai",
        action="store_true",
        help="Check for and report AI-generated code patterns"
    )
    verify_parallel_parser.add_argument(
        "--audit-diff",
        action="store_true",
        help="Audit the git diff to ensure changes match acceptance criteria"
    )
    verify_parallel_parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save verification report to file"
    )
    verify_parallel_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed verification output"
    )

    return ticket_parser


def _handle_create_tickets(args) -> int:
    """Handle ticket create command."""
    try:
        project_type = getattr(args, 'project_type', None)
        success = generate_tickets_md(
            args.description,
            args.output,
            project_type
        )

        if success and getattr(args, 'interactive', False):
            # Launch interactive refinement
            from hydra.interactive.refinement_cli import run_interactive_refinement
            print(f"\n🔧 Launching interactive refinement for {args.output}...")
            refinement_result = run_interactive_refinement(args.output)
            return refinement_result

        return 0 if success else 1
    except Exception as e:
        print(f"Error creating tickets: {e}")
        return 1


def _handle_execute_ticket(args) -> int:
    """Handle ticket execute command."""
    try:
        from hydra.monitoring import monitoring
        correlation_id = monitoring.set_correlation_id(f"ticket_{args.identifier}")
        print(f"🔗 Session: {correlation_id}")

        skip_preflight = getattr(args, 'skip_preflight', False)
        include_context = getattr(args, 'context', False)

        # Note: include_context is not currently supported in execute_single_ticket
        # but we capture it for future use
        success = execute_single_ticket(
            args.tickets,
            args.identifier,
            skip_preflight=skip_preflight
        )
        return 0 if success else 1
    except Exception as e:
        print(f"Error executing ticket: {e}")
        return 1


def _handle_run_all_tickets(args) -> int:
    """Handle run all tickets command."""
    try:
        skip_preflight = getattr(args, 'skip_preflight', False)
        max_parallel = getattr(args, 'max_parallel', 1)

        success = run_all_tickets(
            args.tickets,
            skip_preflight=skip_preflight,
            max_parallel=max_parallel
        )
        return 0 if success else 1
    except Exception as e:
        print(f"Error running tickets: {e}")
        return 1


def _handle_auto_workflow(args) -> int:
    """Handle automated workflow with dependency-aware parallel execution."""
    try:
        original_dir = os.getcwd()

        if args.dir:
            target_dir = Path(args.dir).resolve()
            if not target_dir.exists():
                print(f"❌ Directory not found: {target_dir}")
                return 1
            os.chdir(target_dir)
            print(f"📁 Changed to: {target_dir}")

        tickets_path = Path(args.tickets).resolve()
        if not tickets_path.exists():
            print(f"❌ Tickets file not found: {tickets_path}")
            return 1

        print(f"🎯 Processing: {tickets_path}")
        print(f"⚡ Max parallel agents: {args.parallel}")

        skip_preflight = getattr(args, 'skip_preflight', False)
        success = run_all_tickets(
            str(tickets_path),
            max_parallel=args.parallel,
            skip_preflight=skip_preflight
        )

        os.chdir(original_dir)
        return 0 if success else 1

    except Exception as e:
        print(f"Error in auto workflow: {e}")
        return 1


def handle_ticket_command(args) -> int:
    """Handle ticket workflow subcommands."""
    if args.ticket_action == "create":
        return _handle_create_tickets(args)
    elif args.ticket_action == "execute":
        return _handle_execute_ticket(args)
    elif args.ticket_action == "run-all":
        return _handle_run_all_tickets(args)
    elif args.ticket_action == "auto":
        return _handle_auto_workflow(args)
    elif args.ticket_action == "parallel":
        from hydra.cli.commands.parallel import handle_parallel_commands
        return handle_parallel_commands(args)
    elif args.ticket_action == "verify-parallel":
        return _handle_verify_parallel(args)
    else:
        print(f"Unknown ticket action: {args.ticket_action}")
        return 1


def _handle_verify_parallel(args) -> int:
    """Handle comprehensive parallel verification of all tickets."""
    from pathlib import Path
    import asyncio
    from hydra.verification.parallel_verifier import ParallelTicketVerifier
    
    async def run_verification():
        try:
            tickets_path = Path(args.tickets).resolve()
            if not tickets_path.exists():
                print(f"❌ Tickets file not found: {tickets_path}")
                return 1
                
            print(f"🔍 Starting parallel verification of tickets from: {tickets_path}")
            print(f"⚡ Using {args.workers} parallel workers")
            
            # Initialize verifier with options
            verifier = ParallelTicketVerifier(
                tickets_path=str(tickets_path),
                max_workers=args.workers,
                check_ai_patterns=getattr(args, 'check_ai', False),
                audit_diff=getattr(args, 'audit_diff', False)
            )
            
            # Run verification
            report = await verifier.verify_all_tickets()
            
            # Display results
            print("\n" + "="*60)
            print("PARALLEL TICKET VERIFICATION REPORT")
            print("="*60)
            
            print(f"\n📊 Summary:")
            print(f"  Total tickets: {report['total_tickets']}")
            print(f"  Tickets claiming DONE: {report.get('tickets_claiming_done', 0)}")
            print(f"  ✅ Actually fully verified: {report['fully_verified']}")
            print(f"  ⚠️  Partially verified: {report.get('partially_verified', 0)}")
            print(f"  ❌ Failed verification: {report.get('failed_verification', 0)}")
            print(f"  ⏸️  Not started: {report.get('not_started', 0)}")
            
            if report.get('status_mismatches'):
                print(f"\n⚠️ Status Mismatches (ticket status vs actual):")
                for ticket_id, mismatch in report['status_mismatches'].items():
                    print(f"  {ticket_id}: {mismatch}")
            
            if report.get('ai_code_detected'):
                print(f"\n🤖 AI-Generated Code Detection:")
                for ticket_id, ai_issues in report['ai_code_detected'].items():
                    print(f"  {ticket_id}: {len(ai_issues)} patterns detected")
                    
            if report.get('diff_audit_issues'):
                print(f"\n📝 Diff Audit Issues:")
                for ticket_id, issues in report['diff_audit_issues'].items():
                    print(f"  {ticket_id}: {issues}")
                    
            if report['failed_verification'] > 0:
                print(f"\n❌ Failed Tickets:")
                for ticket_id, details in report['failures'].items():
                    print(f"  {ticket_id}:")
                    for criterion in details['failed_criteria']:
                        print(f"    - {criterion}")
                        
            # Save report if requested
            if args.save_report:
                import json
                report_path = Path(".hydra/reports") / f"verify_parallel_{Path(tickets_path).stem}.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                with open(report_path, 'w') as f:
                    json.dump(report, f, indent=2, default=str)
                print(f"\n📄 Verification report saved: {report_path}")
                
            # Return based on verification status
            if report['failed_verification'] == 0:
                print("\n✅ All tickets passed verification!")
                return 0
            else:
                print(f"\n⚠️ {report['failed_verification']} tickets failed verification")
                return 1
                
        except Exception as e:
            print(f"❌ Verification error: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            return 1
            
    return asyncio.run(run_verification())
