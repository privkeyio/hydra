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

## Overview

Hydra orchestrates multiple AI agents to build production software autonomously. It manages parallel execution, dependency resolution, quality gates, and real-time monitoring while maintaining complete control over the development process.

### Core Architecture

**Parallel Execution Engine**
- Concurrent agent management with ThreadPoolExecutor
- Wave-based execution respecting dependencies
- Dynamic resource allocation and pooling
- File lock management prevents conflicts

**Claude Code Integration**
- Direct tmux session control
- Automatic prompt handling and responses
- Session persistence and recovery
- File operation automation

**Quality Assurance**
- Acceptance criteria verification
- Language-specific quality gates
- Production safety guardrails
- Automatic rollback on failure

**Real-time Monitoring**
- Live dashboard at localhost:8080
- Server-sent events for instant updates
- Execution metrics and performance tracking
- Session state visualization

---

## Installation

```bash
git clone https://github.com/username/hydra.git
cd hydra
pip install -e .
```

### Requirements

- Python 3.11+
- tmux (for Claude Code orchestration)
- Claude CLI or Anthropic API key

### Configuration

```bash
# Claude CLI path
export CLAUDE_CLI_PATH=/path/to/claude

# Or use API key
export ANTHROPIC_API_KEY=your_key

# Optional configurations
export LLM_TIMEOUT=300          # Task timeout in seconds
export MAX_WORKERS=4            # Parallel agent limit
export DASHBOARD_PORT=8080      # Dashboard port
```

---

## Quick Start

### Single Task Execution

```bash
hydra claude execute "Create a FastAPI service with JWT authentication, 
rate limiting, and PostgreSQL integration"
```

### Ticket-Based Development

Generate tickets from project description:

```bash
hydra ticket create "Build a real-time collaborative code editor with 
WebSocket sync, conflict resolution, and syntax highlighting"
```

Execute with parallel agents:

```bash
hydra ticket parallel --workers 4
```

Monitor progress at http://localhost:8080

---

## Ticket System

Hydra uses a ticket-based workflow for complex projects. Each ticket represents an atomic unit of work with dependencies, model selection, and acceptance criteria.

### Ticket Structure

```markdown
## Ticket 001: Initialize project structure
**Model:** Sonnet 4
**Dependencies:** None
**Description:** Create base project with TypeScript, ESLint, and testing

**Acceptance Criteria:**
- [ ] Package.json with required dependencies
- [ ] TypeScript configuration
- [ ] ESLint and Prettier setup
- [ ] Jest testing framework configured

## Ticket 002: Implement WebSocket server
**Model:** Opus 4
**Dependencies:** 001
**Description:** Build WebSocket server with room management

**Acceptance Criteria:**
- [ ] WebSocket server on port 8080
- [ ] Room creation and joining logic
- [ ] Client connection handling
- [ ] Automatic reconnection support
```

### Execution Modes

**Sequential Execution**
```bash
hydra ticket execute 001
hydra ticket execute 002
```

**Parallel Execution**
```bash
hydra ticket parallel --workers 3
```

**Automatic Workflow**
```bash
hydra ticket auto --parallel 4
```

---

## CLI Reference

### Ticket Operations

```bash
# Generate tickets from description
hydra ticket create "project description"

# Execute single ticket
hydra ticket execute 001 --tickets custom.md

# Parallel execution with monitoring
hydra ticket parallel --workers 4 --save-log

# Verify ticket completion
hydra ticket verify 001

# Run quality gates
hydra ticket quality 001 --save
```

### Claude Code Management

```bash
# Direct execution
hydra claude execute "task" --timeout 600 --cwd /project

# Session management
hydra claude session /path/to/project --name dev_session
hydra claude list
hydra claude attach dev_session
hydra claude kill dev_session

# State persistence
hydra claude save dev_session
hydra claude restore dev_session
```

### Template System

```bash
# List available templates
hydra template list

# Create from template
hydra template create fastapi_service ./my-service \
  --param project_name=MyService \
  --param port=8000

# Validate templates
hydra template validate
```

---

## Python API

### Basic Usage

```python
from hydra.parallel import ParallelExecutor
from hydra.orchestrator import ClaudeCodeOrchestrator

# Initialize executor
executor = ParallelExecutor(max_workers=4)

# Load and execute tickets
tickets = executor.load_tickets("tickets.md")
plan = executor.build_execution_plan()
results = executor.execute_plan(plan, "tickets.md")

# Generate report
report = executor.generate_report(results)
print(report)
```

### Advanced Integration

```python
from hydra.agents.pool import AgentPool
from hydra.safety.file_lock import FileLockManager
from hydra.monitoring import MonitoringService

# Agent pool management
pool = AgentPool(max_agents=6, idle_timeout=300)
pool.start()
agent_id = pool.spawn_agent("task_001")

# File locking for concurrent operations
lock_manager = FileLockManager()
if lock_manager.acquire_lock("src/main.py", agent_id):
    # Safe to modify file
    pass
lock_manager.release_lock("src/main.py", agent_id)

# Real-time monitoring
monitor = MonitoringService()
monitor.track_execution("task_001", metrics)
```

---

## Architecture

### Execution Flow

