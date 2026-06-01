"""Integration tests for the NEAR AI Cloud provider."""

from unittest.mock import MagicMock, patch

from hydra.providers.base import LLMConfig
from hydra.providers.nearai import NearAIProvider
from hydra.providers.output_handler import OutputHandlerFactory, VeniceOutputHandler
from hydra.providers.provider_factory import ProviderFactory
from hydra.providers.provider_registry import ProviderRegistry


def create_nearai_provider(config: LLMConfig) -> NearAIProvider:
    """Create a NEAR AI provider with OpenAI clients patched."""
    with (
        patch("hydra.providers.venice.OpenAI"),
        patch("hydra.providers.venice.AsyncOpenAI"),
        patch("hydra.providers.venice.get_session_manager", return_value=MagicMock()),
        patch("hydra.providers.venice.get_token_tracker", return_value=MagicMock()),
    ):
        return NearAIProvider(config)


class TestNearAIProviderIntegration:
    """Test NEAR AI Cloud provider integration."""

    def test_nearai_provider_initialization_defaults(self):
        """Test NEAR AI provider initializes with expected defaults."""
        config = LLMConfig(provider_type="nearai", api_key="test-key")

        provider = create_nearai_provider(config)

        assert provider.name == "nearai"
        assert provider.config.base_url == "https://cloud-api.near.ai/v1"
        assert provider.config.model == "zai-org/GLM-5.1-FP8"

    def test_nearai_model_mapping_and_metadata(self):
        """Test NEAR AI model mappings and TEE metadata."""
        config = LLMConfig(provider_type="nearai", api_key="test-key")
        provider = create_nearai_provider(config)

        mapping = provider.get_model_mapping()
        assert mapping["fast"] == "Qwen/Qwen3.6-35B-A3B-FP8"
        assert mapping["balanced"] == "zai-org/GLM-5.1-FP8"
        assert mapping["smart"] == "Qwen/Qwen3.5-122B-A10B"

        models = provider.list_models()
        assert any(model.identifier == "zai-org/GLM-5.1-FP8" for model in models)
        assert all(model.metadata["provider"] == "nearai" for model in models)
        assert all(model.metadata["tee_inference"] is True for model in models)

    def test_nearai_selects_generic_model(self):
        """Test selecting a generic model alias."""
        config = LLMConfig(provider_type="nearai", api_key="test-key")
        provider = create_nearai_provider(config)

        assert provider.select_model("fast") is True
        assert provider.config.model == "Qwen/Qwen3.6-35B-A3B-FP8"

    def test_nearai_registered_in_provider_registry(self):
        """Test registry can create the NEAR AI provider."""
        registry = ProviderRegistry()
        config = LLMConfig(provider_type="nearai", api_key="test-key")

        with (
            patch("hydra.providers.venice.OpenAI"),
            patch("hydra.providers.venice.AsyncOpenAI"),
            patch(
                "hydra.providers.venice.get_session_manager",
                return_value=MagicMock(),
            ),
            patch("hydra.providers.venice.get_token_tracker", return_value=MagicMock()),
        ):
            provider = registry.create_provider("nearai", config)

        assert isinstance(provider, NearAIProvider)
        assert provider.name == "nearai"

    def test_nearai_factory_environment_config(self):
        """Test factory environment handling for NEAR AI."""
        factory = ProviderFactory()

        with (
            patch.dict(
                "os.environ",
                {"LLM_PROVIDER": "nearai", "NEARAI_API_KEY": "test-key"},
                clear=True,
            ),
            patch("hydra.providers.venice.OpenAI"),
            patch("hydra.providers.venice.AsyncOpenAI"),
            patch(
                "hydra.providers.venice.get_session_manager",
                return_value=MagicMock(),
            ),
            patch("hydra.providers.venice.get_token_tracker", return_value=MagicMock()),
        ):
            provider = factory.from_environment()

        assert isinstance(provider, NearAIProvider)
        assert provider.config.api_key == "test-key"

    def test_nearai_uses_openai_compatible_output_handler(self):
        """Test NEAR AI output handling uses the OpenAI-compatible parser."""
        handler = OutputHandlerFactory.create("nearai")
        parsed = handler.parse("```python\nprint('ok')\n```")

        assert isinstance(handler, VeniceOutputHandler)
        assert parsed.metadata["provider"] == "nearai"
        assert parsed.metadata["requires_code_extraction"] is True
