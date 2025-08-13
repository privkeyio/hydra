"""Unit tests for provider discovery utilities."""
import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Set

from hydra.providers.discovery import ProviderDiscovery
from hydra.providers.interactive_base import ProviderConfig, ProviderCapability


class TestProviderDiscovery:
    """Test ProviderDiscovery class."""
    
    def test_known_tools_structure(self):
        """Test that KNOWN_TOOLS has proper structure."""
        assert 'claude' in ProviderDiscovery.KNOWN_TOOLS
        assert 'aider' in ProviderDiscovery.KNOWN_TOOLS
        
        claude_info = ProviderDiscovery.KNOWN_TOOLS['claude']
        assert 'commands' in claude_info
        assert 'provider_name' in claude_info
        assert 'capabilities' in claude_info
        assert isinstance(claude_info['commands'], list)
        assert isinstance(claude_info['capabilities'], set)
    
    @patch('hydra.providers.discovery.ProviderDiscovery._is_command_available')
    def test_discover_all(self, mock_is_available):
        """Test discovering all available tools."""
        # Mock claude as available, aider as not available
        def mock_available(command):
            return command in ['claude', 'claude-cli']
        
        mock_is_available.side_effect = mock_available
        
        discovered = ProviderDiscovery.discover_all()
        
        # Should find at least claude
        assert len(discovered) >= 1
        claude_config = next((c for c in discovered if c.provider_name == 'claude_cli'), None)
        assert claude_config is not None
        assert claude_config.tool_executable in ['claude', 'claude-cli']
        assert ProviderCapability.FILE_OPERATIONS in claude_config.capabilities
    
    @patch('hydra.providers.discovery.ProviderDiscovery._is_command_available')
    def test_discover_by_name(self, mock_is_available):
        """Test discovering a specific tool by name."""
        mock_is_available.return_value = True
        
        config = ProviderDiscovery.discover_by_name('claude')
        assert config is not None
        assert config.provider_name == 'claude_cli'
        assert config.tool_executable in ['claude', 'claude-cli']
        
        # Test non-existent tool
        config = ProviderDiscovery.discover_by_name('nonexistent')
        assert config is None
        
        # Test when tool commands are not available
        mock_is_available.return_value = False
        config = ProviderDiscovery.discover_by_name('claude')
        assert config is None
    
    @patch('shutil.which')
    def test_find_executable_path(self, mock_which):
        """Test finding executable paths."""
        mock_which.return_value = '/usr/bin/claude'
        
        path = ProviderDiscovery.find_executable_path('claude')
        assert path == '/usr/bin/claude'
        mock_which.assert_called_once_with('claude')
        
        mock_which.return_value = None
        path = ProviderDiscovery.find_executable_path('nonexistent')
        assert path is None
    
    @patch('shutil.which')
    def test_is_command_available(self, mock_which):
        """Test command availability checking."""
        mock_which.return_value = '/usr/bin/claude'
        assert ProviderDiscovery._is_command_available('claude') is True
        
        mock_which.return_value = None
        assert ProviderDiscovery._is_command_available('nonexistent') is False
    
    @patch('subprocess.run')
    def test_probe_tool_capabilities(self, mock_run):
        """Test probing tool capabilities."""
        # Mock successful --help output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Usage: tool [options]\nSupports file editing and shell commands"
        mock_run.return_value = mock_result
        
        capabilities = ProviderDiscovery.probe_tool_capabilities('/usr/bin/test-tool')
        
        assert ProviderCapability.TASK_EXECUTION in capabilities
        assert ProviderCapability.FILE_OPERATIONS in capabilities
        assert ProviderCapability.SHELL_EXECUTION in capabilities
        
        # Test tool that doesn't support --help
        mock_result.returncode = 1
        capabilities = ProviderDiscovery.probe_tool_capabilities('/usr/bin/bad-tool')
        assert len(capabilities) == 0
        
        # Test timeout scenario
        mock_run.side_effect = subprocess.TimeoutExpired('test', 10)
        capabilities = ProviderDiscovery.probe_tool_capabilities('/usr/bin/timeout-tool')
        assert len(capabilities) == 0
    
    def test_probe_tool_capabilities_keywords(self):
        """Test capability detection based on help text keywords."""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            # Test different keyword combinations
            test_cases = [
                ("interactive chat interface", {ProviderCapability.TASK_EXECUTION, ProviderCapability.PROMPT_HANDLING}),
                ("streaming responses", {ProviderCapability.TASK_EXECUTION, ProviderCapability.STREAMING_RESPONSE}),
                ("file operations", {ProviderCapability.TASK_EXECUTION, ProviderCapability.FILE_OPERATIONS}),
                ("shell execution", {ProviderCapability.TASK_EXECUTION, ProviderCapability.SHELL_EXECUTION}),
                ("basic tool", {ProviderCapability.TASK_EXECUTION}),
            ]
            
            for help_text, expected_caps in test_cases:
                mock_result.stdout = help_text
                capabilities = ProviderDiscovery.probe_tool_capabilities('/usr/bin/test')
                for cap in expected_caps:
                    assert cap in capabilities, f"Expected {cap} for text: {help_text}"
    
    def test_create_config_from_path(self):
        """Test creating configuration from executable path."""
        with patch.object(ProviderDiscovery, 'probe_tool_capabilities') as mock_probe:
            mock_probe.return_value = {ProviderCapability.FILE_OPERATIONS, ProviderCapability.TASK_EXECUTION}
            
            config = ProviderDiscovery.create_config_from_path('/usr/bin/test-tool')
            
            assert config.provider_name == 'test-tool'
            assert config.tool_executable == '/usr/bin/test-tool'
            assert config.auto_discover is False
            assert ProviderCapability.FILE_OPERATIONS in config.capabilities
            assert ProviderCapability.TASK_EXECUTION in config.capabilities
            
            # Test with custom provider name
            config = ProviderDiscovery.create_config_from_path('/usr/bin/tool', 'custom_name')
            assert config.provider_name == 'custom_name'
    
    def test_scan_directory(self):
        """Test scanning directory for AI tools."""
        with patch('pathlib.Path.exists') as mock_exists, \
             patch('pathlib.Path.is_dir') as mock_is_dir, \
             patch('pathlib.Path.is_file') as mock_is_file:
            
            mock_exists.return_value = True
            mock_is_dir.return_value = True
            
            # Mock that claude executable exists in directory
            def mock_file_exists(path_obj):
                return str(path_obj).endswith('claude')
            
            mock_is_file.side_effect = mock_file_exists
            
            configs = ProviderDiscovery.scan_directory('/usr/bin')
            
            # Should find claude config
            claude_config = next((c for c in configs if c.provider_name == 'claude_cli'), None)
            assert claude_config is not None
            assert claude_config.tool_executable.endswith('claude')
            assert claude_config.auto_discover is False
        
        # Test non-existent directory
        configs = ProviderDiscovery.scan_directory('/nonexistent')
        assert len(configs) == 0
    
    def test_get_supported_tools(self):
        """Test getting list of supported tools."""
        tools = ProviderDiscovery.get_supported_tools()
        
        assert 'claude' in tools
        assert 'aider' in tools
        assert isinstance(tools, list)
        assert len(tools) > 0
    
    def test_add_tool_definition(self):
        """Test adding new tool definition."""
        original_tools = ProviderDiscovery.KNOWN_TOOLS.copy()
        
        try:
            # Add new tool
            ProviderDiscovery.add_tool_definition(
                'new_tool',
                ['newtool', 'nt'],
                'new_provider',
                {ProviderCapability.TASK_EXECUTION}
            )
            
            assert 'new_tool' in ProviderDiscovery.KNOWN_TOOLS
            tool_info = ProviderDiscovery.KNOWN_TOOLS['new_tool']
            assert tool_info['commands'] == ['newtool', 'nt']
            assert tool_info['provider_name'] == 'new_provider'
            assert ProviderCapability.TASK_EXECUTION in tool_info['capabilities']
            
        finally:
            # Restore original tools
            ProviderDiscovery.KNOWN_TOOLS = original_tools
    
    @patch('subprocess.run')
    def test_probe_tool_capabilities_error_handling(self, mock_run):
        """Test error handling in capability probing."""
        # Test CalledProcessError
        mock_run.side_effect = subprocess.CalledProcessError(1, 'test')
        capabilities = ProviderDiscovery.probe_tool_capabilities('/usr/bin/error-tool')
        assert len(capabilities) == 0
        
        # Test FileNotFoundError
        mock_run.side_effect = FileNotFoundError()
        capabilities = ProviderDiscovery.probe_tool_capabilities('/usr/bin/missing-tool')
        assert len(capabilities) == 0
    
    def test_discover_all_no_tools_available(self):
        """Test discover_all when no tools are available."""
        with patch.object(ProviderDiscovery, '_is_command_available', return_value=False):
            discovered = ProviderDiscovery.discover_all()
            assert len(discovered) == 0
    
    @patch('pathlib.Path')
    def test_scan_directory_path_handling(self, mock_path_class):
        """Test directory scanning with various path conditions."""
        # Test when directory doesn't exist
        mock_path = Mock()
        mock_path.exists.return_value = False
        mock_path_class.return_value = mock_path
        
        configs = ProviderDiscovery.scan_directory('/nonexistent')
        assert len(configs) == 0
        
        # Test when path is not a directory
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = False
        
        configs = ProviderDiscovery.scan_directory('/not/a/dir')
        assert len(configs) == 0