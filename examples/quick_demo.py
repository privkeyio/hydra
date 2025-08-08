#!/usr/bin/env python3
"""Quick Hydra Demo - See the multi-agent system in action!
"""

import os
import sys

from dotenv import load_dotenv

# Setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from hydra import execute_workflow
from hydra.agents.base import CodeAgent


def demo_single_agent():
    """Demo: Single agent generating code."""
    print("\n🤖 DEMO 1: Single Agent Code Generation")
    print("-" * 50)

    agent = CodeAgent("coder")
    task = "Write a Python function to reverse a string without using slicing"

    print(f"Task: {task}")
    code = agent.generate_code(task)

    print("\nGenerated Code:")
    print(code)

    # Execute it
    test_code = code + '\n\nprint(reverse_string("Hello Hydra!"))'
    result = agent.execute_code(test_code)

    if result['success']:
        print(f"\nExecution Output: {result['stdout'].strip()}")


def demo_multi_agent():
    """Demo: Multi-agent collaborative task."""
    print("\n\n🤝 DEMO 2: Multi-Agent Collaboration")
    print("-" * 50)

    task = """Create a Python module with:
    1. A function to check if a number is prime
    2. A function to generate first N prime numbers
    3. A function to find prime factors of a number"""

    print(f"Task: {task}")
    print("\nExecuting with multi-agent system...")

    result = execute_workflow(task, agent_name="math_boss")

    print("\n✅ Task completed!")
    print(f"Agents involved: {', '.join(result['agents'])}")
    print(f"Subtasks created: {len(result.get('subtasks', []))}")


def demo_complex_task():
    """Demo: Complex task with deep hierarchy."""
    print("\n\n🏗️  DEMO 3: Complex Hierarchical Task")
    print("-" * 50)

    task = """Build a simple REST API client that:
    - Makes GET and POST requests
    - Handles JSON responses
    - Includes error handling
    - Has retry logic"""

    print(f"Task: {task}")
    print("\nBuilding with Hydra...")

    result = execute_workflow(task, agent_name="api_architect")

    print("\n✅ Construction complete!")
    print("\nAgent Hierarchy:")
    for agent in result['agents']:
        depth = agent.count('_employee')
        indent = "  " * depth
        print(f"{indent}└─ {agent}")


def main():
    if not os.getenv('VENICE_API_KEY'):
        print("❌ VENICE_API_KEY not found! Set it in .env file")
        return

    print("🚀 HYDRA QUICK DEMO - Multi-Agent Code Generation")
    print("=" * 50)
    print("Using Venice AI for code generation")

    # Run all demos
    demo_single_agent()
    demo_multi_agent()
    demo_complex_task()

    print("\n\n✨ Demo Complete! Hydra's key features:")
    print("  • Autonomous code generation")
    print("  • Task decomposition")
    print("  • Multi-agent collaboration")
    print("  • Hierarchical execution")
    print("  • Safe code sandboxing")


if __name__ == "__main__":
    main()
