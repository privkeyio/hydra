"""Hierarchical configuration management system for Hydra.

This module provides a comprehensive configuration management system that supports:
- Multiple configuration sources with proper precedence
- Environment variable overrides
- Configuration validation with JSON schema
- Runtime configuration updates
- Secure handling of sensitive values
- Configuration migration for version compatibility
"""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from cryptography.fernet import Fernet
from jsonschema import ValidationError, validate


class ConfigurationError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""

    pass

class ConfigManager:
    """Hierarchical configuration manager with validation and security features."""

    # Configuration precedence order (higher index = higher precedence)
    PRECEDENCE_ORDER = [
        'defaults',
        'system',
        'user',
        'project',
        'environment',
        'runtime'
    ]

    # Default schema for configuration validation
    DEFAULT_SCHEMA = {
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "llm": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "model": {"type": ["string", "null"]},
                    "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0},
                    "max_tokens": {"type": "integer", "minimum": 1},
                    "timeout": {"type": "integer", "minimum": 1}
                },
                "required": ["provider"]
            },
            "agent": {
                "type": "object",
                "properties": {
                    "max_depth": {"type": "integer", "minimum": 1},
                    "retry_attempts": {"type": "integer", "minimum": 0},
                    "timeout": {"type": "integer", "minimum": 1}
                }
            },
            "logging": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
                    },
                    "file": {"type": "string"},
                    "max_bytes": {"type": "integer", "minimum": 1},
                    "backup_count": {"type": "integer", "minimum": 0}
                }
            },
            "security": {
                "type": "object",
                "properties": {
                    "encrypt_sensitive": {"type": "boolean"},
                    "allowed_paths": {"type": "array", "items": {"type": "string"}},
                    "blocked_operations": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "required": ["version", "llm"]
    }

    def __init__(self,
                 hydra_dir: Optional[Path] = None,
                 config_schema: Optional[Dict] = None,
                 encryption_key: Optional[bytes] = None):
        """Initialize configuration manager.

        Args:
            hydra_dir: Path to .hydra directory (defaults to current dir/.hydra)
            config_schema: JSON schema for configuration validation
            encryption_key: Key for encrypting sensitive values (generates if None)

        """
        self.hydra_dir = hydra_dir or Path.cwd() / '.hydra'
        self.config_dir = self.hydra_dir / 'config'
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Initialize encryption for sensitive values
        self._init_encryption(encryption_key)

        # Configuration schema
        self.schema = config_schema or self.DEFAULT_SCHEMA

        # Configuration sources storage
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._merged_config: Optional[Dict[str, Any]] = None
        self._change_callbacks: List[Callable[[Dict[str, Any]], None]] = []

        # Load all configuration sources
        self._load_all_configs()

        # Initialize runtime overrides
        self._runtime_overrides: Dict[str, Any] = {}

    def _init_encryption(self, encryption_key: Optional[bytes] = None):
        """Initialize encryption for sensitive configuration values."""
        key_file = self.config_dir / '.encryption_key'

        if encryption_key:
            self._encryption_key = encryption_key
            # Save key for future use
            key_file.write_bytes(self._encryption_key)
        elif key_file.exists():
            # Load existing key
            self._encryption_key = key_file.read_bytes()
        else:
            # Generate new key
            self._encryption_key = Fernet.generate_key()
            key_file.write_bytes(self._encryption_key)
            key_file.chmod(0o600)  # Restrict access

        self._fernet = Fernet(self._encryption_key)

    def _load_all_configs(self):
        """Load configuration from all sources in precedence order."""
        for source in self.PRECEDENCE_ORDER[:-2]:  # Exclude environment and runtime
            if source == 'defaults':
                self._configs[source] = self._get_default_config()
            elif source == 'system':
                self._configs[source] = self._load_system_config()
            elif source == 'user':
                self._configs[source] = self._load_user_config()
            elif source == 'project':
                self._configs[source] = self._load_project_config()

        # Load environment overrides
        self._configs['environment'] = self._load_environment_overrides()

        # Initialize runtime overrides
        self._configs['runtime'] = {}

        # Merge all configurations
        self._merge_configs()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            "version": "1.0.0",
            "llm": {
                "provider": "venice",
                "model": None,
                "temperature": 0.2,
                "max_tokens": 2048,
                "timeout": 120
            },
            "agent": {
                "max_depth": 2,
                "retry_attempts": 2,
                "timeout": 30
            },
            "logging": {
                "level": "INFO",
                "file": "logs/hydra.log",
                "max_bytes": 10485760,
                "backup_count": 5
            },
            "security": {
                "encrypt_sensitive": True,
                "allowed_paths": ["."],
                "blocked_operations": ["rm -rf", "format", "fdisk"]
            }
        }

    def _load_system_config(self) -> Dict[str, Any]:
        """Load system-wide configuration."""
        system_paths = [
            Path('/etc/hydra/config.yaml'),
            Path('/etc/hydra/config.yml'),
            Path('/usr/local/etc/hydra/config.yaml')
        ]

        for path in system_paths:
            if path.exists():
                return self._load_config_file(path)

        return {}

    def _load_user_config(self) -> Dict[str, Any]:
        """Load user-specific configuration."""
        user_config_dir = Path.home() / '.hydra' / 'config'
        config_files = ['config.yaml', 'config.yml', 'hydra.yaml']

        for filename in config_files:
            config_path = user_config_dir / filename
            if config_path.exists():
                return self._load_config_file(config_path)

        return {}

    def _load_project_config(self) -> Dict[str, Any]:
        """Load project-specific configuration."""
        config_files = [
            self.config_dir / 'config.yaml',
            self.config_dir / 'config.yml',
            self.config_dir / 'hydra.yaml'
        ]

        for config_path in config_files:
            if config_path.exists():
                return self._load_config_file(config_path)

        return {}

    def _load_environment_overrides(self) -> Dict[str, Any]:
        """Load configuration overrides from environment variables."""
        overrides = {}

        # LLM configuration
        if os.getenv('HYDRA_LLM_PROVIDER'):
            overrides.setdefault('llm', {})['provider'] = os.getenv('HYDRA_LLM_PROVIDER')

        if os.getenv('HYDRA_LLM_MODEL'):
            overrides.setdefault('llm', {})['model'] = os.getenv('HYDRA_LLM_MODEL')

        if os.getenv('HYDRA_LLM_TEMPERATURE'):
            try:
                overrides.setdefault('llm', {})['temperature'] = float(os.getenv('HYDRA_LLM_TEMPERATURE'))
            except ValueError:
                pass

        if os.getenv('HYDRA_LLM_MAX_TOKENS'):
            try:
                overrides.setdefault('llm', {})['max_tokens'] = int(os.getenv('HYDRA_LLM_MAX_TOKENS'))
            except ValueError:
                pass

        if os.getenv('HYDRA_LLM_TIMEOUT'):
            try:
                overrides.setdefault('llm', {})['timeout'] = int(os.getenv('HYDRA_LLM_TIMEOUT'))
            except ValueError:
                pass

        # Agent configuration
        if os.getenv('HYDRA_AGENT_MAX_DEPTH'):
            try:
                overrides.setdefault('agent', {})['max_depth'] = int(os.getenv('HYDRA_AGENT_MAX_DEPTH'))
            except ValueError:
                pass

        if os.getenv('HYDRA_AGENT_RETRY_ATTEMPTS'):
            try:
                overrides.setdefault('agent', {})['retry_attempts'] = int(os.getenv('HYDRA_AGENT_RETRY_ATTEMPTS'))
            except ValueError:
                pass

        # Logging configuration
        if os.getenv('HYDRA_LOG_LEVEL'):
            overrides.setdefault('logging', {})['level'] = os.getenv('HYDRA_LOG_LEVEL')

        if os.getenv('HYDRA_LOG_FILE'):
            overrides.setdefault('logging', {})['file'] = os.getenv('HYDRA_LOG_FILE')

        # Security configuration
        if os.getenv('HYDRA_ENCRYPT_SENSITIVE'):
            overrides.setdefault('security', {})['encrypt_sensitive'] = os.getenv('HYDRA_ENCRYPT_SENSITIVE').lower() == 'true'

        return overrides

    def _load_config_file(self, config_path: Path) -> Dict[str, Any]:
        """Load configuration from a file with proper error handling."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix in ['.yaml', '.yml']:
                    config = yaml.safe_load(f)
                elif config_path.suffix == '.json':
                    config = json.load(f)
                else:
                    raise ConfigurationError(f"Unsupported config file format: {config_path}")

            # Decrypt sensitive values if needed
            return self._decrypt_sensitive_values(config or {})

        except (yaml.YAMLError, json.JSONDecodeError) as e:
            raise ConfigurationError(f"Invalid configuration file {config_path}: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration file {config_path}: {e}")

    def _merge_configs(self):
        """Merge all configuration sources according to precedence."""
        merged = {}

        for source in self.PRECEDENCE_ORDER:
            source_config = self._configs.get(source, {})
            if source_config:
                merged = self._deep_merge(merged, source_config)

        self._merged_config = merged
        self._validate_configuration(self._merged_config)

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries, with override taking precedence."""
        result = deepcopy(base)

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)

        return result

    def _validate_configuration(self, config: Dict[str, Any]):
        """Validate configuration against JSON schema."""
        try:
            validate(instance=config, schema=self.schema)
        except ValidationError as e:
            raise ConfigurationError(f"Configuration validation failed: {e.message}") from e

    def _encrypt_sensitive_values(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive configuration values."""
        if not self.get('security.encrypt_sensitive', True):
            return config

        result = deepcopy(config)
        sensitive_keys = ['api_key', 'password', 'secret', 'token', 'key']

        def encrypt_recursive(obj: Any, path: str = '') -> Any:
            if isinstance(obj, dict):
                return {k: encrypt_recursive(v, f"{path}.{k}" if path else k) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [encrypt_recursive(item, f"{path}[{i}]") for i, item in enumerate(obj)]
            elif isinstance(obj, str) and any(key in path.lower() for key in sensitive_keys):
                if not obj.startswith('encrypted:'):
                    encrypted = self._fernet.encrypt(obj.encode()).decode()
                    return f"encrypted:{encrypted}"
            return obj

        return encrypt_recursive(result)

    def _decrypt_sensitive_values(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive configuration values."""
        result = deepcopy(config)

        def decrypt_recursive(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: decrypt_recursive(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [decrypt_recursive(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith('encrypted:'):
                try:
                    encrypted_data = obj[10:]  # Remove 'encrypted:' prefix
                    return self._fernet.decrypt(encrypted_data.encode()).decode()
                except Exception:
                    # Return original if decryption fails
                    return obj
            return obj

        return decrypt_recursive(result)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation."""
        if self._merged_config is None:
            return default

        keys = key_path.split('.')
        value = self._merged_config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any, source: str = 'runtime'):
        """Set configuration value with runtime override."""
        if source not in self.PRECEDENCE_ORDER:
            raise ConfigurationError(f"Invalid configuration source: {source}")

        keys = key_path.split('.')
        config_source = self._configs.setdefault(source, {})

        # Navigate to the parent dict
        for key in keys[:-1]:
            config_source = config_source.setdefault(key, {})

        # Set the value
        config_source[keys[-1]] = value

        # Re-merge and validate
        old_config = deepcopy(self._merged_config)
        self._merge_configs()

        # Notify change callbacks
        self._notify_change_callbacks(old_config, self._merged_config)

    def update(self, config_updates: Dict[str, Any], source: str = 'runtime'):
        """Update multiple configuration values."""
        for key_path, value in self._flatten_dict(config_updates).items():
            self.set(key_path, value, source)

    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = '') -> Dict[str, str]:
        """Flatten nested dictionary with dot notation keys."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def save_config(self, config_path: Optional[Path] = None, encrypt: bool = True):
        """Save current configuration to file."""
        if config_path is None:
            config_path = self.config_dir / 'config.yaml'

        config_to_save = deepcopy(self._merged_config)

        if encrypt:
            config_to_save = self._encrypt_sensitive_values(config_to_save)

        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_to_save, f, default_flow_style=False, sort_keys=False)

    def reload_config(self):
        """Reload configuration from all sources."""
        old_config = deepcopy(self._merged_config)
        self._load_all_configs()
        self._notify_change_callbacks(old_config, self._merged_config)

    def add_change_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add callback to be notified of configuration changes."""
        self._change_callbacks.append(callback)

    def remove_change_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Remove configuration change callback."""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)

    def _notify_change_callbacks(self, old_config: Dict[str, Any], new_config: Dict[str, Any]):
        """Notify all registered callbacks of configuration changes."""
        for callback in self._change_callbacks:
            try:
                callback(new_config)
            except Exception as e:
                # Log error but don't let callback failures affect configuration
                print(f"Configuration change callback failed: {e}")

    def migrate_config(self, from_version: str, to_version: str):
        """Migrate configuration from one version to another."""
        migration_map = {
            ("1.0.0", "1.1.0"): self._migrate_1_0_to_1_1,
            # Add more migration functions as needed
        }

        migration_func = migration_map.get((from_version, to_version))
        if migration_func:
            self._merged_config = migration_func(self._merged_config)
            self.set('version', to_version)
        else:
            raise ConfigurationError(f"No migration path from {from_version} to {to_version}")

    def _migrate_1_0_to_1_1(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate configuration from version 1.0.0 to 1.1.0."""
        # Example: rename old key to new key
        if 'old_section' in config:
            config['new_section'] = config.pop('old_section')
        return config

    def get_config_sources(self) -> Dict[str, Dict[str, Any]]:
        """Get all configuration sources for debugging."""
        return deepcopy(self._configs)

    def get_merged_config(self) -> Dict[str, Any]:
        """Get the final merged configuration."""
        return deepcopy(self._merged_config) if self._merged_config else {}

    def validate_config(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Validate configuration against schema."""
        config_to_validate = config or self._merged_config
        if not config_to_validate:
            return False

        try:
            self._validate_configuration(config_to_validate)
            return True
        except ConfigurationError:
            return False

    def reset_runtime_overrides(self):
        """Reset all runtime configuration overrides."""
        self._configs['runtime'] = {}
        self._merge_configs()
