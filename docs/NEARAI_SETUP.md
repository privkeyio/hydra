# NEAR AI Cloud Provider Setup Guide

NEAR AI Cloud provides OpenAI-compatible TEE inference through
`https://cloud-api.near.ai/v1`.

## Quick Start

### 1. Get Your API Key

Create an API key from the NEAR AI Cloud dashboard at `https://cloud.near.ai`.

### 2. Configure Hydra

```bash
export LLM_PROVIDER=nearai
export NEARAI_API_KEY=your_api_key_here
```

Optional overrides:

```bash
export NEARAI_BASE_URL=https://cloud-api.near.ai/v1
export LLM_MODEL=zai-org/GLM-5.1-FP8
```

### 3. Test Initialization

```bash
python -c "
from hydra.providers.nearai import NearAIProvider
from hydra.providers.base import LLMConfig
import os

config = LLMConfig(
    provider_type='nearai',
    api_key=os.getenv('NEARAI_API_KEY'),
)
provider = NearAIProvider(config)
print(provider.name, provider.config.base_url, provider.config.model)
"
```

## Default Models

Hydra maps generic model names to TEE-backed NEAR AI Cloud chat models:

| Generic name | NEAR AI Cloud model |
|--------------|---------------------|
| `fast` | `Qwen/Qwen3.6-35B-A3B-FP8` |
| `balanced` | `zai-org/GLM-5.1-FP8` |
| `smart` | `Qwen/Qwen3.5-122B-A10B` |
| `coder` | `zai-org/GLM-5.1-FP8` |
| `vision` | `Qwen/Qwen3-VL-30B-A3B-Instruct` |

The static list was generated from the public model catalog endpoint:

```bash
curl https://cloud-api.near.ai/v1/model/list
```

## Programmatic Usage

```python
from hydra.providers.base import LLMConfig
from hydra.providers.nearai import NearAIProvider

config = LLMConfig(
    provider_type="nearai",
    model="zai-org/GLM-5.1-FP8",
    api_key="your_api_key",
    base_url="https://cloud-api.near.ai/v1",
    temperature=0.3,
    max_tokens=3000,
)

provider = NearAIProvider(config)
response = provider.generate("Create a Python data validation module")
```

## Troubleshooting

If authentication fails, confirm `NEARAI_API_KEY` is set in the same shell that
runs Hydra. If a model is unavailable, fetch the current catalog and set
`LLM_MODEL` to one of the returned `modelId` values.
