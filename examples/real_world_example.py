#!/usr/bin/env python3
"""Real-World Hydra Example: Building a Complete Python Project
This example shows how to use Hydra to build an entire Python package.
"""

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
load_dotenv()

from hydra import CodeAgent, execute_workflow
from hydra.config import get_config


def build_weather_api_client():
    """Use Hydra to build a complete weather API client package."""
    print("🌤️  Building a Weather API Client with Hydra")
    print("=" * 60)

    # Define the project requirements
    project_spec = """
    Create a complete Python package called 'weather_client' that:
    
    1. Main client class (WeatherClient) that:
       - Fetches weather data from OpenWeatherMap API
       - Supports getting weather by city name
       - Supports getting weather by coordinates
       - Caches results for 10 minutes
       - Has proper error handling
    
    2. Data models using dataclasses:
       - Weather (temperature, humidity, description)
       - Location (city, country, coordinates)
       - Forecast (list of weather data)
    
    3. Utility functions:
       - Temperature conversion (C to F, F to C)
       - Wind speed conversion (m/s to mph)
       - Format weather data for display
    
    4. Configuration management:
       - Load API key from environment
       - Configurable units (metric/imperial)
       - Timeout settings
    
    5. Basic tests:
       - Test temperature conversions
       - Test data model creation
       - Mock API responses
    """

    print("📋 Project Requirements:")
    print(project_spec)

    print("\n🚀 Starting Hydra...")

    # Execute the workflow
    result = execute_workflow(
        project_spec,
        agent_name="project_architect"
    )

    print("\n✅ Project generation complete!")
    print("\n📊 Generation Statistics:")
    print(f"   Total agents created: {len(result['agents'])}")
    print(f"   Subtasks identified: {len(result.get('subtasks', []))}")

    # Show the task breakdown
    if result.get('subtasks'):
        print("\n📝 Task Breakdown:")
        for i, subtask in enumerate(result['subtasks'], 1):
            print(f"   {i}. {subtask[:70]}...")

    # Show agent hierarchy
    print("\n🤖 Agent Collaboration:")
    agents_by_depth = {}
    for agent in result['agents']:
        depth = agent.count('_employee')
        if depth not in agents_by_depth:
            agents_by_depth[depth] = []
        agents_by_depth[depth].append(agent)

    for depth in sorted(agents_by_depth.keys()):
        indent = "  " * depth
        for agent in agents_by_depth[depth]:
            role = "Boss" if depth == 0 else f"Level {depth} Employee"
            print(f"{indent}└─ {agent} ({role})")

    return result


def analyze_codebase():
    """Use Hydra to analyze and document an existing codebase."""
    print("\n\n📚 Code Analysis with Hydra")
    print("=" * 60)

    analysis_task = """
    Analyze this Python codebase and create:
    1. A comprehensive README with:
       - Project overview
       - Installation instructions
       - Usage examples
       - API documentation links
    
    2. Architecture documentation explaining:
       - Main components and their responsibilities
       - Data flow between components
       - Design patterns used
       - Extension points
    
    3. A getting started guide for new developers
    """

    print("📋 Analysis Task:")
    print(analysis_task)

    # Single agent for analysis
    analyst = CodeAgent("code_analyst")

    print("\n🔍 Analyzing codebase structure...")

    # Get analysis plan
    plan = analyst.reason(analysis_task)

    print(f"\n📋 Analysis Plan: {plan['plan']}")

    if plan['subtasks']:
        print("\n📝 Analysis Steps:")
        for i, step in enumerate(plan['subtasks'], 1):
            print(f"   {i}. {step}")


