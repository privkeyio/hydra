#!/usr/bin/env python3

import asyncio
import os

from hydra_sdk import HydraAsyncClient


async def main():
    api_key = os.getenv("HYDRA_API_KEY")
    if not api_key:
        print("Please set HYDRA_API_KEY environment variable")
        return

    async with HydraAsyncClient(
        api_key=api_key,
        base_url=os.getenv("HYDRA_BASE_URL", "http://localhost:8000")
    ) as client:
        try:
            print("Checking API health...")
            health = await client.get_health()
            print(f"API Status: {health.status}")
            print()

            print("Starting code generation and workflow in parallel...")

            code_task = await client.generate_code(
                prompt="Create a Python class for a binary search tree with insert and search methods",
                language="python"
            )

            workflow_task = await client.execute_workflow(
                task="Create a simple REST API with user authentication and CRUD operations",
                agents=2,
                max_iterations=5
            )

            print(f"Code task: {code_task.task_id}")
            print(f"Workflow task: {workflow_task.task_id}")

            code_status, workflow_status = await asyncio.gather(
                client.wait_for_completion(code_task.task_id, timeout=120),
                client.wait_for_completion(workflow_task.task_id, timeout=300)
            )

            print("\nCode generation result:")
            if code_status.status == "completed":
                print("✓ Completed")
                print(f"Code: {code_status.result.get('code', 'No code')[:200]}...")
            else:
                print(f"✗ Failed: {code_status.error}")

            print("\nWorkflow result:")
            if workflow_status.status == "completed":
                print("✓ Completed")
                print(f"Result: {str(workflow_status.result)[:200]}...")
            else:
                print(f"✗ Failed: {workflow_status.error}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
