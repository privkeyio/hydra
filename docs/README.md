# Hydra Documentation

Multi-agent orchestration system with pluggable LLM provider support.

## 📚 Documentation Index

### Core Documentation
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design
- **[API_REFERENCE.md](API_REFERENCE.md)** - Complete API documentation
- **[CLI Commands](cli-commands.md)** - Command-line interface reference

### Provider System
- **[Provider Configuration](providers/configuration.md)** - Setup LLM providers
- **[Provider Implementation](providers/implementation.md)** - Create custom providers

## 🚀 Quick Start

```bash
# Set your provider (claude_tmux, venice, mock)
export LLM_PROVIDER=claude_tmux

# Configure provider credentials
export CLAUDE_CLI_PATH=/path/to/claude  # For Claude
export VENICE_API_KEY=your_key         # For Venice

# Run a task
hydra claude execute "Create a Python function"

# Or use tickets for complex projects
hydra ticket create "Build a REST API"
hydra ticket parallel --workers 4
```

## 📦 Supported Providers

| Provider | Type | Description |
|----------|------|-------------|
| `claude_tmux` | Interactive | Claude Code CLI via tmux sessions |
| `venice` | API | Venice.ai API integration |
| `mock` | Testing | Development and testing provider |

## 🔧 Key Features

- **Provider Abstraction** - Switch between LLM providers without code changes
- **Parallel Execution** - Multiple agents working simultaneously
- **Smart Routing** - Automatic model selection based on task complexity
- **Error Recovery** - Fallback providers and retry mechanisms
- **Performance Monitoring** - Built-in profiling and optimization
- [Security Architecture](ARCHITECTURE.md#security-architecture)
- [Data Flow](ARCHITECTURE_DIAGRAMS.md#data-flow-sequence)

## 🔍 Key Concepts

### Agent System
The Hydra system uses a hierarchical agent structure where:
- **Boss Agent**: Root agent that receives initial tasks
- **Employee Agents**: Spawned by boss to handle subtasks
- **Sub-Employee Agents**: Second-level agents (max depth)

### Workflow Engine
Built on LangGraph, the workflow engine orchestrates:
- Task planning and decomposition
- Agent spawning and management
- Result aggregation

### Safety Mechanisms
- Recursion depth limit (max 2 levels)
- Sandboxed code execution
- Timeout protection (30 seconds)
- Comprehensive error handling

## 📝 Documentation Standards

When updating documentation:

1. **Keep diagrams updated** - Use ASCII art or Mermaid
2. **Include examples** - Show real usage patterns
3. **Version changes** - Note breaking changes
4. **Cross-reference** - Link between related docs

## 🚀 Getting Started

For first-time users:
```bash
# 1. Review system architecture
cat docs/ARCHITECTURE.md

# 2. Understand the API
cat docs/API_REFERENCE.md

# 3. See visual diagrams
cat docs/ARCHITECTURE_DIAGRAMS.md
```

## 📊 Documentation Coverage

| Component | Architecture | API Docs | Diagrams | Examples |
|-----------|-------------|----------|----------|----------|
| Agents    | ✅          | ✅       | ✅       | ✅       |
| Workflow  | ✅          | ✅       | ✅       | ✅       |
| CLI       | ✅          | ✅       | ✅       | ✅       |
| Config    | ✅          | ✅       | ✅       | ✅       |
| Security  | ✅          | ✅       | ✅       | ✅       |

---

**Note**: This is internal documentation for the Hydra project. All information is confidential and should not be shared outside the organization.