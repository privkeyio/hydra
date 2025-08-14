"""Main entry point for Hydra CLI."""

import argparse
import json
import os
import sys

# Import command handlers
from hydra.cli.commands.claude import add_claude_parser, handle_claude_command
from hydra.cli.commands.context import add_context_parser, handle_context_command
from hydra.cli.commands.dashboard import add_dashboard_parser, handle_dashboard_command
from hydra.cli.commands.parallel import add_parallel_parser, handle_parallel_commands
from hydra.cli.commands.template import add_template_parser, handle_template_command
from hydra.cli.commands.ticket import add_ticket_parser, handle_ticket_command
from hydra.cli.commands.verify import add_verify_parser, handle_verify_command

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, skip loading
    pass


def format_code_block(code: str) -> str:
    """Format code with a box border."""
    lines = code.strip().split('\n')
    max_width = max(len(line) for line in lines) if lines else 0
    border = '─' * (max_width + 4)

    result = f"┌{border}┐\n"
    for line in lines:
        result += f"│ {line:<{max_width + 2}} │\n"
    result += f"└{border}┘"

    return result


def format_results(results: dict, indent: int = 0) -> str:
    """Format execution results for display."""
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


def print_results(results: dict, json_output: bool) -> None:
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
            print(f"\nSubtasks ({len(results['subtasks'])})")
            for i, subtask in enumerate(results["subtasks"], 1):
                print(f"  {i}. {subtask}")

        if results.get("results"):
            print("\nDetailed Results:")
            print(format_results(results["results"]))

        agents = results.get("agents", [])
        if agents:
            print(f"\nAgents created: {', '.join(agents)}")


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Hydra: Multi-agent code generation system with project templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  hydra ticket create 'Build a web scraper'\n"
               "  hydra template create flask_web_app ./my-app\n"
               "  hydra ticket execute 001\n"
               "  hydra ticket parallel --workers 4"
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

    # Add version argument
    parser.add_argument(
        "--version",
        action="version",
        version="Hydra CLI v1.0.0"
    )

    # Create subparsers for different command groups
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands"
    )

    # Add command parsers
    add_template_parser(subparsers)
    add_ticket_parser(subparsers)
    add_parallel_parser(subparsers)
    add_verify_parser(subparsers)
    add_claude_parser(subparsers)
    add_context_parser(subparsers)
    add_dashboard_parser(subparsers)

    # Task execution subcommand (legacy support)
    task_parser = subparsers.add_parser(
        "run",
        help="Execute a task (legacy command)"
    )
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

    return parser


def handle_run_command(args) -> int:
    """Handle the legacy run command."""
    task = args.task

    # Validate task is not empty
    if not task or not task.strip():
        print("Error: No task provided", file=sys.stderr)
        return 1

    # Print header (even in JSON mode for backwards compatibility)
    print(f"Executing task: {task}")
    print(f"Agent: {args.agent_name}, Starting depth: {args.depth}")
    print("-" * 60)

    try:
        from hydra.workflows.engine import execute_workflow
        results = execute_workflow(task, args.agent_name, args.depth)

        if "error" in results:
            print(f"\nExecution failed: {results['error']}", file=sys.stderr)
            return 1

        # Ensure the results are printed cleanly after the dashes
        if args.json:
            # Add task to results if not present (for backwards compatibility)
            if "task" not in results:
                results["task"] = task
            if "agents" not in results and "agent" in results:
                results["agents"] = [results["agent"]]
        
        print_results(results, args.json)
        return 0

    except KeyboardInterrupt:
        print("\nExecution interrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Execute the main CLI entry point."""
    # Install uvloop for better async performance if available
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass

    parser = create_parser()
    args = parser.parse_args()

    # Run startup checks
    from hydra.startup_checks import StartupChecker
    checker = StartupChecker()
    startup_results = checker.run_startup_checks()

    # Show startup warnings/issues unless running help or version commands
    show_startup = args.command not in [None] and getattr(args, 'command', '') != 'help'
    if show_startup:
        checker.print_startup_report(startup_results, verbose=False)

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

    # Handle different commands
    if not args.command:
        # No command specified
        parser.print_help()
        return 1
    elif args.command == "template":
        return handle_template_command(args)
    elif args.command == "ticket":
        return handle_ticket_command(args)
    elif args.command == "parallel":
        return handle_parallel_commands(args)
    elif args.command == "verify":
        return handle_verify_command(args)
    elif args.command == "claude":
        return handle_claude_command(args)
    elif args.command == "context":
        return handle_context_command(args)
    elif args.command == "dashboard":
        return handle_dashboard_command(args)
    elif args.command == "run":
        return handle_run_command(args)
    else:
        # Unknown command
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

