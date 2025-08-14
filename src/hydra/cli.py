"""Cli module."""

#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, skip loading
    pass

from hydra.templates import TemplateEngine, TemplateValidator
from hydra.ticket_workflow import (
    execute_single_ticket,
    generate_tickets_md,
    run_all_tickets,
)


def format_code_block(code: str) -> str:
    lines = code.strip().split('\n')
    max_width = max(len(line) for line in lines) if lines else 0
    border = '─' * (max_width + 4)

    result = f"┌{border}┐\n"
    for line in lines:
        result += f"│ {line:<{max_width + 2}} │\n"
    result += f"└{border}┘"

    return result


def format_results(results: Dict[str, Any], indent: int = 0) -> str:
    output = []
    prefix = "  " * indent

    for key, value in results.items():
        if key == "summary":
            output.append(f"{prefix}Summary:")
            output.append(f"{prefix}  Total agents: {value.get('total_agents', 0)}")
            output.append(f"{prefix}  Successful: {value.get('successful', 0)}")
            output.append(f"{prefix}  Failed: {value.get('failed', 0)}")
            output.append(f"{prefix}  Max depth: {value.get('max_depth', 0)}")
            code_gen = value.get('code_generated', False)
            output.append(f"{prefix}  Code generated: {code_gen}")
        elif isinstance(value, dict):
            if "error" in value:
                output.append(f"{prefix}{key}: ❌ {value['error']}")
            elif value.get("success", True):
                output.append(f"{prefix}{key}: ✅ Completed")
                if "task" in value:
                    task = value['task']
                    task_preview = task[:50] + "..." if len(task) > 50 else task
                    output.append(f"{prefix}  Task: {task_preview}")
                if value.get("generated_code") and len(value['generated_code']) < 200:
                    code_len = len(value['generated_code'])
                    output.append(f"{prefix}  Generated: {code_len} chars of code")
            else:
                output.append(f"{prefix}{key}: ❌ Failed")
                if "task" in value:
                    output.append(f"{prefix}  Task: {value['task'][:50]}...")
        elif isinstance(value, str) and len(value) < 100:
            output.append(f"{prefix}{key}: {value}")

    return "\n".join(output)


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Hydra: Multi-agent code generation system with project templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  hydra \"Calculate fibonacci numbers\"\n  "
               "hydra template create flask_web_app ./my-app --project_name=MyApp"
    )

    # Global provider override flags
    parser.add_argument(
        "--provider",
        choices=["venice", "claude_tmux", "claude_code", "anthropic", "openai", "mock"],
        help="Override the LLM provider (default: from env or config)"
    )
    parser.add_argument(
        "--model",
        help="Override the model (e.g., qwen-2.5-coder-32b, gpt-4)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass all caching (model lists, parsed tickets, etc.)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Task execution subcommand (default behavior)
    task_parser = subparsers.add_parser("run", help="Execute a task")
    task_parser.add_argument(
        "task",
        help="Task description for the agent system"
    )
    task_parser.add_argument(
        "--agent-name",
        default="boss",
        help="Name of the root agent (default: boss)"
    )
    task_parser.add_argument(
        "--depth",
        type=int,
        default=0,
        help="Starting depth (default: 0)"
    )
    task_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    # Template subcommand
    template_parser = subparsers.add_parser(
        "template", help="Project template operations"
    )
    template_subparsers = template_parser.add_subparsers(
        dest="template_action", help="Template actions"
    )

    # Template list
    template_subparsers.add_parser("list", help="List available templates")

    # Template create
    create_parser = template_subparsers.add_parser(
        "create", help="Create project from template"
    )
    create_parser.add_argument("template_name", help="Template to use")
    create_parser.add_argument("output_dir", help="Output directory")
    create_parser.add_argument(
        "--param", action="append",
        help="Template parameter (format: key=value)"
    )

    # Template validate
    validate_parser = template_subparsers.add_parser(
        "validate", help="Validate templates"
    )
    validate_parser.add_argument("--template", help="Specific template to validate")

    # Ticket workflow subcommand
    ticket_parser = subparsers.add_parser("ticket", help="Ticket workflow operations")
    ticket_subparsers = ticket_parser.add_subparsers(
        dest="ticket_action", help="Ticket actions"
    )

    # Create tickets
    create_tickets_parser = ticket_subparsers.add_parser(
        "create", help="Create tickets.md from project description"
    )
    create_tickets_parser.add_argument("description", help="Project description")
    create_tickets_parser.add_argument(
        "--output", default="tickets.md", help="Output file (default: tickets.md)"
    )
    create_tickets_parser.add_argument(
        "--project-type", choices=["migration", "feature", "bugfix", "refactor"],
        help="Project type for template-based ticket structure"
    )
    create_tickets_parser.add_argument(
        "--interactive", action="store_true",
        help="Launch interactive refinement after ticket creation"
    )

    # Execute ticket
    execute_ticket_parser = ticket_subparsers.add_parser(
        "execute", help="Execute specific ticket"
    )
    execute_ticket_parser.add_argument(
        "identifier", help="Ticket identifier to execute (e.g., 1, 007, TICKET-001)"
    )
    execute_ticket_parser.add_argument(
        "--tickets", default="tickets.md", help="Tickets file (default: tickets.md)"
    )
    execute_ticket_parser.add_argument(
        "--skip-preflight", action="store_true",
        help="Skip pre-flight validation checks"
    )
    execute_ticket_parser.add_argument(
        "--no-cache", action="store_true",
        help="Bypass all caching (model lists, parsed tickets, etc.)"
    )

    # Run all tickets
    run_tickets_parser = ticket_subparsers.add_parser(
        "run-all", help="Execute all tickets in sequence"
    )
    run_tickets_parser.add_argument(
        "--tickets", default="tickets.md", help="Tickets file (default: tickets.md)"
    )
    run_tickets_parser.add_argument(
        "--skip-preflight", action="store_true",
        help="Skip pre-flight validation checks"
    )
    run_tickets_parser.add_argument(
        "--no-cache", action="store_true",
        help="Bypass all caching (model lists, parsed tickets, etc.)"
    )

    # Verify ticket completion
    verify_parser = ticket_subparsers.add_parser(
        "verify", help="Verify ticket acceptance criteria"
    )
    verify_parser.add_argument("identifier", help="Ticket identifier to verify")
    verify_parser.add_argument(
        "--tickets", default="tickets.md", help="Tickets file (default: tickets.md)"
    )

    # Run quality gates
    quality_parser = ticket_subparsers.add_parser(
        "quality", help="Run quality gates for a ticket"
    )
    quality_parser.add_argument("identifier", help="Ticket identifier")
    quality_parser.add_argument(
        "--save", action="store_true", help="Save report to file"
    )

    # Auto workflow - dependency-aware parallel execution
    auto_parser = ticket_subparsers.add_parser(
        "auto", help="Automatically execute tickets with dependency-aware parallelism"
    )
    auto_parser.add_argument(
        "--tickets", default="tickets.md", help="Tickets file (default: tickets.md)"
    )
    auto_parser.add_argument(
        "--parallel", type=int, default=3, help="Max parallel agents (default: 3)"
    )
    auto_parser.add_argument("--dir", help="Project directory (default: current dir)")
    auto_parser.add_argument(
        "--skip-preflight", action="store_true",
        help="Skip pre-flight validation checks"
    )

    # Parallel execution
    parallel_parser = ticket_subparsers.add_parser(
        "parallel", help="Execute tickets in parallel with dependency resolution"
    )
    parallel_parser.add_argument(
        "--tickets", default="tickets.md", help="Tickets file (default: tickets.md)"
    )
    parallel_parser.add_argument(
        "--workers", type=int, default=3, help="Max parallel workers (default: 3)"
    )
    parallel_parser.add_argument(
        "--save-log", action="store_true", help="Save execution log"
    )
    parallel_parser.add_argument(
        "--async", action="store_true", help="Use async execution engine (experimental)"
    )
    parallel_parser.add_argument(
        "--skip-preflight", action="store_true",
        help="Skip pre-flight validation checks"
    )

    # Batch execution
    batch_parser = ticket_subparsers.add_parser(
        "batch", help="Execute compatible tickets in batches to reduce session overhead"
    )
    batch_parser.add_argument(
        "--tickets", default="tickets.md", help="Tickets file (default: tickets.md)"
    )
    batch_parser.add_argument(
        "--workers", type=int, default=3, help="Max parallel workers (default: 3)"
    )
    batch_parser.add_argument(
        "--max-batch-size", type=int, default=5,
        help="Maximum tickets per batch (default: 5)"
    )
    batch_parser.add_argument(
        "--max-complexity", type=int, default=100,
        help="Maximum complexity score per batch (default: 100)"
    )
    batch_parser.add_argument(
        "--min-batch-tickets", type=int, default=2,
        help="Minimum tickets to create a batch (default: 2)"
    )
    batch_parser.add_argument(
        "--disable-batching", action="store_true",
        help="Disable batching (run individual tickets)"
    )
    batch_parser.add_argument(
        "--save-log", action="store_true", help="Save execution log"
    )
    batch_parser.add_argument(
        "--skip-preflight", action="store_true",
        help="Skip pre-flight validation checks"
    )

    # Verify and fix tickets in parallel
    verify_parallel_parser = ticket_subparsers.add_parser(
        "verify-parallel", help="Verify and fix unmet acceptance criteria in parallel"
    )
    verify_parallel_parser.add_argument(
        "--tickets", default="tickets.md", help="Tickets file (default: tickets.md)"
    )
    verify_parallel_parser.add_argument(
        "--workers", type=int, default=4, help="Max parallel workers (default: 4)"
    )
    verify_parallel_parser.add_argument(
        "--save-report", help="Save verification report to file"
    )
    verify_parallel_parser.add_argument(
        "--static-only", action="store_true",
        help="Only use static analysis, skip model-based verification"
    )
    verify_parallel_parser.add_argument(
        "--skip-preflight", action="store_true",
        help="Skip pre-flight validation checks"
    )

    # Claude Code orchestration subcommand
    claude_parser = subparsers.add_parser(
        "claude", help="Claude Code CLI orchestration"
    )
    claude_subparsers = claude_parser.add_subparsers(
        dest="claude_action", help="Claude Code actions"
    )

    # Execute task with Claude Code
    execute_parser = claude_subparsers.add_parser(
        "execute", help="Execute a task with Claude Code"
    )
    execute_parser.add_argument("task", help="Task description for Claude Code")
    execute_parser.add_argument(
        "--timeout", type=int, default=300, help="Timeout in seconds (default: 300)"
    )
    execute_parser.add_argument(
        "--cwd", help="Working directory (default: current dir)"
    )

    # Create development session
    session_parser = claude_subparsers.add_parser(
        "session", help="Create a Claude Code development session"
    )
    session_parser.add_argument("project_path", help="Path to project directory")
    session_parser.add_argument(
        "--name", help="Session name (auto-generated if not provided)"
    )

    # List sessions
    claude_subparsers.add_parser(
        "list", help="List active Claude Code sessions"
    )

    # Attach to session
    attach_parser = claude_subparsers.add_parser(
        "attach", help="Attach to a Claude Code session"
    )
    attach_parser.add_argument("session_name", help="Name of session to attach to")

    # Kill session
    kill_parser = claude_subparsers.add_parser(
        "kill", help="Kill a Claude Code session"
    )
    kill_parser.add_argument("session_name", help="Name of session to kill")

    # Save session
    save_parser = claude_subparsers.add_parser(
        "save", help="Save Claude Code session state"
    )
    save_parser.add_argument("session_name", help="Name of session to save")

    # Restore session
    restore_parser = claude_subparsers.add_parser(
        "restore", help="Restore Claude Code session"
    )
    restore_parser.add_argument("session_name", help="Name of session to restore")

    # Context management subcommand
    context_parser = subparsers.add_parser(
        "context", help="Manage ticket execution context and artifacts"
    )
    context_subparsers = context_parser.add_subparsers(
        dest="context_action", help="Context actions"
    )

    # Show all contexts
    context_subparsers.add_parser(
        "show", help="Show all tracked ticket contexts"
    )

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
    clear_parser.add_argument(
        "--all", action="store_true", help="Clear all contexts"
    )

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
        "--format", choices=["json", "text"], default="text",
        help="Export format (default: text)"
    )

    # Preview ticket updates
    preview_parser = context_subparsers.add_parser(
        "preview-updates", help="Preview how future tickets would be updated"
    )
    preview_parser.add_argument(
        "ticket_id", help="Completed ticket ID to preview updates for"
    )

    # Main parser arguments (not including task - that's in subparsers)
    parser.add_argument(
        "--agent-name",
        default="boss",
        help="Name of the root agent (default: boss)"
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=0,
        help="Starting depth (default: 0)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    return parser


def get_task_input(args, parser):
    """Get task input from arguments or stdin."""
    if args.task is None:
        if sys.stdin.isatty():
            parser.print_help()
            return None, 1
        else:
            task = sys.stdin.read().strip()
    else:
        task = args.task

    if not task:
        print("Error: No task provided", file=sys.stderr)
        return None, 1

    return task, 0


def print_results(results, json_output):
    """Print execution results in the specified format."""
    if json_output:
        print(json.dumps(results, indent=2, default=str))
    else:
        # Show final generated code prominently
        if results.get("final_code"):
            print("\n" + "="*60)
            print("GENERATED CODE:")
            print("="*60)
            print(results["final_code"])
            print("="*60)

        # Show execution outputs if any
        if results.get("execution_outputs"):
            print("\nEXECUTION OUTPUTS:")
            print("-"*40)
            print(results["execution_outputs"])
            print("-"*40)

        # Show plan if it's not code
        plan = results.get("plan", "")
        if plan and not results.get("final_code"):
            print("\nGenerated Code:")
            print("-"*40)
            print(plan)
            print("-"*40)

        if results.get("subtasks"):
            print(f"\nSubtasks ({len(results['subtasks'])}):")
            for i, subtask in enumerate(results["subtasks"], 1):
                print(f"  {i}. {subtask}")

        if results.get("results"):
            print("\nDetailed Results:")
            print(format_results(results["results"]))

        agents = results.get("agents", [])
        if agents:
            print(f"\nAgents created: {', '.join(agents)}")


def _handle_list_templates(engine):
    """Handle template list command."""
    templates = engine.list_templates()
    if not templates:
        print("No templates available.")
        return 0

    print("Available templates:")
    for template_name in templates:
        try:
            template = engine.load_template(template_name)
            print(f"  {template_name}: {template.description}")
            print(f"    Tags: {', '.join(template.tags)}")
        except Exception as e:
            print(f"  {template_name}: Error loading template ({e})")
    return 0


def _parse_template_params(param_list):
    """Parse template parameters from command line."""
    params = {}
    if param_list:
        for param_str in param_list:
            if '=' not in param_str:
                print(f"Invalid parameter format: {param_str}. Use key=value")
                return None
            key, value = param_str.split('=', 1)
            try:
                params[key] = json.loads(value)
            except Exception:
                params[key] = value
    return params


def _handle_create_template(engine, args):
    """Handle template create command."""
    try:
        engine.load_template(args.template_name)
        params = _parse_template_params(args.param)
        if params is None:
            return 1

        result = engine.generate_project(
            args.template_name, Path(args.output_dir), params
        )

        print(f"Project created successfully in {result['output_dir']}")
        print(f"Generated {len(result['generated_files'])} files")

        if result['post_generation_commands']:
            print("\nRecommended next steps:")
            for i, cmd in enumerate(result['post_generation_commands'], 1):
                print(f"  {i}. {cmd}")
        return 0

    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


def _handle_validate_templates(args):
    """Handle template validation command."""
    if args.template:
        # Validate specific template
        template_dir = (
            Path(__file__).parent / 'templates' / 'templates' / args.template
        )
        is_valid, errors = TemplateValidator.validate_template_structure(
            template_dir
        )

        if is_valid:
            print(f"Template '{args.template}' is valid ✅")
        else:
            print(f"Template '{args.template}' has errors ❌")
            for error in errors:
                print(f"  - {error}")
        return 0 if is_valid else 1
    else:
        # Validate all templates
        templates_dir = Path(__file__).parent / 'templates' / 'templates'
        results = TemplateValidator.validate_all_templates(templates_dir)

        valid_count = sum(1 for is_valid, _ in results.values() if is_valid)
        total_count = len(results)

        print(f"Template validation results: {valid_count}/{total_count} valid")

        for template_name, (is_valid, errors) in results.items():
            status = "✅" if is_valid else "❌"
            print(f"  {template_name}: {status}")
            if not is_valid:
                for error in errors[:3]:  # Show first 3 errors
                    print(f"    - {error}")
                if len(errors) > 3:
                    print(f"    ... and {len(errors) - 3} more errors")

        return 0 if valid_count == total_count else 1


def handle_template_command(args):
    """Handle template subcommands."""
    engine = TemplateEngine()

    if args.template_action == "list":
        return _handle_list_templates(engine)
    elif args.template_action == "create":
        return _handle_create_template(engine, args)
    elif args.template_action == "validate":
        return _handle_validate_templates(args)
    else:
        print("Unknown template action")
        return 1


def _handle_create_tickets(args):
    """Handle ticket create command."""
    try:
        project_type = getattr(args, 'project_type', None)
        success = generate_tickets_md(args.description, args.output, project_type)

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


def _handle_execute_ticket(args):
    """Handle ticket execute command."""
    try:
        from hydra.monitoring import monitoring
        correlation_id = monitoring.set_correlation_id(f"ticket_{args.identifier}")
        print(f"🔗 Session: {correlation_id}")

        skip_preflight = getattr(args, 'skip_preflight', False)
        success = execute_single_ticket(args.tickets, args.identifier, skip_preflight=skip_preflight)
        return 0 if success else 1
    except Exception as e:
        print(f"Error executing ticket: {e}")
        return 1


def _handle_run_all_tickets(args):
    """Handle run all tickets command."""
    try:
        skip_preflight = getattr(args, 'skip_preflight', False)
        success = run_all_tickets(args.tickets, skip_preflight=skip_preflight)
        return 0 if success else 1
    except Exception as e:
        print(f"Error running tickets: {e}")
        return 1


def _handle_verify_ticket(args):
    """Handle ticket verification."""
    from hydra.verification.ticket_verifier import TicketVerifier

    verifier = TicketVerifier(os.path.dirname(args.tickets))

    try:
        report = verifier.verify_ticket(args.tickets, args.identifier)
        print(verifier.generate_report(report))

        if report.coverage >= 80:
            return 0
        else:
            return 1

    except Exception as e:
        print(f"Verification error: {e}")
        return 1


def _handle_quality_gates(args):
    """Handle quality gates command."""
    from hydra.quality import QualityGateRunner

    runner = QualityGateRunner(os.getcwd())

    try:
        report = runner.run_quality_gates(args.identifier)
        print(runner.generate_report(report))

        if args.save:
            report_file = runner.save_report(report)
            print(f"\n📄 Report saved: {report_file}")

        if report.overall_status.value == "passed":
            return 0
        elif report.overall_status.value == "warning":
            return 0
        else:
            return 1

    except Exception as e:
        print(f"Quality gate error: {e}")
        return 1


def _handle_parallel_execution(args):
    """Handle parallel ticket execution with dependency resolution."""
    # Check if async mode is requested
    if getattr(args, 'async', False):
        return _handle_async_parallel_execution(args)
    else:
        return _handle_sync_parallel_execution(args)


def _handle_sync_parallel_execution(args):
    """Handle synchronous parallel ticket execution."""
    from hydra.dashboard import DashboardServer, DashboardState
    from hydra.parallel import ParallelExecutor
    from hydra.parallel.executor import ExecutionStatus
    from hydra.production_config import get_production_config

    try:
        # Load production configuration
        config = get_production_config()

        # Override with command line arguments if provided
        if hasattr(args, 'workers'):
            config.max_parallel_tickets = args.workers

        # Apply environment variables from config
        for key, value in config.to_env_vars().items():
            os.environ[key] = value

        # Get absolute path to tickets file
        tickets_path = Path(args.tickets).resolve()
        if not tickets_path.exists():
            print(f"❌ Tickets file not found: {tickets_path}")
            return 1

        # Initialize dashboard if enabled
        dashboard_state = None
        dashboard_server = None
        if config.enable_dashboard:
            dashboard_state = DashboardState()
            dashboard_server = DashboardServer(state=dashboard_state)
            dashboard_server.start()

        # Initialize executor with production config
        project_root = tickets_path.parent
        executor = ParallelExecutor(
            max_workers=config.max_parallel_tickets,
            project_root=str(project_root),
            dashboard_state=dashboard_state
        )

        # Log configuration mode
        print(f"🔧 Production Mode: File locking {'enabled' if config.enable_file_locking else 'disabled'}")
        print(f"🔧 Smart scheduling: {'enabled' if config.enable_smart_scheduling else 'disabled'}")

        print(f"🎯 Loading tickets from: {tickets_path}")

        # Load tickets
        tickets = executor.load_tickets(str(tickets_path))
        if not tickets:
            print("❌ No pending tickets found")
            return 1

        # Run preflight validation unless skipped
        skip_preflight = getattr(args, 'skip_preflight', False)
        if not skip_preflight:
            print("🚀 Running preflight validation...")
            from hydra.preflight import PreflightChecker
            checker = PreflightChecker()
            report = checker.run_preflight_checks(str(tickets_path))

            if report.has_critical_issues():
                print("🚨 PREFLIGHT FAILED - Critical issues found!")
                print("\nCritical Issues:")
                for check in report.get_critical_issues():
                    print(f"❌ {check.description}: {check.message}")
                print("\nUse --skip-preflight to override, but execution may fail.")
                return 1
            elif report.has_errors() or report.has_warnings():
                print("⚠️  Preflight validation completed with warnings/errors:")
                for check in report.get_failed_checks()[:3]:  # Show first 3
                    print(f"{check.status_emoji} {check.description}: {check.message}")
                if len(report.get_failed_checks()) > 3:
                    print(f"   ... and {len(report.get_failed_checks()) - 3} more issues")
                print("Proceeding with execution despite warnings...")
            else:
                print("✅ Preflight validation passed")
        else:
            print("⚡ Skipping preflight validation (--skip-preflight)")

        # Count only pending tickets (not already completed)
        pending_count = len([t for t in tickets.values()
                           if t.status == ExecutionStatus.PENDING])
        total_count = len(tickets)
        completed_count = len(executor.completed_tickets)

        if completed_count > 0:
            print(f"✅ {completed_count} tickets already completed")
        print(f"📋 Found {pending_count} pending tickets")

        # Build execution plan
        plan = executor.build_execution_plan()

        # Initialize dashboard session
        import uuid
        session_id = str(uuid.uuid4())[:8]
        dashboard_state.start_session(
            session_id=session_id,
            tickets_path=str(tickets_path),
            total_tickets=len(tickets),
            total_waves=len(plan.waves),
            workers=args.workers
        )

        # Execute plan
        summary = executor.execute_plan(plan, str(tickets_path))

        # Generate and print report
        report = executor.generate_report(summary)
        print(report)

        # Save log if requested
        if args.save_log:
            log_file = executor.save_execution_log(summary)
            print(f"\n📄 Execution log saved: {log_file}")

        # Return success if all tickets completed
        if summary['completed'] == summary['total_tickets']:
            print("\n✅ All tickets completed successfully!")

            # Save completion report
            report_path = executor.save_completion_report(summary)
            print(f"\n📄 Completion report saved: {report_path}")
            print(f"📊 Dashboard snapshot saved in: {tickets_path.parent}/.hydra/dashboard/")
            print("\n💡 Tip: Keep the dashboard open at http://localhost:8080 to review results")

            executor.shutdown()
            dashboard_server.stop()
            return 0
        else:
            functionally_completed = summary.get('functionally_completed', summary['completed'])
            quality_passed = summary.get('quality_passed', summary['completed'])
            total = summary['total_tickets']

            if functionally_completed == total:
                # All tickets ran but some had quality issues
                print(f"\n✅ All {total} tickets executed successfully!")
                if quality_passed < functionally_completed:
                    print(f"⚠️  {functionally_completed - quality_passed} tickets have quality issues (lint/test warnings)")
                    print("   Review the output and fix quality issues as needed.")
            else:
                # Some tickets failed to execute
                print(f"\n⚠️ Execution incomplete: {functionally_completed}/{total} tickets executed")
                if summary.get('failed', 0) > 0:
                    print(f"   ❌ {summary['failed']} tickets failed to execute")
                if summary.get('blocked', 0) > 0:
                    print(f"   ⛔ {summary['blocked']} tickets blocked by dependencies")

            # Still save a report even if incomplete
            if functionally_completed > 0:
                report_path = executor.save_completion_report(summary)
                print(f"\n📄 Completion report saved: {report_path}")

            executor.shutdown()
            dashboard_server.stop()
            return 1

    except Exception as e:
        print(f"❌ Parallel execution error: {e}")
        if 'executor' in locals():
            executor.shutdown()
        if 'dashboard_server' in locals():
            dashboard_server.stop()
        return 1


def _handle_async_parallel_execution(args):
    """Handle asynchronous parallel ticket execution."""
    import asyncio

    from hydra.dashboard import DashboardServer, DashboardState
    from hydra.parallel import AsyncParallelExecutor
    from hydra.parallel.async_executor import ExecutionStatus
    from hydra.production_config import get_production_config

    async def async_main():
        try:
            # Load production configuration
            config = get_production_config()

            # Override with command line arguments
            if hasattr(args, 'workers'):
                config.max_parallel_tickets = args.workers

            # Apply environment variables from config
            for key, value in config.to_env_vars().items():
                os.environ[key] = value

            # Get absolute path to tickets file
            tickets_path = Path(args.tickets).resolve()
            if not tickets_path.exists():
                print(f"❌ Tickets file not found: {tickets_path}")
                return 1

            # Initialize dashboard if enabled
            dashboard_state = None
            dashboard_server = None
            if config.enable_dashboard:
                dashboard_state = DashboardState()
                dashboard_server = DashboardServer(state=dashboard_state)
                dashboard_server.start()

            # Initialize async executor
            project_root = tickets_path.parent
            executor = AsyncParallelExecutor(
                max_concurrent=config.max_parallel_tickets,
                project_root=str(project_root),
                dashboard_state=dashboard_state
            )

            # Log configuration mode
            print(f"🔧 Production Mode: File locking {'enabled' if config.enable_file_locking else 'disabled'}")
            print("⚡ Async Mode: Dynamic scheduling enabled")
            print(f"🎯 Loading tickets from: {tickets_path}")

            # Load tickets asynchronously
            tickets = await executor.load_tickets(str(tickets_path))
            if not tickets:
                print("❌ No pending tickets found")
                return 1

            # Run preflight validation unless skipped
            skip_preflight = getattr(args, 'skip_preflight', False)
            if not skip_preflight:
                print("🚀 Running preflight validation...")
                from hydra.preflight import PreflightChecker
                checker = PreflightChecker()
                report = checker.run_preflight_checks(str(tickets_path))

                if report.has_critical_issues():
                    print("🚨 PREFLIGHT FAILED - Critical issues found!")
                    print("\nCritical Issues:")
                    for check in report.get_critical_issues():
                        print(f"❌ {check.description}: {check.message}")
                    print("\nUse --skip-preflight to override, but execution may fail.")
                    return 1
                elif report.has_errors() or report.has_warnings():
                    print("⚠️  Preflight validation completed with warnings/errors:")
                    for check in report.get_failed_checks()[:3]:  # Show first 3
                        print(f"{check.status_emoji} {check.description}: {check.message}")
                    if len(report.get_failed_checks()) > 3:
                        print(f"   ... and {len(report.get_failed_checks()) - 3} more issues")
                    print("Proceeding with execution despite warnings...")
                else:
                    print("✅ Preflight validation passed")
            else:
                print("⚡ Skipping preflight validation (--skip-preflight)")

            # Count pending tickets
            pending_count = len([t for t in tickets.values()
                               if t.status == ExecutionStatus.PENDING])
            completed_count = len(executor.completed_tickets)

            if completed_count > 0:
                print(f"✅ {completed_count} tickets already completed")
            print(f"📋 Found {pending_count} pending tickets")

            # Build dynamic execution plan
            plan = executor.build_dynamic_execution_plan()

            # Execute plan asynchronously
            summary = await executor.execute_tickets_dynamically(str(tickets_path))

            # Generate and print report
            report = executor.generate_report(summary)
            print(report)

            # Save log if requested
            if args.save_log:
                log_file = await executor.save_execution_log(summary)
                print(f"\n📄 Execution log saved: {log_file}")

            # Return success if all tickets completed
            if summary['completed'] == summary['total_tickets']:
                print("\n✅ All tickets completed successfully!")

                # Save completion report
                report_path = await executor.save_completion_report(summary)
                print(f"\n📄 Async completion report saved: {report_path}")
                print("\n💡 Tip: Async execution completed with dynamic scheduling")

                executor.shutdown()
                if dashboard_server:
                    dashboard_server.stop()
                return 0
            else:
                functionally_completed = summary.get('functionally_completed', summary['completed'])
                quality_passed = summary.get('quality_passed', summary['completed'])
                total = summary['total_tickets']

                if functionally_completed == total:
                    print(f"\n✅ All {total} tickets executed successfully!")
                    if quality_passed < functionally_completed:
                        print(f"⚠️  {functionally_completed - quality_passed} tickets have quality issues")
                else:
                    print(f"\n⚠️ Execution incomplete: {functionally_completed}/{total} tickets executed")

                # Still save a report even if incomplete
                if functionally_completed > 0:
                    report_path = await executor.save_completion_report(summary)
                    print(f"\n📄 Completion report saved: {report_path}")

                executor.shutdown()
                if dashboard_server:
                    dashboard_server.stop()
                return 1

        except Exception as e:
            print(f"❌ Async parallel execution error: {e}")
            if 'executor' in locals():
                executor.shutdown()
            if 'dashboard_server' in locals():
                dashboard_server.stop()
            return 1

    try:
        # Run async main function
        return asyncio.run(async_main())
    except Exception as e:
        print(f"❌ Failed to start async execution: {e}")
        return 1


def _handle_batch_execution(args):
    """Handle batch ticket execution with reduced session overhead."""
    import asyncio

    from hydra.dashboard import DashboardServer, DashboardState
    from hydra.parallel.batch_executor import BatchConfig, BatchExecutor
    from hydra.production_config import get_production_config

    async def batch_main():
        try:
            # Load production configuration
            config = get_production_config()

            # Override with command line arguments
            if hasattr(args, 'workers'):
                config.max_parallel_tickets = args.workers

            # Apply environment variables from config
            for key, value in config.to_env_vars().items():
                os.environ[key] = value

            # Get absolute path to tickets file
            tickets_path = Path(args.tickets).resolve()
            if not tickets_path.exists():
                print(f"❌ Tickets file not found: {tickets_path}")
                return 1

            # Initialize dashboard if enabled
            dashboard_state = None
            dashboard_server = None
            if config.enable_dashboard:
                dashboard_state = DashboardState()
                dashboard_server = DashboardServer(state=dashboard_state)
                dashboard_server.start()

            # Configure batch processing
            batch_config = BatchConfig(
                max_batch_size=getattr(args, 'max_batch_size', 5),
                max_complexity_score=getattr(args, 'max_complexity', 100),
                min_tickets_for_batch=getattr(args, 'min_batch_tickets', 2),
                enable_batching=not getattr(args, 'disable_batching', False)
            )

            # Initialize batch executor
            project_root = tickets_path.parent
            executor = BatchExecutor(
                batch_config=batch_config,
                max_concurrent=config.max_parallel_tickets,
                project_root=str(project_root),
                dashboard_state=dashboard_state
            )

            print(f"📦 Batch Processing Mode: {'enabled' if batch_config.enable_batching else 'disabled'}")
            print(f"🎯 Max batch size: {batch_config.max_batch_size}")
            print(f"🎯 Loading tickets from: {tickets_path}")

            # Load tickets and analyze for batching
            tickets = await executor.load_tickets(str(tickets_path))
            if not tickets:
                print("❌ No pending tickets found")
                return 1

            # Run preflight validation unless skipped
            skip_preflight = getattr(args, 'skip_preflight', False)
            if not skip_preflight:
                print("🚀 Running preflight validation...")
                from hydra.preflight import PreflightChecker
                checker = PreflightChecker()
                report = checker.run_preflight_checks(str(tickets_path))

                if report.has_critical_issues():
                    print("🚨 PREFLIGHT FAILED - Critical issues found!")
                    print("\nCritical Issues:")
                    for check in report.get_critical_issues():
                        print(f"❌ {check.description}: {check.message}")
                    print("\nUse --skip-preflight to override, but execution may fail.")
                    return 1
                elif report.has_errors() or report.has_warnings():
                    print("⚠️  Preflight validation completed with warnings/errors:")
                    for check in report.get_failed_checks()[:3]:  # Show first 3
                        print(f"{check.status_emoji} {check.description}: {check.message}")
                    if len(report.get_failed_checks()) > 3:
                        print(f"   ... and {len(report.get_failed_checks()) - 3} more issues")
                    print("Proceeding with execution despite warnings...")
                else:
                    print("✅ Preflight validation passed")
            else:
                print("⚡ Skipping preflight validation (--skip-preflight)")

            pending_count = len([t for t in tickets.values()
                               if t.status.name == "PENDING"])
            completed_count = len(executor.completed_tickets)

            if completed_count > 0:
                print(f"✅ {completed_count} tickets already completed")
            print(f"📋 Found {pending_count} pending tickets")

            if batch_config.enable_batching and len(executor.batches) > 0:
                print(f"📦 Created {len(executor.batches)} batch groups:")
                for batch_id, batch in executor.batches.items():
                    print(f"   {batch_id}: {len(batch.ticket_ids)} tickets ({batch.model})")

            # Execute with batch processing
            summary = await executor.execute_tickets_dynamically(str(tickets_path))

            # Generate and print report
            report = executor.generate_report(summary)
            print(report)

            # Save log if requested
            if args.save_log:
                log_file = await executor.save_execution_log(summary)
                print(f"\n📄 Execution log saved: {log_file}")

            # Return success if all tickets completed
            if summary['completed'] == summary['total_tickets']:
                print("\n✅ All tickets completed successfully!")

                # Save completion report
                report_path = await executor.save_completion_report(summary)
                print(f"\n📄 Batch completion report saved: {report_path}")

                if summary.get('overhead_reduction', 0) > 0:
                    print(f"⚡ Session overhead reduced by {summary['overhead_reduction']:.1f}%!")

                executor.shutdown()
                if dashboard_server:
                    dashboard_server.stop()
                return 0
            else:
                functionally_completed = summary.get('functionally_completed', summary['completed'])
                quality_passed = summary.get('quality_passed', summary['completed'])
                total = summary['total_tickets']

                if functionally_completed == total:
                    print(f"\n✅ All {total} tickets executed successfully!")
                    if quality_passed < functionally_completed:
                        print(f"⚠️  {functionally_completed - quality_passed} tickets have quality issues")
                else:
                    print(f"\n⚠️ Execution incomplete: {functionally_completed}/{total} tickets executed")

                executor.shutdown()
                if dashboard_server:
                    dashboard_server.stop()
                return 1

        except Exception as e:
            print(f"❌ Batch execution error: {e}")
            if 'executor' in locals():
                executor.shutdown()
            if 'dashboard_server' in locals():
                dashboard_server.stop()
            return 1

    try:
        # Run batch processing asynchronously
        return asyncio.run(batch_main())
    except Exception as e:
        print(f"❌ Failed to start batch execution: {e}")
        return 1


def _handle_auto_workflow(args):
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
        success = run_all_tickets(str(tickets_path), max_parallel=args.parallel, skip_preflight=skip_preflight)

        os.chdir(original_dir)
        return 0 if success else 1

    except Exception as e:
        print(f"Error in auto workflow: {e}")
        return 1


def handle_ticket_command(args):
    """Handle ticket workflow subcommands."""
    if args.ticket_action == "create":
        return _handle_create_tickets(args)
    elif args.ticket_action == "execute":
        return _handle_execute_ticket(args)
    elif args.ticket_action == "run-all":
        return _handle_run_all_tickets(args)
    elif args.ticket_action == "verify":
        return _handle_verify_ticket(args)
    elif args.ticket_action == "quality":
        return _handle_quality_gates(args)
    elif args.ticket_action == "parallel":
        return _handle_parallel_execution(args)
    elif args.ticket_action == "batch":
        return _handle_batch_execution(args)
    elif args.ticket_action == "auto":
        return _handle_auto_workflow(args)
    elif args.ticket_action == "verify-parallel":
        return _handle_ticket_verification(args)
    else:
        print("Unknown ticket action")
        return 1


def _handle_ticket_verification(args):
    """Handle parallel ticket verification and fixing."""
    import json
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path

    from hydra.monitoring import monitoring
    from hydra.ticket_workflow import parse_all_tickets, parse_ticket

    print("🔍 Parallel Ticket Verification & Fixing")
    print("=" * 50)
    print("📝 Verifying and fixing unmet acceptance criteria")
    print("🤖 Each ticket will use its specified model (opus/sonnet)")
    print("🔧 Will implement missing features to meet criteria")

    # Set up monitoring
    correlation_id = monitoring.set_correlation_id("verify_fix_tickets")
    print(f"🔗 Session: {correlation_id}")

    # Get tickets file path (same pattern as parallel command)
    tickets_path = Path(args.tickets).resolve()
    if not tickets_path.exists():
        print(f"❌ Tickets file not found: {tickets_path}")
        return 1

    print(f"🎯 Loading tickets from: {tickets_path}")

    # Parse all tickets
    all_tickets = parse_all_tickets(str(tickets_path))
    if not all_tickets:
        print("❌ No tickets found")
        return 1

    # Get all tickets (including completed ones for verification)
    print(f"📋 Found {len(all_tickets)} total tickets to verify")
    print(f"👷 Using {args.workers} parallel workers")

    # Results tracking
    results = {}
    successful_tickets = []
    failed_tickets = []
    fixed_tickets = []

    def verify_and_fix_ticket(ticket_id, ticket_data):
        """Verify ticket criteria and fix any unmet ones using the ticket's specified model."""
        try:
            # Handle case where ticket_data might be None or not a dict
            if not ticket_data or not isinstance(ticket_data, dict):
                print(f"   ❌ Invalid ticket data for {ticket_id}")
                failed_tickets.append(ticket_id)
                return (ticket_id, False)

            title = ticket_data.get('title', 'Unknown')
            # For verify-parallel with Claude Code, default to balanced (sonnet 4)
            model = ticket_data.get('model', 'balanced')  # Default to balanced (sonnet 4 for Claude)
            # Map model emoji based on category
            model_emojis = {
                'smart': '🧠',
                'balanced': '⚡',
                'fast': '💨',
                'coder': '💻'
            }
            model_emoji = model_emojis.get(model, '⚡')

            print(f"\n🔍 Verifying Ticket {ticket_id}: {title}")
            print(f"   {model_emoji} Using {model.upper()} model")

            # Build the verification and fixing prompt (similar to execute_single_ticket)
            criteria_list = '\n'.join([f"- {c}" for c in ticket_data.get('acceptance_criteria', [])])

            prompt = f"""IMPORTANT: You MUST verify and fix ONLY Ticket {ticket_id} from tickets.md - NOT any other ticket!

Find "## Ticket {ticket_id}:" in tickets.md and check its acceptance criteria.

Your job is to:
1. First CHECK if all acceptance criteria are already met
2. If ANY criteria are NOT met, IMPLEMENT them immediately
3. After implementing, VERIFY again that criteria are now met
4. Update tickets.md to mark completed criteria with [x]

Ticket {ticket_id}: {title}
Acceptance Criteria to verify/fix:
{criteria_list}

Requirements:
1. Be minimalistic, surgical and future proof
2. Avoid using any code or comments that may be construed as AI generated
3. Make sure you do a good job because other LLMs said your code sucked
4. When finished, ensure acceptance criteria is met then update tickets.md
5. Run lint, build, test etc before marking complete
6. DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS
7. This has to be production quality, take your time

DO NOT work on any other ticket even if it appears easier. You are assigned ONLY to ticket {ticket_id}.

Once ALL acceptance criteria are met:
- Update tickets.md to mark the criteria as completed with [x]
- Update status to DONE if all criteria are met
- Run any necessary tests/lints/builds
- Report success

REMINDER: Focus ONLY on Ticket {ticket_id}. Verify first, fix if needed, then verify again."""

            # Use provider abstraction for execution
            import os  # Import os here for access to environ

            from hydra.providers.model_mapper import get_model_mapper
            from hydra.providers.provider_factory import (
                create_provider_from_environment,
            )

            # Get provider and map the model
            provider = create_provider_from_environment()
            mapper = get_model_mapper()

            # Map the ticket's model category to provider-specific model
            if hasattr(provider, 'config') and hasattr(provider.config, 'provider_type'):
                provider_type = provider.config.provider_type
            else:
                provider_type = os.environ.get('LLM_PROVIDER', 'claude_tmux')
            ticket_model = mapper.map_model(model, provider_type)

            # Execute verification and fixing
            project_dir = str(tickets_path.parent)
            print("   🚀 Verifying and fixing acceptance criteria...")

            # Execute via provider abstraction
            provider.generate(
                prompt,  # Pass as positional argument
                model=ticket_model,
                mode="ticket_verification",
                cwd=project_dir,
                ticket_id=ticket_id
            )

            # Check if ticket was updated/fixed
            updated_ticket = parse_ticket(str(tickets_path), ticket_id)
            if updated_ticket:
                completed_criteria = len([c for c in updated_ticket.get('acceptance_criteria', [])
                                        if c.startswith('✅')])
                total_criteria = len(updated_ticket.get('acceptance_criteria', []))

                if completed_criteria == total_criteria and total_criteria > 0:
                    print(f"   ✅ All {total_criteria} criteria verified and met!")
                    successful_tickets.append(ticket_id)
                    if ticket_id not in [t.get('number') for t in all_tickets.values() if t.get('completed')]:
                        fixed_tickets.append(ticket_id)
                else:
                    print(f"   ⚠️ {completed_criteria}/{total_criteria} criteria met")
                    if completed_criteria > 0:
                        fixed_tickets.append(ticket_id)
                    else:
                        failed_tickets.append(ticket_id)

            return (ticket_id, True)

        except Exception as e:
            print(f"   ❌ Error verifying/fixing {ticket_id}: {e}")
            failed_tickets.append(ticket_id)
            return (ticket_id, False)

    # Execute verification and fixing in parallel
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(verify_and_fix_ticket, tid, tdata): tid
            for tid, tdata in all_tickets.items()
        }

        for future in as_completed(futures):
            ticket_id = futures[future]
            try:
                tid, report = future.result()
                if report:
                    results[tid] = report
            except Exception as e:
                print(f"❌ Failed to verify {ticket_id}: {e}")

    elapsed = time.time() - start_time

    # Generate summary report
    print("\n" + "=" * 50)
    print("📊 Verification & Fixing Summary")
    print("=" * 50)
    print(f"⏱️  Total time: {elapsed:.2f}s")
    print(f"📋 Tickets processed: {len(results)}/{len(all_tickets)}")
    print(f"✅ Successfully verified/fixed: {len(successful_tickets)}")
    print(f"🔧 Fixed during verification: {len(fixed_tickets)}")
    print(f"❌ Failed to fix: {len(failed_tickets)}")

    if successful_tickets:
        print("\n✅ Successfully Verified/Fixed:")
        for tid in successful_tickets:
            print(f"   - {tid}: {all_tickets[tid].get('title', 'Unknown')}")

    if fixed_tickets:
        print("\n🔧 Fixed During Verification:")
        for tid in fixed_tickets:
            print(f"   - {tid}: {all_tickets[tid].get('title', 'Unknown')}")

    if failed_tickets:
        print("\n❌ Failed to Fix:")
        for tid in failed_tickets:
            print(f"   - {tid}: {all_tickets[tid].get('title', 'Unknown')}")

    # Save detailed report if requested
    if args.save_report:
        report_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total_tickets": len(all_tickets),
                "processed": len(results),
                "successful": len(successful_tickets),
                "fixed": len(fixed_tickets),
                "failed": len(failed_tickets),
                "elapsed_seconds": elapsed
            },
            "tickets": {}
        }

        for tid, success in results.items():
            status = "fixed" if tid in fixed_tickets else "successful" if tid in successful_tickets else "failed"
            report_data["tickets"][tid] = {
                "title": all_tickets[tid].get('title', 'Unknown'),
                "model": all_tickets[tid].get('model', 'sonnet'),
                "status": status,
                "success": success
            }

        with open(args.save_report, 'w') as f:
            json.dump(report_data, f, indent=2)
        print(f"\n📄 Detailed report saved to: {args.save_report}")

    # Show which tickets might need manual intervention
    if failed_tickets and len(failed_tickets) <= 3:
        print("\n💡 Failed tickets may need manual intervention:")
        for tid in failed_tickets:
            print(f"   • Ticket {tid}: Check acceptance criteria manually")

    # Return exit code based on results
    if len(failed_tickets) == 0:
        print("\n✅ All tickets successfully verified/fixed!")
        if len(fixed_tickets) > 0:
            print(f"   🔧 {len(fixed_tickets)} tickets were fixed during verification")
        return 0
    else:
        print(f"\n⚠️  {len(failed_tickets)} tickets could not be fixed")
        return 1


