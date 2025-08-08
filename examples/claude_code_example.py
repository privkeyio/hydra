#!/usr/bin/env python3
"""Example: Using Hydra with Claude Code Agent

This example demonstrates how to use Hydra's Claude Code integration
for complex, multi-file project development with persistent context.
"""

import os

from hydra.agents.claude_code_agent import ClaudeCodeAgent
from hydra.monitoring import monitoring, profiler
from hydra.orchestrator.project_orchestrator import ProjectOrchestrator
from hydra.routing.model_router import ModelRouter
from hydra.safety.guardrails import ProductionGuardrails
from hydra.state.project_state import ProjectStateManager


def claude_code_session():
    """Create a Claude Code-like interactive session."""
    # Initialize Claude Code agent with persistent context
    agent = ClaudeCodeAgent(
        agent_id="claude_developer",
        working_directory="./workspace",
        persistent_session=True
    )

    # Initialize session
    agent.initialize_session()

    print("Claude Code Session Started")
    print("Working directory:", agent.working_directory)
    print("-" * 50)

    # Task 1: Analyze project structure
    print("\n1. Analyzing project structure...")
    analysis = agent.analyze_task(
        "Understand the codebase structure and identify main components"
    )
    print(f"Components found: {len(analysis.get('components', []))}")

    # Task 2: Create a new feature
    print("\n2. Creating new feature...")
    feature_code = agent.execute_task({
        'type': 'file_create',
        'path': 'features/data_processor.py',
        'description': 'Create a data processing module with pandas integration'
    })
    print(f"Created: {feature_code.get('file_path')}")

    # Task 3: Modify existing code
    print("\n3. Modifying existing code...")
    modification = agent.execute_task({
        'type': 'file_edit',
        'path': 'features/data_processor.py',
        'description': 'Add error handling and logging to the data processor'
    })
    print(f"Modified: {modification.get('files_changed', 0)} files")

    # Task 4: Run tests
    print("\n4. Running tests...")
    test_result = agent.execute_command(
        "python -m pytest tests/ -v"
    )
    print(f"Test status: {test_result.get('status')}")

    # Get session summary
    summary = agent.get_progress_summary()
    print("\nSession Summary:")
    print(f"- Files created: {summary.get('files_created', 0)}")
    print(f"- Files modified: {summary.get('files_modified', 0)}")
    print(f"- Commands executed: {summary.get('commands_executed', 0)}")

    # Save session for later resumption
    session_file = agent.save_session("claude_session.json")
    print(f"\nSession saved to: {session_file}")

    return agent


def intelligent_model_routing():
    """Demonstrate intelligent routing between Claude models."""
    # Initialize model router
    router = ModelRouter()
    router.load_config("config/routing_rules.json")

    # Initialize guardrails for cost tracking
    guardrails = ProductionGuardrails()
    guardrails.register_tenant("claude_example")

    # Define tasks with varying complexity
    tasks = [
        {
            'id': 'simple_1',
            'description': 'Format this JSON string',
            'complexity': 'simple'
        },
        {
            'id': 'moderate_1',
            'description': 'Refactor this function to improve performance',
            'complexity': 'moderate'
        },
        {
            'id': 'complex_1',
            'description': 'Design and implement a distributed cache system',
            'complexity': 'complex'
        },
        {
            'id': 'critical_1',
            'description': 'Architect a microservices migration strategy',
            'complexity': 'critical'
        }
    ]

    print("Model Routing Demonstration")
    print("-" * 50)

    total_cost = 0
    for task in tasks:
        # Route to appropriate model
        routing_decision = router.route_task(task)

        print(f"\nTask: {task['id']}")
        print(f"Complexity: {task['complexity']}")
        print(f"Routed to: {routing_decision['model']}")
        print(f"Confidence: {routing_decision['confidence']:.2f}")
        print(f"Estimated cost: ${routing_decision['estimated_cost']:.4f}")

        total_cost += routing_decision['estimated_cost']

        # Execute with appropriate model
        with guardrails.protected_execution(
            tenant_id="claude_example",
            operation_name=task['id'],
            model=routing_decision['model']
        ):
            # Simulate task execution
            if routing_decision['model'] == 'claude-3-sonnet':
                print("  → Executing with Sonnet (fast, cost-effective)")
            else:
                print("  → Executing with Opus (powerful, comprehensive)")

    # Report savings
    savings = router.get_cost_savings_report()
    print(f"\n{'='*50}")
    print(f"Total estimated cost: ${total_cost:.2f}")
    print(f"Savings from smart routing: ${savings['total_savings']:.2f}")
    print(f"Routing accuracy: {savings['routing_accuracy']:.1f}%")

    return savings


