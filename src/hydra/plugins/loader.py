"""Plugin loader for Hydra AI orchestration system."""
import importlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import yaml

from hydra.providers.base import LLMProvider


class PluginCapability:
    """Represents a plugin capability."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description


class PluginManifest:
    """Plugin manifest containing metadata and configuration."""

    def __init__(self, manifest_data: Dict[str, Any], plugin_path: Path):
        self.name = manifest_data.get("name", "")
        self.version = manifest_data.get("version", "1.0.0")
        self.description = manifest_data.get("description", "")
        self.author = manifest_data.get("author", "")
        self.capabilities = [
            PluginCapability(cap) for cap in manifest_data.get("capabilities", [])
        ]
        self.requirements = manifest_data.get("requirements", {})
        self.providers = manifest_data.get("providers", [])
        self.entry_points = manifest_data.get("entry_points", {})
        self.plugin_path = plugin_path
        self.manifest_data = manifest_data

    def check_requirements(self) -> Dict[str, bool]:
        """Check if plugin requirements are met."""
        results = {}

        # Check required executables
        executables = self.requirements.get("executables", [])
        for exe in executables:
            exe_name = exe.get("name", "")
            paths = exe.get("paths", [exe_name])
            found = False

            for path in paths:
                # Expand environment variables
                expanded_path = os.path.expanduser(os.path.expandvars(path))
                if shutil.which(expanded_path) or Path(expanded_path).exists():
                    found = True
                    break

            results[f"executable:{exe_name}"] = found

        # Check optional executables
        optional_executables = self.requirements.get("optional_executables", [])
        for exe in optional_executables:
            exe_name = exe.get("name", "")
            paths = exe.get("paths", [exe_name])
            found = False

            for path in paths:
                expanded_path = os.path.expanduser(os.path.expandvars(path))
                if shutil.which(expanded_path) or Path(expanded_path).exists():
                    found = True
                    break

            results[f"optional_executable:{exe_name}"] = found

        return results

    def get_provider_config(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration schema for a specific provider."""
        for provider in self.providers:
            if provider.get("name") == provider_name:
                return provider.get("config_schema", {})
        return None


