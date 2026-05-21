# Provider Configuration Guide

## Overview

Hydra supports multiple LLM providers through a flexible provider abstraction layer. This guide covers how to configure and use different providers in your Hydra setup.

## Supported Providers

Hydra currently supports the following providers:

- **Claude (Tmux)** - Interactive Claude Code CLI sessions via tmux
- **NEAR AI Cloud** - OpenAI-compatible TEE inference
- **Venice AI** - API-based access to various open-source models
- **Mock Provider** - For testing and development

## Configuration Methods

### 1. Environment Variables

The simplest way to configure a provider is through environment variables:

```bash
# Select the provider
export LLM_PROVIDER=claude_tmux  # Options: claude_tmux, nearai, venice, mock

# Provider-specific configuration
export CLAUDE_CLI_PATH=/path/to/claude  # For Claude provider
export NEARAI_API_KEY=your_api_key      # For NEAR AI Cloud provider
export VENICE_API_KEY=your_api_key      # For Venice provider

# Optional settings
export LLM_TIMEOUT=300    # Request timeout in seconds
export LLM_MAX_RETRIES=3  # Number of retries on failure
```

### 2. Configuration Files

For more complex setups, you can use configuration files:

#### `~/.hydra/config.yaml`

```yaml
provider:
  default: claude
  fallback: [venice, mock]

providers:
  claude:
    type: claude_tmux
    cli_path: ${CLAUDE_CLI_PATH:-claude}
    default_model: opus
    models:
      opus: claude-opus-4-1-20250805
      sonnet: claude-sonnet-4-20250514
      haiku: claude-3-haiku-20240307
    tmux:
      session_prefix: hydra_claude
      capture_method: pane
    features:
      interactive: true
      streaming: true
      file_safety: true
      
  venice:
    type: venice_api
    api_key: ${VENICE_API_KEY}
    base_url: https://api.venice.ai/v1
    default_model: llama-3.1-70b
    models:
      fast: llama-3.1-8b
      balanced: llama-3.1-70b
      smart: llama-3.1-405b
    features:
      interactive: false
      streaming: true
      file_safety: false

  nearai:
    type: nearai
    api_key: ${NEARAI_API_KEY}
    base_url: https://cloud-api.near.ai/v1
    default_model: zai-org/GLM-5.1-FP8
    models:
      fast: Qwen/Qwen3.6-35B-A3B-FP8
      balanced: zai-org/GLM-5.1-FP8
      smart: Qwen/Qwen3.5-122B-A10B
    features:
      interactive: false
      streaming: true
      file_safety: false
      
  mock:
    type: mock
    default_model: test
    response_delay: 0.1
    features:
      interactive: false
      streaming: false
      file_safety: true
```

### 3. Programmatic Configuration

You can also configure providers programmatically:

```python
from hydra.providers import ProviderFactory, ProviderConfig

# Configure a provider
config = ProviderConfig(
    provider_type="venice",
    api_key="your_api_key",
    model="llama-3.1-70b",
    timeout=300
)

# Create provider instance
provider = ProviderFactory.create(config)

# Use the provider
response = provider.generate("Write a Python function to calculate factorial")
```

## Provider-Specific Configuration

### Claude Provider

The Claude provider uses the Claude Code CLI through tmux sessions for interactive capabilities.

#### Requirements

- Claude Code CLI installed and accessible
- tmux installed on the system
- Valid Claude account/credentials

#### Configuration Options

| Option | Environment Variable | Description | Default |
|--------|---------------------|-------------|---------|
| cli_path | CLAUDE_CLI_PATH | Path to Claude CLI executable | `claude` |
| model | LLM_MODEL | Model to use (opus/sonnet/haiku) | `opus` |
| session_prefix | - | Tmux session name prefix | `hydra_claude` |
| capture_method | - | How to capture output (pane/pipe) | `pane` |
| timeout | LLM_TIMEOUT | Command timeout in seconds | `300` |

#### Example Setup

