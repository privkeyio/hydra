# Venice AI Provider Setup Guide

Venice AI provides access to powerful open-source models through a simple API, making it an excellent choice for Hydra's multi-agent system.

## Quick Start

### 1. Get Your API Key

1. Visit [venice.ai](https://venice.ai)
2. Sign up for a free account
3. Generate your API key from the dashboard

### 2. Configure Hydra

Create a `.env` file in your Hydra directory:

```bash
# .env
LLM_PROVIDER=venice
VENICE_API_KEY=your_api_key_here
```

### 3. Test Your Setup

```bash
# List available models
python -c "
from hydra.providers.venice import VeniceProvider
from hydra.providers.base import LLMConfig
import os

config = LLMConfig(
    provider_type='venice',
    model='llama-3.2-3b',
    api_key=os.getenv('VENICE_API_KEY'),
    base_url='https://api.venice.ai/api/v1'
)
provider = VeniceProvider(config)
print('✅ Venice provider initialized successfully!')
"
```

## Available Models

Venice offers various models optimized for different tasks:

### Coding Models (Recommended for Hydra)
- **qwen-2.5-coder-32b** - Best overall coding performance
- **deepseek-coder-v2-lite** - Fast, specialized for code
- **qwen3-4b** - Lightweight but capable

### General Purpose Models
- **llama-3.3-70b** - Excellent balance of speed and capability
- **llama-3.1-405b** - Most powerful, best for complex tasks
- **llama-3.2-3b** - Fast responses for simple tasks

### Specialized Models
- **qwen-2.5-qwq-32b** - Advanced reasoning and problem-solving
- **dolphin-2.9.2-qwen2-72b** - Uncensored, creative responses
- **venice-uncensored** - No content restrictions

## Using Venice with Hydra

### Simple Task Execution

```bash
# Set Venice as your provider
export LLM_PROVIDER=venice
export VENICE_API_KEY=your_key

# Execute a task
hydra claude execute "Create a Python REST API with FastAPI"
```

### Ticket Workflow

```bash
# Generate tickets with Venice
hydra ticket create "Build a web scraper with data processing pipeline"

# Execute in parallel with Venice agents
hydra ticket parallel --workers 4
```

### Programmatic Usage

```python
from hydra.providers.venice import VeniceProvider
from hydra.providers.base import LLMConfig

# Initialize provider
config = LLMConfig(
    provider_type="venice",
    model="qwen-2.5-coder-32b",
    api_key="your_api_key",
    base_url="https://api.venice.ai/api/v1",
    temperature=0.3,  # Lower for deterministic code
    max_tokens=3000
)

provider = VeniceProvider(config)

# Execute a development ticket
result = provider.execute_ticket(
    ticket_content="Create a Python module for data validation",
    working_directory="./output"
)
```

## Model Selection Strategy

Choose your model based on the task:

| Task Type | Recommended Model | Why |
|-----------|------------------|-----|
| Code Generation | qwen-2.5-coder-32b | Optimized for code, understands patterns |
| Quick Scripts | llama-3.2-3b | Fast, efficient for simple tasks |
| Complex Projects | llama-3.3-70b | Good balance of capability and speed |
| Debugging | deepseek-coder-v2-lite | Specialized in code analysis |
| Documentation | qwen-2.5-qwq-32b | Excellent reasoning and explanation |

## Configuration Options

### Environment Variables

```bash
# Required
VENICE_API_KEY=your_key

# Optional
LLM_PROVIDER=venice
LLM_MODEL=qwen-2.5-coder-32b  # Override default model
LLM_TEMPERATURE=0.3           # 0.0-1.0, lower = more deterministic
LLM_MAX_TOKENS=3000           # Maximum response length
```

### Advanced Configuration

```python
config = LLMConfig(
    provider_type="venice",
    model="qwen-2.5-coder-32b",
    api_key=api_key,
    base_url="https://api.venice.ai/api/v1",
    temperature=0.3,
    max_tokens=4000,
    timeout=60,  # Request timeout in seconds
    extra_params={
        "top_p": 0.95,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0
    }
)
```

## Troubleshooting

### API Key Issues
```bash
# Verify your API key is set
echo $VENICE_API_KEY

# Test API connection
curl -H "Authorization: Bearer $VENICE_API_KEY" \
     https://api.venice.ai/api/v1/models
```

### Model Not Found
- Use exact model names from `hydra venice list-models`
- Model availability may change; check Venice dashboard

### Rate Limiting
- Venice has generous rate limits
- If hit, implement exponential backoff
- Consider upgrading plan for production use

### Response Quality
- Use lower temperature (0.2-0.4) for code generation
- Increase max_tokens for complex tasks
- Be specific in prompts about output format

## Best Practices

1. **Model Selection**: Use coding-optimized models for development tasks
2. **Temperature**: Keep low (0.2-0.4) for consistent code generation
3. **Prompting**: Be explicit about file structure and naming conventions
4. **Error Handling**: Venice models may occasionally need retry logic
5. **Cost Optimization**: Use smaller models for simple tasks

## Example Projects

See `/examples/venice_provider_example.py` for complete examples:

```bash
# Run examples
cd examples
python venice_provider_example.py simple  # Simple generation
python venice_provider_example.py ticket  # Execute a ticket
python venice_provider_example.py list    # List available models
```

## Support

- Venice Documentation: [docs.venice.ai](https://docs.venice.ai)
- Venice Discord: Community support
- Hydra Issues: Report provider-specific issues on GitHub