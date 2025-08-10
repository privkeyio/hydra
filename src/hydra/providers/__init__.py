"""LLM Providers module for Hydra."""
from .anthropic import AnthropicProvider
from .base import LLMConfig, LLMProvider
from .base_provider import BaseProvider
from .claude_tmux import ClaudeTmuxProvider
from .factory import LLMProviderFactory, ProviderRegistry
from .openai_provider import OpenAIProvider

# Import providers to register them
from .venice import VeniceProvider

# Create global factory instance
provider_factory = LLMProviderFactory()

__all__ = [
    'LLMProvider',
    'LLMConfig',
    'BaseProvider',
    'LLMProviderFactory',
    'provider_factory',
    'ProviderRegistry',
    'VeniceProvider',
    'AnthropicProvider',
    'OpenAIProvider',
    'ClaudeTmuxProvider'
]
