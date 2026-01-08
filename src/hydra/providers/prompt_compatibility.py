"""Backward compatibility layer for prompt system migration.

This module provides compatibility wrappers for code that still uses
the old prompt system, ensuring smooth migration to the new injection framework.
"""

import logging
from typing import Optional

from hydra.prompts.injection import (
    InjectionContext,
    InjectorRegistry,
    initialize_default_injectors,
)
from hydra.prompts.system_prompts import get_system_prompt as new_get_system_prompt

logger = logging.getLogger(__name__)

# Global registry for compatibility
_compatibility_registry: Optional[InjectorRegistry] = None


def ensure_compatibility_registry():
    """Ensure the compatibility registry is initialized."""
    global _compatibility_registry
    if _compatibility_registry is None:
        _compatibility_registry = InjectorRegistry()
        if not _compatibility_registry.injectors:
            initialize_default_injectors()


def get_system_prompt(prompt_type: str = "code") -> str:
    """Compatibility wrapper for get_system_prompt.
    
    Args:
        prompt_type: Type of system prompt to get
        
    Returns:
        System prompt string

    """
    # Use new system with fallback to old behavior
    try:
        return new_get_system_prompt(prompt_type)
    except Exception as e:
        logger.warning(f"Failed to get system prompt {prompt_type}: {e}")
        # Fallback to simple default
        return "You are a helpful coding assistant. Provide clear, concise, working code."


def optimize_prompt(prompt: str, context: str = "general") -> str:
    """Compatibility wrapper for prompt optimization.
    
    Args:
        prompt: Original prompt
        context: Context for optimization
        
    Returns:
        Optimized prompt

    """
    try:
        ensure_compatibility_registry()

        # Create injection context for optimization
        injection_context = InjectionContext(
            operation=f"compat_{context}",
            provider="compatibility",
            model="unknown",
            user_prompt=prompt,
            metadata={"context": context, "legacy": True}
        )

        # Get appropriate injector
        if "execution" in context or "code" in context:
            injector = _compatibility_registry.get("production")
        elif "json" in context:
            # Minimal processing for JSON
            return prompt + "\nJSON only."
        elif "ticket" in context:
            injector = _compatibility_registry.get("ticket")
        else:
            # Use production as safe default
            injector = _compatibility_registry.get("production")

        if injector:
            return injector.inject(injection_context)

        return prompt

    except Exception as e:
        logger.warning(f"Prompt optimization failed for {context}: {e}")
        return prompt


def inject_provider_prompts(
    provider_name: str,
    operation: str,
    user_prompt: str,
    model: str = "unknown",
    **kwargs
) -> str:
    """Inject prompts for a specific provider and operation.
    
    Args:
        provider_name: Name of the provider
        operation: Operation being performed
        user_prompt: User's original prompt
        model: Model being used
        **kwargs: Additional metadata
        
    Returns:
        Prompt with injections applied

    """
    try:
        ensure_compatibility_registry()

        # Create injection context
        injection_context = InjectionContext(
            operation=operation,
            provider=provider_name,
            model=model,
            user_prompt=user_prompt,
            metadata=kwargs
        )

        # Apply appropriate injection
        if "execution" in operation:
            injector = _compatibility_registry.get("production")
        elif "verification" in operation:
            injector = _compatibility_registry.get("verification")
        elif "ticket" in operation:
            injector = _compatibility_registry.get("ticket")
        else:
            # Use production as safe default
            injector = _compatibility_registry.get("production")

        if injector:
            return injector.inject(injection_context)

        return user_prompt

    except Exception as e:
        logger.warning(f"Prompt injection failed for {provider_name}/{operation}: {e}")
        return user_prompt


def create_compatibility_wrapper(provider_instance):
    """Create a compatibility wrapper for a provider instance.
    
    Args:
        provider_instance: Provider instance to wrap
        
    Returns:
        Wrapped provider with compatibility methods

    """
    # Add compatibility methods if they don't exist
    if not hasattr(provider_instance, '_original_generate'):
        provider_instance._original_generate = provider_instance.generate

        def compatible_generate(prompt: str, **kwargs):
            """Generate with automatic prompt injection."""
            # Apply compatibility injection
            enhanced_prompt = inject_provider_prompts(
                provider_name=provider_instance.name,
                operation=kwargs.get("operation", "execution"),
                user_prompt=prompt,
                model=getattr(provider_instance.config, "model", "unknown"),
                **kwargs
            )

            return provider_instance._original_generate(enhanced_prompt, **kwargs)

        provider_instance.generate = compatible_generate

    return provider_instance


# Legacy import aliases for backward compatibility
def get_code_prompt() -> str:
    """Legacy function for getting code prompt."""
    return get_system_prompt("code")


def get_json_prompt() -> str:
    """Legacy function for getting JSON prompt."""
    return get_system_prompt("json")


def format_prompt_for_provider(provider_name: str, prompt: str) -> str:
    """Legacy function for formatting prompts by provider."""
    return inject_provider_prompts(
        provider_name=provider_name,
        operation="execution",
        user_prompt=prompt
    )


# Export compatibility functions
__all__ = [
    "get_system_prompt",
    "optimize_prompt",
    "inject_provider_prompts",
    "create_compatibility_wrapper",
    "get_code_prompt",
    "get_json_prompt",
    "format_prompt_for_provider",
]
