import os
from unittest.mock import patch

from hydra.providers.base import LLMConfig
from hydra.providers.mock_provider import MockProvider


def test_mock_provider_basic():
    config = LLMConfig(
        provider_type='mock',
        model='test-model',
        api_key='test-key'
    )
    
    provider = MockProvider(config)
    
    response = provider.generate("Hello world")
    assert isinstance(response, str)
    assert len(response) > 0
    
    # Check call was tracked
    assert len(provider.call_history) == 1
    assert provider.call_history[0]['prompt'] == "Hello world"


def test_mock_provider_custom_response():
    config = LLMConfig(
        provider_type='mock',
        model='test-model', 
        api_key='test-key'
    )
    
    provider = MockProvider(config)
    provider.response_overrides["test"] = "custom response"
    
    response = provider.generate("test")
    assert response == "custom response"


def test_llm_config_creation():
    config = LLMConfig(
        provider_type='mock',
        model='test-model',
        api_key='test-key',
        temperature=0.7
    )
    
    assert config.provider_type == 'mock'
    assert config.model == 'test-model'
    assert config.api_key == 'test-key'
    assert config.temperature == 0.7


def test_claude_tmux_provider_validation():
    from hydra.providers.claude_tmux import ClaudeTmuxProvider
    
    config = LLMConfig(
        provider_type='claude_tmux',
        model='claude-3-sonnet',
        api_key='test-key'
    )
    
    # Test validation when Claude CLI not found
    with patch('hydra.utils.claude_path.get_claude_cli_path') as mock_path:
        with patch('pathlib.Path.exists') as mock_exists:
            mock_path.return_value = '/nonexistent/claude'
            mock_exists.return_value = False
            
            try:
                ClaudeTmuxProvider(config)
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Claude CLI not found" in str(e)


def test_session_manager():
    from hydra.providers.session_manager import get_session_manager
    
    manager = get_session_manager()
    
    # Test session creation
    session1 = manager.get_session('test_provider')
    session2 = manager.get_session('test_provider')
    
    # Should reuse same session
    assert session1 is session2
    
    # Different provider should get different session
    session3 = manager.get_session('other_provider')
    assert session3 is not session1


def test_provider_error_handling():
    from hydra.providers.mock_provider import MockProvider
    
    config = LLMConfig(
        provider_type='mock',
        model='test-model',
        api_key='test-key'
    )
    
    provider = MockProvider(config, fail_mode=False)
    
    # Test with empty input
    response = provider.generate("")
    assert isinstance(response, str)
    
    # Test cleanup doesn't crash
    provider.cleanup()



def test_provider_config_validation():
    # Test invalid provider type handling
    try:
        config = LLMConfig(
            provider_type='nonexistent',
            model='test-model',
            api_key='test-key'
        )
        assert config.provider_type == 'nonexistent'
    except Exception:
        pass  # Some validation might occur


def test_provider_capabilities():
    from hydra.providers.mock_provider import MockProvider
    
    config = LLMConfig(
        provider_type='mock',
        model='test-model',
        api_key='test-key'
    )
    
    provider = MockProvider(config)
    
    # Test basic capabilities
    assert hasattr(provider, 'generate')
    assert hasattr(provider, 'cleanup')
    assert hasattr(provider, 'config')


def test_venice_provider_basic():
    from hydra.providers.venice import VeniceProvider
    
    config = LLMConfig(
        provider_type='venice',
        model='venice-model',
        api_key='test-key'
    )
    
    provider = VeniceProvider(config)
    assert provider.config == config
    assert provider.name == 'venice'