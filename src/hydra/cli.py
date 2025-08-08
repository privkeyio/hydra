#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from hydra.templates import TemplateEngine, TemplateValidator
from hydra.ticket_workflow import (
    execute_single_ticket,
    generate_tickets_md,
    run_all_tickets,
)
from hydra.workflows.engine import execute_workflow


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
    ticket_subparsers = ticket_parser.add_subparsers(dest="ticket_action", help="Ticket actions")

    # Create tickets
    create_tickets_parser = ticket_subparsers.add_parser("create", help="Create tickets.md from project description")
    create_tickets_parser.add_argument("description", help="Project description")
    create_tickets_parser.add_argument("--output", default="tickets.md", help="Output file (default: tickets.md)")

    # Execute ticket
    execute_ticket_parser = ticket_subparsers.add_parser("execute", help="Execute specific ticket")
    execute_ticket_parser.add_argument("identifier", help="Ticket identifier to execute (e.g., 1, 007, TICKET-001)")
    execute_ticket_parser.add_argument("--tickets", default="tickets.md", help="Tickets file (default: tickets.md)")

    # Run all tickets
    run_tickets_parser = ticket_subparsers.add_parser("run-all", help="Execute all tickets in sequence")
    run_tickets_parser.add_argument("--tickets", default="tickets.md", help="Tickets file (default: tickets.md)")
    
    # Verify ticket completion
    verify_parser = ticket_subparsers.add_parser("verify", help="Verify ticket acceptance criteria")
    verify_parser.add_argument("identifier", help="Ticket identifier to verify")
    verify_parser.add_argument("--tickets", default="tickets.md", help="Tickets file (default: tickets.md)")

    # Auto workflow - dependency-aware parallel execution
    auto_parser = ticket_subparsers.add_parser("auto", help="Automatically execute tickets with dependency-aware parallelism")
    auto_parser.add_argument("--tickets", default="tickets.md", help="Tickets file (default: tickets.md)")
    auto_parser.add_argument("--parallel", type=int, default=3, help="Max parallel agents (default: 3)")
    auto_parser.add_argument("--dir", help="Project directory (default: current dir)")

    # Claude Code orchestration subcommand
    claude_parser = subparsers.add_parser("claude", help="Claude Code CLI orchestration")
    claude_subparsers = claude_parser.add_subparsers(dest="claude_action", help="Claude Code actions")
    
    # Execute task with Claude Code
    execute_parser = claude_subparsers.add_parser("execute", help="Execute a task with Claude Code")
    execute_parser.add_argument("task", help="Task description for Claude Code")
    execute_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default: 300)")
    execute_parser.add_argument("--cwd", help="Working directory (default: current dir)")
    
    # Create development session
    session_parser = claude_subparsers.add_parser("session", help="Create a Claude Code development session")
    session_parser.add_argument("project_path", help="Path to project directory")
    session_parser.add_argument("--name", help="Session name (auto-generated if not provided)")
    
    # List sessions
    list_parser = claude_subparsers.add_parser("list", help="List active Claude Code sessions")
    
    # Attach to session
    attach_parser = claude_subparsers.add_parser("attach", help="Attach to a Claude Code session")
    attach_parser.add_argument("session_name", help="Name of session to attach to")
    
    # Kill session
    kill_parser = claude_subparsers.add_parser("kill", help="Kill a Claude Code session")
    kill_parser.add_argument("session_name", help="Name of session to kill")
    
    # Save session
    save_parser = claude_subparsers.add_parser("save", help="Save Claude Code session state")
    save_parser.add_argument("session_name", help="Name of session to save")
    
    # Restore session
    restore_parser = claude_subparsers.add_parser("restore", help="Restore Claude Code session")
    restore_parser.add_argument("session_name", help="Name of session to restore")

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
        success = generate_tickets_md(args.description, args.output)
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

        success = execute_single_ticket(args.tickets, args.identifier)
        return 0 if success else 1
    except Exception as e:
        print(f"Error executing ticket: {e}")
        return 1


def _handle_run_all_tickets(args):
    """Handle run all tickets command."""
    try:
        success = run_all_tickets(args.tickets)
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

        success = run_all_tickets(str(tickets_path), max_parallel=args.parallel)

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
    elif args.ticket_action == "auto":
        return _handle_auto_workflow(args)
    else:
        print("Unknown ticket action")
        return 1


def handle_claude_command(args):
    """Handle Claude Code orchestration commands."""
    from hydra.orchestrator.claude_code_orchestrator import ClaudeCodeOrchestrator
    
    try:
        orchestrator = ClaudeCodeOrchestrator()
    except ValueError as e:
        print(f"Error initializing Claude Code orchestrator: {e}")
        return 1
    
    if args.claude_action == "execute":
        # Execute a task with Claude Code
        task = orchestrator.create_task(
            description=args.task[:50],
            prompt=args.task,
            working_directory=args.cwd,
            timeout=args.timeout
        )
        
        print(f"🚀 Executing task with Claude Code CLI...")
        result = orchestrator.execute_task(task)
        
        if result.status.value == "completed":
            print(f"✅ Task completed successfully")
            if result.files_changed:
                print(f"📝 Files changed: {', '.join(result.files_changed)}")
            return 0
        else:
            print(f"❌ Task failed: {result.error}")
            return 1
            
    elif args.claude_action == "session":
        # Create development session
        session_name = orchestrator.create_development_session(
            args.project_path,
            args.name
        )
        return 0
        
    elif args.claude_action == "list":
        # List sessions
        sessions = orchestrator.list_sessions()
        if not sessions:
            print("No active Claude Code sessions")
        else:
            print("Active Claude Code sessions:")
            for session in sessions:
                print(f"  - {session['name']}: {session['project_path']}")
        return 0
        
    elif args.claude_action == "attach":
        # Attach to session
        orchestrator.attach_to_session(args.session_name)
        return 0
        
    elif args.claude_action == "kill":
        # Kill session
        orchestrator.kill_session(args.session_name)
        return 0
    
    elif args.claude_action == "save":
        # Save session state
        from hydra.persistence.session_manager import SessionManager
        manager = SessionManager()
        
        # Get session tasks from orchestrator
        tasks = orchestrator.task_history
        project_path = os.getcwd()
        
        save_path = manager.save_session(args.session_name, project_path, tasks)
        print(f"✅ Session saved to: {save_path}")
        return 0
    
    elif args.claude_action == "restore":
        # Restore session state
        from hydra.persistence.session_manager import SessionManager
        manager = SessionManager()
        
        state = manager.restore_session(args.session_name)
        if state:
            print(f"✅ Session restored: {args.session_name}")
            print(f"📁 Project: {state.project_path}")
            print(f"📋 Tasks: {len(state.tasks)}")
            
            # Restore task history
            orchestrator.task_history = state.tasks
            return 0
        else:
            print(f"❌ Session not found: {args.session_name}")
            return 1
        
    else:
        print("Unknown Claude action")
        return 1


def main():
    """Execute the main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle template commands
    if args.command == "template":
        return handle_template_command(args)

    # Handle ticket commands
    if args.command == "ticket":
        return handle_ticket_command(args)
    
    # Handle Claude Code orchestration commands
    if args.command == "claude":
        return handle_claude_command(args)

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
