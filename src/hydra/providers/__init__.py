"""LLM Providers module for Hydra."""
from .base import LLMConfig, LLMProvider
from .base_provider import BaseProvider
from .factory import LLMProviderFactory, ProviderRegistry

# Try to import optional providers that require external dependencies
try:
    from .anthropic import AnthropicProvider
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AnthropicProvider = None
    _ANTHROPIC_AVAILABLE = False

try:
    from .claude_tmux import ClaudeTmuxProvider
    _CLAUDE_TMUX_AVAILABLE = True
except ImportError:
    ClaudeTmuxProvider = None
    _CLAUDE_TMUX_AVAILABLE = False

try:
    from .openai_provider import OpenAIProvider
    _OPENAI_AVAILABLE = True
except ImportError:
    OpenAIProvider = None
    _OPENAI_AVAILABLE = False

try:
    # Import providers to register them
    from .venice import VeniceProvider
    _VENICE_AVAILABLE = True
except ImportError:
    VeniceProvider = None
    _VENICE_AVAILABLE = False

try:
    from .nearai import NearAIProvider
    _NEARAI_AVAILABLE = True
except ImportError:
    NearAIProvider = None
    _NEARAI_AVAILABLE = False

# Create global factory instance
provider_factory = LLMProviderFactory()

__all__ = [
    'LLMProvider',
    'LLMConfig',
    'BaseProvider',
    'LLMProviderFactory',
    'provider_factory',
    'ProviderRegistry',
]

# Add optional providers to __all__ if available
if _VENICE_AVAILABLE:
    __all__.append('VeniceProvider')
if _NEARAI_AVAILABLE:
    __all__.append('NearAIProvider')
if _ANTHROPIC_AVAILABLE:
    __all__.append('AnthropicProvider')
if _OPENAI_AVAILABLE:
    __all__.append('OpenAIProvider')
if _CLAUDE_TMUX_AVAILABLE:
    __all__.append('ClaudeTmuxProvider')