def _handle_claude_execute(orchestrator, args):
    """Handle claude execute command."""
    task = orchestrator.create_task(
        description=args.task[:50],
        prompt=args.task,
        working_directory=args.cwd,
        timeout=args.timeout
    )

    print("🚀 Executing task with Claude Code CLI...")
    result = orchestrator.execute_task(task)

    if result.status.value == "completed":
        print("✅ Task completed successfully")
        if result.files_changed:
            changed_files = ', '.join(result.files_changed)
            print(f"📝 Files changed: {changed_files}")
        return 0
    else:
        print(f"❌ Task failed: {result.error}")
        return 1


def _handle_claude_session_management(orchestrator, args):
    """Handle session-related commands."""
    if args.claude_action == "session":
        orchestrator.create_development_session(args.project_path, args.name)
        return 0
    elif args.claude_action == "list":
        sessions = orchestrator.list_sessions()
        if not sessions:
            print("No active Claude Code sessions")
        else:
            print("Active Claude Code sessions:")
            for session in sessions:
                session_info = f"  - {session['name']}: {session['project_path']}"
                print(session_info)
        return 0
    elif args.claude_action == "attach":
        orchestrator.attach_to_session(args.session_name)
        return 0
    elif args.claude_action == "kill":
        orchestrator.kill_session(args.session_name)
        return 0
    return None


