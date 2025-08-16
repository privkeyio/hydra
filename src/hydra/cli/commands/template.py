"""Template management commands for Hydra CLI."""

import json
from pathlib import Path

from hydra.templates import TemplateEngine, TemplateValidator


def add_template_parser(subparsers):
    """Add template subcommands to the parser."""
    template_parser = subparsers.add_parser(
        "template",
        help="Project template operations - list, create, and validate templates"
    )
    template_subparsers = template_parser.add_subparsers(
        dest="template_action",
        help="Template operations"
    )

    # List templates
    template_subparsers.add_parser(
        "list",
        help="List all available project templates"
    )

    # Create project from template
    create_parser = template_subparsers.add_parser(
        "create",
        help="Create a new project from a template"
    )
    create_parser.add_argument(
        "template_name",
        help="Name of the template to use"
    )
    create_parser.add_argument(
        "output_dir",
        help="Directory where the project will be created"
    )
    create_parser.add_argument(
        "--param",
        action="append",
        help="Template parameter in key=value format (can be used multiple times)"
    )

    # Validate templates
    validate_parser = template_subparsers.add_parser(
        "validate",
        help="Validate template structure and configuration"
    )
    validate_parser.add_argument(
        "--template",
        help="Specific template to validate (validates all if not specified)"
    )


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
            Path(__file__).parent.parent.parent / 'templates' / 'templates' / args.template
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
        templates_dir = Path(__file__).parent.parent.parent / 'templates' / 'templates'
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