def parallel_claude_agents():
    """Run multiple Claude Code agents in parallel for large projects."""
    from hydra.workflows.parallel_engine import ParallelExecutionEngine

    print("Parallel Claude Agents Execution")
    print("-" * 50)

    # Initialize parallel engine
    engine = ParallelExecutionEngine(max_workers=5)

    # Create project orchestrator
    orchestrator = ProjectOrchestrator()

    # Define complex project with parallel tasks
    project = {
        'name': 'full_stack_app',
        'tasks': [
            {
                'id': 'backend',
                'agent': 'claude_backend',
                'description': 'Build FastAPI backend with PostgreSQL',
                'model': 'claude-3-opus'
            },
            {
                'id': 'frontend',
                'agent': 'claude_frontend',
                'description': 'Create React frontend with TypeScript',
                'model': 'claude-3-sonnet'
            },
            {
                'id': 'database',
                'agent': 'claude_database',
                'description': 'Design database schema and migrations',
                'model': 'claude-3-opus'
            },
            {
                'id': 'testing',
                'agent': 'claude_testing',
                'description': 'Write comprehensive test suites',
                'model': 'claude-3-sonnet',
                'dependencies': ['backend', 'frontend']
            },
            {
                'id': 'deployment',
                'agent': 'claude_devops',
                'description': 'Create Docker compose and CI/CD pipeline',
                'model': 'claude-3-sonnet',
                'dependencies': ['testing']
            }
        ]
    }

    # Start performance profiling
    profiler.start_profile("parallel_execution")

    # Execute project with parallel agents
    print("\nStarting parallel execution...")
    results = orchestrator.execute_project(project)

    # End profiling and get metrics
    profile = profiler.end_profile("parallel_execution")

    print("\nExecution Results:")
    for task_id, result in results.items():
        status = "✓" if result.get('success') else "✗"
        print(f"  {status} {task_id}: {result.get('status')}")

    print("\nPerformance Metrics:")
    print(f"  Total duration: {profile['total_duration']:.2f}s")
    print(f"  Parallel efficiency: {profile.get('efficiency', 0):.1f}%")

    # Get bottlenecks
    bottlenecks = profiler.get_bottlenecks()
    if bottlenecks:
        print("\nIdentified Bottlenecks:")
        for b in bottlenecks[:3]:
            print(f"  - {b['bottleneck']}: {b['duration']:.2f}s")

    return results


def stateful_project_management():
    """Demonstrate stateful project execution with checkpoints."""
    print("Stateful Project Management")
    print("-" * 50)

    # Initialize state manager
    state_manager = ProjectStateManager(
        project_id="claude_project_001",
        storage_path="./project_states"
    )

    # Initialize project
    state_manager.initialize_project({
        'name': 'e_commerce_platform',
        'description': 'Build complete e-commerce platform',
        'total_tasks': 10
    })

    # Create Claude Code agent
    agent = ClaudeCodeAgent("stateful_agent")

    # Simulate project execution with checkpoints
    tasks = [
        "Setup project structure",
        "Create database models",
        "Implement authentication",
        "Build product catalog",
        "Add shopping cart",
        "Implement checkout",
        "Add payment integration",
        "Create admin panel",
        "Write tests",
        "Setup deployment"
    ]

    try:
        # Check if resuming from checkpoint
        last_checkpoint = state_manager.get_last_checkpoint()
        start_idx = 0

        if last_checkpoint:
            print(f"\nResuming from checkpoint: {last_checkpoint['description']}")
            start_idx = last_checkpoint.get('task_index', 0) + 1

        # Execute tasks with checkpointing
        for idx, task in enumerate(tasks[start_idx:], start=start_idx):
            print(f"\nTask {idx + 1}/{len(tasks)}: {task}")

            # Record operation start
            state_manager.add_operation({
                'task': task,
                'index': idx,
                'status': 'in_progress'
            })

            # Execute task
            result = agent.execute_task({
                'type': 'code_generation',
                'description': task
            })

            # Record completion
            state_manager.add_operation({
                'task': task,
                'index': idx,
                'status': 'completed',
                'result': result
            })

            # Create checkpoint every 3 tasks
            if (idx + 1) % 3 == 0:
                checkpoint_id = state_manager.create_checkpoint(
                    f"Checkpoint after {task}",
                    metadata={'task_index': idx}
                )
                print(f"  → Checkpoint created: {checkpoint_id}")

        print("\n" + "="*50)
        print("Project completed successfully!")

        # Get project summary
        summary = state_manager.get_project_summary()
        print(f"Total operations: {summary['total_operations']}")
        print(f"Success rate: {summary['success_rate']:.1f}%")
        print(f"Checkpoints created: {summary['checkpoint_count']}")

        # Export project state
        export_file = state_manager.export_project("claude_project_export.json")
        print(f"\nProject exported to: {export_file}")

    except Exception as e:
        print(f"\nError occurred: {e}")
        print("Project state saved. Can resume from last checkpoint.")

    return state_manager