class PluginLoader:
    """Loads and manages plugins for the Hydra system."""

    def __init__(self, plugins_dir: Optional[Path] = None):
        if plugins_dir is None:
            # Default to plugins directory next to this file
            plugins_dir = Path(__file__).parent
        self.plugins_dir = Path(plugins_dir)
        self.loaded_plugins: Dict[str, PluginManifest] = {}
        self.provider_registry: Dict[str, Type[LLMProvider]] = {}

    def discover_plugins(self) -> List[Path]:
        """Discover all available plugins."""
        plugins = []

        if not self.plugins_dir.exists():
            return plugins

        for plugin_dir in self.plugins_dir.iterdir():
            if plugin_dir.is_dir() and plugin_dir.name != "__pycache__":
                manifest_file = plugin_dir / "plugin.yaml"
                if manifest_file.exists():
                    plugins.append(plugin_dir)

        return plugins

    def load_plugin_manifest(self, plugin_dir: Path) -> Optional[PluginManifest]:
        """Load plugin manifest from directory."""
        manifest_file = plugin_dir / "plugin.yaml"

        if not manifest_file.exists():
            return None

        try:
            with open(manifest_file, 'r') as f:
                manifest_data = yaml.safe_load(f)
            return PluginManifest(manifest_data, plugin_dir)
        except Exception as e:
            print(f"Error loading plugin manifest from {plugin_dir}: {e}")
            return None

    def check_plugin_requirements(self, manifest: PluginManifest) -> bool:
        """Check if plugin requirements are satisfied."""
        requirements_status = manifest.check_requirements()

        # All required executables must be available
        required_met = True
        for key, available in requirements_status.items():
            if key.startswith("executable:") and not available:
                required_met = False
                break

        return required_met

    def load_plugin_provider(self, manifest: PluginManifest, provider_config: Dict[str, Any]) -> Optional[Type[LLMProvider]]:
        """Load a specific provider from a plugin."""
        try:
            module_name = provider_config.get("module")
            class_name = provider_config.get("class")

            if not module_name or not class_name:
                return None

            # Construct module path relative to plugin
            module_path = f"hydra.plugins.{manifest.plugin_path.name}.providers.{module_name}"

            # Import the module
            try:
                module = importlib.import_module(module_path)
            except ImportError:
                # Try alternative import path
                providers_dir = manifest.plugin_path / "providers"
                if providers_dir.exists():
                    spec = importlib.util.spec_from_file_location(
                        module_name,
                        providers_dir / f"{module_name}.py"
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_path] = module
                        spec.loader.exec_module(module)
                    else:
                        return None
                else:
                    return None

            # Get the provider class
            if hasattr(module, class_name):
                provider_class = getattr(module, class_name)
                return provider_class

        except Exception as e:
            print(f"Error loading provider {provider_config.get('name')}: {e}")

        return None

    def load_plugin(self, plugin_dir: Path) -> bool:
        """Load a single plugin."""
        manifest = self.load_plugin_manifest(plugin_dir)
        if not manifest:
            return False

        # Check requirements
        if not self.check_plugin_requirements(manifest):
            print(f"Plugin {manifest.name} requirements not met, skipping")
            return False

        # Load providers
        for provider_config in manifest.providers:
            provider_class = self.load_plugin_provider(manifest, provider_config)
            if provider_class:
                provider_name = provider_config.get("name")
                self.provider_registry[provider_name] = provider_class

        self.loaded_plugins[manifest.name] = manifest
        return True

    def load_all_plugins(self) -> int:
        """Load all discovered plugins."""
        plugins = self.discover_plugins()
        loaded_count = 0

        for plugin_dir in plugins:
            if self.load_plugin(plugin_dir):
                loaded_count += 1

        return loaded_count

    def get_provider_class(self, provider_name: str) -> Optional[Type[LLMProvider]]:
        """Get a provider class by name."""
        return self.provider_registry.get(provider_name)

    def list_available_providers(self) -> List[str]:
        """List all available provider names."""
        return list(self.provider_registry.keys())

    def get_plugins_with_capability(self, capability: str) -> List[PluginManifest]:
        """Get all plugins that provide a specific capability."""
        matching_plugins = []

        for manifest in self.loaded_plugins.values():
            for cap in manifest.capabilities:
                if cap.name == capability:
                    matching_plugins.append(manifest)
                    break

        return matching_plugins

    def find_executable(self, executable_name: str) -> Optional[str]:
        """Find executable path using plugin manifests."""
        for manifest in self.loaded_plugins.values():
            # Check required executables
            for exe in manifest.requirements.get("executables", []):
                if exe.get("name") == executable_name:
                    paths = exe.get("paths", [executable_name])
                    for path in paths:
                        expanded_path = os.path.expanduser(os.path.expandvars(path))
                        if shutil.which(expanded_path) or Path(expanded_path).exists():
                            return expanded_path

            # Check optional executables
            for exe in manifest.requirements.get("optional_executables", []):
                if exe.get("name") == executable_name:
                    paths = exe.get("paths", [executable_name])
                    for path in paths:
                        expanded_path = os.path.expanduser(os.path.expandvars(path))
                        if shutil.which(expanded_path) or Path(expanded_path).exists():
                            return expanded_path

        return None


# Global plugin loader instance
_plugin_loader = None


def get_plugin_loader() -> PluginLoader:
    """Get or create the global plugin loader."""
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader()
        _plugin_loader.load_all_plugins()
    return _plugin_loader


def reset_plugin_loader(plugins_dir: Optional[Path] = None):
    """Reset the global plugin loader."""
    global _plugin_loader
    _plugin_loader = PluginLoader(plugins_dir)
    _plugin_loader.load_all_plugins()
    return _plugin_loader
