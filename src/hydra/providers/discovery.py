"""Provider discovery utilities.

This module provides utilities for automatically discovering available AI tools
in the system PATH and creating appropriate provider configurations.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Set

from .interactive_base import ProviderCapability, ProviderConfig


class ProviderDiscovery:
    """Utility class for discovering available AI providers in the system."""

    # Known AI tools and their typical command names
    KNOWN_TOOLS = {
        "claude": {
            "commands": ["claude", "claude-cli"],
            "provider_name": "claude_cli",
            "capabilities": {
                ProviderCapability.FILE_OPERATIONS,
                ProviderCapability.SHELL_EXECUTION,
                ProviderCapability.TASK_EXECUTION,
                ProviderCapability.PROMPT_HANDLING,
                ProviderCapability.SESSION_PERSISTENCE,
            },
        },
        "aider": {
            "commands": ["aider"],
            "provider_name": "aider",
            "capabilities": {
                ProviderCapability.FILE_OPERATIONS,
                ProviderCapability.TASK_EXECUTION,
                ProviderCapability.TOOL_INTEGRATION,
            },
        },
        "cursor": {
            "commands": ["cursor"],
            "provider_name": "cursor",
            "capabilities": {
                ProviderCapability.FILE_OPERATIONS,
                ProviderCapability.TASK_EXECUTION,
            },
        },
        "codeium": {
            "commands": ["codeium"],
            "provider_name": "codeium",
            "capabilities": {
                ProviderCapability.FILE_OPERATIONS,
                ProviderCapability.TASK_EXECUTION,
            },
        },
        "copilot": {
            "commands": ["gh", "github-copilot-cli"],
            "provider_name": "github_copilot",
            "capabilities": {
                ProviderCapability.TASK_EXECUTION,
                ProviderCapability.SHELL_EXECUTION,
            },
        },
    }

    @classmethod
    def discover_all(cls) -> List[ProviderConfig]:
        """Discover all available AI tools in the system.

        Returns:
            List[ProviderConfig]: List of configurations for discovered providers.

        """
        discovered = []

        for _tool_name, tool_info in cls.KNOWN_TOOLS.items():
            for command in tool_info["commands"]:
                if cls._is_command_available(command):
                    config = ProviderConfig(
                        provider_name=tool_info["provider_name"],
                        tool_executable=command,
                        auto_discover=True,
                        capabilities=tool_info["capabilities"],
                    )
                    discovered.append(config)
                    break  # Only add one config per tool

        return discovered

    @classmethod
    def discover_by_name(cls, tool_name: str) -> Optional[ProviderConfig]:
        """Discover a specific AI tool by name.

        Args:
            tool_name: Name of the tool to discover.

        Returns:
            Optional[ProviderConfig]: Configuration if tool is found, None otherwise.

        """
        if tool_name not in cls.KNOWN_TOOLS:
            return None

        tool_info = cls.KNOWN_TOOLS[tool_name]

        for command in tool_info["commands"]:
            if cls._is_command_available(command):
                return ProviderConfig(
                    provider_name=tool_info["provider_name"],
                    tool_executable=command,
                    auto_discover=True,
                    capabilities=tool_info["capabilities"],
                )

        return None

    @classmethod
    def find_executable_path(cls, command: str) -> Optional[str]:
        """Find the full path to an executable command.

        Args:
            command: Command name to find.

        Returns:
            Optional[str]: Full path to executable if found, None otherwise.

        """
        return shutil.which(command)

    @classmethod
    def _is_command_available(cls, command: str) -> bool:
        """Check if a command is available in the system PATH.

        Args:
            command: Command name to check.

        Returns:
            bool: True if command is available.

        """
        return cls.find_executable_path(command) is not None

    @classmethod
    def probe_tool_capabilities(cls, executable_path: str) -> Set[ProviderCapability]:
        """Probe a tool to determine its capabilities.

        Args:
            executable_path: Path to the tool executable.

        Returns:
            Set[ProviderCapability]: Detected capabilities.

        """
        capabilities = set()

        try:
            # Test basic execution
            result = subprocess.run(
                [executable_path, "--help"], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                capabilities.add(ProviderCapability.TASK_EXECUTION)

                help_text = result.stdout.lower()

                # Check for file operation capabilities
                if any(
                    keyword in help_text
                    for keyword in ["file", "edit", "write", "read"]
                ):
                    capabilities.add(ProviderCapability.FILE_OPERATIONS)

                # Check for shell execution capabilities
                if any(
                    keyword in help_text
                    for keyword in ["shell", "bash", "command", "execute"]
                ):
                    capabilities.add(ProviderCapability.SHELL_EXECUTION)

                # Check for interactive capabilities
                if any(
                    keyword in help_text
                    for keyword in ["interactive", "prompt", "chat"]
                ):
                    capabilities.add(ProviderCapability.PROMPT_HANDLING)

                # Check for streaming capabilities
                if any(keyword in help_text for keyword in ["stream", "streaming"]):
                    capabilities.add(ProviderCapability.STREAMING_RESPONSE)

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ):
            pass  # Tool doesn't support --help or isn't accessible

        return capabilities

    @classmethod
    def create_config_from_path(
        cls, executable_path: str, provider_name: Optional[str] = None
    ) -> ProviderConfig:
        """Create a provider configuration from an executable path.

        Args:
            executable_path: Path to the tool executable.
            provider_name: Optional provider name. If None, derives from executable.

        Returns:
            ProviderConfig: Configuration for the tool.

        """
        if provider_name is None:
            provider_name = Path(executable_path).stem

        capabilities = cls.probe_tool_capabilities(executable_path)

        return ProviderConfig(
            provider_name=provider_name,
            tool_executable=executable_path,
            auto_discover=False,
            capabilities=capabilities,
        )

    @classmethod
    def scan_directory(cls, directory: str) -> List[ProviderConfig]:
        """Scan a directory for AI tools.

        Args:
            directory: Directory path to scan.

        Returns:
            List[ProviderConfig]: List of configurations for found tools.

        """
        configs = []
        directory_path = Path(directory)

        if not directory_path.exists() or not directory_path.is_dir():
            return configs

        # Look for known command patterns
        for _tool_name, tool_info in cls.KNOWN_TOOLS.items():
            for command in tool_info["commands"]:
                executable_path = directory_path / command
                if executable_path.exists() and executable_path.is_file():
                    config = ProviderConfig(
                        provider_name=tool_info["provider_name"],
                        tool_executable=str(executable_path),
                        auto_discover=False,
                        capabilities=tool_info["capabilities"],
                    )
                    configs.append(config)

        return configs

    @classmethod
    def get_supported_tools(cls) -> List[str]:
        """Get list of supported tool names.

        Returns:
            List[str]: List of supported tool names.

        """
        return list(cls.KNOWN_TOOLS.keys())

    @classmethod
    def add_tool_definition(
        cls,
        tool_name: str,
        commands: List[str],
        provider_name: str,
        capabilities: Set[ProviderCapability],
    ) -> None:
        """Add a new tool definition for discovery.

        Args:
            tool_name: Name of the tool.
            commands: List of command names to look for.
            provider_name: Provider name to use.
            capabilities: Set of capabilities the tool supports.

        """
        cls.KNOWN_TOOLS[tool_name] = {
            "commands": commands,
            "provider_name": provider_name,
            "capabilities": capabilities,
        }
