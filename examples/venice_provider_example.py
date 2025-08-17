#!/usr/bin/env python3
"""Venice AI Provider Example

This example demonstrates how to use Hydra with Venice AI's open-source models.
Venice provides access to powerful models like Qwen, Llama, and DeepSeek.

Prerequisites:
1. Get your API key from https://venice.ai
2. Set environment variable: export VENICE_API_KEY=your_key
"""

import os
import sys
from pathlib import Path

# Add hydra to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hydra.providers.base import LLMConfig
from hydra.providers.venice import VeniceProvider


def example_simple_generation():
    """Example of simple code generation with Venice."""
    # Initialize Venice provider
    config = LLMConfig(
        provider_type="venice",
        model="qwen-2.5-coder-32b",  # Best coding model
        api_key=os.getenv("VENICE_API_KEY"),
        base_url="https://api.venice.ai/api/v1",
        temperature=0.3,  # Lower for more deterministic output
        max_tokens=2000,
    )

    provider = VeniceProvider(config)

    # Generate code
    prompt = """
    Write a Python function that implements a binary search algorithm.
    Include proper documentation and type hints.
    """

    response = provider.generate(prompt)
    print("Generated Code:")
    print(response)


def example_ticket_execution():
    """Example of executing a development ticket with Venice."""
    from dotenv import load_dotenv

    load_dotenv()

    # Initialize Venice provider
    config = LLMConfig(
        provider_type="venice",
        model="llama-3.3-70b",  # Balanced model for complex tasks
        api_key=os.getenv("VENICE_API_KEY"),
        base_url="https://api.venice.ai/api/v1",
    )

    provider = VeniceProvider(config)

    # Define a development ticket
    ticket = """
    Create a Python CLI tool for file organization:
    
    1. Create 'file_organizer.py' with these features:
       - Function to organize files by extension
       - Function to organize by date modified
       - CLI interface using argparse
    
    2. Create 'README.md' with usage instructions
    
    Output files in code blocks with filename comments.
    """

    # Execute the ticket (creates actual files)
    output_dir = Path.cwd() / "example_output"
    output_dir.mkdir(exist_ok=True)

    result = provider.execute_ticket(
        ticket_content=ticket, working_directory=output_dir
    )

    print(f"Execution Success: {result['success']}")
    print(f"Files Created: {result['actions_executed']}")

    # List created files
    for file in output_dir.rglob("*"):
        if file.is_file():
            print(f"  - {file.relative_to(output_dir)}")


def example_model_selection():
    """Example showing different Venice models for different tasks."""
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("VENICE_API_KEY")

    # Fast model for simple tasks
    fast_config = LLMConfig(
        provider_type="venice",
        model="llama-3.2-3b",  # Small, fast model
        api_key=api_key,
        base_url="https://api.venice.ai/api/v1",
    )

    # Smart model for complex reasoning
    smart_config = LLMConfig(
        provider_type="venice",
        model="qwen-2.5-qwq-32b",  # Advanced reasoning model
        api_key=api_key,
        base_url="https://api.venice.ai/api/v1",
    )

    # Coding specialist
    coder_config = LLMConfig(
        provider_type="venice",
        model="deepseek-coder-v2-lite",  # Optimized for code
        api_key=api_key,
        base_url="https://api.venice.ai/api/v1",
    )

    print("Venice models configured for different use cases!")
    print("- Fast responses: llama-3.2-3b")
    print("- Complex reasoning: qwen-2.5-qwq-32b")
    print("- Code generation: deepseek-coder-v2-lite")


def list_available_models():
    """List all available Venice models."""
    import requests
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("VENICE_API_KEY")
    if not api_key:
        print("Please set VENICE_API_KEY environment variable")
        return

    # Query Venice API for available models
    url = "https://api.venice.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        models = response.json()
        print("Available Venice Models:")
        for model in models.get("data", []):
            model_id = model.get("id", "unknown")
            print(f"  - {model_id}")
    else:
        print(f"Error: {response.status_code}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Venice AI Provider Examples")
    parser.add_argument(
        "example",
        choices=["simple", "ticket", "models", "list"],
        help="Which example to run",
    )

    args = parser.parse_args()

    # Check for API key
    if not os.getenv("VENICE_API_KEY"):
        print("⚠️  Please set VENICE_API_KEY environment variable")
        print("   Get your key at: https://venice.ai")
        sys.exit(1)

    if args.example == "simple":
        example_simple_generation()
    elif args.example == "ticket":
        example_ticket_execution()
    elif args.example == "models":
        example_model_selection()
    elif args.example == "list":
        list_available_models()
