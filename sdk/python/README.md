# Hydra Python SDK

Python SDK for the Hydra AI agent system API.

## Installation

```bash
pip install hydra-sdk
```

## Quick Start

### Synchronous Client

```python
from hydra_sdk import HydraClient

client = HydraClient(api_key="your-api-key", base_url="https://api.hydra-ai.com")

# Generate code
task = client.generate_code("Create a Python function to calculate fibonacci numbers")
status = client.wait_for_completion(task.task_id)
print(status.result)

# Execute workflow
workflow_task = client.execute_workflow("Build a REST API with authentication")
workflow_status = client.wait_for_completion(workflow_task.task_id)
print(workflow_status.result)

# Check health
health = client.get_health()
print(f"API Status: {health.status}")
```

### Asynchronous Client

```python
import asyncio
from hydra_sdk import HydraAsyncClient

async def main():
    async with HydraAsyncClient(api_key="your-api-key") as client:
        # Generate code
        task = await client.generate_code("Create a FastAPI endpoint")
        status = await client.wait_for_completion(task.task_id)
        print(status.result)
        
        # Execute workflow
        workflow_task = await client.execute_workflow("Build a microservice")
        workflow_status = await client.wait_for_completion(workflow_task.task_id)
        print(workflow_status.result)

asyncio.run(main())
```

## Features

- **Full API Coverage**: All Hydra API endpoints supported
- **Type Safety**: Complete type hints with Pydantic models
- **Automatic Retries**: Exponential backoff for failed requests
- **Rate Limit Handling**: Automatic retry on rate limit errors
- **Both Sync/Async**: Choose the client that fits your needs
- **Task Monitoring**: Built-in task completion waiting

## API Reference

### HydraClient / HydraAsyncClient

#### Methods

- `generate_code(prompt, language=None, max_tokens=4000)` - Generate code
- `execute_workflow(task, agents=3, max_iterations=10)` - Execute multi-agent workflow
- `get_task_status(task_id)` - Get task status and progress
- `wait_for_completion(task_id, poll_interval=2.0, timeout=None)` - Wait for task completion
- `get_health()` - Get API health status
- `invalidate_cache(cache_type, key=None)` - Invalidate cache entries
- `get_cache_stats()` - Get cache statistics
- `generate_signature(method, path, body, timestamp)` - Generate request signature
- `query_audit_logs(query)` - Query audit logs (admin only)

#### Configuration

```python
client = HydraClient(
    api_key="your-api-key",
    base_url="https://api.hydra-ai.com",  # Default: http://localhost:8000
    timeout=60,                           # Request timeout in seconds
    max_retries=3,                        # Maximum retry attempts
    retry_delay=1.0,                      # Base retry delay in seconds
)
```

## Error Handling

```python
from hydra_sdk import HydraClient
from hydra_sdk.exceptions import (
    HydraAPIError,
    HydraAuthenticationError,
    HydraRateLimitError,
    HydraTimeoutError,
)

client = HydraClient(api_key="your-api-key")

try:
    task = client.generate_code("Create a function")
    status = client.wait_for_completion(task.task_id)
except HydraAuthenticationError:
    print("Invalid API key")
except HydraRateLimitError:
    print("Rate limit exceeded")
except HydraTimeoutError:
    print("Request timed out")
except HydraAPIError as e:
    print(f"API error {e.status_code}: {e.message}")
```

## License

MIT License