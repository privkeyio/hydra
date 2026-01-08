#!/usr/bin/env python3
"""Example: Using Hydra with Venice AI for Code Generation

This example demonstrates how to use Hydra with Venice AI provider
for various code generation tasks.
"""

import os

from hydra.agents.base import CodeAgent
from hydra.monitoring import monitoring
from hydra.providers.venice import VeniceProvider
from hydra.safety.guardrails import ProductionGuardrails


def basic_code_generation():
    """Simple code generation using Venice AI."""
    # Initialize Venice provider
    provider = VeniceProvider(
        api_key=os.getenv("VENICE_API_KEY"), model="qwen-2.5-coder-32b"
    )

    # Create a code agent
    agent = CodeAgent("venice_developer", provider=provider)

    # Generate code
    task = "Create a Python function that validates email addresses using regex"
    result = agent.generate_code(task)

    print("Generated Code:")
    print(result["code"])
    print("\nExplanation:")
    print(result["description"])

    return result


def parallel_task_execution():
    """Execute multiple tasks in parallel using Venice."""
    from hydra.workflows.parallel_engine import ParallelExecutionEngine

    # Initialize parallel engine
    engine = ParallelExecutionEngine(max_workers=3)

    # Define multiple tasks
    tasks = [
        {
            "id": "task1",
            "description": "Create a function to parse JSON",
            "model": "venice",
        },
        {
            "id": "task2",
            "description": "Create a function to validate URLs",
            "model": "venice",
        },
        {
            "id": "task3",
            "description": "Create a function to hash passwords",
            "model": "venice",
        },
    ]

    # Execute tasks in parallel
    results = engine.execute_tasks(tasks)

    # Display results
    for task_id, result in results.items():
        print(f"\n{'='*50}")
        print(f"Task: {task_id}")
        print(f"Status: {'Success' if result['success'] else 'Failed'}")
        if result["success"]:
            print(f"Code:\n{result['code']}")

    return results


def monitored_execution():
    """Execute code generation with monitoring and safety guardrails."""
    # Initialize guardrails
    guardrails = ProductionGuardrails()
    guardrails.register_tenant(
        "venice_example",
        rate_limit={"requests_per_minute": 30},
        budget={"daily_limit_usd": 10.0},
    )

    # Set up monitoring
    monitoring.set_correlation_id("venice_example_001")

    try:
        # Protected execution with guardrails
        with guardrails.protected_execution(
            tenant_id="venice_example",
            operation_name="generate_api",
            estimated_tokens=2000,
            model="venice",
        ) as exec_id:
            print(f"Execution ID: {exec_id}")

            # Create agent and generate code
            agent = CodeAgent("monitored_agent")

            # Track operation
            monitoring.track_agent_lifecycle(agent.name, "start")

            result = agent.generate_code(
                "Create a complete REST API endpoint for user management with CRUD operations"
            )

            # Record metrics
            monitoring.record_agent_operation(
                agent.name,
                "code_generation",
                duration=2.5,
                success=True,
                metadata={"lines": len(result["code"].split("\n"))},
            )

            monitoring.track_agent_lifecycle(agent.name, "stop")

            print("Code generated successfully with monitoring!")
            lines_count = len(result["code"].split("\n"))
            print(f"Lines of code: {lines_count}")

            # Get status report
            status = guardrails.get_tenant_status("venice_example")
            print("\nResource Usage:")
            print(f"- Requests: {status['rate_limit_usage']}")
            print(f"- Cost: ${status['cost_usage']['daily_spent']:.2f}")

            return result

    except Exception as e:
        print(f"Error during execution: {e}")
        return None


async def async_venice_workflow():
    """Asynchronous workflow using Venice for complex project generation."""
    from hydra.orchestrator.project_orchestrator import ProjectOrchestrator
    from hydra.specifications.task_spec import TaskSpec

    # Define project specification
    project_spec = {
        "name": "microservice_api",
        "description": "Build a microservice with Venice AI",
        "tasks": [
            {
                "id": "design",
                "type": "analysis",
                "description": "Design the API structure",
                "model": "venice",
            },
            {
                "id": "implement",
                "type": "code_generation",
                "description": "Implement the API endpoints",
                "dependencies": ["design"],
                "model": "venice",
            },
            {
                "id": "test",
                "type": "code_generation",
                "description": "Create unit tests",
                "dependencies": ["implement"],
                "model": "venice",
            },
        ],
    }

    # Create orchestrator
    orchestrator = ProjectOrchestrator()

    # Parse specification
    spec = TaskSpec.from_dict(project_spec)

    # Execute project
    print("Starting async project execution with Venice...")
    results = await orchestrator.execute_project_async(spec)

    print("\nProject completed!")
    print(f"Total tasks: {len(results)}")
    print(f"Successful: {sum(1 for r in results.values() if r.get('success'))}")

    return results


def template_based_generation():
    """Use templates with Venice for rapid project scaffolding."""
    from hydra.templates.template_engine import TemplateEngine

    # Initialize template engine
    engine = TemplateEngine()

    # List available templates
    templates = engine.list_templates()
    print("Available templates:")
    for tmpl in templates:
        print(f"  - {tmpl['name']}: {tmpl['description']}")

    # Generate project from template
    params = {
        "project_name": "venice_api",
        "description": "API generated with Venice AI",
        "author": "Venice Developer",
        "port": 8080,
    }

    # Create project
    output_path = engine.create_project(
        template_name="fastapi_rest_api",
        output_path="./generated/venice_api",
        parameters=params,
    )

    print(f"\nProject generated at: {output_path}")

    # Now enhance with Venice AI
    agent = CodeAgent("venice_enhancer")

    enhancement = agent.generate_code(
        f"Add authentication middleware to the FastAPI app at {output_path}"
    )

    print("\nEnhancement code generated:")
    print(enhancement["code"][:500] + "...")

    return output_path


if __name__ == "__main__":
    print("Venice AI Integration Examples")
    print("=" * 50)

    # Check for API key
    if not os.getenv("VENICE_API_KEY"):
        print("ERROR: Please set VENICE_API_KEY environment variable")
        exit(1)

    # Run examples
    print("\n1. Basic Code Generation")
    print("-" * 30)
    basic_code_generation()

    print("\n2. Parallel Task Execution")
    print("-" * 30)
    parallel_task_execution()

    print("\n3. Monitored Execution with Guardrails")
    print("-" * 30)
    monitored_execution()

    print("\n4. Template-based Generation")
    print("-" * 30)
    template_based_generation()

    print("\n5. Async Workflow (requires event loop)")
    print("-" * 30)
    # asyncio.run(async_venice_workflow())
    print("Uncomment the line above to run async workflow")

    print("\n" + "=" * 50)
    print("Examples completed successfully!")
