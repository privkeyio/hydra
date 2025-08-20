"""Prompt configuration system for Hydra.

Manages YAML-based prompt configuration with environment overrides,
provider customization, versioning, hot-reload, and validation.
"""

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    # Create dummy classes if watchdog is not available
    class FileSystemEventHandler:
        def on_modified(self, event):
            pass

    class Observer:
        def schedule(self, handler, path, recursive=False):
            pass
        def start(self):
            pass
        def stop(self):
            pass
        def join(self):
            pass

    WATCHDOG_AVAILABLE = False


@dataclass
class PromptVersion:
    """Represents a versioned prompt configuration."""

    version: str
    content: Dict[str, Any]
    timestamp: datetime
    checksum: str


@dataclass
class PromptConfig:
    """Configuration for a single prompt."""

    name: str
    template: str
    variables: List[str] = field(default_factory=list)
    provider_overrides: Dict[str, str] = field(default_factory=dict)
    version: str = "1.0.0"
    description: str = ""
    category: str = "general"


class PromptConfigHandler(FileSystemEventHandler):
    """Handles file system events for hot-reload functionality."""

    def __init__(self, config_manager: 'PromptConfigManager'):
        self.config_manager = config_manager

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(('.yaml', '.yml')):
            self.config_manager._reload_config()


class PromptValidator:
    """Validates prompt templates and configurations."""

    @staticmethod
    def validate_template(template: str, variables: List[str]) -> List[str]:
        """Validate prompt template has all required variables.
        
        Args:
            template: Prompt template string
            variables: List of required variables
            
        Returns:
            List of validation errors

        """
        errors = []

        # Check for required variables
        for var in variables:
            if f"{{{var}}}" not in template and f"{{{{{var}}}}}" not in template:
                errors.append(f"Missing required variable: {var}")

        # Check for undefined variables in template
        import re
        template_vars = re.findall(r'\{([^}]+)\}', template)
        for var in template_vars:
            if var not in variables:
                errors.append(f"Undefined variable in template: {var}")

        return errors

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> List[str]:
        """Validate complete prompt configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            List of validation errors

        """
        errors = []

        required_fields = ['prompts']
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")

        if 'prompts' in config:
            for name, prompt_config in config['prompts'].items():
                if 'template' not in prompt_config:
                    errors.append(f"Prompt '{name}' missing template")
                    continue

                variables = prompt_config.get('variables', [])
                template = prompt_config['template']
                template_errors = PromptValidator.validate_template(template, variables)
                errors.extend([f"Prompt '{name}': {error}" for error in template_errors])

        return errors


