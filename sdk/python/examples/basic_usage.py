#!/usr/bin/env python3

import os

from hydra_sdk import HydraClient


def main():
    api_key = os.getenv("HYDRA_API_KEY")
    if not api_key:
        print("Please set HYDRA_API_KEY environment variable")
        return

    client = HydraClient(
        api_key=api_key, base_url=os.getenv("HYDRA_BASE_URL", "http://localhost:8000")
    )

    try:
        print("Checking API health...")
        health = client.get_health()
        print(f"API Status: {health.status}")
        print(f"Providers: {health.providers}")
        print()

        print("Generating code...")
        task = client.generate_code(
            prompt="Create a Python function that calculates the factorial of a number",
            language="python",
        )
        print(f"Task created: {task.task_id}")

        print("Waiting for completion...")
        status = client.wait_for_completion(task.task_id, timeout=120)

        if status.status == "completed":
            print("Code generation completed!")
            print("Generated code:")
            print("-" * 50)
            print(status.result.get("code", "No code returned"))
            print("-" * 50)
        else:
            print(f"Task failed: {status.error}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
