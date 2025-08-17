"""Unit tests for provider modules."""

import os
from unittest.mock import Mock, patch

import pytest

from hydra.providers.base import LLMConfig
from hydra.providers.mock_provider import MockProvider
from hydra.providers.provider_factory import ProviderFactory


class TestMockProvider:
    """Test mock provider functionality."""

    def test_mock_provider_initialization(self):
        """Test mock provider initialization."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        provider = MockProvider(config)
        
        assert provider.config == config
        assert provider.response_count == 0

    def test_mock_provider_generate(self):
        """Test mock provider generate method."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        provider = MockProvider(config)
        
        response = provider.generate("Test prompt")
        
        assert "Mock response" in response
        assert provider.response_count == 1

    def test_mock_provider_generate_with_context(self):
        """Test mock provider with context."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        provider = MockProvider(config)
        
        response = provider.generate(
            "Test prompt",
            context={"key": "value"}
        )
        
        assert "Mock response" in response

    def test_mock_provider_cleanup(self):
        """Test mock provider cleanup."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        provider = MockProvider(config)
        
        # Should not raise
        provider.cleanup()


class TestProviderFactory:
    """Test provider factory functionality."""

    @patch.dict(os.environ, {"LLM_PROVIDER": "mock"})
    def test_provider_factory_get_mock_provider(self):
        """Test getting mock provider from factory."""
        provider = ProviderFactory.get_provider("test")
        
        assert provider is not None
        assert isinstance(provider, MockProvider)

    @patch.dict(os.environ, {"LLM_PROVIDER": "claude_tmux"})
    @patch('hydra.providers.provider_factory.ClaudeTmuxProvider')
    def test_provider_factory_get_claude_provider(self, mock_claude_class):
        """Test getting Claude provider from factory."""
        mock_provider = Mock()
        mock_claude_class.return_value = mock_provider
        
        provider = ProviderFactory.get_provider("smart")
        
        assert provider == mock_provider
        mock_claude_class.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_provider_factory_default_to_mock(self):
        """Test factory defaults to mock provider."""
        provider = ProviderFactory.get_provider("test")
        
        assert isinstance(provider, MockProvider)

    def test_provider_factory_model_mapping(self):
        """Test provider factory model mapping."""
        # Test model mappings
        assert ProviderFactory._get_model_for_type("fast") is not None
        assert ProviderFactory._get_model_for_type("balanced") is not None
        assert ProviderFactory._get_model_for_type("smart") is not None
        assert ProviderFactory._get_model_for_type("unknown") is not None


class TestProviderConfig:
    """Test provider configuration."""

    def test_llm_config_creation(self):
        """Test LLM config creation."""
        config = LLMConfig(
            provider_type="test",
            model="test-model",
            api_key="test-key",
            temperature=0.7,
            max_tokens=1000
        )
        
        assert config.provider_type == "test"
        assert config.model == "test-model"
        assert config.api_key == "test-key"
        assert config.temperature == 0.7
        assert config.max_tokens == 1000

    def test_llm_config_defaults(self):
        """Test LLM config with defaults."""
        config = LLMConfig(
            provider_type="test",
            model="test-model",
            api_key="test-key"
        )
        
        assert config.temperature == 0.0  # Default
        assert config.max_tokens == 4096  # Default

    def test_llm_config_from_env(self):
        """Test LLM config from environment."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "mock",
            "ANTHROPIC_API_KEY": "test-key"
        }):
            config = LLMConfig.from_env()
            
            assert config.provider_type == "mock"
            assert config.api_key == "test-key"


class TestProviderSessionManagement:
    """Test provider session management."""

    @patch('hydra.providers.session_manager.get_session_manager')
    def test_provider_session_reuse(self, mock_get_manager):
        """Test session reuse across providers."""
        mock_manager = Mock()
        mock_session = Mock()
        mock_manager.get_session.return_value = mock_session
        mock_get_manager.return_value = mock_manager
        
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        
        provider1 = MockProvider(config)
        provider2 = MockProvider(config)
        
        # Both should use same session manager
        mock_get_manager.assert_called()

    def test_provider_cleanup_no_error(self):
        """Test provider cleanup doesn't raise errors."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        
        provider = MockProvider(config)
        
        # Multiple cleanups should not raise
        provider.cleanup()
        provider.cleanup()


class TestProviderErrorHandling:
    """Test provider error handling."""

    def test_mock_provider_error_simulation(self):
        """Test mock provider error simulation."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        provider = MockProvider(config)
        
        # Force error mode
        provider.error_mode = True
        
        with pytest.raises(Exception):
            provider.generate("Test prompt")

    @patch('hydra.providers.mock_provider.logger')
    def test_mock_provider_logging(self, mock_logger):
        """Test mock provider logging."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",  
            api_key="test-key"
        )
        provider = MockProvider(config)
        
        provider.generate("Test prompt")
        
        # Should log the generation
        mock_logger.info.assert_called()


class TestProviderMetrics:
    """Test provider metrics and monitoring."""

    def test_mock_provider_response_count(self):
        """Test mock provider tracks response count."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        provider = MockProvider(config)
        
        assert provider.response_count == 0
        
        provider.generate("Test 1")
        assert provider.response_count == 1
        
        provider.generate("Test 2")
        assert provider.response_count == 2

    def test_mock_provider_get_metrics(self):
        """Test mock provider metrics retrieval."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test-key"
        )
        provider = MockProvider(config)
        
        provider.generate("Test")
        
        metrics = provider.get_metrics()
        
        assert metrics["response_count"] == 1
        assert metrics["provider_type"] == "mock"
        assert metrics["model"] == "test-model"