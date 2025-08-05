# Getting Started with Hydra Examples

Welcome to Hydra's example collection! This guide will help you get started with using Hydra for multi-agent code generation.

## Quick Start

1. **Set up your Venice API key**:
   ```bash
   # In the root directory, create a .env file
   echo "VENICE_API_KEY=your_venice_api_key_here" > ../.env
   ```

2. **Run your first example**:
   ```bash
   python quick_demo.py
   ```

## Understanding the Examples

### Start Here: `quick_demo.py`
- **Purpose**: See Hydra in action in under a minute
- **What it shows**: Basic code generation, multi-agent collaboration, hierarchical execution
- **Best for**: Getting a quick overview of capabilities

### Go Deeper: `interactive_example.py`
- **Purpose**: Explore Hydra's features interactively
- **What it shows**: Menu-driven examples with detailed output
- **Best for**: Understanding how different features work

### Full Showcase: `example.py`
- **Purpose**: Comprehensive demonstration of all features
- **What it shows**: Various task types and complexity levels
- **Best for**: Seeing the full range of what Hydra can do

### Real World: `real_world_example.py`
- **Purpose**: Production-style use cases
- **What it shows**: Building complete packages, CLI tools, API wrappers
- **Best for**: Learning how to integrate Hydra into real projects

## Example Outputs

### Single Agent Code Generation
```python
# Task: "Calculate factorial"
def factorial(n):
    if n == 0 or n == 1:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
```

### Multi-Agent Task Decomposition
```
Task: Build a REST API client
Plan: Create a modular API client with proper error handling

Subtasks:
1. Create base HTTP client class
2. Implement GET request method
3. Implement POST request method
4. Add JSON response handling
5. Implement retry logic
6. Add error handling
```

### Agent Hierarchy Visualization
```
api_architect (Boss)
├── api_architect_employee_0 (HTTP client)
├── api_architect_employee_1 (GET method)
├── api_architect_employee_2 (POST method)
├── api_architect_employee_3 (JSON handler)
├── api_architect_employee_4 (Retry logic)
└── api_architect_employee_5 (Error handling)
```

## Common Patterns

### 1. Simple Code Generation
```python
from hydra.agents.base import CodeAgent

agent = CodeAgent("my_coder")
code = agent.generate_code("Create a function to validate email")
print(code)
```

### 2. Complex Task with Workflow
```python
from hydra import execute_workflow

result = execute_workflow(
    "Build a complete CLI tool for task management",
    agent_name="cli_architect"
)
```

### 3. Task Analysis
```python
agent = CodeAgent("analyst")
plan = agent.reason("Analyze and refactor this codebase")
print(f"Plan: {plan['plan']}")
print(f"Subtasks: {plan['subtasks']}")
```

## Tips for Success

1. **Be Specific**: Clear, detailed task descriptions yield better results
   - ❌ "Make a calculator"
   - ✅ "Create a calculator class with add, subtract, multiply, divide methods and error handling"

2. **Use Appropriate Complexity**: Hydra shines with multi-step tasks
   - Simple tasks: Use single agent
   - Complex tasks: Use workflow for automatic decomposition

3. **Monitor Progress**: Watch the agent hierarchy form in real-time
   ```bash
   # Run with visible logging
   tail -f ../logs/agent_activity.log
   ```

4. **Experiment with Models**: Venice offers multiple models
   ```bash
   # In your .env file
   LLM_MODEL=qwen-2.5-coder-32b  # Best for code
   LLM_MODEL=llama-3.3-70b       # Good all-around
   ```

## Debugging

If examples aren't working:

1. **Check API Key**:
   ```bash
   echo $VENICE_API_KEY  # Should show your key
   ```

2. **Verify Installation**:
   ```bash
   cd .. && pip install -e .
   ```

3. **Check Logs**:
   ```bash
   tail -n 50 ../logs/agent_activity.log
   ```

## Next Steps

1. **Modify Examples**: Try changing task descriptions in the examples
2. **Create Your Own**: Use the patterns to build custom solutions
3. **Integrate**: Add Hydra to your development workflow
4. **Explore Providers**: Try other LLM providers (OpenAI, Anthropic)

## Need Help?

- Check the main [README](../README.md)
- Review [ARCHITECTURE](../docs/ARCHITECTURE.md) docs
- See [API_REFERENCE](../docs/API_REFERENCE.md) for details

Happy coding with Hydra! 🚀