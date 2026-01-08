"""Provider Configuration Manager.

This module provides centralized configuration management for all providers,
making it easy to switch between different provider configurations and modes.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import orjson


class ProviderType(Enum):
    """Supported provider types."""

    CLAUDE = "claude"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    VENICE = "venice"
    MOCK = "mock"


@dataclass
class ProviderProfile:
    """Provider configuration profile."""

    name: str
    provider_type: ProviderType
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 0  # Higher priority = preferred provider


@dataclass
class ProviderConfiguration:
    """Complete provider configuration."""

    profiles: Dict[str, ProviderProfile]
    default_profile: str
    fallback_chain: List[str] = field(default_factory=list)
    global_settings: Dict[str, Any] = field(default_factory=dict)


class ConfigurationManager:
    """Manages provider configurations and profiles."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration manager.

        Args:
            config_path: Path to configuration file

        """
        self.config_path = config_path or self._get_default_config_path()
        self.configuration: Optional[ProviderConfiguration] = None
        self._load_configuration()

    def _get_default_config_path(self) -> Path:
        """Get default configuration path."""
        # Check environment variable
        if env_path := os.environ.get("HYDRA_CONFIG_PATH"):
            return Path(env_path)

        # Check user config directory
        config_dir = Path.home() / ".config" / "hydra"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "providers.json"

    def _load_configuration(self):
        """Load configuration from file or create default."""
        if self.config_path.exists():
            with open(self.config_path, "rb") as f:
                data = orjson.loads(f.read())
                self.configuration = self._parse_configuration(data)
        else:
            self.configuration = self._create_default_configuration()
            self.save_configuration()

    def _parse_configuration(self, data: Dict) -> ProviderConfiguration:
        """Parse configuration from dictionary."""
        profiles = {}
        for name, profile_data in data.get("profiles", {}).items():
            profiles[name] = ProviderProfile(
                name=name,
                provider_type=ProviderType(profile_data["provider_type"]),
                model=profile_data["model"],
                api_key=profile_data.get("api_key"),
                base_url=profile_data.get("base_url"),
                extra_params=profile_data.get("extra_params", {}),
                environment=profile_data.get("environment", {}),
                enabled=profile_data.get("enabled", True),
                priority=profile_data.get("priority", 0),
            )

        return ProviderConfiguration(
            profiles=profiles,
            default_profile=data.get("default_profile", "claude_tmux"),
            fallback_chain=data.get("fallback_chain", []),
            global_settings=data.get("global_settings", {}),
        )

    def _create_default_configuration(self) -> ProviderConfiguration:
        """Create default provider configuration."""
        profiles = {
            # Claude profiles
            "claude_simple": ProviderProfile(
                name="claude_simple",
                provider_type=ProviderType.CLAUDE,
                model="smart",
                extra_params={
                    "mode": "simple",
                    "max_retries": 3,
                },
                priority=1,
            ),
            "claude_tmux": ProviderProfile(
                name="claude_tmux",
                provider_type=ProviderType.CLAUDE,
                model="smart",
                extra_params={
                    "mode": "tmux",
                    "tmux_timeout": 300,
                    "max_retries": 3,
                },
                priority=3,
            ),
            "claude_enhanced": ProviderProfile(
                name="claude_enhanced",
                provider_type=ProviderType.CLAUDE,
                model="smart",
                extra_params={
                    "mode": "enhanced",
                    "file_interception": True,
                    "session_persistence": True,
                    "max_retries": 3,
                },
                priority=2,
            ),
            # OpenAI profile
            "openai_gpt4": ProviderProfile(
                name="openai_gpt4",
                provider_type=ProviderType.OPENAI,
                model="gpt-4-turbo-preview",
                api_key=os.environ.get("OPENAI_API_KEY"),
                extra_params={
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
                enabled=bool(os.environ.get("OPENAI_API_KEY")),
                priority=1,
            ),
            # Venice profile
            "venice": ProviderProfile(
                name="venice",
                provider_type=ProviderType.VENICE,
                model="llama-3.3-70b",
                api_key=os.environ.get("VENICE_API_KEY"),
                base_url="https://api.venice.ai/api/v1",
                enabled=bool(os.environ.get("VENICE_API_KEY")),
                priority=0,
            ),
            # Mock profile for testing
            "mock": ProviderProfile(
                name="mock",
                provider_type=ProviderType.MOCK,
                model="mock-model",
                extra_params={"response": "Mock response"},
                enabled=True,
                priority=-1,
            ),
        }

        return ProviderConfiguration(
            profiles=profiles,
            default_profile="claude_tmux",
            fallback_chain=["claude_tmux", "claude_enhanced", "claude_simple"],
            global_settings={
                "timeout": 300,
                "max_retries": 3,
                "enable_telemetry": False,
                "cache_responses": True,
            },
        )

    def save_configuration(self):
        """Save configuration to file."""
        if not self.configuration:
            return

        data = {
            "profiles": {},
            "default_profile": self.configuration.default_profile,
            "fallback_chain": self.configuration.fallback_chain,
            "global_settings": self.configuration.global_settings,
        }

        for name, profile in self.configuration.profiles.items():
            data["profiles"][name] = {
                "provider_type": profile.provider_type.value,
                "model": profile.model,
                "api_key": profile.api_key,
                "base_url": profile.base_url,
                "extra_params": profile.extra_params,
                "environment": profile.environment,
                "enabled": profile.enabled,
                "priority": profile.priority,
            }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "wb") as f:
            f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

    def get_profile(self, name: str) -> Optional[ProviderProfile]:
        """Get a specific provider profile.

        Args:
            name: Profile name

        Returns:
            Provider profile or None if not found

        """
        if not self.configuration:
            return None
        return self.configuration.profiles.get(name)

    def get_default_profile(self) -> Optional[ProviderProfile]:
        """Get the default provider profile.

        Returns:
            Default provider profile or None

        """
        if not self.configuration:
            return None
        return self.configuration.profiles.get(self.configuration.default_profile)

    def get_enabled_profiles(self) -> List[ProviderProfile]:
        """Get all enabled provider profiles sorted by priority.

        Returns:
            List of enabled profiles sorted by priority (highest first)

        """
        if not self.configuration:
            return []

        enabled = [p for p in self.configuration.profiles.values() if p.enabled]
        return sorted(enabled, key=lambda p: p.priority, reverse=True)

    def get_fallback_profiles(self) -> List[ProviderProfile]:
        """Get fallback provider profiles in order.

        Returns:
            List of fallback profiles

        """
        if not self.configuration:
            return []

        profiles = []
        for name in self.configuration.fallback_chain:
            if profile := self.get_profile(name):
                if profile.enabled:
                    profiles.append(profile)
        return profiles

    def add_profile(self, profile: ProviderProfile) -> bool:
        """Add a new provider profile.

        Args:
            profile: Provider profile to add

        Returns:
            True if added successfully

        """
        if not self.configuration:
            return False

        self.configuration.profiles[profile.name] = profile
        self.save_configuration()
        return True

    def remove_profile(self, name: str) -> bool:
        """Remove a provider profile.

        Args:
            name: Profile name to remove

        Returns:
            True if removed successfully

        """
        if not self.configuration or name not in self.configuration.profiles:
            return False

        del self.configuration.profiles[name]

        # Update default if necessary
        if self.configuration.default_profile == name:
            if self.configuration.profiles:
                self.configuration.default_profile = next(
                    iter(self.configuration.profiles.keys())
                )
            else:
                self.configuration.default_profile = ""

        # Remove from fallback chain
        self.configuration.fallback_chain = [
            p for p in self.configuration.fallback_chain if p != name
        ]

        self.save_configuration()
        return True

    def update_profile(self, name: str, **kwargs) -> bool:
        """Update a provider profile.

        Args:
            name: Profile name to update
            **kwargs: Fields to update

        Returns:
            True if updated successfully

        """
        if not self.configuration or name not in self.configuration.profiles:
            return False

        profile = self.configuration.profiles[name]

        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        self.save_configuration()
        return True

    def set_default_profile(self, name: str) -> bool:
        """Set the default provider profile.

        Args:
            name: Profile name to set as default

        Returns:
            True if set successfully

        """
        if not self.configuration or name not in self.configuration.profiles:
            return False

        self.configuration.default_profile = name
        self.save_configuration()
        return True

    def set_fallback_chain(self, chain: List[str]) -> bool:
        """Set the fallback provider chain.

        Args:
            chain: List of profile names in fallback order

        Returns:
            True if set successfully

        """
        if not self.configuration:
            return False

        # Validate all profiles exist
        for name in chain:
            if name not in self.configuration.profiles:
                return False

        self.configuration.fallback_chain = chain
        self.save_configuration()
        return True

    def export_configuration(self, path: Path):
        """Export configuration to a file.

        Args:
            path: Path to export to

        """
        if not self.configuration:
            return

        # Create a copy without sensitive data
        export_data = {
            "profiles": {},
            "default_profile": self.configuration.default_profile,
            "fallback_chain": self.configuration.fallback_chain,
            "global_settings": self.configuration.global_settings,
        }

        for name, profile in self.configuration.profiles.items():
            export_data["profiles"][name] = {
                "provider_type": profile.provider_type.value,
                "model": profile.model,
                "base_url": profile.base_url,
                "extra_params": profile.extra_params,
                "environment": profile.environment,
                "enabled": profile.enabled,
                "priority": profile.priority,
                # Mask API keys
                "api_key": "***" if profile.api_key else None,
            }

        with open(path, "wb") as f:
            f.write(orjson.dumps(export_data, option=orjson.OPT_INDENT_2))

    def import_configuration(self, path: Path, merge: bool = False):
        """Import configuration from a file.

        Args:
            path: Path to import from
            merge: Whether to merge with existing configuration

        """
        with open(path, "rb") as f:
            data = orjson.loads(f.read())

        new_config = self._parse_configuration(data)

        if merge and self.configuration:
            # Merge profiles
            self.configuration.profiles.update(new_config.profiles)

            # Keep existing settings if not in import
            if not new_config.default_profile:
                new_config.default_profile = self.configuration.default_profile
            if not new_config.fallback_chain:
                new_config.fallback_chain = self.configuration.fallback_chain

            self.configuration = new_config
        else:
            self.configuration = new_config

        self.save_configuration()


# Global configuration manager instance
_config_manager: Optional[ConfigurationManager] = None


def get_config_manager() -> ConfigurationManager:
    """Get or create the global configuration manager.

    Returns:
        Configuration manager instance

    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigurationManager()
    return _config_manager


def reset_config_manager():
    """Reset the global configuration manager."""
    global _config_manager
    _config_manager = None
