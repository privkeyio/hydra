# Hydra Examples

This directory contains various examples demonstrating Hydra's multi-agent code generation capabilities using Venice AI.

## Prerequisites

Before running any examples, ensure you have:

1. Venice API key set in your `.env` file:
   ```bash
   VENICE_API_KEY=your_venice_api_key_here
   ```

2. Hydra installed:
   ```bash
   pip install -e .
   ```

## Available Examples

### 1. Quick Demo (`quick_demo.py`)

A fast demonstration of Hydra's core features:
- Single agent code generation
- Multi-agent collaboration
- Hierarchical task execution

```bash
python quick_demo.py
```

### 2. Interactive Example (`interactive_example.py`)

An interactive menu-driven demonstration:
- Real-time code generation
- Task decomposition visualization
- Hierarchical execution with statistics

```bash
python interactive_example.py
```

### 3. Showcase Example (`example.py`)

Comprehensive showcase of Hydra capabilities:
- Multiple code generation tasks
- Error handling demonstrations
- Complex multi-step projects

```bash
python example.py          # Full showcase
python example.py --simple # Simple example only
```

### 4. Real-World Example (`real_world_example.py`)

Production-style use cases:
- Building complete Python packages
- Generating CLI tools
- Creating API wrappers
- Codebase analysis

```bash
python real_world_example.py
```

## Example Output

Here's what you can expect from running the examples:

### Single Agent Generation
```python
# Task: "Write a function to reverse a string"
def reverse_string(s):
    reversed_str = ''
    for char in s:
        reversed_str = char + reversed_str
    return reversed_str
```

### Multi-Agent Hierarchy
```
Agent Hierarchy:
└─ api_architect (Boss)
   └─ api_architect_employee_0
   └─ api_architect_employee_1
   └─ api_architect_employee_2
```

## Key Features Demonstrated

1. **Autonomous Code Generation**
   - Agents generate syntactically correct Python code
   - Automatic handling of imports and dependencies

2. **Task Decomposition**
   - Complex tasks broken into manageable subtasks
   - Intelligent planning before execution

3. **Hierarchical Execution**
   - Boss agents delegate to employee agents
   - Depth-limited to prevent infinite recursion

4. **Safe Execution**
   - Generated code runs in sandboxed subprocesses
   - Timeout protection and error handling

5. **Provider Flexibility**
   - Examples use Venice AI by default
   - Easy to switch to other providers via config

## Tips for Best Results

1. **Clear Task Descriptions**: The more specific your task description, the better the generated code.

2. **Appropriate Complexity**: Hydra excels at tasks that benefit from decomposition. Simple one-liners might not showcase its full potential.

3. **Monitor Logs**: Check `logs/agent_activity.log` for detailed execution traces.

4. **Experiment with Models**: Try different Venice models by setting `LLM_MODEL` in your `.env`:
   ```bash
   LLM_MODEL=qwen-2.5-coder-32b  # For code generation
   LLM_MODEL=llama-3.3-70b       # For general tasks
   ```

## Troubleshooting

- **API Key Issues**: Ensure your Venice API key is valid and has sufficient credits
- **Import Errors**: Make sure you're running from the Hydra root directory
- **Timeout Errors**: Complex tasks might need increased timeouts in `config/default.yaml`

## Next Steps

After exploring these examples:

1. Try modifying the task descriptions to generate different code
2. Experiment with different agent hierarchies
3. Create your own examples using Hydra's API
4. Integrate Hydra into your development workflow