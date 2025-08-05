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
            output.append(f"{prefix}  Max depth: {value.get('depth_reached', 0)}")
        elif isinstance(value, dict):
            output.append(f"{prefix}{key}:")
            if "error" in value:
                output.append(f"{prefix}  ERROR: {value['error']}")
            else:
                if "plan" in value:
                    output.append(f"{prefix}  Plan: {value['plan']}")
                if "task" in value:
                    output.append(f"{prefix}  Task: {value['task']}")
                if "subtasks" in value and value["subtasks"]:
                    output.append(f"{prefix}  Subtasks: {len(value['subtasks'])}")
        elif isinstance(value, str):
            output.append(f"{prefix}{key}: {value}")

    return "\n".join(output)


def main():
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

    args = parser.parse_args()

    if args.task is None:
        if sys.stdin.isatty():
            parser.print_help()
            return 1
        else:
            task = sys.stdin.read().strip()
    else:
        task = args.task

    if not task:
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

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print("\nPlan:", results.get("plan", "No plan generated"))

            if results.get("subtasks"):
                print(f"\nSubtasks ({len(results['subtasks'])}):")
                for i, subtask in enumerate(results["subtasks"], 1):
                    print(f"  {i}. {subtask}")

            if results.get("results"):
                print("\nExecution Results:")
                print(format_results(results["results"]))

            agents = results.get("agents", [])
            if agents:
                print(f"\nAgents created: {', '.join(agents)}")

        return 0

    except KeyboardInterrupt:
        print("\nExecution interrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
