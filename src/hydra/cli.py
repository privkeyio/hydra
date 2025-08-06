#!/usr/bin/env python3
import argparse
import json
import sys
from typing import Any, Dict

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
            output.append(f"{prefix}  Code generated: {value.get('code_generated', False)}")
        elif isinstance(value, dict):
            if "error" in value:
                output.append(f"{prefix}{key}: ❌ {value['error']}")
            elif value.get("success", True):
                output.append(f"{prefix}{key}: ✅ Completed")
                if "task" in value:
                    task_preview = value['task'][:50] + "..." if len(value['task']) > 50 else value['task']
                    output.append(f"{prefix}  Task: {task_preview}")
                if value.get("generated_code") and len(value['generated_code']) < 200:
                    output.append(f"{prefix}  Generated: {len(value['generated_code'])} chars of code")
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
        description="Hydra: Multi-agent code generation system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python main.py \"Calculate fibonacci numbers\""
    )

    parser.add_argument(
        "task",
        help="Task description for the agent system",
        nargs="?",
        default=None
    )

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


def main():
    """Execute the main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    task, exit_code = get_task_input(args, parser)
    if task is None:
        return exit_code

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
