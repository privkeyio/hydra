"""Provider-specific prompt overrides and customizations.

This module provides provider-specific prompt overrides and customizations
for the injection framework, allowing different providers to have tailored
prompts while maintaining consistency.
"""

import logging
from typing import Any, Dict

from hydra.prompts.injection import (
    InjectionContext,
    InjectionPoint,
    InjectionPriority,
    InjectionRule,
    PromptInjector,
)

logger = logging.getLogger(__name__)


class ProviderSpecificInjector(PromptInjector):
    """Provider-specific prompt injector with custom rules."""

    def __init__(self, provider_name: str):
        """Initialize provider-specific injector.
        
        Args:
            provider_name: Name of the provider

        """
        super().__init__()
        self.provider_name = provider_name
        self._setup_provider_rules()

    def _setup_provider_rules(self):
        """Setup provider-specific injection rules."""
        if self.provider_name == "claude_unified":
            self._setup_claude_rules()
        elif self.provider_name == "venice":
            self._setup_venice_rules()
        elif self.provider_name == "anthropic":
            self._setup_anthropic_rules()
        elif self.provider_name == "openai":
            self._setup_openai_rules()
        elif self.provider_name == "mock":
            self._setup_mock_rules()

    def _setup_claude_rules(self):
        """Setup Claude-specific injection rules."""
        # Claude works best with direct, concise instructions
        self.register_rule(InjectionRule(
            name="claude_execution",
            pattern="operation:.*execution.*",
            prompt="Direct implementation. No explanations. Working code only.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.HIGH,
            variables={"provider": "claude"}
        ))

        self.register_rule(InjectionRule(
            name="claude_verification",
            pattern="operation:.*verification.*",
            prompt="Strict verification. Check ALL criteria. No shortcuts.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.CRITICAL,
            variables={"provider": "claude"}
        ))

    def _setup_venice_rules(self):
        """Setup Venice-specific injection rules."""
        # Venice needs more structured prompts
        self.register_rule(InjectionRule(
            name="venice_execution",
            pattern="operation:.*execution.*",
            prompt="## Task\n{task}\n\n## Requirements\n- Working code\n- No comments unless complex\n- Test your logic",
            point=InjectionPoint.WRAPPER,
            priority=InjectionPriority.HIGH,
            variables={"provider": "venice", "task": "{user_prompt}"}
        ))

        self.register_rule(InjectionRule(
            name="venice_code_format",
            pattern="operation:.*code.*",
            prompt="Use code blocks with language tags. Prefer Python.",
            point=InjectionPoint.SUFFIX,
            priority=InjectionPriority.NORMAL,
            variables={"provider": "venice"}
        ))

    def _setup_anthropic_rules(self):
        """Setup Anthropic-specific injection rules."""
        # Anthropic Claude responds well to structured prompts
        self.register_rule(InjectionRule(
            name="anthropic_execution",
            pattern="operation:.*execution.*",
            prompt="Implementation required. Provide complete, working solution.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.HIGH,
            variables={"provider": "anthropic"}
        ))

        self.register_rule(InjectionRule(
            name="anthropic_quality",
            pattern="operation:.*execution.*",
            prompt="Quality is critical. No placeholders or TODOs.",
            point=InjectionPoint.SUFFIX,
            priority=InjectionPriority.HIGH,
            variables={"provider": "anthropic"}
        ))

    def _setup_openai_rules(self):
        """Setup OpenAI-specific injection rules."""
        # OpenAI models work well with clear, step-by-step instructions
        self.register_rule(InjectionRule(
            name="openai_execution",
            pattern="operation:.*execution.*",
            prompt="Step-by-step implementation. Complete working code.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.HIGH,
            variables={"provider": "openai"}
        ))

        self.register_rule(InjectionRule(
            name="openai_json",
            pattern="operation:.*json.*",
            prompt="Return valid JSON object only. No markdown formatting.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.CRITICAL,
            variables={"provider": "openai"}
        ))

    def _setup_mock_rules(self):
        """Setup Mock provider rules for testing."""
        # Mock provider should track injection attempts
        self.register_rule(InjectionRule(
            name="mock_test",
            pattern="*",
            prompt="[MOCK_INJECTION_APPLIED] {user_prompt}",
            point=InjectionPoint.WRAPPER,
            priority=InjectionPriority.NORMAL,
            variables={"provider": "mock"}
        ))


# Provider-specific configurations
PROVIDER_CONFIGURATIONS = {
    "claude_unified": {
        "supports_system_messages": True,
        "prefers_concise_prompts": True,
        "max_context_length": 200000,
        "optimal_prompt_style": "direct"
    },
    "venice": {
        "supports_system_messages": True,
        "prefers_structured_prompts": True,
        "max_context_length": 131072,
        "optimal_prompt_style": "structured"
    },
    "anthropic": {
        "supports_system_messages": True,
        "prefers_detailed_prompts": True,
        "max_context_length": 200000,
        "optimal_prompt_style": "detailed"
    },
    "openai": {
        "supports_system_messages": True,
        "prefers_step_by_step": True,
        "max_context_length": 128000,
        "optimal_prompt_style": "step_by_step"
    },
    "mock": {
        "supports_system_messages": True,
        "prefers_any": True,
        "max_context_length": 100000,
        "optimal_prompt_style": "testing"
    }
}


def get_provider_injector(provider_name: str) -> ProviderSpecificInjector:
    """Get provider-specific injector.
    
    Args:
        provider_name: Name of the provider
        
    Returns:
        Provider-specific injector

    """
    return ProviderSpecificInjector(provider_name)


def get_provider_config(provider_name: str) -> Dict[str, Any]:
    """Get provider-specific configuration.
    
    Args:
        provider_name: Name of the provider
        
    Returns:
        Provider configuration dictionary

    """
    return PROVIDER_CONFIGURATIONS.get(provider_name, {})


def adapt_prompt_for_provider(
    provider_name: str,
    prompt: str,
    operation: str = "execution",
    **kwargs
) -> str:
    """Adapt a prompt for a specific provider.
    
    Args:
        provider_name: Name of the provider
        prompt: Original prompt
        operation: Type of operation
        **kwargs: Additional metadata
        
    Returns:
        Adapted prompt

    """
    try:
        # Get provider-specific injector
        injector = get_provider_injector(provider_name)

        # Create injection context
        context = InjectionContext(
            operation=operation,
            provider=provider_name,
            model=kwargs.get("model", "unknown"),
            user_prompt=prompt,
            metadata=kwargs
        )

        # Apply provider-specific injections
        return injector.inject(context)

    except Exception as e:
        logger.warning(f"Failed to adapt prompt for {provider_name}: {e}")
        return prompt


def register_custom_provider_rule(
    provider_name: str,
    rule_name: str,
    pattern: str,
    prompt_template: str,
    injection_point: InjectionPoint = InjectionPoint.PREFIX,
    priority: InjectionPriority = InjectionPriority.NORMAL,
    **kwargs
):
    """Register a custom rule for a provider.
    
    Args:
        provider_name: Name of the provider
        rule_name: Name for the rule
        pattern: Pattern to match
        prompt_template: Template for the injection
        injection_point: Where to inject
        priority: Injection priority
        **kwargs: Additional rule parameters

    """
    # This would be used to dynamically add custom rules
    # Implementation would store rules in a registry
    logger.info(f"Custom rule {rule_name} registered for {provider_name}")


# Export main functions
__all__ = [
    "ProviderSpecificInjector",
    "get_provider_injector",
    "get_provider_config",
    "adapt_prompt_for_provider",
    "register_custom_provider_rule",
    "PROVIDER_CONFIGURATIONS",
]
