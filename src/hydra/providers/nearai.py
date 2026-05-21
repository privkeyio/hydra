"""NEAR AI Cloud provider implementation."""

from hydra.providers.venice import VeniceProvider


class NearAIProvider(VeniceProvider):
    """NEAR AI Cloud TEE inference provider using the OpenAI-compatible API."""

    PROVIDER_TYPE = "nearai"
    PROVIDER_SLUG = "nearai"
    DISPLAY_NAME = "NEAR AI Cloud"
    API_KEY_ENV_VAR = "NEARAI_API_KEY"
    DEFAULT_BASE_URL = "https://cloud-api.near.ai/v1"
    DEFAULT_MODEL = "zai-org/GLM-5.1-FP8"

    # Static chat model snapshot generated from:
    # GET https://cloud-api.near.ai/v1/model/list on 2026-05-21.
    MODEL_CATALOG = {
        "Qwen/Qwen3.6-35B-A3B-FP8": {
            "display_name": "Qwen 3.6 35B A3B FP8",
            "category": "fast",
            "context_window": 262144,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000017,
            "metadata": {
                "tee_inference": True,
                "verifiable": True,
                "attestation_supported": True,
            },
        },
        "zai-org/GLM-5.1-FP8": {
            "display_name": "GLM 5.1",
            "category": "balanced",
            "context_window": 202752,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000085,
            "metadata": {
                "tee_inference": True,
                "verifiable": True,
                "attestation_supported": True,
            },
        },
        "Qwen/Qwen3.5-122B-A10B": {
            "display_name": "Qwen3.5 122B A10B",
            "category": "smart",
            "context_window": 131072,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.0000004,
            "metadata": {
                "tee_inference": True,
                "verifiable": True,
                "attestation_supported": True,
            },
        },
        "Qwen/Qwen3-30B-A3B-Instruct-2507": {
            "display_name": "Qwen3 30B A3B Instruct 2507",
            "category": "balanced",
            "context_window": 262144,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000015,
            "metadata": {
                "tee_inference": True,
                "verifiable": True,
                "attestation_supported": True,
            },
        },
        "openai/gpt-oss-120b": {
            "display_name": "GPT OSS 120B",
            "category": "smart",
            "context_window": 131000,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000015,
            "metadata": {
                "tee_inference": True,
                "verifiable": True,
                "attestation_supported": True,
            },
        },
        "google/gemma-4-31B-it": {
            "display_name": "Gemma 4 31B Instruct",
            "category": "fast",
            "context_window": 262144,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000013,
            "metadata": {
                "tee_inference": True,
                "verifiable": True,
                "attestation_supported": True,
            },
        },
        "Qwen/Qwen3-VL-30B-A3B-Instruct": {
            "display_name": "Qwen3 VL 30B A3B Instruct",
            "category": "balanced",
            "context_window": 256000,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000015,
            "metadata": {
                "tee_inference": True,
                "verifiable": True,
                "attestation_supported": True,
                "vision": True,
            },
        },
    }

    MODEL_MAPPINGS = {
        "fast": "Qwen/Qwen3.6-35B-A3B-FP8",
        "balanced": "zai-org/GLM-5.1-FP8",
        "smart": "Qwen/Qwen3.5-122B-A10B",
        "coder": "zai-org/GLM-5.1-FP8",
        "vision": "Qwen/Qwen3-VL-30B-A3B-Instruct",
        "opus": "zai-org/GLM-5.1-FP8",
        "sonnet": "Qwen/Qwen3.6-35B-A3B-FP8",
    }
