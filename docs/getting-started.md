# Getting Started with Hydra

This guide gets you running with Hydra in 5 minutes.

## Installation

```bash
# Install with pipx (recommended)
pipx install git+https://github.com/privkeyio/hydra.git

# Or with pip
pip install git+https://github.com/privkeyio/hydra.git
```

## First Project

### 1. Set Provider

```bash
# For testing (no API needed)
export LLM_PROVIDER=mock

# For real projects
export LLM_PROVIDER=venice
export VENICE_API_KEY=your_key  # Get from venice.ai
```

### 2. Create Tickets

```bash
hydra ticket create "Build a todo list API with CRUD operations" --output tickets.yaml
```

This generates a `tickets.yaml` file:
```yaml
tickets:
  - id: "001"
    title: Setup project
    status: TODO
    acceptance_criteria:
      - Create project structure
      - Setup dependencies
```

### 3. Execute Tickets

```bash
# Single ticket
hydra ticket execute tickets.yaml 001

# All tickets in parallel
hydra ticket parallel tickets.yaml --workers 4
```

### 4. Verify Results

```bash
hydra ticket verify-parallel tickets.yaml
```

## Ticket Format

Tickets use YAML for structure and reliability:

```yaml
version: '1.0'
project:
  name: My Project
  description: Project description
  
tickets:
  - id: "001"
    title: Task title
    status: TODO        # TODO, IN_PROGRESS, DONE
    priority: 1         # Lower = higher priority
    model: balanced     # fast, balanced, smart
    description: Detailed description
    acceptance_criteria:
      - Specific requirement 1
      - Specific requirement 2
    dependencies: []    # List of ticket IDs
```

## Key Commands

| Command | Purpose |
|---------|---------|
| `hydra ticket create` | Generate tickets from description |
| `hydra ticket execute` | Run single ticket |
| `hydra ticket parallel` | Run multiple tickets |
| `hydra ticket verify-parallel` | Check acceptance criteria |
| `hydra dashboard start` | Launch monitoring UI |

## Providers

### Mock (Testing)
```bash
export LLM_PROVIDER=mock
```
No API needed, returns sample responses.

### Venice (Recommended)
```bash
export LLM_PROVIDER=venice
export VENICE_API_KEY=your_key
```
Access to open-source models like Qwen, Llama, etc.

### Claude
```bash
export LLM_PROVIDER=claude_tmux
export ANTHROPIC_API_KEY=your_key
```
Uses Claude via tmux sessions.

## Tips

1. **Start with mock**: Test your workflow without API costs
2. **Small tickets**: Break work into focused, testable pieces
3. **Clear criteria**: Specific acceptance criteria = better results
4. **Use dependencies**: Ensure correct execution order
5. **Review output**: Always check generated code

## Next Steps

- [CLI Commands Reference](cli-commands.md)
- [Ticket Creation Guide](ticket_creation_guide.md)
- [Provider Setup](providers/README.md)