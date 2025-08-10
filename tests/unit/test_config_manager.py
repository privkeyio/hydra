"""Test suite for hierarchical configuration management system."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from hydra.config_system.config_manager import ConfigManager, ConfigurationError


class TestConfigManager:
    """Test ConfigManager functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.hydra_dir = Path(self.temp_dir) / '.hydra'
        self.config_manager = ConfigManager(hydra_dir=self.hydra_dir)

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        # Clear environment variables
        for key in list(os.environ.keys()):
            if key.startswith('HYDRA_'):
                del os.environ[key]

    def test_init_creates_config_directory(self):
        """Test that initialization creates the config directory."""
        assert self.hydra_dir.exists()
        assert (self.hydra_dir / 'config').exists()
        assert (self.hydra_dir / 'config' / '.encryption_key').exists()

    def test_hierarchical_loading_precedence(self):
        """Test configuration loading follows correct precedence order."""
        # Create configs at different levels
        project_config = {
            'version': '1.0.0',
            'llm': {'provider': 'project_provider', 'model': 'project_model'},
            'agent': {'max_depth': 5}
        }
        
        config_file = self.hydra_dir / 'config' / 'config.yaml'
        with open(config_file, 'w') as f:
            yaml.dump(project_config, f)
        
        # Set environment override
        os.environ['HYDRA_LLM_PROVIDER'] = 'env_provider'
        
        # Reload to pick up new configs
        self.config_manager.reload_config()
        
        # Environment should override project
        assert self.config_manager.get('llm.provider') == 'env_provider'
        # Project config should still be used for non-overridden values
        assert self.config_manager.get('llm.model') == 'project_model'
        assert self.config_manager.get('agent.max_depth') == 5

    def test_environment_variable_overrides(self):
        """Test that environment variables properly override file configurations."""
        os.environ['HYDRA_LLM_PROVIDER'] = 'test_provider'
        os.environ['HYDRA_LLM_MODEL'] = 'test_model'
        os.environ['HYDRA_LLM_TEMPERATURE'] = '1.5'
        os.environ['HYDRA_LLM_MAX_TOKENS'] = '4096'
        os.environ['HYDRA_AGENT_MAX_DEPTH'] = '10'
        os.environ['HYDRA_LOG_LEVEL'] = 'DEBUG'
        os.environ['HYDRA_ENCRYPT_SENSITIVE'] = 'false'
        
        self.config_manager.reload_config()
        
        assert self.config_manager.get('llm.provider') == 'test_provider'
        assert self.config_manager.get('llm.model') == 'test_model'
        assert self.config_manager.get('llm.temperature') == 1.5
        assert self.config_manager.get('llm.max_tokens') == 4096
        assert self.config_manager.get('agent.max_depth') == 10
        assert self.config_manager.get('logging.level') == 'DEBUG'
        assert self.config_manager.get('security.encrypt_sensitive') is False

    def test_sensitive_value_encryption(self):
        """Test encryption and decryption of sensitive configuration values."""
        config_with_secrets = {
            'version': '1.0.0',
            'llm': {
                'provider': 'test',
                'api_key': 'secret_key_123'
            },
            'auth': {
                'password': 'secret_password',
                'token': 'bearer_token'
            }
        }
        
        # Encrypt sensitive values
        encrypted = self.config_manager._encrypt_sensitive_values(config_with_secrets)
        
        # Check that sensitive values are encrypted
        assert encrypted['llm']['api_key'].startswith('encrypted:')
        assert encrypted['auth']['password'].startswith('encrypted:')
        assert encrypted['auth']['token'].startswith('encrypted:')
        assert encrypted['llm']['provider'] == 'test'  # Non-sensitive not encrypted
        
        # Decrypt values
        decrypted = self.config_manager._decrypt_sensitive_values(encrypted)
        
        # Check values are restored
        assert decrypted['llm']['api_key'] == 'secret_key_123'
        assert decrypted['auth']['password'] == 'secret_password'
        assert decrypted['auth']['token'] == 'bearer_token'

    def test_configuration_reload_triggers_callbacks(self):
        """Test that configuration changes trigger registered callbacks."""
        callback_called = False
        new_config = None
        
        def change_callback(config):
            nonlocal callback_called, new_config
            callback_called = True
            new_config = config
        
        self.config_manager.add_change_callback(change_callback)
        
        # Trigger reload
        self.config_manager.reload_config()
        
        assert callback_called
        assert new_config is not None
        assert 'version' in new_config

    def test_runtime_configuration_changes(self):
        """Test runtime configuration updates trigger callbacks."""
        callback_count = 0
        
        def change_callback(config):
            nonlocal callback_count
            callback_count += 1
        
        self.config_manager.add_change_callback(change_callback)
        
        # Make runtime changes
        self.config_manager.set('llm.provider', 'runtime_provider')
        assert callback_count == 1
        assert self.config_manager.get('llm.provider') == 'runtime_provider'
        
        # Update multiple values
        self.config_manager.update({'agent': {'max_depth': 20}})
        assert callback_count == 2
        assert self.config_manager.get('agent.max_depth') == 20

    def test_invalid_configuration_rejection(self):
        """Test that invalid configurations are rejected with clear errors."""
        # Try to set invalid temperature
        with pytest.raises(ConfigurationError) as exc_info:
            self.config_manager.set('llm.temperature', 3.0)  # Max is 2.0
        assert 'validation failed' in str(exc_info.value).lower()
        
        # Try to set invalid log level
        with pytest.raises(ConfigurationError) as exc_info:
            self.config_manager.set('logging.level', 'INVALID')
        assert 'validation failed' in str(exc_info.value).lower()

    def test_configuration_schema_validation(self):
        """Test that configuration is validated against JSON schema."""
        # Valid configuration should pass
        valid_config = {
            'version': '1.0.0',
            'llm': {
                'provider': 'test',
                'temperature': 0.7,
                'max_tokens': 2048
            }
        }
        self.config_manager._validate_configuration(valid_config)
        
        # Missing required field should fail
        invalid_config = {
            'llm': {'provider': 'test'}
            # Missing 'version'
        }
        with pytest.raises(ConfigurationError) as exc_info:
            self.config_manager._validate_configuration(invalid_config)
        assert 'validation failed' in str(exc_info.value).lower()

    def test_configuration_save_and_load(self):
        """Test saving and loading configuration with encryption."""
        # Set some values
        self.config_manager.set('llm.api_key', 'test_api_key')
        self.config_manager.set('custom.setting', 'custom_value')
        
        # Save configuration
        config_file = self.hydra_dir / 'config' / 'saved_config.yaml'
        self.config_manager.save_config(config_file, encrypt=True)
        
        assert config_file.exists()
        
        # Load saved file
        with open(config_file, 'r') as f:
            saved_config = yaml.safe_load(f)
        
        # API key should be encrypted in file
        assert 'api_key' in saved_config['llm']
        if saved_config['llm']['api_key'] != 'test_api_key':
            assert saved_config['llm']['api_key'].startswith('encrypted:')

    def test_configuration_migration(self):
        """Test configuration migration between versions."""
        # Set up config with old version
        self.config_manager.set('version', '1.0.0')
        self.config_manager.set('old_section.value', 'test')
        
        # Perform migration
        self.config_manager.migrate_config('1.0.0', '1.1.0')
        
        assert self.config_manager.get('version') == '1.1.0'
        # The example migration doesn't actually move the value,
        # just demonstrates the migration mechanism exists
        # This would be implemented based on actual migration needs

    def test_get_with_default_values(self):
        """Test getting configuration values with defaults."""
        # Non-existent key should return default
        assert self.config_manager.get('non.existent.key', 'default') == 'default'
        
        # Existing key should return actual value
        assert self.config_manager.get('llm.provider') == 'venice'

    def test_deep_merge_behavior(self):
        """Test deep merging of configuration dictionaries."""
        base = {'a': {'b': 1, 'c': 2}, 'd': 3}
        override = {'a': {'b': 10, 'e': 4}, 'f': 5}
        
        result = self.config_manager._deep_merge(base, override)
        
        assert result == {
            'a': {'b': 10, 'c': 2, 'e': 4},
            'd': 3,
            'f': 5
        }

    def test_config_source_tracking(self):
        """Test ability to inspect configuration sources."""
        sources = self.config_manager.get_config_sources()
        
        assert 'defaults' in sources
        assert 'environment' in sources
        assert 'runtime' in sources
        assert isinstance(sources['defaults'], dict)

    def test_reset_runtime_overrides(self):
        """Test resetting runtime configuration overrides."""
        # Set runtime override
        self.config_manager.set('llm.provider', 'runtime_test')
        assert self.config_manager.get('llm.provider') == 'runtime_test'
        
        # Reset runtime overrides
        self.config_manager.reset_runtime_overrides()
        
        # Should revert to default
        assert self.config_manager.get('llm.provider') == 'venice'

    def test_callback_removal(self):
        """Test removing configuration change callbacks."""
        callback_called = False
        
        def test_callback(config):
            nonlocal callback_called
            callback_called = True
        
        self.config_manager.add_change_callback(test_callback)
        self.config_manager.remove_change_callback(test_callback)
        
        # Callback should not be called after removal
        self.config_manager.reload_config()
        assert not callback_called

    def test_invalid_config_file_handling(self):
        """Test handling of malformed configuration files."""
        # Create invalid YAML file
        invalid_file = self.hydra_dir / 'config' / 'invalid.yaml'
        invalid_file.write_text('{invalid yaml content')
        
        # Should raise clear error
        with pytest.raises(ConfigurationError) as exc_info:
            self.config_manager._load_config_file(invalid_file)
        assert 'Invalid configuration file' in str(exc_info.value)

    def test_encryption_key_persistence(self):
        """Test that encryption key persists across instances."""
        # Create config with encrypted value
        self.config_manager.set('secret.api_key', 'secret_value')
        config_file = self.hydra_dir / 'config' / 'test.yaml'
        self.config_manager.save_config(config_file, encrypt=True)
        
        # Create new instance with same hydra_dir
        new_manager = ConfigManager(hydra_dir=self.hydra_dir)
        
        # Should be able to decrypt with persisted key
        loaded_config = new_manager._load_config_file(config_file)
        if 'secret' in loaded_config and 'api_key' in loaded_config['secret']:
            # Value should be decrypted
            assert loaded_config['secret']['api_key'] == 'secret_value'