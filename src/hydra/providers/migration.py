"""Provider Migration Module.

This module provides utilities to migrate from the old provider architecture
to the new consolidated architecture, maintaining backward compatibility.
"""

import logging
import warnings
from typing import Any, Dict, Optional

from hydra.providers.base import LLMConfig, LLMProvider

from .config_manager import ProviderType, get_config_manager
from .unified_factory import get_provider_factory

logger = logging.getLogger(__name__)


class ProviderMigrator:
    """Handles migration from old provider implementations to unified architecture."""

    # Mapping of old provider names to new profiles
    PROVIDER_MAPPING = {
        "claude_cli": ("claude_simple", {"mode": "simple"}),
        "claude_tmux": ("claude_tmux", {"mode": "tmux"}),
        "claude_cli_enhanced": ("claude_enhanced", {"mode": "enhanced"}),
        "anthropic": ("claude_simple", {"mode": "simple"}),
        "openai": ("openai_gpt4", {}),
        "venice": ("venice", {}),
        "mock": ("mock", {}),
    }

    @classmethod
    def migrate_config(cls, old_config: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate old configuration format to new format.

        Args:
            old_config: Old configuration dictionary

        Returns:
            New configuration dictionary

        """
        new_config = {}

        # Migrate provider type
        old_provider = old_config.get("provider", "claude_tmux")
        if old_provider in cls.PROVIDER_MAPPING:
            profile_name, extra_params = cls.PROVIDER_MAPPING[old_provider]
            new_config["profile"] = profile_name
            new_config["extra_params"] = extra_params.copy()
        else:
            # Unknown provider, try to use as-is
            new_config["profile"] = old_provider
            new_config["extra_params"] = {}

        # Migrate model
        if "model" in old_config:
            new_config["model"] = old_config["model"]

        # Migrate API keys
        if "api_key" in old_config:
            new_config["api_key"] = old_config["api_key"]
        elif "ANTHROPIC_API_KEY" in old_config:
            new_config["api_key"] = old_config["ANTHROPIC_API_KEY"]
        elif "OPENAI_API_KEY" in old_config:
            new_config["api_key"] = old_config["OPENAI_API_KEY"]

        # Migrate other parameters
        skip_keys = {"provider", "model", "api_key", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"}
        for key, value in old_config.items():
            if key not in skip_keys:
                new_config["extra_params"][key] = value

        logger.info(f"Migrated config from {old_provider} to profile {new_config.get('profile')}")
        return new_config

    @classmethod
    def create_provider_from_old_config(
        cls, old_config: Dict[str, Any]
    ) -> LLMProvider:
        """Create a provider instance from old configuration.

        Args:
            old_config: Old configuration dictionary

        Returns:
            Provider instance

        """
        # Migrate configuration
        new_config = cls.migrate_config(old_config)

        # Create provider using new factory
        factory = get_provider_factory()
        return factory.create_provider(
            profile_name=new_config.get("profile"),
            model=new_config.get("model"),
            api_key=new_config.get("api_key"),
            extra_params=new_config.get("extra_params", {}),
        )


class LegacyProviderWrapper:
    """Wrapper to provide backward compatibility for old provider imports."""

    def __init__(self, legacy_name: str):
        """Initialize wrapper for legacy provider.

        Args:
            legacy_name: Name of the legacy provider

        """
        self.legacy_name = legacy_name
        self._provider: Optional[LLMProvider] = None

    def __call__(self, config: LLMConfig) -> LLMProvider:
        """Create provider instance (callable for backward compatibility).

        Args:
            config: Provider configuration

        Returns:
            Provider instance

        """
        warnings.warn(
            f"Using legacy provider '{self.legacy_name}' is deprecated. "
            f"Please use the unified provider architecture.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Convert to new architecture
        old_config = {
            "provider": self.legacy_name,
            "model": config.model,
            "api_key": config.api_key,
            **config.extra_params,
        }

        self._provider = ProviderMigrator.create_provider_from_old_config(old_config)
        return self._provider

    def __getattr__(self, name):
        """Forward attribute access to the actual provider."""
        if self._provider is None:
            raise RuntimeError(
                f"Legacy provider '{self.legacy_name}' not initialized. "
                f"Call the wrapper with a config first."
            )
        return getattr(self._provider, name)


# Legacy provider classes for backward compatibility
class ClaudeCLIProvider(LegacyProviderWrapper):
    """Legacy ClaudeCLIProvider for backward compatibility."""

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize legacy provider."""
        super().__init__("claude_cli")
        if config:
            self.__call__(config)


class ClaudeTmuxProvider(LegacyProviderWrapper):
    """Legacy ClaudeTmuxProvider for backward compatibility."""

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize legacy provider."""
        super().__init__("claude_tmux")
        if config:
            self.__call__(config)


class ClaudeCLIEnhancedProvider(LegacyProviderWrapper):
    """Legacy ClaudeCLIEnhancedProvider for backward compatibility."""

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize legacy provider."""
        super().__init__("claude_cli_enhanced")
        if config:
            self.__call__(config)


def migrate_provider_imports():
    """Monkey-patch old provider imports to use new architecture.

    This function should be called early in the application startup
    to ensure backward compatibility.
    """
    import sys

    # Create module aliases
    sys.modules["hydra.providers.claude_cli"] = sys.modules[__name__]
    sys.modules["hydra.providers.claude_tmux"] = sys.modules[__name__]
    sys.modules["hydra.providers.claude_cli_enhanced"] = sys.modules[__name__]

    logger.info("Provider imports migrated to unified architecture")


def check_provider_compatibility(config: Dict[str, Any]) -> Dict[str, Any]:
    """Check and report compatibility issues with old configuration.

    Args:
        config: Configuration to check

    Returns:
        Dictionary with compatibility report

    """
    report = {
        "compatible": True,
        "warnings": [],
        "errors": [],
        "suggestions": [],
    }

    # Check provider type
    provider = config.get("provider", config.get("provider_type"))
    if provider:
        if provider in ProviderMigrator.PROVIDER_MAPPING:
            report["suggestions"].append(
                f"Provider '{provider}' can be migrated to new architecture"
            )
        elif provider not in ["claude", "openai", "venice", "mock"]:
            report["warnings"].append(f"Unknown provider type: {provider}")
            report["compatible"] = False

    # Check for deprecated parameters
    deprecated_params = ["claude_path", "tmux_timeout", "use_tmux"]
    for param in deprecated_params:
        if param in config:
            report["warnings"].append(
                f"Parameter '{param}' is deprecated. It will be migrated to extra_params"
            )

    # Check for missing required parameters
    if not provider and not config.get("profile"):
        report["errors"].append("No provider or profile specified")
        report["compatible"] = False

    return report


def auto_migrate_project_config(project_path: str) -> bool:
    """Automatically migrate project configuration to new architecture.

    Args:
        project_path: Path to the project

    Returns:
        True if migration successful

    """
    import json
    from pathlib import Path

    config_file = Path(project_path) / ".hydra" / "config.json"

    if not config_file.exists():
        logger.info("No configuration file found, skipping migration")
        return True

    try:
        # Load old configuration
        with open(config_file, "r") as f:
            old_config = json.load(f)

        # Check if already migrated
        if "profiles" in old_config:
            logger.info("Configuration already migrated")
            return True

        # Backup old configuration
        backup_file = config_file.with_suffix(".json.backup")
        with open(backup_file, "w") as f:
            json.dump(old_config, f, indent=2)
        logger.info(f"Backed up old configuration to {backup_file}")

        # Migrate configuration
        new_config = ProviderMigrator.migrate_config(old_config)

        # Save new configuration
        config_manager = get_config_manager()
        profile_name = new_config.get("profile", "migrated")

        # Create profile from migrated config
        from .config_manager import ProviderProfile

        profile = ProviderProfile(
            name=profile_name,
            provider_type=ProviderType.CLAUDE,  # Default to Claude
            model=new_config.get("model", "smart"),
            api_key=new_config.get("api_key"),
            extra_params=new_config.get("extra_params", {}),
        )

        config_manager.add_profile(profile)
        config_manager.set_default_profile(profile_name)

        logger.info(f"Successfully migrated configuration to profile '{profile_name}'")
        return True

    except Exception as e:
        logger.error(f"Failed to migrate configuration: {e}")
        return False
