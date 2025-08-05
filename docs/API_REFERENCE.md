# Hydra API Reference

## Table of Contents
- [CodeAgent Class](#codeagent-class)
- [LLM Provider System](#llm-provider-system)
- [Workflow Engine](#workflow-engine)
- [CLI Interface](#cli-interface)
- [Configuration](#configuration)
- [Utilities](#utilities)

## CodeAgent Class

The core agent implementation for the Hydra system.

### Class: `hydra.agents.base.CodeAgent`

#### Constructor

```python
CodeAgent(name: str, parent: Optional['CodeAgent'] = None, depth: int = 0)
```

**Parameters:**
- `name` (str): Unique identifier for the agent
- `parent` (Optional[CodeAgent]): Parent agent reference for hierarchy
- `depth` (int): Current depth in the hierarchy (0-2)

**Example:**
```python
from hydra.agents.base import CodeAgent

boss = CodeAgent("boss")
employee = CodeAgent("worker", parent=boss, depth=1)
```

#### Methods

##### `reason(task: str) -> Dict[str, Any]`

Analyzes a task and creates an execution plan with potential subtasks.

**Parameters:**
- `task` (str): The task description to analyze

**Returns:**
- Dict containing:
  - `plan` (str): Strategy to accomplish the task
  - `subtasks` (List[str]): List of subtasks (empty if atomic)

**Raises:**
- `RecursionError`: If agent depth exceeds maximum (2)

**Example:**
```python
result = agent.reason("Create a calculator with basic operations")
# Returns: {
#   "plan": "Build calculator with add, subtract, multiply, divide",
#   "subtasks": ["Create add function", "Create subtract function", ...]
# }
```

##### `generate_code(prompt: str, retry_count: int = 0) -> str`

Generates Python code based on the given prompt.

**Parameters:**
- `prompt` (str): Description of code to generate
- `retry_count` (int): Current retry attempt (internal use)

**Returns:**
- str: Valid Python code as a string

**Raises:**
- `ValueError`: If generated code fails AST validation after retries

**Example:**
```python
code = agent.generate_code("Create a function that adds two numbers")
# Returns: "def add(a, b):\n    return a + b"
```

##### `execute_code(code_str: str, retry_count: int = 0) -> Dict[str, Any]`

Executes Python code in a sandboxed subprocess.

**Parameters:**
- `code_str` (str): Python code to execute
- `retry_count` (int): Current retry attempt (internal use)

**Returns:**
- Dict containing:
  - `success` (bool): Execution status
  - `stdout` (str): Standard output
  - `stderr` (str): Standard error
  - `returncode` (int): Process return code

**Example:**
```python
result = agent.execute_code("print('Hello, World!')")
# Returns: {
#   "success": True,
#   "stdout": "Hello, World!\n",
#   "stderr": "",
#   "returncode": 0
# }
```

##### `create_employee(subtask: str) -> Dict[str, Any]`

Spawns a child agent to handle a subtask.

**Parameters:**
- `subtask` (str): Task for the employee to handle

**Returns:**
- Dict containing:
  - `success` (bool): Spawn status
  - `employee` (CodeAgent): Employee agent instance
  - `result` (Dict): Employee execution results
  - `spawn_code` (str): Generated spawn code
  - `error` (str, optional): Error message if failed

**Raises:**
- `RecursionError`: If current depth is at maximum

**Example:**
```python
result = boss.create_employee("Implement data validation")
```

## Workflow Engine

### Function: `hydra.workflows.engine.execute_workflow`

```python
execute_workflow(
    task: str,
    agent_name: str = "boss",
    depth: int = 0
) -> Dict[str, Any]
```

Executes the complete agent workflow for a given task.

**Parameters:**
- `task` (str): Task description to execute
- `agent_name` (str): Name of the root agent
- `depth` (int): Starting depth level

**Returns:**
- Dict containing full workflow state including:
  - `task`: Original task
  - `plan`: Execution plan
  - `subtasks`: Decomposed subtasks
  - `results`: Aggregated results
  - `agents`: List of created agents

**Example:**
```python
from hydra.workflows import execute_workflow

results = execute_workflow(
    task="Create a REST API endpoint",
    agent_name="architect"
)
```

### Function: `hydra.workflows.engine.create_workflow`

```python
create_workflow() -> CompiledGraph
```

Creates and compiles the LangGraph workflow.

**Returns:**
- Compiled LangGraph workflow instance

## CLI Interface

### Function: `hydra.cli.main`

```python
main() -> int
```

Main CLI entry point for the Hydra system.

**Command Line Arguments:**
- `task` (positional): Task description
- `--agent-name`: Root agent name (default: "boss")
- `--depth`: Starting depth (default: 0)
- `--json`: Output in JSON format

**Returns:**
- int: Exit code (0 for success, 1 for error)

**Example:**
```bash
# Basic usage
python -m hydra.cli "Create a function"

# With options
python -m hydra.cli "Complex task" --agent-name "manager" --json
```

## LLM Provider System

### Abstract Base Class: `hydra.providers.base.LLMProvider`

Base class for all LLM provider implementations.

#### Properties

- `name` (str): Provider identifier
- `model` (str): Current model being used
- `config` (LLMConfig): Provider configuration

#### Abstract Methods

##### `validate_config()`

Validates provider-specific configuration requirements.

**Raises:**
- `ValueError`: If configuration is invalid

##### `generate(prompt: str, **kwargs) -> str`

Generates text response from the LLM.

**Parameters:**
- `prompt` (str): Input prompt
- `**kwargs`: Optional parameters (temperature, max_tokens, etc.)

**Returns:**
- str: Generated text response

##### `generate_json(prompt: str, **kwargs) -> Dict[str, Any]`

Generates JSON response from the LLM.

**Parameters:**
- `prompt` (str): Input prompt requesting JSON
- `**kwargs`: Optional parameters

**Returns:**
- Dict: Parsed JSON response

##### `list_models() -> List[str]`

Lists available models for this provider.

**Returns:**
- List[str]: Available model identifiers

### Data Class: `hydra.providers.base.LLMConfig`

Configuration for LLM providers.

```python
@dataclass
class LLMConfig:
    provider_type: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout: int = 30
    extra_params: Dict[str, Any] = None
```

### Factory: `hydra.providers.factory.LLMProviderFactory`

Factory for creating provider instances.

#### Method: `create(config: LLMConfig) -> LLMProvider`

Creates a provider instance from configuration.

**Parameters:**
- `config` (LLMConfig): Provider configuration

**Returns:**
- LLMProvider: Instantiated provider

**Example:**
```python
from hydra.providers import LLMConfig, provider_factory

config = LLMConfig(
    provider_type='venice',
    model='qwen-2.5-coder-32b',
    api_key='your-api-key'
)

provider = provider_factory.create(config)
response = provider.generate("Write a hello world function")
```

### Available Providers

#### VeniceProvider

Venice AI provider using OpenAI-compatible API.

**Configuration:**
- `api_key`: Required Venice API key
- `base_url`: API endpoint (default: https://api.venice.ai/api/v1)
- `model`: Model to use (default: qwen-2.5-coder-32b)

#### AnthropicProvider

Anthropic Claude provider.

**Configuration:**
- `api_key`: Required Anthropic API key
- `model`: Claude model (default: claude-3-5-sonnet-20241022)

#### OpenAIProvider

OpenAI GPT provider.

**Configuration:**
- `api_key`: Required OpenAI API key
- `base_url`: Optional custom endpoint
- `model`: GPT model (default: gpt-4)

#### ClaudeCLIProvider

Claude CLI wrapper provider.

**Configuration:**
- `claude_path`: Path to Claude binary (in extra_params)
- `cli_flags`: Optional CLI flags (in extra_params)

## Configuration

### Module: `hydra.config`

#### Variables

- `USE_VENICE` (bool): Whether to use Venice API fallback
- `anthropic_client` (Anthropic): Configured Anthropic client instance

#### Function: `generate_code_with_claude_cli`

```python
generate_code_with_claude_cli(prompt: str) -> str
```

Generates code using Claude CLI with fallback options.

**Parameters:**
- `prompt` (str): Code generation prompt

**Returns:**
- str: Generated code

## Utilities

### Module: `hydra.utils.venice`

#### Function: `venice_call`

```python
venice_call(prompt: str) -> str
```

Makes API call to Venice for code generation.

**Parameters:**
- `prompt` (str): Generation prompt

**Returns:**
- str: Generated response

**Example:**
```python
from hydra.utils import venice_call

response = venice_call("Generate a sorting algorithm")
```

## Type Definitions

### WorkflowState

```python
from typing import TypedDict, List, Dict, Any

class WorkflowState(TypedDict):
    task: str
    depth: int
    results: Dict[str, Any]
    agents: List[str]
    current_agent: str
    subtasks: List[str]
    plan: str
```

## Error Handling

### Common Exceptions

- `RecursionError`: Agent depth limit exceeded
- `ValueError`: Invalid code generation or validation failure
- `subprocess.TimeoutExpired`: Code execution timeout (30s)
- `anthropic.APIError`: LLM API errors

### Error Response Format

```python
{
    "success": False,
    "error": "Error message",
    "stdout": "",
    "stderr": "Detailed error information",
    "returncode": -1
}
```

## Best Practices

1. **Depth Management**: Always check depth before spawning
2. **Error Handling**: Wrap API calls in try-except blocks
3. **Logging**: Use agent's logger for debugging
4. **Timeouts**: Be aware of 30s execution limit
5. **Task Clarity**: Provide clear, specific task descriptions

## Example: Complete Usage

```python
from hydra import CodeAgent, execute_workflow

# Method 1: Direct agent usage
boss = CodeAgent("boss")
reasoning = boss.reason("Create a calculator")

if reasoning["subtasks"]:
    for subtask in reasoning["subtasks"]:
        result = boss.create_employee(subtask)
        print(f"Subtask '{subtask}': {result['success']}")

# Method 2: Workflow engine
results = execute_workflow("Create a calculator")
print(f"Plan: {results['plan']}")
print(f"Agents created: {results['agents']}")
```