```bash
# Install Claude CLI
curl -fsSL https://claude.ai/install.sh | sh

# Set up environment
export LLM_PROVIDER=claude
export CLAUDE_CLI_PATH=~/.local/bin/claude
export LLM_MODEL=opus

# Verify configuration
hydra config verify
```

### Venice Provider

The Venice provider connects to Venice AI's API for accessing various open-source models.

#### Requirements

- Venice API key
- Internet connection
- Python requests library

#### Configuration Options

| Option | Environment Variable | Description | Default |
|--------|---------------------|-------------|---------|
| api_key | VENICE_API_KEY | Venice API key | Required |
| base_url | VENICE_BASE_URL | API endpoint URL | `https://api.venice.ai/v1` |
| model | LLM_MODEL | Model identifier | `llama-3.1-70b` |
| timeout | LLM_TIMEOUT | Request timeout | `300` |
| max_retries | LLM_MAX_RETRIES | Retry attempts | `3` |

#### Available Models

Venice provides access to multiple model families:

- **Llama 3.1**: 8B (fast), 70B (balanced), 405B (smart)
- **Mistral**: 7B, Mixtral 8x7B
- **CodeLlama**: Various sizes for code generation
- **And more**: Check Venice documentation for full list

#### Example Setup

```bash
# Get API key from Venice dashboard
export VENICE_API_KEY=vn_key_...

# Configure provider
export LLM_PROVIDER=venice
export LLM_MODEL=llama-3.1-70b

# Test connection
hydra test-provider
```

### NEAR AI Cloud Provider

The NEAR AI Cloud provider connects to NEAR AI's OpenAI-compatible Cloud API
and defaults to TEE-backed model entries from the public model catalog.

#### Requirements

- NEAR AI Cloud API key
- Internet connection

#### Configuration Options

| Option | Environment Variable | Description | Default |
|--------|---------------------|-------------|---------|
| api_key | NEARAI_API_KEY | NEAR AI Cloud API key | Required |
| base_url | NEARAI_BASE_URL | API endpoint URL | `https://cloud-api.near.ai/v1` |
| model | LLM_MODEL | Model identifier | `zai-org/GLM-5.1-FP8` |
| timeout | LLM_TIMEOUT | Request timeout | `300` |
| max_retries | LLM_MAX_RETRIES | Retry attempts | `3` |

#### Example Setup

```bash
export NEARAI_API_KEY=your_key
export LLM_PROVIDER=nearai
export LLM_MODEL=zai-org/GLM-5.1-FP8
```

### Mock Provider

The mock provider is useful for testing and development without consuming API credits.

#### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| response_delay | Simulated response delay | `0.1` |
| mock_responses | Predefined responses | `{}` |
| error_rate | Simulated error rate (0-1) | `0` |

#### Example Usage

```bash
# Use mock provider for testing
export LLM_PROVIDER=mock

# Run tests without API calls
hydra test --provider mock
```

## Model Selection

### Model Mapping

Hydra uses a model mapping system to translate generic model identifiers to provider-specific names:

```yaml
model_mappings:
  fast:
    claude: haiku
    nearai: Qwen/Qwen3.6-35B-A3B-FP8
    venice: llama-3.1-8b
    
  balanced:
    claude: sonnet
    nearai: zai-org/GLM-5.1-FP8
    venice: llama-3.1-70b
    
  smart:
    claude: opus
    nearai: Qwen/Qwen3.5-122B-A10B
    venice: llama-3.1-405b
```

### Selecting Models

You can select models in several ways:

```bash
# Via environment variable
export LLM_MODEL=opus

# Via CLI argument
hydra generate --model sonnet "Create a web server"

# In tickets.md
**Model:** balanced
```

## Feature Compatibility

Not all providers support all features. Here's a compatibility matrix:

| Feature | Claude | NEAR AI Cloud | Venice | Mock |
|---------|--------|---------------|--------|------|
| Interactive Mode | ✓ | ✗ | ✗ | ✗ |
| Streaming Output | ✓ | ✓ | ✓ | ✗ |
| Session Persistence | ✓ | ✗ | ✗ | ✗ |
| File Safety Checks | ✓ | ✗ | ✗ | ✓ |
| Parallel Execution | ✓ | ✓ | ✓ | ✓ |
| Code Extraction | ✓ | ✓ | ✓ | ✓ |
| Custom Prompts | ✓ | ✓ | ✓ | ✓ |

