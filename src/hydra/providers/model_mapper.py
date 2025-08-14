"""Centralized model mapping system for provider abstraction."""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ModelCategory(Enum):
    """Generic model categories for provider-agnostic selection."""

    FAST = "fast"
    BALANCED = "balanced"
    SMART = "smart"
    CODER = "coder"


@dataclass
class ModelMapping:
    """Model mapping configuration."""

    category: ModelCategory
    provider_model: str
    display_name: str
    context_window: int
    max_output_tokens: int
    relative_cost: float  # 1.0 = baseline


class ModelMapper:
    """Centralized model mapping for all providers."""

    def __init__(self):
        """Initialize the model mapper with provider mappings."""
        self.provider_mappings = self._load_provider_mappings()
        self.legacy_mappings = self._load_legacy_mappings()

    def _load_provider_mappings(self) -> Dict[str, Dict[str, ModelMapping]]:
        """Load provider-specific model mappings.

        Returns:
            Dictionary of provider -> model category -> model mapping

        """
        return {
            "claude_tmux": {
                ModelCategory.FAST: ModelMapping(
                    category=ModelCategory.FAST,
                    provider_model="claude-3-5-haiku-20241022",
                    display_name="Claude 3.5 Haiku",
                    context_window=200000,
                    max_output_tokens=8192,
                    relative_cost=0.1
                ),
                ModelCategory.BALANCED: ModelMapping(
                    category=ModelCategory.BALANCED,
                    provider_model="claude-3-5-sonnet-20241022",
                    display_name="Claude 3.5 Sonnet",
                    context_window=200000,
                    max_output_tokens=8192,
                    relative_cost=0.3
                ),
                ModelCategory.SMART: ModelMapping(
                    category=ModelCategory.SMART,
                    provider_model="claude-3-opus-20240229",
                    display_name="Claude 3 Opus",
                    context_window=200000,
                    max_output_tokens=4096,
                    relative_cost=1.0
                ),
                ModelCategory.CODER: ModelMapping(
                    category=ModelCategory.CODER,
                    provider_model="claude-3-5-sonnet-20241022",
                    display_name="Claude 3.5 Sonnet",
                    context_window=200000,
                    max_output_tokens=8192,
                    relative_cost=0.3
                ),
            },
            "venice": {
                ModelCategory.FAST: ModelMapping(
                    category=ModelCategory.FAST,
                    provider_model="llama-3.1-8b",
                    display_name="Llama 3.1 8B",
                    context_window=131072,
                    max_output_tokens=4096,
                    relative_cost=0.05
                ),
                ModelCategory.BALANCED: ModelMapping(
                    category=ModelCategory.BALANCED,
                    provider_model="llama-3.3-70b",
                    display_name="Llama 3.3 70B",
                    context_window=131072,
                    max_output_tokens=4096,
                    relative_cost=0.2
                ),
                ModelCategory.SMART: ModelMapping(
                    category=ModelCategory.SMART,
                    provider_model="qwen-2.5-coder-32b",
                    display_name="Qwen 2.5 Coder 32B",
                    context_window=32768,
                    max_output_tokens=4096,
                    relative_cost=0.15
                ),
                ModelCategory.CODER: ModelMapping(
                    category=ModelCategory.CODER,
                    provider_model="qwen-2.5-coder-32b",
                    display_name="Qwen 2.5 Coder 32B",
                    context_window=32768,
                    max_output_tokens=4096,
                    relative_cost=0.15
                ),
            },
            "mock": {
                ModelCategory.FAST: ModelMapping(
                    category=ModelCategory.FAST,
                    provider_model="mock-fast-model",
                    display_name="Mock Fast Model",
                    context_window=4096,
                    max_output_tokens=2048,
                    relative_cost=0.1
                ),
                ModelCategory.BALANCED: ModelMapping(
                    category=ModelCategory.BALANCED,
                    provider_model="mock-balanced-model",
                    display_name="Mock Balanced Model",
                    context_window=8192,
                    max_output_tokens=4096,
                    relative_cost=0.3
                ),
                ModelCategory.SMART: ModelMapping(
                    category=ModelCategory.SMART,
                    provider_model="mock-smart-model",
                    display_name="Mock Smart Model",
                    context_window=16384,
                    max_output_tokens=8192,
                    relative_cost=0.8
                ),
                ModelCategory.CODER: ModelMapping(
                    category=ModelCategory.CODER,
                    provider_model="mock-coder-model",
                    display_name="Mock Coder Model",
                    context_window=16384,
                    max_output_tokens=8192,
                    relative_cost=0.6
                ),
            },
        }

    def _load_legacy_mappings(self) -> Dict[str, ModelCategory]:
        """Load legacy model name mappings for backward compatibility.

        Returns:
            Dictionary of legacy name -> model category

        """
        return {
            # Claude legacy names
            "opus": ModelCategory.SMART,
            "opus 4": ModelCategory.SMART,
            "claude-opus": ModelCategory.SMART,
            "claude-3-opus": ModelCategory.SMART,
            "claude-3-opus-20240229": ModelCategory.SMART,
            "claude-opus-4-1-20250805": ModelCategory.SMART,
            "claude-opus-4-20250514": ModelCategory.SMART,

            "sonnet": ModelCategory.BALANCED,
            "sonnet 4": ModelCategory.BALANCED,
            "claude-sonnet": ModelCategory.BALANCED,
            "claude-3-sonnet": ModelCategory.BALANCED,
            "claude-3-sonnet-20240229": ModelCategory.BALANCED,
            "claude-sonnet-4-20250514": ModelCategory.BALANCED,
            "claude-3-5-sonnet-20241022": ModelCategory.BALANCED,
            "claude-3-7-sonnet-20250220": ModelCategory.BALANCED,

            "haiku": ModelCategory.FAST,
            "claude-haiku": ModelCategory.FAST,
            "claude-3-haiku": ModelCategory.FAST,
            "claude-3-haiku-20240307": ModelCategory.FAST,
            "claude-3-5-haiku-20241022": ModelCategory.FAST,

            # Venice model names
            "qwen-2.5-coder-32b": ModelCategory.CODER,
            "llama-3.1-8b": ModelCategory.FAST,
            "llama-3.1-70b": ModelCategory.BALANCED,
            "llama-3.3-70b": ModelCategory.BALANCED,
            "llama-3.1-405b": ModelCategory.SMART,
            "deepseek-coder-v2-lite": ModelCategory.CODER,
            "qwen-2.5-qwq-32b": ModelCategory.SMART,

            # Generic aliases
            "fast": ModelCategory.FAST,
            "balanced": ModelCategory.BALANCED,
            "smart": ModelCategory.SMART,
            "coder": ModelCategory.CODER,
        }

    def map_model(
        self,
        model_name: str,
        provider: Optional[str] = None
    ) -> Optional[str]:
        """Map a model name to provider-specific model identifier.

        Args:
            model_name: Generic or legacy model name
            provider: Target provider (auto-detected if not specified)

        Returns:
            Provider-specific model identifier or None if not found

        """
        if not model_name:
            return None

        # Clean and normalize model name
        model_name = model_name.strip().lower()

        # If no provider specified, get from environment
        if not provider:
            provider = os.getenv("LLM_PROVIDER", "claude_tmux").lower()

        # Get provider mappings
        provider_models = self.provider_mappings.get(provider)
        if not provider_models:
            logger.warning(f"Unknown provider: {provider}")
            return None

        # First check if it's already a provider-specific model
        for mapping in provider_models.values():
            if model_name == mapping.provider_model.lower():
                return mapping.provider_model

        # Check legacy mappings
        category = self.legacy_mappings.get(model_name)
        if category:
            mapping = provider_models.get(category)
            if mapping:
                logger.debug(
                    f"Mapped '{model_name}' -> {category.value} -> "
                    f"{mapping.provider_model}"
                )
                return mapping.provider_model

        # Try to parse as category directly
        try:
            category = ModelCategory(model_name)
            mapping = provider_models.get(category)
            if mapping:
                return mapping.provider_model
        except ValueError:
            pass

        # Default to balanced model
        logger.warning(
            f"Unknown model '{model_name}', defaulting to balanced"
        )
        balanced = provider_models.get(ModelCategory.BALANCED)
        return balanced.provider_model if balanced else None

    def get_model_category(self, model_name: str) -> Optional[ModelCategory]:
        """Get the category for a model name.

        Args:
            model_name: Model name to categorize

        Returns:
            Model category or None

        """
        if not model_name:
            return None
        model_name = model_name.strip().lower()

        # Check legacy mappings
        category = self.legacy_mappings.get(model_name)
        if category:
            return category

        # Try to parse as category
        try:
            return ModelCategory(model_name)
        except ValueError:
            pass

        # Check all provider mappings
        for provider_models in self.provider_mappings.values():
            for cat, mapping in provider_models.items():
                if model_name == mapping.provider_model.lower():
                    return cat

        return None

    def get_provider_models(self, provider: str) -> Dict[str, str]:
        """Get all available models for a provider.

        Args:
            provider: Provider name

        Returns:
            Dictionary of category -> model identifier

        """
        provider_models = self.provider_mappings.get(provider, {})
        return {
            cat.value: mapping.provider_model
            for cat, mapping in provider_models.items()
        }

    def suggest_model_for_task(
        self,
        task_complexity: str,
        provider: Optional[str] = None
    ) -> Optional[str]:
        """Suggest a model based on task complexity.

        Args:
            task_complexity: simple, moderate, complex, or critical
            provider: Target provider

        Returns:
            Suggested model identifier

        """
        complexity_mapping = {
            "simple": ModelCategory.FAST,
            "moderate": ModelCategory.BALANCED,
            "complex": ModelCategory.SMART,
            "critical": ModelCategory.SMART,
        }

        category = complexity_mapping.get(task_complexity.lower())
        if not category:
            category = ModelCategory.BALANCED

        if not provider:
            provider = os.getenv("LLM_PROVIDER", "claude_tmux").lower()

        provider_models = self.provider_mappings.get(provider, {})
        mapping = provider_models.get(category)

        return mapping.provider_model if mapping else None


# Global mapper instance
_mapper = None


def get_model_mapper() -> ModelMapper:
    """Get the global model mapper instance.

    Returns:
        ModelMapper instance

    """
    global _mapper
    if _mapper is None:
        _mapper = ModelMapper()
    return _mapper


def map_model(model_name: str, provider: Optional[str] = None) -> Optional[str]:
    """Convenience function to map a model name.

    Args:
        model_name: Model name to map
        provider: Target provider

    Returns:
        Provider-specific model identifier

    """
    mapper = get_model_mapper()
    return mapper.map_model(model_name, provider)


def get_model_for_complexity(
    complexity: str,
    provider: Optional[str] = None
) -> Optional[str]:
    """Get appropriate model for task complexity.

    Args:
        complexity: Task complexity level
        provider: Target provider

    Returns:
        Model identifier

    """
    mapper = get_model_mapper()
    return mapper.suggest_model_for_task(complexity, provider)
