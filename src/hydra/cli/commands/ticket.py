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
        help="[DEPRECATED - Always on] AI pattern detection is now enabled by default"
    )
    verify_parallel_parser.add_argument(
        "--audit-diff",
        action="store_true",
        help="[DEPRECATED - Always on] Diff auditing is now enabled by default"
    )
    verify_parallel_parser.add_argument(
        "--no-critical-review",
        action="store_true",
        help="Disable critical code review (NOT RECOMMENDED - use only for quick checks)"
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
    """Handle comprehensive parallel verification of all tickets using Claude agents."""
    from pathlib import Path
    from hydra.parallel import ParallelExecutor
    from hydra.production_config import get_production_config
    import os
    
    try:
        tickets_path = Path(args.tickets).resolve()
        if not tickets_path.exists():
            print(f"❌ Tickets file not found: {tickets_path}")
            return 1
            
        print(f"🔍 Starting parallel verification of tickets from: {tickets_path}")
        print(f"⚡ Using {args.workers} parallel workers with Claude agents")
        print(f"🤖 Agents will verify and complete any unfinished acceptance criteria")
        
        # Load production configuration
        config = get_production_config()
        config.max_parallel_tickets = args.workers
        
        # Apply environment variables from config
        for key, value in config.to_env_vars().items():
            os.environ[key] = value
        
        # Initialize executor for verification mode
        project_root = tickets_path.parent
        executor = ParallelExecutor(
            max_workers=args.workers,
            project_root=str(project_root),
            dashboard_state=None  # No dashboard for verification
        )
        
        # Load all tickets (not just pending ones)
        from hydra.tickets.compatibility import TicketFormatHandler
        handler = TicketFormatHandler()
        all_tickets = handler.get_all_tickets(str(tickets_path))
        
        if not all_tickets:
            print("❌ No tickets found")
            return 1
            
        print(f"📋 Found {len(all_tickets)} tickets to verify")
        
        # Execute verification for each ticket using agents
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        def verify_ticket_with_agent(ticket_id: str) -> bool:
            """Verify and complete a single ticket using Claude agent."""
            import random
            from hydra.orchestrator.claude_code_orchestrator import ClaudeCodeOrchestrator
            
            # Add staggered start to prevent session collisions
            start_delay = random.uniform(0.5, 3.0)
            print(f"⏱️  Ticket {ticket_id} verification starting in {start_delay:.1f}s...")
            time.sleep(start_delay)
            
            print(f"\n{'='*60}")
            print(f"🔍 Verifying Ticket {ticket_id}")
            print(f"⏰ Started at: {time.strftime('%H:%M:%S')}")
            print('='*60)
            
            try:
                # Get ticket details
                ticket_data = all_tickets.get(ticket_id)
                if not ticket_data:
                    print(f"❌ Ticket {ticket_id} not found")
                    return False
                
                # Create orchestrator for Claude agent
                orchestrator = ClaudeCodeOrchestrator()
                
                # Build verification prompt
                prompt = f"""Verify and complete ticket {ticket_id} from tickets.yaml in the current directory.

VERIFICATION TASK:
1. First, use 'cat tickets.yaml' or Read tool to understand ticket {ticket_id} requirements
2. Check EACH acceptance criterion to see if it has been met:
   - For file creation criteria: Check if the file exists with correct content
   - For implementation criteria: Verify the feature is properly implemented
   - For update criteria: Check if the updates were made correctly
3. If ANY criteria are NOT met, COMPLETE them now with production-quality code
4. Once ALL criteria are verified/completed, update tickets.yaml status to "DONE"

CRITICAL REQUIREMENTS:
- Actually CHECK if work is done, don't assume
- If work is incomplete, FINISH it properly
- Be surgical and minimalistic - only add what's missing
- Ensure production quality - no shortcuts or mocks
- Update ticket status ONLY after all criteria are verified

Report what you found and what you completed."""
                
                # Create task for orchestrator
                task = orchestrator.create_task(
                    description=f"Verify Ticket {ticket_id}",
                    prompt=prompt,
                    working_directory=str(project_root),
                    timeout=600,  # 10 minutes for verification
                    task_id=f"verify_{ticket_id}"  # Unique ID for tmux session
                )
                
                # Execute task with Claude agent
                result = orchestrator.execute_task(task)
                
                if result.status.value == "completed":
                    # Now actually validate the acceptance criteria
                    from hydra.ticket_workflow import validate_acceptance_criteria
                    
                    print(f"\n🔍 Validating ticket {ticket_id} after verification...")
                    validation_passed = validate_acceptance_criteria(ticket_data, str(project_root))
                    
                    if validation_passed:
                        print(f"✅ Ticket {ticket_id} verified and all criteria met")
                        return True
                    else:
                        print(f"❌ Ticket {ticket_id} - agent ran but criteria still not met")
                        return False
                else:
                    print(f"❌ Ticket {ticket_id} verification task failed")
                    return False
                    
            except Exception as e:
                print(f"❌ Error verifying ticket {ticket_id}: {e}")
                return False
        
        # Run verification in parallel
        results = {}
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(verify_ticket_with_agent, ticket_id): ticket_id
                for ticket_id in all_tickets.keys()
            }
            
            for future in as_completed(futures):
                ticket_id = futures[future]
                try:
                    success = future.result()
                    results[ticket_id] = success
                except Exception as e:
                    print(f"❌ Exception for ticket {ticket_id}: {e}")
                    results[ticket_id] = False
        
        # Generate report
        elapsed = time.time() - start_time
        successful = sum(1 for s in results.values() if s)
        failed = len(results) - successful
        
        # Display results
        print("\n" + "="*60)
        print("PARALLEL TICKET VERIFICATION REPORT")
        print("="*60)
        
        print(f"\n📊 Summary:")
        print(f"  Total tickets verified: {len(results)}")
        print(f"  ✅ Successfully verified/completed: {successful}")
        print(f"  ❌ Failed verification: {failed}")
        print(f"  ⏱️  Total time: {elapsed:.1f}s")
        print(f"  ⚡ Average time per ticket: {elapsed/len(results):.1f}s")
        
        # Show individual results
        if failed > 0:
            print(f"\n❌ Failed tickets:")
            for ticket_id, success in results.items():
                if not success:
                    print(f"  - Ticket {ticket_id}")
        
        # Save report if requested
        if args.save_report:
            import json
            report_path = Path(".hydra/reports") / f"verify_parallel_{Path(tickets_path).stem}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_data = {
                'tickets_path': str(tickets_path),
                'total_tickets': len(results),
                'successful': successful,
                'failed': failed,
                'elapsed_time': elapsed,
                'results': results,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(report_path, 'w') as f:
                json.dump(report_data, f, indent=2, default=str)
            print(f"\n📄 Verification report saved: {report_path}")
        
        # Return based on verification status
        if failed == 0:
            print("\n✅ All tickets successfully verified and completed!")
            return 0
        else:
            print(f"\n⚠️  {failed} tickets failed verification")
            return 1
            
    except Exception as e:
        print(f"❌ Verification error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