class PromptConfigManager:
    """Manages prompt configuration with YAML, overrides, versioning, and hot-reload."""

    def __init__(self, config_path: Optional[str] = None, enable_hot_reload: bool = False):
        """Initialize prompt configuration manager.
        
        Args:
            config_path: Path to YAML configuration file
            enable_hot_reload: Enable file watching for hot-reload

        """
        self.config_path = config_path or self._get_default_config_path()
        self.enable_hot_reload = enable_hot_reload
        self._config: Dict[str, Any] = {}
        self._versions: Dict[str, List[PromptVersion]] = {}
        self._observers: List[Observer] = []
        self._reload_callbacks: List[Callable] = []
        self._lock = threading.RLock()

        self._load_config()

        if enable_hot_reload:
            self._setup_hot_reload()

    def _get_default_config_path(self) -> str:
        """Get default configuration file path."""
        # Check environment variable first
        env_path = os.getenv('HYDRA_PROMPT_CONFIG')
        if env_path:
            return env_path

        # Default to prompts directory
        prompts_dir = Path(__file__).parent
        return str(prompts_dir / 'prompts.yaml')

    def _load_config(self):
        """Load configuration from YAML file."""
        with self._lock:
            try:
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r') as f:
                        self._config = yaml.safe_load(f) or {}
                else:
                    self._config = self._get_default_config()
                    self._save_config()

                # Apply environment variable overrides
                self._apply_env_overrides()

                # Validate configuration
                errors = PromptValidator.validate_config(self._config)
                if errors:
                    raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

                # Store version
                self._store_version()

            except Exception as e:
                print(f"Error loading prompt config: {e}")
                self._config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration if no file exists."""
        return {
            'version': '1.0.0',
            'metadata': {
                'description': 'Hydra prompt configuration',
                'created': datetime.now().isoformat()
            },
            'prompts': {
                'ticket_generation': {
                    'template': 'Generate implementation tickets for: {description}',
                    'variables': ['description'],
                    'category': 'ticket',
                    'description': 'Generates tickets from project description'
                },
                'ticket_execution': {
                    'template': 'Execute ticket: {ticket_id} - {title}',
                    'variables': ['ticket_id', 'title'],
                    'category': 'execution',
                    'description': 'Executes individual tickets'
                },
                'verification': {
                    'template': 'Verify completion of: {criteria}',
                    'variables': ['criteria'],
                    'category': 'verification',
                    'description': 'Verifies ticket completion'
                }
            },
            'provider_overrides': {
                'claude_tmux': {
                    'ticket_execution': 'Execute via tmux: {ticket_id}'
                },
                'venice': {
                    'ticket_execution': 'Venice execution: {ticket_id}'
                }
            },
            'settings': {
                'hot_reload': False,
                'validation_strict': True,
                'version_retention': 10
            }
        }

    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration."""
        # Check for environment variable overrides
        for key, value in os.environ.items():
            if key.startswith('HYDRA_PROMPT_'):
                # Convert HYDRA_PROMPT_TICKET_EXECUTION to ['prompts', 'ticket_execution', 'template']
                parts = key[13:].lower().split('_')  # Remove HYDRA_PROMPT_ prefix

                if len(parts) >= 1:
                    prompt_name = '_'.join(parts)
                    if 'prompts' not in self._config:
                        self._config['prompts'] = {}

                    if prompt_name not in self._config['prompts']:
                        self._config['prompts'][prompt_name] = {
                            'template': value,
                            'variables': [],
                            'category': 'env_override'
                        }
                    else:
                        self._config['prompts'][prompt_name]['template'] = value

    def _store_version(self):
        """Store current configuration as a version."""
        import hashlib

        config_str = yaml.dump(self._config)
        checksum = hashlib.md5(config_str.encode()).hexdigest()
        version = self._config.get('version', '1.0.0')

        if version not in self._versions:
            self._versions[version] = []

        # Check if this exact version already exists
        for existing_version in self._versions[version]:
            if existing_version.checksum == checksum:
                return

        # Add new version
        prompt_version = PromptVersion(
            version=version,
            content=self._config.copy(),
            timestamp=datetime.now(),
            checksum=checksum
        )

        self._versions[version].append(prompt_version)

        # Maintain version retention limit
        retention_limit = self._config.get('settings', {}).get('version_retention', 10)
        if len(self._versions[version]) > retention_limit:
            self._versions[version] = self._versions[version][-retention_limit:]

    def _setup_hot_reload(self):
        """Setup file watching for hot-reload."""
        if not WATCHDOG_AVAILABLE:
            print("Warning: watchdog not available, hot-reload disabled")
            return

        if not os.path.exists(self.config_path):
            return

        config_dir = os.path.dirname(self.config_path)
        event_handler = PromptConfigHandler(self)
        observer = Observer()
        observer.schedule(event_handler, config_dir, recursive=False)
        observer.start()
        self._observers.append(observer)

    def _reload_config(self):
        """Reload configuration from file."""
        old_config = self._config.copy()
        self._load_config()

        # Notify callbacks of reload
        for callback in self._reload_callbacks:
            try:
                callback(old_config, self._config)
            except Exception as e:
                print(f"Error in reload callback: {e}")

    def _save_config(self):
        """Save current configuration to file."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False, indent=2)

    def get_prompt(self, name: str, provider: Optional[str] = None, **variables) -> str:
        """Get formatted prompt by name.
        
        Args:
            name: Prompt name
            provider: Optional provider for overrides
            **variables: Variables to substitute in template
            
        Returns:
            Formatted prompt string

        """
        with self._lock:
            # Check provider-specific override first
            if provider:
                override_path = ['provider_overrides', provider, name]
                override_template = self._get_nested_value(self._config, override_path)
                if override_template:
                    return override_template.format(**variables)

            # Get standard prompt
            prompt_path = ['prompts', name, 'template']
            template = self._get_nested_value(self._config, prompt_path)

            if not template:
                raise KeyError(f"Prompt '{name}' not found")

            return template.format(**variables)

    def get_prompt_config(self, name: str) -> Optional[PromptConfig]:
        """Get prompt configuration object.
        
        Args:
            name: Prompt name
            
        Returns:
            PromptConfig object or None

        """
        with self._lock:
            prompt_data = self._config.get('prompts', {}).get(name)
            if not prompt_data:
                return None

            provider_overrides = {}
            for provider, overrides in self._config.get('provider_overrides', {}).items():
                if name in overrides:
                    provider_overrides[provider] = overrides[name]

            return PromptConfig(
                name=name,
                template=prompt_data.get('template', ''),
                variables=prompt_data.get('variables', []),
                provider_overrides=provider_overrides,
                version=prompt_data.get('version', '1.0.0'),
                description=prompt_data.get('description', ''),
                category=prompt_data.get('category', 'general')
            )

    def list_prompts(self, category: Optional[str] = None) -> List[str]:
        """List available prompt names.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of prompt names

        """
        with self._lock:
            prompts = self._config.get('prompts', {})

            if category:
                return [
                    name for name, config in prompts.items()
                    if config.get('category') == category
                ]

            return list(prompts.keys())

    def get_prompt_variables(self, name: str) -> List[str]:
        """Get required variables for a prompt.
        
        Args:
            name: Prompt name
            
        Returns:
            List of variable names

        """
        prompt_config = self.get_prompt_config(name)
        return prompt_config.variables if prompt_config else []

    def validate_prompt_variables(self, name: str, **variables) -> List[str]:
        """Validate provided variables for a prompt.
        
        Args:
            name: Prompt name
            **variables: Variables to validate
            
        Returns:
            List of missing variables

        """
        required_vars = self.get_prompt_variables(name)
        provided_vars = set(variables.keys())
        required_set = set(required_vars)

        return list(required_set - provided_vars)

    def add_prompt(self, name: str, template: str, variables: List[str],
                   category: str = 'custom', description: str = '') -> bool:
        """Add new prompt to configuration.
        
        Args:
            name: Prompt name
            template: Prompt template
            variables: Required variables
            category: Prompt category
            description: Prompt description
            
        Returns:
            True if added successfully

        """
        with self._lock:
            # Validate template
            errors = PromptValidator.validate_template(template, variables)
            if errors:
                raise ValueError(f"Invalid prompt template: {'; '.join(errors)}")

            if 'prompts' not in self._config:
                self._config['prompts'] = {}

            self._config['prompts'][name] = {
                'template': template,
                'variables': variables,
                'category': category,
                'description': description,
                'version': '1.0.0'
            }

            self._save_config()
            self._store_version()
            return True

    def update_prompt(self, name: str, **updates) -> bool:
        """Update existing prompt configuration.
        
        Args:
            name: Prompt name
            **updates: Fields to update
            
        Returns:
            True if updated successfully

        """
        with self._lock:
            if name not in self._config.get('prompts', {}):
                return False

            prompt_config = self._config['prompts'][name]

            # Validate updates
            if 'template' in updates and 'variables' in updates:
                errors = PromptValidator.validate_template(updates['template'], updates['variables'])
                if errors:
                    raise ValueError(f"Invalid prompt template: {'; '.join(errors)}")

            prompt_config.update(updates)
            self._save_config()
            self._store_version()
            return True

    def delete_prompt(self, name: str) -> bool:
        """Delete prompt from configuration.
        
        Args:
            name: Prompt name
            
        Returns:
            True if deleted successfully

        """
        with self._lock:
            if name not in self._config.get('prompts', {}):
                return False

            del self._config['prompts'][name]
            self._save_config()
            self._store_version()
            return True

    def get_versions(self, version: Optional[str] = None) -> List[PromptVersion]:
        """Get prompt configuration versions.
        
        Args:
            version: Optional specific version
            
        Returns:
            List of PromptVersion objects

        """
        with self._lock:
            if version:
                return self._versions.get(version, [])

            all_versions = []
            for version_list in self._versions.values():
                all_versions.extend(version_list)

            return sorted(all_versions, key=lambda v: v.timestamp, reverse=True)

    def rollback_to_version(self, version: str, timestamp: Optional[datetime] = None) -> bool:
        """Rollback to a specific version.
        
        Args:
            version: Version to rollback to
            timestamp: Optional specific timestamp
            
        Returns:
            True if rollback successful

        """
        with self._lock:
            version_list = self._versions.get(version, [])
            if not version_list:
                return False

            if timestamp:
                target_version = None
                for v in version_list:
                    if v.timestamp == timestamp:
                        target_version = v
                        break
                if not target_version:
                    return False
            else:
                target_version = version_list[-1]  # Latest version

            self._config = target_version.content.copy()
            self._save_config()
            return True

    def add_reload_callback(self, callback: Callable[[Dict, Dict], None]):
        """Add callback for configuration reload events.
        
        Args:
            callback: Function called with (old_config, new_config)

        """
        self._reload_callbacks.append(callback)

    def _get_nested_value(self, data: Dict, path: List[str]) -> Any:
        """Get nested value from dictionary by path."""
        current = data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def cleanup(self):
        """Cleanup resources."""
        for observer in self._observers:
            observer.stop()
            observer.join()
        self._observers.clear()


# Global instance for easy access
_global_config_manager: Optional[PromptConfigManager] = None


def get_config_manager(**kwargs) -> PromptConfigManager:
    """Get global prompt configuration manager instance."""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = PromptConfigManager(**kwargs)
    return _global_config_manager


def get_prompt(name: str, provider: Optional[str] = None, **variables) -> str:
    """Get formatted prompt using global configuration manager."""
    return get_config_manager().get_prompt(name, provider, **variables)


def list_prompts(category: Optional[str] = None) -> List[str]:
    """List available prompts using global configuration manager."""
    return get_config_manager().list_prompts(category)


def validate_prompt_variables(name: str, **variables) -> List[str]:
    """Validate prompt variables using global configuration manager."""
    return get_config_manager().validate_prompt_variables(name, **variables)