def _handle_claude_persistence(orchestrator, args):
    """Handle save/restore commands."""
    from hydra.persistence.session_manager import SessionManager
    manager = SessionManager()

    if args.claude_action == "save":
        tasks = orchestrator.task_history
        project_path = os.getcwd()
        save_path = manager.save_session(args.session_name, project_path, tasks)
        print(f"✅ Session saved to: {save_path}")
        return 0
    elif args.claude_action == "restore":
        state = manager.restore_session(args.session_name)
        if state:
            print(f"✅ Session restored: {args.session_name}")
            print(f"📁 Project: {state.project_path}")
            print(f"📋 Tasks: {len(state.tasks)}")
            orchestrator.task_history = state.tasks
            return 0
        else:
            print(f"❌ Session not found: {args.session_name}")
            return 1
    return None


def handle_claude_command(args):
    """Handle Claude Code orchestration commands."""
    from hydra.orchestrator.claude_code_orchestrator import ClaudeCodeOrchestrator

    try:
        orchestrator = ClaudeCodeOrchestrator()
    except ValueError as e:
        print(f"Error initializing Claude Code orchestrator: {e}")
        return 1

    if args.claude_action == "execute":
        return _handle_claude_execute(orchestrator, args)

    session_result = _handle_claude_session_management(orchestrator, args)
    if session_result is not None:
        return session_result

    persistence_result = _handle_claude_persistence(orchestrator, args)
    if persistence_result is not None:
        return persistence_result

    print("Unknown Claude action")
    return 1


