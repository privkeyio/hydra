# Project Hydra: Self-Replicating Coding Agent System

## Overview
This project implements a hierarchical AI agent system designed for in-house coding assistance. It enables a primary "boss" agent to decompose tasks, generate and execute code, and spawn "employee" agents that inherit the same capabilities. This creates a recursive structure for delegating workloads, such as code refactoring, function development, or testing.

The system uses Claude Code (via its Python SDK) for intelligent reasoning and code generation, powered by Anthropic's Claude models (Sonnet 4 for quick tasks, Opus 4 for complex ones). A fallback to the Venice API is available for open-source model alternatives.

Key principles: Modular design for easy extension, safeguards against recursion issues, and local execution for security.

## Features
- **Task Decomposition and Delegation**: Agents break down complex coding tasks and assign subtasks to spawned employees.
- **Code Generation and Execution**: Uses Claude Code to produce and run Python code in a sandboxed environment.
- **Hierarchy and Recursion**: Supports up to 2 levels of agent spawning with depth limits to prevent infinite loops.
- **Logging and Error Handling**: Tracks agent interactions, results, and retries on failures.
- **CLI Interface**: Simple command-line entry point for task input.
- **Fallback Integration**: Configurable switch to Venice API for alternative models.

## Requirements
- Python 3.12+
- Virtual environment (recommended)
- API keys for Claude Code (Anthropic) or Venice API

## Installation
1. Clone the repository:
   ```
   git clone <internal-repo-url>
   cd project-hydra
   ```

2. Set up a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
   (Dependencies include: langchain, langgraph, claude-code-sdk, python-dotenv. For fallback: openai)

4. Configure environment variables:
   - Create a `.env` file in the root directory.
   - Add your API key(s):
     ```
     ANTHROPIC_API_KEY=your_claude_code_key_here
     VENICE_API_KEY=your_venice_key_here  # Optional for fallback
     ```

## Usage
Run the system via the CLI in `main.py`. Provide a coding task as an argument.

Example:
```
python main.py "Refactor the following Python code into modular functions: def add(a, b): return a + b; def subtract(a, b): return a - b;"
```

- The boss agent will process the task, potentially spawning employees for subtasks.
- Output: Aggregated results (e.g., generated code, execution outputs) printed to console.
- Logs: Appended to `agent_log.txt` for review.

To switch to Venice API fallback (if needed), set a config flag in `config.py` (e.g., `USE_VENICE=True`).

## Configuration
- **Model Selection**: Defaults to Claude Sonnet 4; switch to Opus 4 for tasks in code (e.g., via SDK params).
- **Recursion Depth**: Hard-coded to max 2; adjust in `CodeAgent` class if needed.
- **Sandboxing**: Uses `subprocess` for isolation; ensure no sensitive data in execution paths.

## Development and Maintenance
- **Project Structure**:
  - `code_agent.py`: Core `CodeAgent` class.
  - `workflow.py`: LangGraph workflow definition.
  - `main.py`: CLI entry point.
  - `utils.py`: Logging, safeguards, and helpers.
- **Testing**: Run `pytest` for unit and integration tests.
- **Extending**: Add new nodes to LangGraph for features like external tool integration.
- For in-house contributions, follow internal Git workflow and review processes.

## Troubleshooting
- API Errors: Verify keys in `.env` and check Anthropic/Venice quotas.
- Recursion Issues: If depth exceeded, task will raise an error—simplify input tasks.
- Execution Failures: Sandbox logs errors; retries are automatic.

This system is for internal use only. Contact the development team for support or enhancements.