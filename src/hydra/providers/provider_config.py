"""Provider configuration management system."""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from hydra.providers.base import LLMConfig


@dataclass
class ModelMapping:
    """Model mapping configuration."""

    generic_name: str  # e.g., "opus", "sonnet", "fast", "smart"
    provider_identifier: str  # e.g., "claude-opus-4-1-20250805"
    category: str  # e.g., "smart", "balanced", "fast"
    context_window: int = 200000
    max_output_tokens: int = 4096
    cost_per_million_tokens: Optional[float] = None


@dataclass
class ProviderFeatures:
    """Provider feature flags."""

    interactive: bool = False
    streaming: bool = False
    file_interception: bool = False
    session_persistence: bool = False
    code_execution: bool = False
    context_extension: bool = False


@dataclass
class ProviderConfig:
    """Complete provider configuration."""

    name: str
    type: str  # Provider implementation type
    enabled: bool = True
    default_model: str = None
    models: Dict[str, ModelMapping] = field(default_factory=dict)
    features: ProviderFeatures = field(default_factory=ProviderFeatures)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    cli_path: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)
    fallback_providers: List[str] = field(default_factory=list)

    def to_llm_config(self) -> LLMConfig:
        """Convert to LLMConfig for provider initialization."""
        return LLMConfig(
            provider_type=self.type,
            model=self.default_model,
            api_key=self.api_key,
            base_url=self.base_url,
            extra_params=self.extra_params
        )


