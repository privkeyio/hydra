# 🐉 HYDRA

**Multi-headed AI orchestration for autonomous code generation**

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

Hydra orchestrates Claude Code CLI and other AI models to autonomously build production software. Execute complex development workflows with parallel agents, automatic verification, and real-time monitoring.

### 🚀 Core Capabilities

**Claude Code Orchestration**
- Direct integration with Claude Code CLI through tmux
- Session persistence and state management
- Automatic file operation handling

**Parallel Ticket Execution**
- Dependency-aware task scheduling
- Concurrent agent execution
- Wave-based workflow optimization

**Automatic Quality Assurance**
- Acceptance criteria verification
- Multi-language quality gates
- Production safety guardrails

**Real-time Monitoring**
- Live web dashboard at `localhost:8080`
- Server-sent events for instant updates
- Session state persistence

---

## Quick Start

### Installation

```bash
git clone https://github.com/privkeyio/hydra.git
cd hydra
pip install -e .
```

### Configure Claude

```bash
export CLAUDE_CLI_PATH=/path/to/claude
# or
export ANTHROPIC_API_KEY=your_key
```

### Execute Your First Task

```bash
# Single task
hydra claude execute "Build a FastAPI service with auth"

# Ticket-based workflow
hydra ticket create "Build a complete web application"
hydra ticket parallel --workers 4
```

---

## Ticket Workflow

Hydra's ticket system enables complex project execution:

### 1. Generate Tickets

```bash
hydra ticket create "Build a P2P chat application with encryption"
```

Creates `tickets.md` with dependency-aware tasks:

```markdown
## Ticket 001: Initialize project structure
**Model:** Sonnet 4
**Dependencies:** None

## Ticket 002: Implement encryption module  
**Model:** Opus 4
**Dependencies:** 001

## Ticket 003: Build networking layer
**Model:** Opus 4
**Dependencies:** 001, 002
```

### 2. Execute with Dashboard

```bash
hydra ticket parallel --workers 3
```

Opens real-time dashboard showing:
- Progress visualization
- Wave execution status  
- Per-ticket metrics
- Quality gate results

### 3. Automatic Verification

Each ticket undergoes:
- Acceptance criteria validation
- Quality gate checks (lint, test, build)
- Dependency verification
- State persistence

---

## CLI Commands

### Ticket Operations

```bash
# Create tickets from description
hydra ticket create "Project description"

# Execute single ticket
hydra ticket execute 001

# Parallel execution with dashboard
hydra ticket parallel --workers 4

# Verify completion
hydra ticket verify 001

# Run quality gates
hydra ticket quality 001
```

### Claude Code Orchestration

```bash
# Direct task execution
hydra claude execute "Task description" --timeout 300

# Session management
hydra claude session /path/to/project
hydra claude list
hydra claude attach session_name
hydra claude kill session_name

# State persistence
hydra claude save session_name
hydra claude restore session_name
```

### Template Operations

```bash
# List available templates
hydra template list

# Create from template
hydra template create fastapi_app ./my-app
```

---

## Python API

```python
from hydra.parallel import ParallelExecutor
from hydra.dashboard import DashboardServer

# Initialize with dashboard
dashboard = DashboardServer()
dashboard.start()

# Execute tickets in parallel
executor = ParallelExecutor(max_workers=4)
tickets = executor.load_tickets("tickets.md")
plan = executor.build_execution_plan()
results = executor.execute_plan(plan, "tickets.md")
```

---

## Architecture

```
┌──────────────────────────────────────────┐
│            HYDRA ORCHESTRATOR            │
├──────────────────────────────────────────┤
│                                          │
│  ┌────────────┐      ┌────────────┐     │
│  │   Claude   │      │  Parallel  │     │
│  │   Code     │◄────►│  Executor  │     │
│  │   (tmux)   │      │            │     │
│  └────────────┘      └────────────┘     │
│         ▲                   ▲            │
│         │                   │            │
│  ┌────────────┐      ┌────────────┐     │
│  │  Session   │      │  Dashboard │     │
│  │ Persistence│      │   Server   │     │
│  └────────────┘      └────────────┘     │
│         ▲                   ▲            │
│         │                   │            │
│  ┌────────────┐      ┌────────────┐     │
│  │  Quality   │      │   Ticket   │     │
│  │   Gates    │      │  Verifier  │     │
│  └────────────┘      └────────────┘     │
│                                          │
└──────────────────────────────────────────┘
```

---

## Features

### 🎯 Ticket Verification
- Pattern-based acceptance criteria checking
- File existence validation
- Function/endpoint detection
- Automatic completion tracking

### 💾 Session Persistence
- Save/restore Claude Code sessions
- File snapshot preservation
- Task history tracking
- State serialization

### 🚦 Quality Gates
- Language-specific tool detection
- Automatic lint/test/build execution
- Python: ruff, pytest, mypy
- JavaScript: eslint, jest, bun test
- Rust: cargo check, clippy, test
- Go: go vet, test, build

### ⚡ Parallel Execution
- Dependency graph resolution
- Wave-based scheduling
- Concurrent agent management
- Resource pool optimization

### 📊 Progress Dashboard
- Real-time execution monitoring
- Server-sent events streaming
- Ticket status visualization
- Wave progress tracking

---

## Configuration

### Environment Variables

```bash
# LLM Provider
export LLM_PROVIDER=claude_tmux  # or venice, anthropic, openai
export CLAUDE_CLI_PATH=/home/user/.claude/local/claude

# Timeouts and Limits
export LLM_TIMEOUT=300
export MAX_WORKERS=4

# Dashboard
export DASHBOARD_PORT=8080
```

### Project Configuration

Create `CLAUDE.md` in your project:

```markdown
## Project Context
Node.js application using Hyperswarm

## Quality Commands
- Lint: bun run lint
- Test: bun test
- Build: bun run build

## Conventions
- Use TypeScript
- Functional programming style
- No console.log in production
```

---

## Development

### Testing

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/

# With coverage
pytest --cov=hydra --cov-report=html
```

### Linting

```bash
ruff check src/
ruff format src/
```

---

## Examples

### Build Complete Application

```bash
# Generate tickets for full-stack app
hydra ticket create "Build a real-time collaborative editor with React frontend, 
FastAPI backend, WebSocket sync, and PostgreSQL storage"

# Execute with 4 parallel workers
hydra ticket parallel --workers 4

# Monitor at http://localhost:8080
```

### Complex Refactoring

```bash
# Direct Claude Code execution
hydra claude execute "Refactor the entire codebase to use async/await 
patterns, add comprehensive error handling, and implement retry logic 
for all external API calls" --timeout 600
```

---

## License

Proprietary. Internal use only.

---

Built with precision. No shortcuts. Production ready.

**HYDRA** - When one head isn't enough.