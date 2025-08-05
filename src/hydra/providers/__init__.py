"""
LLM Providers module for Hydra.
"""
from .base import LLMProvider, LLMConfig
from .factory import LLMProviderFactory, ProviderRegistry

# Import providers to register them
from .venice import VeniceProvider
from .anthropic import AnthropicProvider
from .openai_provider import OpenAIProvider
from .claude_cli import ClaudeCLIProvider

# Create global factory instance
provider_factory = LLMProviderFactory()

__all__ = [
    'LLMProvider',
    'LLMConfig',
    'LLMProviderFactory',
    'provider_factory',
    'ProviderRegistry',
    'VeniceProvider',
    'AnthropicProvider',
    'OpenAIProvider',
    'ClaudeCLIProvider'
]