```
┌─────────────────────────────────────┐
│         CLI Entry Point             │
│    (hydra ticket parallel)          │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│      ParallelExecutor               │
│   - Dependency resolution           │
│   - Wave-based scheduling           │
│   - Resource allocation             │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│         AgentPool                   │
│   - Session lifecycle               │
│   - Health checking                 │
│   - Dynamic scaling                 │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│     ClaudeTmuxProvider              │
│   - Terminal multiplexing           │
│   - Interactive sessions            │
│   - Prompt automation               │
└─────────────────────────────────────┘
```

### Component Overview

**Parallel Executor**
- Topological sort for dependency resolution
- Wave-based execution planning
- Thread pool management
- Progress tracking and reporting

**Agent Pool**
- Dynamic agent spawning and termination
- Session reuse and health monitoring
- Automatic cleanup of idle agents
- Resource limit enforcement

**File Lock Manager**
- Thread-safe file access control
- Deadlock detection and prevention
- Timeout-based lock acquisition
- Automatic cleanup on agent termination

**Quality Gates**
- Language detection and tool selection
- Automatic execution of lint/test/build
- Configurable pass/fail criteria
- Report generation and persistence

---

## Performance

### Concurrency Metrics

| Configuration | Agents | Tickets | Time | Efficiency |
|--------------|--------|---------|------|------------|
| Sequential | 1 | 10 | 600s | 100% |
| Parallel-3 | 3 | 10 | 220s | 91% |
| Parallel-5 | 5 | 10 | 140s | 86% |
| Parallel-8 | 8 | 10 | 95s | 79% |

### Optimization Strategies

**Session Pooling**
- Pre-warmed sessions reduce startup from 30s to <1s
- Connection reuse eliminates overhead
- Health checking ensures reliability

**Intelligent Scheduling**
- Dependency-aware task distribution
- Work stealing for load balancing
- Resource prediction and allocation

**File Conflict Resolution**
- Predictive locking based on task analysis
- Compatible change detection
- Automatic conflict resolution

---

## Configuration

### Project Configuration

Create `CLAUDE.md` in your project root:

```markdown
## Project Context
Node.js microservices with TypeScript

## Quality Commands
- Lint: npm run lint
- Test: npm test
- Build: npm run build

## Conventions
- Functional programming patterns
- Error-first callbacks
- Comprehensive JSDoc comments
```

### Environment Variables

```bash
# Provider selection
export LLM_PROVIDER=claude_tmux    # or anthropic, openai
export CLAUDE_CLI_PATH=/usr/local/bin/claude

# Performance tuning
export MAX_WORKERS=6
export LLM_TIMEOUT=300
export SESSION_POOL_SIZE=5
export IDLE_TIMEOUT=180

# Dashboard configuration
export DASHBOARD_PORT=8080
export DASHBOARD_HOST=0.0.0.0

# Safety settings
export ALLOW_GIT_OPERATIONS=false
export SANDBOX_MODE=true
export MAX_FILE_SIZE=10485760
```

---

## Development

### Testing

```bash
# Unit tests with coverage
pytest tests/unit/ --cov=hydra --cov-report=html

# Integration tests
pytest tests/integration/

# Parallel execution tests
pytest tests/test_parallel.py -v

# Performance benchmarks
python benchmarks/concurrency.py
```

### Code Quality

```bash
# Format code
ruff format src/

# Lint with autofix
ruff check --fix src/

# Type checking
mypy src/hydra --strict

# Security scan
bandit -r src/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

---

## Examples

### Build Full-Stack Application

```bash
# Generate comprehensive tickets
hydra ticket create "Build a SaaS platform with Next.js frontend, 
FastAPI backend, PostgreSQL database, Redis caching, 
Stripe payments, and AWS deployment"

# Execute with maximum parallelism
hydra ticket parallel --workers 8

# Monitor dashboard
open http://localhost:8080
```

### Complex Refactoring

```bash
# Large-scale refactoring
hydra claude execute "Refactor the entire codebase to use 
async/await patterns, add comprehensive error handling, 
implement retry logic with exponential backoff, 
and add distributed tracing" --timeout 900
```

### Microservices Development

```bash
# Generate microservices architecture
hydra ticket create "Create microservices: 
- Auth service with JWT and OAuth2
- User service with profile management  
- Payment service with Stripe integration
- Notification service with email/SMS
- API gateway with rate limiting"

# Deploy parallel development
hydra ticket auto --parallel 5 --dir ./microservices
```

---

## Troubleshooting

### Common Issues

**Claude CLI not found**
```bash
export CLAUDE_CLI_PATH=$(which claude)
```

**tmux not installed**
```bash
# Ubuntu/Debian
sudo apt-get install tmux

# macOS
brew install tmux
```

**Session timeout**
```bash
export LLM_TIMEOUT=600  # Increase timeout
```

**Agent pool exhausted**
```bash
export MAX_WORKERS=8  # Increase pool size
```

### Debug Mode

```bash
# Enable verbose logging
export HYDRA_DEBUG=1

# Check agent status
hydra claude list

# View execution logs
tail -f .hydra/logs/execution.log
```

---

## License

Proprietary software. All rights reserved.

---

Built for production. No compromises.

**HYDRA** - Orchestrating the future of autonomous development.