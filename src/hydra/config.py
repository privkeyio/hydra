"""Configuration management for Hydra system."""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from hydra.providers import LLMConfig, provider_factory

# Load environment variables if dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, skip loading
    pass


class HydraConfig:
    """Central configuration management for Hydra."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config_file()
        self.config = self._load_config()
        self._override_with_env()
        self.llm_provider = self._create_llm_provider()

    def _find_config_file(self) -> str:
        """Find the configuration file."""
        # Look for config in multiple locations
        search_paths = [
            Path.cwd() / "config" / "default.yaml",
            Path.cwd() / "hydra.yaml",
            Path(__file__).parent.parent.parent / "config" / "default.yaml",
        ]

        for path in search_paths:
            if path.exists():
                return str(path)

        # If no config file found, use defaults
        return None

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if self.config_path and Path(self.config_path).exists():
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)

        # Default configuration
        return {
            'llm': {
                'provider': 'venice',
                'model': None,  # Will use provider default
                'temperature': 0.2,
                'max_tokens': 2048,
                'timeout': 120  # Increased for complex ticket tasks
            },
            'agent': {
                'max_depth': 2,
                'retry_attempts': 2,
                'timeout': 30
            },
            'logging': {
                'level': 'INFO',
                'file': 'logs/agent_activity.log',
                'max_bytes': 10485760,
                'backup_count': 5
            }
        }

    def _override_with_env(self):
        """Override configuration with environment variables."""
        # LLM provider configuration
        if os.getenv('LLM_PROVIDER'):
            self.config['llm']['provider'] = os.getenv('LLM_PROVIDER')

        if os.getenv('LLM_MODEL'):
            self.config['llm']['model'] = os.getenv('LLM_MODEL')

        if os.getenv('LLM_TEMPERATURE'):
            self.config['llm']['temperature'] = float(os.getenv('LLM_TEMPERATURE'))

        if os.getenv('LLM_MAX_TOKENS'):
            self.config['llm']['max_tokens'] = int(os.getenv('LLM_MAX_TOKENS'))

        if os.getenv('LLM_TIMEOUT'):
            self.config['llm']['timeout'] = int(os.getenv('LLM_TIMEOUT'))

        # Agent configuration
        if os.getenv('AGENT_MAX_DEPTH'):
            self.config['agent']['max_depth'] = int(os.getenv('AGENT_MAX_DEPTH'))

        if os.getenv('AGENT_RETRY_ATTEMPTS'):
            self.config['agent']['retry_attempts'] = int(
                os.getenv('AGENT_RETRY_ATTEMPTS')
            )

    def _create_llm_provider(self):
        """Create the LLM provider based on configuration."""
        llm_config = self.config['llm']
        provider_type = llm_config['provider']

        # Build LLMConfig
        config = LLMConfig(
            provider_type=provider_type,
            model=llm_config.get('model'),
            temperature=llm_config.get('temperature', 0.2),
            max_tokens=llm_config.get('max_tokens', 2048),
            timeout=llm_config.get('timeout', 30),
            extra_params={}
        )

        # Add provider-specific configuration
        if provider_type == 'venice':
            config.api_key = os.getenv('VENICE_API_KEY')
            config.base_url = os.getenv(
                'VENICE_BASE_URL', 'https://api.venice.ai/api/v1'
            )

        elif provider_type in ['nearai', 'nearai_api']:
            config.api_key = os.getenv('NEARAI_API_KEY')
            config.base_url = os.getenv(
                'NEARAI_BASE_URL', 'https://cloud-api.near.ai/v1'
            )

        elif provider_type == 'anthropic':
            config.api_key = os.getenv('ANTHROPIC_API_KEY')

        elif provider_type == 'openai':
            config.api_key = os.getenv('OPENAI_API_KEY')
            config.base_url = os.getenv('OPENAI_BASE_URL')  # For custom endpoints

        elif provider_type == 'claude_cli':
            # Use config file values first, then env vars, then defaults
            extra_params = llm_config.get('extra_params', {})
            config.extra_params['claude_path'] = (
                extra_params.get('claude_path') or
                os.getenv('CLAUDE_CLI_PATH', 'claude')
            )
            config.extra_params['cli_flags'] = (
                extra_params.get('cli_flags') or
                os.getenv('CLAUDE_CLI_FLAGS', '')
            )

        elif provider_type == 'claude_tmux':
            # Configuration for Claude Code tmux provider
            extra_params = llm_config.get('extra_params', {})
            config.extra_params['claude_path'] = (
                extra_params.get('claude_path') or
                os.getenv('CLAUDE_CLI_PATH', 'claude')
            )

        elif provider_type == 'claude_session':
            # Configuration for Claude Code session provider with backend auto-discovery
            extra_params = llm_config.get('extra_params', {})
            config.extra_params['claude_path'] = (
                extra_params.get('claude_path') or
                os.getenv('CLAUDE_CLI_PATH', 'claude')
            )
            config.extra_params['preferred_backend'] = (
                extra_params.get('preferred_backend') or
                os.getenv('SESSION_BACKEND', None)  # tmux, direct_process, docker
            )

        elif provider_type == 'mock':
            config.api_key = 'test_key'  # Mock provider doesn't need real API key

        return provider_factory.create(config)

    def get_agent_config(self) -> Dict[str, Any]:
        """Get agent configuration."""
        return self.config['agent']

    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return self.config['logging']


# Global configuration instance
_config_instance = None


def get_config() -> HydraConfig:
    """Get or create the global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = HydraConfig()
    return _config_instance


def reset_config(config_path: Optional[str] = None):
    """Reset the global configuration instance."""
    global _config_instance
    _config_instance = HydraConfig(config_path)
    return _config_instance
