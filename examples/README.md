# Hydra Examples

This directory contains example scripts demonstrating various Hydra capabilities.

## Examples

### 1. Venice Integration (`venice_example.py`)
Demonstrates using Hydra with Venice AI for code generation:
- Basic code generation
- Parallel task execution
- Monitored execution with guardrails
- Template-based project scaffolding
- Async workflows

**Requirements:**
- Set `VENICE_API_KEY` environment variable

**Run:**
```bash
export VENICE_API_KEY=your_key
python examples/venice_example.py
```

### 2. Claude Code Integration (`claude_code_example.py`)
Shows advanced Claude Code agent capabilities:
- Interactive sessions with persistent context
- Intelligent model routing (Opus vs Sonnet)
- Parallel agent execution
- Stateful project management with checkpoints
- Real-time monitoring dashboard

**Requirements:**
- Set `ANTHROPIC_API_KEY` environment variable
- Redis running (for parallel execution)

**Run:**
```bash
export ANTHROPIC_API_KEY=your_key
python examples/claude_code_example.py
```

## Key Features Demonstrated

### Production Safety
- Rate limiting per tenant
- Resource quotas and monitoring
- Cost budget enforcement
- Circuit breakers for failure handling

### Model Routing
- Automatic complexity analysis
- Smart routing to optimize costs
- Sonnet for simple tasks
- Opus for complex tasks

### State Management
- Project checkpointing
- Resume from interruption
- Operation history tracking
- State export/import

### Monitoring
- OpenTelemetry tracing
- Prometheus metrics
- Real-time dashboard
- Performance profiling

## Quick Start

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Set API keys:**
```bash
export VENICE_API_KEY=your_venice_key
# OR
export ANTHROPIC_API_KEY=your_anthropic_key
```

3. **Run examples:**
```bash
# Venice example
python examples/venice_example.py

# Claude Code example
python examples/claude_code_example.py
```

## Custom Examples

Create your own examples by importing Hydra modules:

```python
from hydra import CodeAgent, ProjectOrchestrator
from hydra.safety.guardrails import ProductionGuardrails

# Your code here
```

See the example files for detailed usage patterns.