<div align="center">
  <img src="assets/hydra-logo.png" alt="Hydra Logo" width="200" height="200">
  
  # HYDRA
  
  **Multi-agent orchestration system for autonomous software development**
</div>

```
╦ ╦╦ ╦╔╦╗╦═╗╔═╗
╠═╣╚╦╝ ║║╠╦╝╠═╣
╩ ╩ ╩ ═╩╝╩╚═╩ ╩
```

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Claude](https://img.shields.io/badge/claude-opus%204.1-purple.svg)]()
[![Production Ready](https://img.shields.io/badge/production-ready-green.svg)]()

---

## What is Hydra?

Hydra orchestrates multiple AI agents to build production software in parallel. Give it a project description, and it creates tickets that agents work on simultaneously - respecting dependencies, preventing conflicts, and ensuring quality.

## Quick Start

### Installation

```bash
git clone https://github.com/username/hydra.git
cd hydra
pip install -e .
```

**Requirements:** Python 3.11+, tmux, Claude CLI

### Basic Setup

```bash
# Set Claude CLI path
export CLAUDE_CLI_PATH=/path/to/claude

# Or use API key
export ANTHROPIC_API_KEY=your_key
```

### Your First Project

```bash
# 1. Generate tickets from your idea
hydra ticket create "Build a REST API with authentication, database, and tests"

# 2. Execute with parallel agents
hydra ticket parallel --workers 4

# 3. Monitor progress
open http://localhost:8080
```

## Core Commands

### Single Task
```bash
hydra claude execute "Create a FastAPI service with JWT auth"
```

### Ticket Workflow
```bash
# Generate tickets
hydra ticket create "project description"

# Execute in parallel
hydra ticket parallel --workers 4

# Verify and fix incomplete work
hydra ticket verify-parallel --workers 4
```

### Session Management
```bash
hydra claude session /project --name dev
hydra claude list
hydra claude attach dev
```

## How It Works

1. **Create Tickets**: Break down your project into atomic tasks with dependencies
2. **Parallel Execution**: Multiple agents work simultaneously on different tickets
3. **Smart Coordination**: Dependency resolution, file locking, conflict prevention
4. **Quality Gates**: Automatic testing, linting, and verification
5. **Live Monitoring**: Real-time dashboard shows progress and logs

## Example Ticket

```markdown
## Ticket 001: Setup API
**Model:** sonnet
**Dependencies:** None
**Description:** Create FastAPI application

**Acceptance Criteria:**
- [ ] Create main.py with FastAPI app
- [ ] Add health check endpoint
- [ ] Setup error handling
```

## Documentation

- 📚 **[Full Documentation](docs/)** - Complete reference and guides
- 🏗️ **[Architecture](docs/ARCHITECTURE.md)** - System design and components
- 🔧 **[API Reference](docs/API_REFERENCE.md)** - Python API and integration
- 💡 **[Examples](examples/)** - Real-world use cases

## Testing Commands

Try these to see Hydra in action:

```bash
# Build a complete web app
hydra ticket create "Build a todo app with React frontend and FastAPI backend"
hydra ticket parallel --workers 4

# Verify all work is complete
hydra ticket verify-parallel --workers 4

# Check the results
ls -la
cat tickets.md
```

## License

Proprietary software. All rights reserved.

---

Built for production. No compromises.

**HYDRA** - Orchestrating the future of autonomous development.
