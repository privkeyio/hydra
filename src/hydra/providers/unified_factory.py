"""Unified Provider Factory.

This module provides a centralized factory for creating provider instances
using the consolidated provider architecture.
"""

import logging
from typing import Any, Dict, Optional, Type

from hydra.providers.base import LLMConfig

from .base_provider import BaseProvider
from .claude_unified import ClaudeUnifiedProvider
from .config_manager import ConfigurationManager, ProviderType, get_config_manager
from .mock_provider import MockProvider
from .openai_provider import OpenAIProvider
from .venice import VeniceProvider

logger = logging.getLogger(__name__)


class UnifiedProviderFactory:
    """Factory for creating provider instances with unified configuration."""

    # Provider class registry
    _provider_classes: Dict[ProviderType, Type[BaseProvider]] = {
        ProviderType.CLAUDE: ClaudeUnifiedProvider,
        ProviderType.OPENAI: OpenAIProvider,
        ProviderType.VENICE: VeniceProvider,
        ProviderType.MOCK: MockProvider,
    }

    def __init__(self, config_manager: Optional[ConfigurationManager] = None):
        """Initialize the factory.

        Args:
            config_manager: Configuration manager instance

        """
        self.config_manager = config_manager or get_config_manager()
        self._provider_cache: Dict[str, BaseProvider] = {}

    def create_provider(
        self,
        profile_name: Optional[str] = None,
        **override_params,
    ) -> BaseProvider:
        """Create a provider instance.

        Args:
            profile_name: Name of the configuration profile to use
            **override_params: Parameters to override from the profile

        Returns:
            Provider instance

        Raises:
            ValueError: If profile not found or provider creation fails

        """
        # Get profile
        if profile_name:
            profile = self.config_manager.get_profile(profile_name)
            if not profile:
                raise ValueError(f"Profile '{profile_name}' not found")
        else:
            profile = self.config_manager.get_default_profile()
            if not profile:
                raise ValueError("No default profile configured")

        # Check if provider is enabled
        if not profile.enabled:
            raise ValueError(f"Profile '{profile.name}' is disabled")

        # Check cache
        cache_key = f"{profile.name}_{hash(frozenset(override_params.items()))}"
        if cache_key in self._provider_cache:
            logger.debug(f"Using cached provider for {cache_key}")
            return self._provider_cache[cache_key]

        # Get provider class
        provider_class = self._provider_classes.get(profile.provider_type)
        if not provider_class:
            raise ValueError(f"Unknown provider type: {profile.provider_type}")

        # Build configuration
        config = self._build_config(profile, override_params)

        # Create provider instance
        try:
            provider = provider_class(config)
            provider.validate_config()

            # Cache the provider
            self._provider_cache[cache_key] = provider
            logger.info(f"Created provider: {profile.name} ({profile.provider_type.value})")

            return provider

        except Exception as e:
            logger.error(f"Failed to create provider {profile.name}: {e}")
            raise ValueError(f"Provider creation failed: {e}") from e

    def _build_config(self, profile, override_params) -> LLMConfig:
        """Build LLMConfig from profile and overrides.

        Args:
            profile: Provider profile
            override_params: Override parameters

        Returns:
            LLMConfig instance

        """
        # Merge parameters
        extra_params = profile.extra_params.copy()
        extra_params.update(override_params.get("extra_params", {}))

        # Apply global settings
        global_settings = self.config_manager.configuration.global_settings
        for key, value in global_settings.items():
            if key not in extra_params:
                extra_params[key] = value

        # Build config
        config = LLMConfig(
            provider_type=profile.provider_type.value,
            model=override_params.get("model", profile.model),
            api_key=override_params.get("api_key", profile.api_key),
            base_url=override_params.get("base_url", profile.base_url),
            extra_params=extra_params,
        )

        # Apply environment variables
        for key, value in profile.environment.items():
            import os

            os.environ[key] = value

        return config

    def create_with_fallback(
        self,
        primary_profile: Optional[str] = None,
        **override_params,
    ) -> BaseProvider:
        """Create a provider with fallback support.

        Args:
            primary_profile: Primary profile to try
            **override_params: Override parameters

        Returns:
            Provider instance (primary or fallback)

        Raises:
            ValueError: If no providers could be created

        """
        errors = []

        # Try primary profile
        if primary_profile:
            try:
                return self.create_provider(primary_profile, **override_params)
            except Exception as e:
                errors.append(f"{primary_profile}: {e}")
                logger.warning(f"Primary provider {primary_profile} failed: {e}")

        # Try fallback chain
        for profile in self.config_manager.get_fallback_profiles():
            try:
                logger.info(f"Trying fallback provider: {profile.name}")
                return self.create_provider(profile.name, **override_params)
            except Exception as e:
                errors.append(f"{profile.name}: {e}")
                logger.warning(f"Fallback provider {profile.name} failed: {e}")

        # Try any enabled provider by priority
        for profile in self.config_manager.get_enabled_profiles():
            try:
                logger.info(f"Trying provider by priority: {profile.name}")
                return self.create_provider(profile.name, **override_params)
            except Exception as e:
                errors.append(f"{profile.name}: {e}")
                logger.warning(f"Provider {profile.name} failed: {e}")

        # All providers failed
        error_msg = "Failed to create any provider:\n" + "\n".join(errors)
        raise ValueError(error_msg)

    def get_best_provider_for_task(
        self,
        task_type: str,
        **requirements,
    ) -> BaseProvider:
        """Get the best provider for a specific task type.

        Args:
            task_type: Type of task (e.g., "code_generation", "analysis", "interactive")
            **requirements: Task requirements (e.g., context_window=100000)

        Returns:
            Best provider for the task

        Raises:
            ValueError: If no suitable provider found

        """
        candidates = []

        for profile in self.config_manager.get_enabled_profiles():
            try:
                # Create provider to check capabilities
                provider = self.create_provider(profile.name)
                capabilities = provider.get_capabilities()

                # Score based on task requirements
                score = self._score_provider_for_task(
                    provider, profile, task_type, capabilities, requirements
                )

                if score > 0:
                    candidates.append((score, profile, provider))

            except Exception as e:
                logger.debug(f"Skipping {profile.name}: {e}")
                continue

        if not candidates:
            raise ValueError(f"No suitable provider found for task: {task_type}")

        # Sort by score and return best
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_profile, best_provider = candidates[0]

        logger.info(
            f"Selected {best_profile.name} for {task_type} (score: {best_score})"
        )
        return best_provider

    def _score_provider_for_task(
        self,
        provider: BaseProvider,
        profile,
        task_type: str,
        capabilities: Dict[str, bool],
        requirements: Dict[str, Any],
    ) -> int:
        """Score a provider for a specific task.

        Args:
            provider: Provider instance
            profile: Provider profile
            task_type: Task type
            capabilities: Provider capabilities
            requirements: Task requirements

        Returns:
            Score (higher is better)

        """
        score = 0

        # Base score from priority
        score += profile.priority * 10

        # Task-specific scoring
        if task_type == "interactive":
            if capabilities.get("interactive"):
                score += 100
            if profile.provider_type == ProviderType.CLAUDE:
                score += 50  # Claude is best for interactive

        elif task_type == "code_generation":
            if capabilities.get("streaming"):
                score += 20
            if profile.model in ["smart", "gpt-4", "claude-3-5-sonnet"]:
                score += 50

        elif task_type == "analysis":
            if capabilities.get("context_window_extension"):
                score += 30
            # Check context window requirement
            if "context_window" in requirements:
                model_info = provider.get_current_model()
                if model_info and model_info.context_window >= requirements["context_window"]:
                    score += 50
                else:
                    score -= 100  # Penalize if context window too small

        elif task_type == "batch_processing":
            # Prefer fast, cheap models for batch
            if profile.model in ["fast", "haiku", "gpt-3.5"]:
                score += 50
            model_info = provider.get_current_model()
            if model_info and model_info.cost_per_token:
                # Lower cost is better for batch
                score += int(100 / (model_info.cost_per_token * 1000000))

        # Check other requirements
        if requirements.get("file_interception") and capabilities.get("file_interception"):
            score += 30

        if requirements.get("session_persistence") and capabilities.get("session_persistence"):
            score += 20

        if requirements.get("code_execution") and capabilities.get("code_execution"):
            score += 40

        return score

    def list_available_providers(self) -> Dict[str, Dict[str, Any]]:
        """List all available providers with their status.

        Returns:
            Dictionary of provider information

        """
        providers = {}

        for profile in self.config_manager.configuration.profiles.values():
            try:
                # Try to create provider to check if it's actually available
                provider = self.create_provider(profile.name)
                status = "available"
                capabilities = provider.get_capabilities()
                provider.cleanup()  # Clean up test instance
            except Exception as e:
                status = f"unavailable: {e}"
                capabilities = {}

            providers[profile.name] = {
                "type": profile.provider_type.value,
                "model": profile.model,
                "enabled": profile.enabled,
                "priority": profile.priority,
                "status": status,
                "capabilities": capabilities,
            }

        return providers

    def cleanup_all(self):
        """Clean up all cached providers."""
        for provider in self._provider_cache.values():
            try:
                provider.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up provider: {e}")

        self._provider_cache.clear()

    def register_provider_class(
        self,
        provider_type: ProviderType,
        provider_class: Type[BaseProvider],
    ):
        """Register a custom provider class.

        Args:
            provider_type: Provider type
            provider_class: Provider class

        """
        self._provider_classes[provider_type] = provider_class
        logger.info(f"Registered provider class for {provider_type.value}")


# Global factory instance
_factory: Optional[UnifiedProviderFactory] = None


def get_provider_factory() -> UnifiedProviderFactory:
    """Get or create the global provider factory.

    Returns:
        Provider factory instance

    """
    global _factory
    if _factory is None:
        _factory = UnifiedProviderFactory()
    return _factory


def reset_provider_factory():
    """Reset the global provider factory."""
    global _factory
    if _factory:
        _factory.cleanup_all()
    _factory = None


def create_provider(profile_name: Optional[str] = None, **kwargs) -> BaseProvider:
    """Convenience function to create a provider.

    Args:
        profile_name: Profile name
        **kwargs: Override parameters

    Returns:
        Provider instance

    """
    factory = get_provider_factory()
    return factory.create_provider(profile_name, **kwargs)


def create_provider_with_fallback(
    primary_profile: Optional[str] = None, **kwargs
) -> BaseProvider:
    """Convenience function to create a provider with fallback.

    Args:
        primary_profile: Primary profile name
        **kwargs: Override parameters

    Returns:
        Provider instance

    """
    factory = get_provider_factory()
    return factory.create_with_fallback(primary_profile, **kwargs)