def monitoring_dashboard_demo():
    """Demonstrate real-time monitoring with Claude Code agents."""
    import threading

    from hydra.dashboard import start_dashboard

    print("Starting Monitoring Dashboard")
    print("-" * 50)
    print("\nDashboard will be available at: http://localhost:8001")
    print("(Run in background, open browser to view)")

    # Start dashboard in background thread
    dashboard_thread = threading.Thread(
        target=start_dashboard,
        kwargs={'host': '127.0.0.1', 'port': 8001},
        daemon=True
    )
    dashboard_thread.start()

    # Initialize monitoring
    monitoring.set_correlation_id("claude_monitoring_demo")

    # Create multiple agents for demonstration
    agents = [
        ClaudeCodeAgent(f"agent_{i}")
        for i in range(3)
    ]

    print("\nExecuting tasks with monitoring...")

    # Execute tasks with monitoring
    for i, agent in enumerate(agents):
        monitoring.track_agent_lifecycle(agent.agent_id, "start")

        # Simulate operations
        for j in range(5):
            operation = f"operation_{j}"
            monitoring.record_agent_operation(
                agent.agent_id,
                operation,
                duration=0.5 + (i * 0.1),
                success=j != 2,  # Simulate some failures
                metadata={'task_num': j}
            )

        monitoring.track_agent_lifecycle(agent.agent_id, "stop")

    # Record workflow metrics
    monitoring.record_workflow_execution(
        workflow_id="demo_workflow",
        duration=15.5,
        tasks_completed=12,
        tasks_failed=3
    )

    # Get health status
    health = monitoring.get_health_status()
    print(f"\nSystem Health: {health['status']}")
    print(f"Active alerts: {health['alerts']['total']}")

    print("\nMonitoring dashboard is running in background.")
    print("Press Ctrl+C to stop.")

    return health


if __name__ == "__main__":
    print("Claude Code Integration Examples")
    print("=" * 50)

    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY not set")
        print("Some examples will use mock data")

    # Run examples
    print("\n1. Claude Code Interactive Session")
    print("-" * 30)
    # claude_code_session()
    print("(Uncomment to run with real API key)")

    print("\n2. Intelligent Model Routing")
    print("-" * 30)
    intelligent_model_routing()

    print("\n3. Parallel Claude Agents")
    print("-" * 30)
    # parallel_claude_agents()
    print("(Uncomment to run with real API key)")

    print("\n4. Stateful Project Management")
    print("-" * 30)
    stateful_project_management()

    print("\n5. Monitoring Dashboard")
    print("-" * 30)
    # monitoring_dashboard_demo()
    print("(Uncomment to start dashboard)")

    print("\n" + "=" * 50)
    print("Examples completed!")
    print("\nFor production use, ensure:")
    print("  - API keys are configured")
    print("  - Redis is running (for queues)")
    print("  - Monitoring endpoints are configured")
    print("  - Safety guardrails are properly set")
