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

**Requirements:** Python 3.11+, tmux, Redis (for distributed features)

#### Option 1: pipx (Recommended)
```bash
# Install pipx if not already installed
# Ubuntu/Debian: sudo apt install pipx
# macOS: brew install pipx
# Or: python3 -m pip install --user pipx

# Ensure pipx is in PATH
pipx ensurepath
# Restart terminal or: source ~/.bashrc

# Install Hydra
git clone https://github.com/username/hydra.git
cd hydra
pipx install .

# For development
pipx install -e .
```

#### Option 2: Virtual Environment
```bash
git clone https://github.com/username/hydra.git
cd hydra
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

#### Option 3: Direct pip install
```bash
git clone https://github.com/username/hydra.git
cd hydra
pip install -e .
```

### Basic Setup

```bash
# Choose your LLM provider (claude_tmux, venice, mock)
export LLM_PROVIDER=venice  # or claude_tmux

# For Claude provider
export CLAUDE_CLI_PATH=/path/to/claude
# OR
export ANTHROPIC_API_KEY=your_key

# For Venice provider (recommended for open-source models)
export VENICE_API_KEY=your_key  # Get from https://venice.ai
```

### Your First Project

```bash
# 1. Generate tickets from your idea
hydra ticket create "Build a REST API with authentication, database, and tests" --output tickets.yaml

# 2. Start the dashboard (auto-detects project)
hydra dashboard start

# 3. Execute tickets (dashboard auto-updates)
hydra ticket execute tickets.yaml 001

# 4. View real-time progress at http://localhost:8080
```

## Core Commands

### Single Task
```bash
hydra claude execute "Create a FastAPI service with JWT auth"
```

### Ticket Workflow
```bash
# Generate tickets
hydra ticket create "project description" --output tickets.yaml

# Execute single ticket
hydra ticket execute tickets.yaml 001

# Execute all tickets in parallel
hydra ticket parallel tickets.yaml --workers 4

# Execute allowing system modifications (for self-improvement)
hydra ticket parallel tickets.yaml --workers 3 --allow-system-modifications

# Verify parallel execution results
hydra ticket verify-parallel tickets.yaml --workers 2
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

```yaml
tickets:
  - id: "001"
    title: Setup API
    status: TODO
    priority: 1
    model: balanced
    description: Create FastAPI application with core structure
    acceptance_criteria:
      - Create main.py with FastAPI app
      - Add health check endpoint at /health
      - Setup global error handling middleware
      - Add CORS configuration
    dependencies: []
```

## Key Features

### 🚀 Performance Optimizations
- **uvloop** integration for 2-5x async performance boost
- **Connection pooling** with singleton patterns for Redis/HTTP
- **Smart batching** for parallel LLM requests
- **Response caching** with configurable TTL

### 🛡️ Safety & Quality
- **AI detection** to flag generated code patterns
- **Quality gates** with automatic linting and testing
- **Safety guards** blocking dangerous operations
- **Graceful shutdown** with proper cleanup sequence

### 📊 Dashboard & Monitoring

**Quick Start:**
```bash
hydra dashboard start  # Auto-detects project, runs at http://localhost:8080
hydra dashboard stop   # Stop the dashboard
```

**Features:**
- **Auto-detects project** - Uses project database when run from project directory
- **Real-time updates** - Status changes reflected within 5 seconds
- **Persistent** - Runs independently, survives hydra restarts
- **Token tracking** - Budget management and cost warnings
- **Cost reporting** with detailed breakdowns
- **Database backend** for persistence and queries

### 🔧 Enhanced Workflow
- **Smart ticket creation** with codebase analysis
- **Context sharing** between dependent tickets
- **.hydra directory** for organized project data
- **Modular CLI** with improved help and documentation

## Provider Support

- **Claude** (claude_tmux) - Interactive Claude Code CLI via tmux
- **Venice AI** (venice) - Production-ready with retry logic and streaming
- **Anthropic** (anthropic) - Direct API integration
- **OpenAI** (openai) - GPT-4 and GPT-3.5 support
- **Mock** (mock) - Testing and development provider

## Documentation

- 📚 **[Full Documentation](docs/)** - Complete reference and guides
- 🏗️ **[Architecture](docs/ARCHITECTURE.md)** - System design and components
- 🔧 **[API Reference](docs/API_REFERENCE.md)** - Python API and integration
- 💡 **[Examples](examples/)** - Real-world use cases

## Testing Commands

Try these to see Hydra in action:

```bash
# Build a complete web app
hydra ticket create "Build a todo app with React frontend and FastAPI backend" --output tickets.yaml
hydra ticket parallel tickets.yaml --workers 4

# Run quality checks on implementation
hydra quality 001 --strict

# Verify all work is complete
hydra ticket verify-parallel tickets.yaml --workers 2

# Check the dashboard
open http://localhost:8080

# Check the results
ls -la .hydra/reports/
cat tickets.yaml
```

## License

Proprietary software. All rights reserved.

---

Built for production. No compromises.

**HYDRA** - Orchestrating the future of autonomous development.
