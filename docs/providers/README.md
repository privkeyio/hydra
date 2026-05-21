# Provider Documentation

## Quick Setup

### Claude Provider
```bash
export LLM_PROVIDER=claude_tmux
export CLAUDE_CLI_PATH=/path/to/claude
# OR
export ANTHROPIC_API_KEY=your_key
```

### Venice Provider
```bash
export LLM_PROVIDER=venice
export VENICE_API_KEY=your_key
```

### NEAR AI Cloud Provider
```bash
export LLM_PROVIDER=nearai
export NEARAI_API_KEY=your_key
```

### Mock Provider (Testing)
```bash
export LLM_PROVIDER=mock
```

## Configuration

See [configuration.md](configuration.md) for detailed setup.

## Custom Providers

See [implementation.md](implementation.md) to create your own provider.