def generate_cli_tool():
    """Use Hydra to generate a complete CLI tool."""
    print("\n\n🛠️  CLI Tool Generation with Hydra")
    print("=" * 60)

    cli_spec = """
    Create a Python CLI tool called 'taskmaster' using Click that:
    
    1. Main commands:
       - add: Add a new task with title and optional tags
       - list: List all tasks with filtering options
       - complete: Mark a task as completed
       - delete: Remove a task
       - stats: Show task statistics
    
    2. Features:
       - Store tasks in JSON file
       - Support for tags and priorities
       - Due date tracking
       - Colored output for better UX
       - Export tasks to markdown
    
    3. Include proper error handling and help messages
    """

    print("📋 CLI Tool Specification:")
    print(cli_spec)

    print("\n🚀 Generating CLI tool...")

    # Use a single agent for focused generation
    cli_expert = CodeAgent("cli_developer")

    # Generate the CLI code
    cli_code = cli_expert.generate_code(cli_spec)

    print("\n✅ CLI tool generated!")
    print("\n📄 Generated Code Preview (first 20 lines):")
    print("-" * 60)
    lines = cli_code.split('\n')[:20]
    for i, line in enumerate(lines, 1):
        print(f"{i:3d} | {line}")
    print("-" * 60)
    print(f"... ({len(cli_code.split('\n'))} total lines)")

    return cli_code


def create_api_wrapper():
    """Use Hydra to create an API wrapper for a service."""
    print("\n\n🔌 API Wrapper Generation with Hydra")
    print("=" * 60)

    # This demonstrates how Hydra can understand API specs
    # and generate appropriate client code

    api_task = """
    Create a Python wrapper for a REST API with these endpoints:
    
    Base URL: https://api.example.com/v1
    
    Endpoints:
    - GET /users - List all users
    - GET /users/{id} - Get user by ID
    - POST /users - Create new user
    - PUT /users/{id} - Update user
    - DELETE /users/{id} - Delete user
    
    Requirements:
    - Use requests library
    - Include authentication via API key header
    - Implement rate limiting (100 requests/minute)
    - Add retry logic for failed requests
    - Create User model with fields: id, name, email, created_at
    - Include comprehensive error handling
    """

    print("📋 API Wrapper Requirements:")
    print(api_task)

    print("\n🚀 Executing with Hydra...")

    result = execute_workflow(api_task, agent_name="api_wrapper_architect")

    print("\n✅ API wrapper design complete!")
    print(f"   Agents involved: {len(result['agents'])}")

    # Show how the task was broken down
    if 'plan' in result:
        print(f"\n🎯 Approach: {result['plan'][:150]}...")


def main():
    """Run the examples."""
    if not os.getenv('VENICE_API_KEY'):
        print("❌ VENICE_API_KEY not found in environment!")
        return

    # Show configuration
    config = get_config()
    print("\n⚙️  Hydra Configuration:")
    print(f"   Provider: {config.llm_provider.name}")
    print(f"   Model: {config.llm_provider.model}")
    print(f"   Max Agent Depth: {config.config['agent']['max_depth']}")

    print("\n" + "=" * 60)
    print("🚀 HYDRA REAL-WORLD EXAMPLES")
    print("=" * 60)

    examples = [
        ("1", "Build Weather API Client Package", build_weather_api_client),
        ("2", "Analyze Existing Codebase", analyze_codebase),
        ("3", "Generate CLI Tool", generate_cli_tool),
        ("4", "Create API Wrapper", create_api_wrapper),
        ("5", "Run All Examples", None)
    ]

    while True:
        print("\n📋 Available Examples:")
        for num, desc, _ in examples:
            print(f"   {num}. {desc}")
        print("   0. Exit")

        choice = input("\nSelect an example (0-5): ").strip()

        if choice == "0":
            print("\n👋 Goodbye!")
            break
        elif choice == "5":
            # Run all examples
            for num, desc, func in examples[:-1]:  # Skip "Run All"
                if func:
                    print(f"\n{'='*60}")
                    func()
                    input("\nPress Enter to continue to next example...")
        else:
            # Find and run selected example
            for num, desc, func in examples:
                if num == choice and func:
                    func()
                    break
            else:
                print("❌ Invalid choice!")

        if choice != "5":
            input("\nPress Enter to return to menu...")


if __name__ == "__main__":
    main()
