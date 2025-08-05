# Project Hydra: Self-Replicating Coding Agent System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Internal Project](https://img.shields.io/badge/status-internal-red.svg)]()

## Overview

Hydra is a production-grade hierarchical AI agent system designed for autonomous code generation and task delegation. It enables a primary "boss" agent to decompose complex coding tasks, generate and execute code, and spawn "employee" agents that inherit the same capabilities, creating a recursive structure for handling sophisticated software development workflows.

## Key Features

- 🤖 **Hierarchical Agent Architecture**: Multi-level agent spawning with parent-child relationships
- 🧠 **Intelligent Task Decomposition**: Automatic breaking down of complex tasks into manageable subtasks
- 💻 **Autonomous Code Generation**: AI-powered code creation using Claude/Anthropic models
- 🔒 **Sandboxed Execution**: Safe code execution in isolated subprocess environments
- 📊 **Comprehensive Logging**: Detailed activity tracking with automatic log rotation
- 🔄 **Retry Logic**: Automatic retry on failures with configurable attempts
- 🛡️ **Safety Guards**: Built-in recursion limits and timeout protection
- 🔌 **Extensible Design**: Modular architecture for easy feature additions

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Virtual environment (recommended)
- Anthropic API key

### Installation

1. **Clone the repository:**
```bash
git clone <internal-repo-url>
cd hydra
```

2. **Run the setup script:**
```bash
./scripts/setup.sh
```

3. **Configure your API keys:**
```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

4. **Verify installation:**
```bash
source venv/bin/activate
make test
```

## Usage

### Command Line Interface

```bash
# Basic usage
hydra "Create a function to calculate fibonacci numbers"

# Multi-line input via stdin
echo "Create two functions:
1. add(a, b) that returns sum
2. subtract(a, b) that returns difference" | hydra

# JSON output format
hydra "Refactor this code" --json

# Custom agent name
hydra "Build a calculator" --agent-name "architect"

# Specify starting depth
hydra "Complex task" --depth 1
```

### Python API

```python
from hydra import CodeAgent, execute_workflow

# Create an agent
agent = CodeAgent("developer")

# Execute a task
results = execute_workflow(
    task="Create a REST API endpoint",
    agent_name="boss",
    depth=0
)
```

## Project Structure

```
hydra/
├── src/hydra/              # Main package source code
│   ├── agents/             # Agent implementations
│   ├── workflows/          # Workflow engine (LangGraph)
│   ├── utils/              # Utility modules
│   └── cli.py              # CLI entry point
├── tests/                  # Test suite
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests
├── config/                 # Configuration files
├── docs/                   # Documentation
├── scripts/                # Utility scripts
├── Makefile               # Development commands
└── pyproject.toml         # Project configuration
```

## Development

### Setting Up Development Environment

```bash
# Install development dependencies
make install-dev

# Run tests
make test

# Run linting
make lint

# Format code
make format

# Build package
make build
```

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# Integration tests only
make test-int

# With coverage report
pytest --cov=hydra --cov-report=html
```

### Code Quality

The project uses:
- **Black** for code formatting
- **Flake8** and **Ruff** for linting
- **MyPy** for type checking
- **Pre-commit** hooks for automated checks

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your_api_key_here
USE_VENICE=false
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### Configuration File

Edit `config/default.yaml` for system-wide settings:

```yaml
agent:
  max_depth: 2
  timeout: 30
  retry_attempts: 2

models:
  primary:
    provider: "anthropic"
    model: "claude-3-5-sonnet-20241022"
```

## Architecture

### Agent Hierarchy
```
Boss Agent (depth 0)
├── Employee 1 (depth 1)
│   ├── Sub-employee 1.1 (depth 2)
│   └── Sub-employee 1.2 (depth 2)
└── Employee 2 (depth 1)
    └── Sub-employee 2.1 (depth 2)
```

### Workflow Engine

Built on LangGraph for stateful workflow management:
- **Plan Node**: Task decomposition and strategy
- **Spawn Node**: Employee agent creation
- **Aggregate Node**: Result collection and synthesis

## Safety & Security

- **Recursion Limit**: Hard limit of 2 levels to prevent infinite loops
- **Execution Timeout**: 30-second timeout for code execution
- **Sandboxed Environment**: Subprocess isolation for generated code
- **Input Validation**: AST parsing before execution
- **Comprehensive Logging**: Full audit trail of all operations

## Troubleshooting

### Common Issues

1. **API Key Errors**
   - Verify `.env` file exists and contains valid keys
   - Check API quota and rate limits

2. **Import Errors**
   - Ensure virtual environment is activated
   - Run `pip install -e .` to install in development mode

3. **Recursion Limit Exceeded**
   - Simplify input tasks
   - Check max_depth configuration

### Debug Mode

Enable detailed logging:
```bash
export LOG_LEVEL=DEBUG
hydra "Your task"
```

## Internal Development

This is an internal project. For modifications:
1. Create a feature branch
2. Make changes with tests
3. Request code review from team lead
4. Merge after approval

## Support

For internal support:
- Open an issue on GitHub
- Contact the development team
- Check documentation in `/docs`

---

**⚠️ INTERNAL USE ONLY**: This tool is proprietary and confidential. Do not share outside the organization. Follow company security guidelines when handling API keys and sensitive data.