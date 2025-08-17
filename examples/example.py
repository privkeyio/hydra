#!/usr/bin/env python3
"""Hydra Example: Showcasing the multi-agent code generation system
This example demonstrates Hydra's capabilities using Venice AI.
"""

import os
import sys

from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from hydra import execute_workflow
from hydra.config import get_config

# Load environment variables
load_dotenv()


def showcase_hydra():
    """Demonstrate various Hydra capabilities."""
    print("🚀 Hydra Multi-Agent Code Generation System")
    print("=" * 60)

    # Check configuration
    config = get_config()
    print("\n📋 Configuration:")
    print(f"   Provider: {config.llm_provider.name}")
    print(f"   Model: {config.llm_provider.model}")
    print(f"   Max Depth: {config.config['agent']['max_depth']}")
    print()

    # Example 1: Simple function generation
    print("Example 1: Simple Function Generation")
    print("-" * 40)
    task1 = "Create a Python function that validates email addresses using regex"

    print(f"Task: {task1}")
    print("\nExecuting...")

    try:
        result1 = execute_workflow(task1, agent_name="validator_boss")
        print("\n✅ Task completed!")
        print(f"Agents created: {len(result1['agents'])}")
        print(f"Plan: {result1['plan'][:100]}...")
        if result1.get("subtasks"):
            print(f"Subtasks: {len(result1['subtasks'])}")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 60)

    # Example 2: Complex multi-step task
    print("\nExample 2: Complex Multi-Step Task")
    print("-" * 40)
    task2 = """Create a complete Python class for a TodoList manager with the following features:
    1. Add tasks with priority levels
    2. Mark tasks as complete
    3. List tasks by priority
    4. Save/load from JSON file
    Include error handling and type hints."""

    print(f"Task: {task2[:100]}...")
    print("\nExecuting...")

    try:
        result2 = execute_workflow(task2, agent_name="architect")
        print("\n✅ Task completed!")
        print(f"Agents created: {len(result2['agents'])}")

        # Show agent hierarchy
        print("\nAgent Hierarchy:")
        for agent in result2["agents"]:
            if agent == "architect":
                print(f"  👔 {agent} (Boss)")
            else:
                print(f"  👷 {agent}")

        if "results" in result2:
            successful = sum(
                1
                for r in result2["results"].values()
                if isinstance(r, dict) and r.get("success")
            )
            print(f"\nSuccessful subtasks: {successful}/{len(result2['results'])}")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 60)

    # Example 3: Algorithm implementation
    print("\nExample 3: Algorithm Implementation")
    print("-" * 40)
    task3 = "Implement a binary search tree in Python with insert, search, and delete operations"

    print(f"Task: {task3}")
    print("\nExecuting...")

    try:
        result3 = execute_workflow(task3, agent_name="algorithm_expert", depth=0)
        print("\n✅ Task completed!")
        print(f"Total agents involved: {len(result3['agents'])}")

        # Show task decomposition
        if result3.get("subtasks"):
            print("\nTask Decomposition:")
            for i, subtask in enumerate(result3["subtasks"], 1):
                print(f"  {i}. {subtask[:60]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 60)

    # Example 4: Testing Hydra's error handling
    print("\nExample 4: Error Handling & Retry Logic")
    print("-" * 40)
    task4 = "Create a function that intentionally has a syntax error, then fix it"

    print(f"Task: {task4}")
    print("\nExecuting...")

    try:
        result4 = execute_workflow(task4, agent_name="debugger")
        print("\n✅ Task completed with retry logic!")
        print("Hydra automatically retries on failures")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 60)
    print("\n🎉 Hydra demonstration complete!")
    print("\nKey Features Demonstrated:")
    print("  ✓ Hierarchical agent spawning")
    print("  ✓ Task decomposition")
    print("  ✓ Autonomous code generation")
    print("  ✓ Error handling and retries")
    print("  ✓ Multi-provider support (Venice AI)")


def simple_example():
    """A simple example for quick testing."""
    print("\n🔧 Simple Hydra Example")
    print("=" * 40)

    task = "Write a Python function to calculate the factorial of a number"
    print(f"Task: {task}")

    try:
        result = execute_workflow(task)
        print(f"\n✅ Success! Created {len(result['agents'])} agents")
        print(f"Plan: {result['plan']}")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    # Check if Venice API key is set
    if not os.getenv("VENICE_API_KEY"):
        print("⚠️  Warning: VENICE_API_KEY not found in environment")
        print("   Please set it in your .env file or environment")
        sys.exit(1)

    # Run examples
    if len(sys.argv) > 1 and sys.argv[1] == "--simple":
        simple_example()
    else:
        showcase_hydra()