def handle_context_command(args):
    """Handle context management commands."""
    from hydra.context import ArtifactTracker

    # Default to current directory for project path
    project_dir = getattr(args, 'dir', '.')
    tracker = ArtifactTracker(project_dir)

    if args.context_action == "show":
        return _handle_context_show(tracker)
    elif args.context_action == "inspect":
        return _handle_context_inspect(tracker, args.ticket_id)
    elif args.context_action == "clear":
        ticket_id = getattr(args, 'ticket_id', None)
        clear_all = getattr(args, 'all', False)
        return _handle_context_clear(tracker, ticket_id, clear_all)
    elif args.context_action == "deps":
        return _handle_context_deps(tracker, args.ticket_id, project_dir)
    elif args.context_action == "export":
        format_type = getattr(args, 'format', 'text')
        return _handle_context_export(tracker, format_type)
    elif args.context_action == "preview-updates":
        return _handle_context_preview_updates(tracker, args.ticket_id, project_dir)
    else:
        print("Unknown context action")
        return 1


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
                op_symbol = {
                    'created': '➕',
                    'modified': '✏️',
                    'deleted': '➖'
                }.get(artifact.operation, '📄')
                desc = artifact.description or 'File'
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
            op_symbol = {
                'created': '➕',
                'modified': '✏️',
                'deleted': '➖'
            }.get(artifact.operation, '📄')
            desc = artifact.description or 'File'
            print(f"  {op_symbol} {artifact.file_path}")
            print(f"     {desc}")

            if artifact.content_preview:
                print("     Preview:")
                for line in artifact.content_preview.split('\n')[:5]:
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
        if response.lower() == 'y':
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

    dependencies = ticket_data.get('dependencies', [])
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

    if format_type == 'json':
        data = {
            tid: ctx.to_dict()
            for tid, ctx in tracker.ticket_contexts.items()
        }
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
            if update['ticket'] != current_ticket:
                current_ticket = update['ticket']
                print(f"\n   Ticket {current_ticket}:")
            print(f"      Before: {update['before']}")
            print("      After:  [would update with specific filename]")
    else:
        print("No future tickets reference this ticket's outputs")

    return 0


