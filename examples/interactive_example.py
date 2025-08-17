#!/usr/bin/env python3
"""Interactive Hydra Example: Real-time code generation with Venice AI"""

import os
import sys

from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from hydra import CodeAgent
from hydra.config import get_config

# Load environment variables
load_dotenv()


def print_separator(char="-", length=60):
    """Print a separator line."""
    print(char * length)


def generate_code_example():
    """Generate actual code and show the output."""
    print("\n🤖 Hydra Code Generation Example")
    print_separator("=")

    # Create a single agent for demonstration
    agent = CodeAgent("demo_agent")

    # Example 1: Generate a utility function
    print("\n1️⃣  Generating a URL shortener function")
    print_separator()

    prompt1 = """Create a Python function that:
    - Takes a long URL as input
    - Generates a short hash-based identifier
    - Returns a shortened URL format
    - Include proper error handling"""

    try:
        code1 = agent.generate_code(prompt1)
        print("Generated Code:")
        print_separator()
        print(code1)
        print_separator()

        # Execute the generated code
        print("\nExecuting generated code...")
        result = agent.execute_code(
            code1
            + '\n\n# Test the function\nprint(shorten_url("https://example.com/very/long/path"))'
        )
        if result["success"]:
            print(f"Output: {result['stdout']}")
        else:
            print(f"Error: {result['stderr']}")
    except Exception as e:
        print(f"Error: {e}")

    # Example 2: Generate a class
    print("\n\n2️⃣  Generating a Cache class")
    print_separator()

    prompt2 = """Create a Python class called LRUCache that:
    - Implements a Least Recently Used cache
    - Has get() and put() methods
    - Has a configurable size limit
    - Includes docstrings and type hints"""

    try:
        code2 = agent.generate_code(prompt2)
        print("Generated Code:")
        print_separator()
        print(code2)
        print_separator()
    except Exception as e:
        print(f"Error: {e}")

    # Example 3: Generate with specific requirements
    print("\n\n3️⃣  Generating code with specific requirements")
    print_separator()

    prompt3 = """Create a Python decorator that:
    - Measures function execution time
    - Logs the function name and duration
    - Works with functions that have any arguments
    - Name it 'measure_time'"""

    try:
        code3 = agent.generate_code(prompt3)
        print("Generated Code:")
        print_separator()
        print(code3)
        print_separator()

        # Test the decorator
        test_code = (
            code3
            + """

@measure_time
def slow_function(n):
    total = 0
    for i in range(n):
        total += i
    return total

# Test it
result = slow_function(1000000)
print(f"Result: {result}")
"""
        )
        print("\nTesting the decorator...")
        result = agent.execute_code(test_code)
        if result["success"]:
            print(f"Output:\n{result['stdout']}")
    except Exception as e:
        print(f"Error: {e}")


def task_decomposition_example():
    """Show how Hydra decomposes complex tasks."""
    print("\n\n🧩 Task Decomposition Example")
    print_separator("=")

    agent = CodeAgent("planner")

    complex_task = """Build a complete web scraping tool that:
    1. Fetches web pages
    2. Parses HTML content
    3. Extracts specific data based on CSS selectors
    4. Saves results to CSV
    5. Handles rate limiting and errors
    6. Includes logging"""

    print(f"Complex Task: {complex_task[:80]}...")
    print("\nAnalyzing and decomposing task...")

    try:
        plan = agent.reason(complex_task)
        print(f"\n📋 Execution Plan: {plan['plan']}")

        if plan["subtasks"]:
            print(f"\n📝 Subtasks ({len(plan['subtasks'])}):")
            for i, subtask in enumerate(plan["subtasks"], 1):
                print(f"   {i}. {subtask}")
    except Exception as e:
        print(f"Error: {e}")


def hierarchical_execution_example():
    """Demonstrate hierarchical agent execution."""
    print("\n\n🏗️  Hierarchical Execution Example")
    print_separator("=")

    from hydra.workflows import execute_workflow

    task = """Create a Python package for data validation that includes:
    1. Email validator
    2. Phone number validator  
    3. Credit card validator
    4. Unit tests for each validator"""

    print(f"Task: {task[:80]}...")
    print("\nExecuting with hierarchical agents...\n")

    try:
        result = execute_workflow(task, agent_name="package_builder")

        print("✅ Execution Complete!")
        print("\n📊 Statistics:")
        print(f"   Total agents created: {len(result['agents'])}")
        print(f"   Task decomposition: {len(result.get('subtasks', []))} subtasks")

        print("\n🤖 Agent Hierarchy:")
        for agent in result["agents"]:
            if agent == "package_builder":
                print(f"   └─ {agent} (Boss)")
            else:
                print(f"      └─ {agent}")

    except Exception as e:
        print(f"Error: {e}")


def main():
    """Run all examples."""
    # Check Venice API key
    if not os.getenv("VENICE_API_KEY"):
        print("⚠️  Error: VENICE_API_KEY not found!")
        print("   Please set it in your .env file")
        return

    # Show configuration
    config = get_config()
    print("\n⚙️  Configuration:")
    print(f"   Provider: {config.llm_provider.name}")
    print(f"   Model: {config.llm_provider.model}")

    # Run examples
    while True:
        print("\n\n📚 Hydra Examples Menu")
        print_separator("=")
        print("1. Code Generation Examples")
        print("2. Task Decomposition Example")
        print("3. Hierarchical Execution Example")
        print("4. Run All Examples")
        print("5. Exit")
        print_separator()

        choice = input("\nSelect an example (1-5): ").strip()

        if choice == "1":
            generate_code_example()
        elif choice == "2":
            task_decomposition_example()
        elif choice == "3":
            hierarchical_execution_example()
        elif choice == "4":
            generate_code_example()
            task_decomposition_example()
            hierarchical_execution_example()
        elif choice == "5":
            print("\n👋 Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
