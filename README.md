# Hydra: Production-Ready AI Code Generation Platform

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Claude Code Integration](https://img.shields.io/badge/claude-code-purple.svg)]()

## Overview

Hydra is an enterprise-grade platform for autonomous code generation with Claude Code-like capabilities. It orchestrates multiple AI agents in parallel, intelligently routes tasks between models, and provides production safety guardrails.

## Key Features

- **Parallel Agent Execution**: Run up to 10 concurrent agents with intelligent task orchestration
- **Multi-Model Support**: Venice, Anthropic Claude (Opus/Sonnet), OpenAI, and Claude CLI
- **Smart Model Routing**: Automatically routes simple tasks to Sonnet, complex to Opus for cost optimization
- **Production Safety**: Rate limiting, resource quotas, circuit breakers, and sandboxed execution
- **State Persistence**: Resume interrupted work with checkpoint-based state management
- **Real-time Monitoring**: OpenTelemetry tracing, Prometheus metrics, and live dashboard
- **Template System**: 12+ project templates for instant scaffolding
- **Task Specification DSL**: Define complex workflows in YAML/JSON

## Quick Start

### Prerequisites

- Python 3.11+
- Redis (for task queue)
- API keys for your chosen provider

### Installation

```bash
# Clone and setup
git clone <repo-url>
cd hydra
pip install -r requirements.txt
pip install -e .

# Configure API keys
export VENICE_API_KEY=your_key  # or ANTHROPIC_API_KEY
```

### Basic Usage

```bash
# Simple code generation
hydra "Create a REST API with FastAPI"

# Use specific model
hydra "Complex refactoring task" --model opus

# Generate from template
hydra template create --template fastapi_rest_api --name my_api
```

### Python API

```python
from hydra import ProductionGuardrails, ProjectOrchestrator
from hydra.specifications import TaskSpec

# Initialize with safety guardrails
guardrails = ProductionGuardrails()
guardrails.register_tenant("my_app")

# Create project orchestrator
orchestrator = ProjectOrchestrator()

# Define task specification
spec = TaskSpec.from_yaml("project.yaml")

# Execute with monitoring
with guardrails.protected_execution("my_app", "build_api"):
    results = orchestrator.execute_project(spec)
```

## Architecture

```
┌─────────────────────────────────────┐
│     Project Orchestrator            │
├─────────────────────────────────────┤
│  Model Router │ Task Scheduler      │
├───────────────┼─────────────────────┤
│  Claude Opus  │  Claude Sonnet      │
├───────────────┴─────────────────────┤
│     Production Guardrails           │
│  • Rate Limiting  • Cost Control    │
│  • Resource Quotas • Circuit Break  │
├─────────────────────────────────────┤
│   Monitoring & Observability        │
│  • OpenTelemetry • Prometheus       │
│  • Real-time Dashboard              │
└─────────────────────────────────────┘
```

## Project Structure

```
hydra/
├── src/hydra/
│   ├── orchestrator/       # Project orchestration
│   ├── agents/            # Claude Code agent wrapper
│   ├── routing/           # Model selection logic
│   ├── safety/            # Production guardrails
│   ├── state/             # Persistence layer
│   ├── monitoring/        # Observability
│   └── templates/         # Project templates
├── examples/              # Usage examples
└── tests/                # Test suite
```

## Configuration

Create `config/default.yaml`:

```yaml
llm:
  provider: venice  # or anthropic, openai, claude_cli
  model_routing:
    enabled: true
    simple_tasks: claude-3-sonnet
    complex_tasks: claude-3-opus

safety:
  rate_limit:
    requests_per_minute: 60
  resource_quota:
    memory_mb: 2048
    cpu_percent: 80
  cost_budget:
    daily_limit_usd: 100

monitoring:
  jaeger_endpoint: localhost:14268
  prometheus_port: 9090
```

## Examples

See the `examples/` directory for:
- Venice API integration
- Claude Code agent usage
- Complex project orchestration
- Template customization

## Testing

```bash
# Run all tests
pytest tests/

# Unit tests only
pytest tests/unit/

# With coverage
pytest --cov=hydra --cov-report=html
```

## License

Internal use only. Proprietary and confidential.