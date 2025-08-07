#!/usr/bin/env python3
import argparse
import json
import sys
from typing import Any, Dict
from pathlib import Path

from hydra.workflows.engine import execute_workflow
from hydra.templates import TemplateEngine, TemplateValidator


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
        description="Hydra: Multi-agent code generation system with project templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  hydra \"Calculate fibonacci numbers\"\n  hydra template create flask_web_app ./my-app --project_name=MyApp"
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
    template_parser = subparsers.add_parser("template", help="Project template operations")
    template_subparsers = template_parser.add_subparsers(dest="template_action", help="Template actions")
    
    # Template list
    template_subparsers.add_parser("list", help="List available templates")
    
    # Template create
    create_parser = template_subparsers.add_parser("create", help="Create project from template")
    create_parser.add_argument("template_name", help="Template to use")
    create_parser.add_argument("output_dir", help="Output directory")
    create_parser.add_argument("--param", action="append", help="Template parameter (format: key=value)")
    
    # Template validate
    validate_parser = template_subparsers.add_parser("validate", help="Validate templates")
    validate_parser.add_argument("--template", help="Specific template to validate")

    # Backward compatibility - direct task as positional argument
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


def handle_template_command(args):
    """Handle template subcommands."""
    engine = TemplateEngine()
    
    if args.template_action == "list":
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
    
    elif args.template_action == "create":
        try:
            template = engine.load_template(args.template_name)
            
            # Parse parameters
            params = {}
            if args.param:
                for param_str in args.param:
                    if '=' not in param_str:
                        print(f"Invalid parameter format: {param_str}. Use key=value")
                        return 1
                    key, value = param_str.split('=', 1)
                    # Try to parse as JSON for complex types
                    try:
                        params[key] = json.loads(value)
                    except:
                        params[key] = value
            
            # Generate project
            result = engine.generate_project(args.template_name, Path(args.output_dir), params)
            
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
    
    elif args.template_action == "validate":
        if args.template:
            # Validate specific template
            template_dir = Path(__file__).parent / 'templates' / 'templates' / args.template
            is_valid, errors = TemplateValidator.validate_template_structure(template_dir)
            
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
    
    else:
        print("Unknown template action")
        return 1


def main():
    """Execute the main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle template commands
    if args.command == "template":
        return handle_template_command(args)
    
    # Handle task execution (run command or direct task)
    if args.command == "run":
        task = args.task
    else:
        # Backward compatibility - direct task argument
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