class ProviderConfigManager:
    """Manages provider configurations from files and environment."""

    DEFAULT_CONFIG = {
        "claude": {
            "type": "claude_tmux",
            "enabled": True,
            "cli_path": "${CLAUDE_CLI_PATH:-claude}",
            "default_model": "opus",
            "models": {
                "opus": {
                    "provider_identifier": "claude-opus-4-1-20250805",
                    "category": "smart",
                    "context_window": 200000,
                    "max_output_tokens": 8192,
                    "cost_per_million_tokens": 15.0
                },
                "sonnet": {
                    "provider_identifier": "claude-sonnet-4-20250514",
                    "category": "balanced",
                    "context_window": 200000,
                    "max_output_tokens": 8192,
                    "cost_per_million_tokens": 3.0
                },
                "haiku": {
                    "provider_identifier": "claude-3-haiku-20240307",
                    "category": "fast",
                    "context_window": 200000,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 0.25
                }
            },
            "features": {
                "interactive": True,
                "streaming": True,
                "file_interception": True,
                "session_persistence": True,
                "code_execution": False,
                "context_extension": False
            },
            "extra_params": {
                "tmux": {
                    "session_prefix": "hydra_claude",
                    "capture_method": "pane",
                    "output_wait_time": 0.5
                }
            }
        },
        "venice": {
            "type": "venice_api",
            "enabled": True,
            "api_key": "${VENICE_API_KEY}",
            "base_url": "https://api.venice.ai/v1",
            "default_model": "llama-3.1-70b",
            "models": {
                "fast": {
                    "provider_identifier": "llama-3.1-8b",
                    "category": "fast",
                    "context_window": 131072,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 0.05
                },
                "balanced": {
                    "provider_identifier": "llama-3.1-70b",
                    "category": "balanced",
                    "context_window": 131072,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 0.35
                },
                "smart": {
                    "provider_identifier": "llama-3.1-405b",
                    "category": "smart",
                    "context_window": 131072,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 2.75
                },
                "opus": {
                    "provider_identifier": "llama-3.1-405b",
                    "category": "smart",
                    "context_window": 131072,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 2.75
                },
                "sonnet": {
                    "provider_identifier": "llama-3.1-70b",
                    "category": "balanced",
                    "context_window": 131072,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 0.35
                }
            },
            "features": {
                "interactive": False,
                "streaming": True,
                "file_interception": False,
                "session_persistence": False,
                "code_execution": False,
                "context_extension": False
            }
        },
        "anthropic": {
            "type": "anthropic_api",
            "enabled": True,
            "api_key": "${ANTHROPIC_API_KEY}",
            "base_url": "https://api.anthropic.com",
            "default_model": "claude-3-opus-20240229",
            "models": {
                "opus": {
                    "provider_identifier": "claude-3-opus-20240229",
                    "category": "smart",
                    "context_window": 200000,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 15.0
                },
                "sonnet": {
                    "provider_identifier": "claude-3-sonnet-20240229",
                    "category": "balanced",
                    "context_window": 200000,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 3.0
                },
                "haiku": {
                    "provider_identifier": "claude-3-haiku-20240307",
                    "category": "fast",
                    "context_window": 200000,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 0.25
                }
            },
            "features": {
                "interactive": False,
                "streaming": True,
                "file_interception": False,
                "session_persistence": False,
                "code_execution": False,
                "context_extension": False
            }
        },
        "mock": {
            "type": "mock_provider",
            "enabled": True,
            "default_model": "mock-model",
            "models": {
                "mock-model": {
                    "provider_identifier": "mock-model-v1",
                    "category": "balanced",
                    "context_window": 100000,
                    "max_output_tokens": 4096,
                    "cost_per_million_tokens": 0.0
                }
            },
            "features": {
                "interactive": False,
                "streaming": False,
                "file_interception": False,
                "session_persistence": False,
                "code_execution": False,
                "context_extension": False
            },
            "extra_params": {
                "mock_responses": {},
                "mock_delay": 0
            }
        }
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration manager.

        Args:
            config_path: Optional path to provider configuration file

        """
        self.config_path = config_path or self._get_default_config_path()
        self._configs: Dict[str, ProviderConfig] = {}
        self._load_configurations()

    def _get_default_config_path(self) -> Path:
        """Get default configuration file path."""
        # Check multiple locations in order
        paths = [
            Path.cwd() / "providers.yaml",
            Path.cwd() / "config" / "providers.yaml",
            Path.home() / ".hydra" / "providers.yaml",
            Path("/etc/hydra/providers.yaml"),
        ]

        for path in paths:
            if path.exists():
                return path

        # Return user config path as default
        return Path.home() / ".hydra" / "providers.yaml"

    def _load_configurations(self) -> None:
        """Load configurations from file and environment."""
        # Start with default configurations
        configs = self.DEFAULT_CONFIG.copy()

        # Load from file if exists
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                file_configs = yaml.safe_load(f)
                if file_configs and 'providers' in file_configs:
                    configs.update(file_configs['providers'])

        # Process each provider configuration
        for name, config_dict in configs.items():
            self._configs[name] = self._parse_provider_config(name, config_dict)

        # Apply environment overrides
        self._apply_environment_overrides()

    def _parse_provider_config(
        self, name: str, config_dict: Dict[str, Any]
    ) -> ProviderConfig:
        """Parse provider configuration dictionary.

        Args:
            name: Provider name
            config_dict: Configuration dictionary

        Returns:
            Parsed ProviderConfig

        """
        # Parse features
        features_dict = config_dict.get('features', {})
        features = ProviderFeatures(**features_dict)

        # Parse model mappings
        models = {}
        models_dict = config_dict.get('models', {})
        for model_name, model_config in models_dict.items():
            if isinstance(model_config, str):
                # Simple string mapping
                models[model_name] = ModelMapping(
                    generic_name=model_name,
                    provider_identifier=model_config,
                    category="balanced"
                )
            else:
                # Full model configuration
                models[model_name] = ModelMapping(
                    generic_name=model_name,
                    **model_config
                )

        # Expand environment variables
        api_key = self._expand_env_var(config_dict.get('api_key'))
        base_url = self._expand_env_var(config_dict.get('base_url'))
        cli_path = self._expand_env_var(config_dict.get('cli_path'))

        # For Claude providers, use dynamic path resolution if not explicitly set
        if name == 'claude' and cli_path == 'claude':
            from hydra.utils.claude_path import get_claude_cli_path
            cli_path = get_claude_cli_path()

        config = ProviderConfig(
            name=name,
            type=config_dict.get('type', name),
            enabled=config_dict.get('enabled', True),
            default_model=config_dict.get('default_model'),
            models=models,
            features=features,
            api_key=api_key,
            base_url=base_url,
            cli_path=cli_path,
            extra_params=config_dict.get('extra_params', {}),
            fallback_providers=config_dict.get('fallback_providers', [])
        )

        # Validate configuration
        self._validate_provider_config(config)

        return config

    def _validate_provider_config(self, config: ProviderConfig) -> None:
        """Validate provider configuration.

        Args:
            config: Provider configuration to validate

        Raises:
            ValueError: If configuration is invalid

        """
        self._validate_required_fields(config)
        self._validate_models(config)
        self._validate_provider_credentials(config)
        self._validate_model_configurations(config)

    def _validate_required_fields(self, config: ProviderConfig) -> None:
        """Validate required configuration fields."""
        if not config.name:
            raise ValueError("Provider name is required")

        if not config.type:
            raise ValueError(f"Provider type is required for {config.name}")

    def _validate_models(self, config: ProviderConfig) -> None:
        """Validate model configuration."""
        if config.enabled and config.models:
            if config.default_model and config.default_model not in config.models:
                # Check if default_model is a provider identifier
                identifier_found = False
                for model in config.models.values():
                    if model.provider_identifier == config.default_model:
                        identifier_found = True
                        break
                if not identifier_found:
                    raise ValueError(
                        f"Default model '{config.default_model}' not found in "
                        f"models for provider {config.name}"
                    )

    def _validate_provider_credentials(self, config: ProviderConfig) -> None:
        """Validate provider-specific credentials."""
        # Only warn about missing API keys if this provider might be used
        # (i.e., if it's explicitly selected via LLM_PROVIDER or if it's the only enabled provider)
        provider_name = os.getenv('LLM_PROVIDER')
        is_selected = (provider_name == config.name)

        # Count enabled providers
        enabled_count = sum(1 for c in self._configs.values() if c.enabled)
        is_only_provider = (config.enabled and enabled_count == 1)

        # Validate API providers have required credentials
        if config.type in ['venice_api', 'anthropic_api', 'openai_api']:
            if not config.api_key and config.enabled and (is_selected or is_only_provider):
                import warnings
                warnings.warn(
                    f"API key not configured for {config.name} provider. "
                    f"Set {config.name.upper()}_API_KEY environment variable.",
                    stacklevel=3
                )

        # Validate CLI providers have CLI path
        if config.type in ['claude_tmux', 'claude_cli']:
            if config.cli_path and not config.cli_path.startswith('$'):
                cli_path = Path(config.cli_path)
                if not cli_path.exists() and config.enabled:
                    import warnings
                    warnings.warn(
                        f"CLI path '{config.cli_path}' not found for "
                        f"{config.name} provider",
                        stacklevel=3
                    )

    def _validate_model_configurations(self, config: ProviderConfig) -> None:
        """Validate individual model configurations."""
        for model_name, model_config in config.models.items():
            if model_config.context_window <= 0:
                raise ValueError(
                    f"Invalid context window for model {model_name} in "
                    f"provider {config.name}"
                )
            if model_config.max_output_tokens <= 0:
                raise ValueError(
                    f"Invalid max output tokens for model {model_name} in "
                    f"provider {config.name}"
                )
            if (
                model_config.cost_per_million_tokens is not None
                and model_config.cost_per_million_tokens < 0
            ):
                raise ValueError(
                    f"Invalid cost for model {model_name} in provider {config.name}"
                )

    def _expand_env_var(self, value: Optional[str]) -> Optional[str]:
        """Expand environment variables in configuration values.

        Args:
            value: Value potentially containing env vars

        Returns:
            Expanded value or None

        """
        if not value:
            return None

        if value.startswith('${') and value.endswith('}'):
            # Handle ${VAR} or ${VAR:-default} format
            inner = value[2:-1]
            if ':-' in inner:
                var_name, default = inner.split(':-', 1)
                return os.getenv(var_name, default)
            else:
                return os.getenv(inner)

        return value

    def _apply_environment_overrides(self) -> None:
        """Apply environment variable overrides to configurations."""
        # Check for provider selection
        provider_name = os.getenv('LLM_PROVIDER')
        if provider_name and provider_name in self._configs:
            # Mark only selected provider as enabled
            for name, config in self._configs.items():
                config.enabled = (name == provider_name)

        # Check for model override
        model_override = os.getenv('LLM_MODEL')
        if model_override:
            for config in self._configs.values():
                if config.enabled:
                    config.default_model = model_override

        # Check for timeout override
        timeout = os.getenv('LLM_TIMEOUT')
        if timeout:
            for config in self._configs.values():
                config.extra_params['timeout'] = int(timeout)

        # Check for max retries
        max_retries = os.getenv('LLM_MAX_RETRIES')
        if max_retries:
            for config in self._configs.values():
                config.extra_params['max_retries'] = int(max_retries)

    def get_provider_config(self, name: str) -> Optional[ProviderConfig]:
        """Get configuration for specific provider.

        Args:
            name: Provider name

        Returns:
            Provider configuration or None

        """
        return self._configs.get(name)

    def get_active_provider(self) -> Optional[ProviderConfig]:
        """Get the currently active provider configuration.

        Returns:
            Active provider config or None

        """
        # Check environment first
        provider_name = os.getenv('LLM_PROVIDER')
        if provider_name and provider_name in self._configs:
            return self._configs[provider_name]

        # Prioritize claude_tmux if available and enabled
        if 'claude' in self._configs and self._configs['claude'].enabled:
            # Check if the Claude CLI is actually available
            if self._configs['claude'].cli_path and (
                os.path.exists(self._configs['claude'].cli_path) or
                shutil.which(self._configs['claude'].cli_path)
            ):
                return self._configs['claude']

        # Return first enabled provider with valid configuration
        for config in self._configs.values():
            if config.enabled:
                # Skip API providers without keys
                if config.type in ['venice_api', 'anthropic_api', 'openai_api']:
                    if not config.api_key:
                        continue
                return config

        return None

    def list_providers(self) -> List[str]:
        """List all available provider names.

        Returns:
            List of provider names

        """
        return list(self._configs.keys())

    def list_enabled_providers(self) -> List[str]:
        """List enabled provider names.

        Returns:
            List of enabled provider names

        """
        return [name for name, config in self._configs.items() if config.enabled]

    def save_config(self, path: Optional[Path] = None) -> None:
        """Save current configuration to file.

        Args:
            path: Optional path to save to

        """
        save_path = path or self.config_path
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert configs to dict format
        config_dict = {'providers': {}}
        for name, config in self._configs.items():
            provider_dict = {
                'type': config.type,
                'enabled': config.enabled,
                'default_model': config.default_model,
                'models': {},
                'features': {
                    'interactive': config.features.interactive,
                    'streaming': config.features.streaming,
                    'file_interception': config.features.file_interception,
                    'session_persistence': config.features.session_persistence,
                    'code_execution': config.features.code_execution,
                    'context_extension': config.features.context_extension,
                },
                'extra_params': config.extra_params
            }

            # Add optional fields
            if config.api_key:
                provider_dict['api_key'] = config.api_key
            if config.base_url:
                provider_dict['base_url'] = config.base_url
            if config.cli_path:
                provider_dict['cli_path'] = config.cli_path

            # Convert model mappings
            for model_name, mapping in config.models.items():
                provider_dict['models'][model_name] = {
                    'provider_identifier': mapping.provider_identifier,
                    'category': mapping.category,
                    'context_window': mapping.context_window,
                    'max_output_tokens': mapping.max_output_tokens,
                }
                if mapping.cost_per_million_tokens:
                    provider_dict['models'][model_name][
                        'cost_per_million_tokens'
                    ] = mapping.cost_per_million_tokens

            config_dict['providers'][name] = provider_dict

        # Write to file
        with open(save_path, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)


# Global instance for easy access
_config_manager: Optional[ProviderConfigManager] = None


def get_config_manager() -> ProviderConfigManager:
    """Get global configuration manager instance.

    Returns:
        Configuration manager instance

    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ProviderConfigManager()
    return _config_manager


def get_provider_config(name: str) -> Optional[ProviderConfig]:
    """Get configuration for specific provider with caching.

    Args:
        name: Provider name

    Returns:
        Provider configuration or None

    """
    # Try to import performance module for caching
    try:
        from hydra.providers.performance import memoize_provider_config

        @memoize_provider_config(ttl_seconds=300)
        def _get_config_cached(provider_name: str) -> Optional[ProviderConfig]:
            return get_config_manager().get_provider_config(provider_name)

        return _get_config_cached(name)
    except ImportError:
        # Fallback to non-cached version
        return get_config_manager().get_provider_config(name)


def get_active_provider_config() -> Optional[ProviderConfig]:
    """Get active provider configuration with caching.

    Returns:
        Active provider config or None

    """
    # Try to import performance module for caching
    try:
        from hydra.providers.performance import memoize_provider_config

        @memoize_provider_config(ttl_seconds=300)
        def _get_active_cached() -> Optional[ProviderConfig]:
            return get_config_manager().get_active_provider()

        return _get_active_cached()
    except ImportError:
        # Fallback to non-cached version
        return get_config_manager().get_active_provider()