## Fallback Configuration

Configure fallback providers for resilience:

```yaml
provider:
  default: claude
  fallback:
    - venice  # Try Venice if Claude fails
    - mock    # Fall back to mock for testing
  
  fallback_strategy:
    on_error: true       # Use fallback on errors
    on_timeout: true     # Use fallback on timeout
    on_rate_limit: true  # Use fallback on rate limits
```

## Advanced Configuration

### Provider Pooling

For high-throughput scenarios, configure provider pooling:

```yaml
pooling:
  enabled: true
  min_instances: 2
  max_instances: 10
  idle_timeout: 300
  warm_start: true
```

### Custom Providers

You can add custom providers by implementing the BaseProvider interface:

```python
from hydra.providers import BaseProvider

class CustomProvider(BaseProvider):
    def generate(self, prompt: str, **kwargs) -> str:
        # Your implementation
        pass
    
    # Implement other required methods...

# Register the provider
from hydra.providers import ProviderRegistry
ProviderRegistry.register("custom", CustomProvider)
```

### Provider Monitoring

Enable monitoring to track provider performance:

```yaml
monitoring:
  enabled: true
  metrics:
    - response_time
    - token_usage
    - error_rate
    - success_rate
  export:
    type: prometheus
    port: 9090
```

## Troubleshooting

### Common Issues

#### 1. Provider Not Found

```
Error: Provider 'xyz' not registered
```

**Solution**: Check that the provider is installed and properly configured:

```bash
hydra providers list
hydra config verify --provider xyz
```

#### 2. Authentication Failures

```
Error: Authentication failed for provider
```

**Solution**: Verify API keys and credentials:

```bash
# For Venice
echo $VENICE_API_KEY

# For Claude
claude auth status
```

#### 3. Model Not Available

```
Error: Model 'abc' not available for provider
```

**Solution**: Check available models:

```bash
hydra models list --provider venice
```

#### 4. Timeout Issues

```
Error: Provider request timed out
```

**Solution**: Increase timeout or use a faster model:

```bash
export LLM_TIMEOUT=600
export LLM_MODEL=fast
```

### Debug Mode

Enable debug mode for detailed logging:

```bash
export HYDRA_DEBUG=true
export HYDRA_LOG_LEVEL=DEBUG

hydra generate --debug "Test prompt"
```

### Health Checks

Run health checks to verify provider configuration:

```bash
# Check specific provider
hydra health --provider claude

# Check all providers
hydra health --all

# Verbose output
hydra health --verbose
```

## Best Practices

1. **Use Environment Variables for Secrets**: Never commit API keys to version control
2. **Configure Fallbacks**: Always have a fallback provider for production
3. **Monitor Usage**: Track token usage and costs
4. **Cache Responses**: Enable caching for repeated queries
5. **Set Appropriate Timeouts**: Balance between reliability and response time
6. **Use Mock Provider for Testing**: Avoid API costs during development
7. **Version Lock Models**: Specify exact model versions for consistency

## Migration from Legacy Configuration

If you're migrating from the old hardcoded Claude implementation:

1. **Update Environment Variables**:
   ```bash
   # Old
   export CLAUDE_MODEL=opus
   
   # New
   export LLM_PROVIDER=claude
   export LLM_MODEL=opus
   ```

2. **Update Configuration Files**: Replace direct Claude references with provider abstraction

3. **Update Code**: Use ProviderFactory instead of direct Claude imports

See the [Migration Guide](migration.md) for detailed instructions.

## Next Steps

- [Provider Implementation Guide](implementation.md) - Create custom providers
- [Venice Setup Guide](venice-setup.md) - Detailed Venice configuration
- [CLI Commands](../cli-commands.md) - Using providers with CLI
- [API Reference](../api/providers.md) - Provider API documentation