def main():
    """Execute the main CLI entry point."""
    # Install uvloop for better async performance if available
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass

    parser = create_parser()
    args = parser.parse_args()

    # Handle global provider/model overrides
    if hasattr(args, 'provider') and args.provider:
        # Map claude_code to claude_tmux for consistency
        provider = 'claude_tmux' if args.provider == 'claude_code' else args.provider
        os.environ['LLM_PROVIDER'] = provider
        print(f"🔧 Using provider: {args.provider}")

    if hasattr(args, 'model') and args.model:
        os.environ['LLM_MODEL'] = args.model
        print(f"🔧 Using model: {args.model}")

    if hasattr(args, 'no_cache') and args.no_cache:
        os.environ['NO_CACHE'] = '1'
        print("🚫 Cache disabled")

    # Handle template commands
    if args.command == "template":
        return handle_template_command(args)

    # Handle ticket commands
    if args.command == "ticket":
        return handle_ticket_command(args)

    # Handle Claude Code orchestration commands
    if args.command == "claude":
        return handle_claude_command(args)

    # Handle context commands
    if args.command == "context":
        return handle_context_command(args)

    # Handle task execution (run command only)
    if args.command == "run":
        task = args.task
    else:
        # No command specified
        parser.print_help()
        return 1

    # Validate task is not empty
    if not task or not task.strip():
        print("Error: No task provided", file=sys.stderr)
        return 1

    print(f"Executing task: {task}")
    print(f"Agent: {args.agent_name}, Starting depth: {args.depth}")
    print("-" * 60)

    try:
        from hydra.workflows.engine import execute_workflow
        results = execute_workflow(task, args.agent_name, args.depth)

        if "error" in results:
            print(f"\nExecution failed: {results['error']}", file=sys.stderr)
            return 1

        print_results(results, args.json)
        return 0

    except KeyboardInterrupt:
        print("\nExecution interrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
