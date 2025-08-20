"""Hydra prompts package for centralized prompt management."""

from .config import (
    PromptConfig,
    PromptConfigManager,
    PromptValidator,
    PromptVersion,
    get_config_manager,
    get_prompt,
    list_prompts,
    validate_prompt_variables,
)

# Import optimization functions
from .optimization import optimize_prompt
from .system_prompts import (
    ExecutionPrompts,
    PromptCategory,
    PromptPriority,
    SystemPrompts,
    TicketPrompts,
    VerificationPrompts,
    get_system_prompt,
    inject_system_prompt,
)
from .versioning import (
    ABTestConfig,
    PromptMetrics,
    PromptVersionInfo,
    PromptVersionManager,
    create_prompt_version,
    get_ab_test_prompt,
    get_version_manager,
    record_prompt_usage,
)

__all__ = [
    # System prompts
    'SystemPrompts',
    'TicketPrompts',
    'VerificationPrompts',
    'ExecutionPrompts',
    'PromptCategory',
    'PromptPriority',
    'get_system_prompt',
    'inject_system_prompt',

    # Configuration
    'PromptConfigManager',
    'PromptConfig',
    'PromptVersion',
    'PromptValidator',
    'get_config_manager',
    'get_prompt',
    'list_prompts',
    'validate_prompt_variables',

    # Optimization (backward compatibility)
    'optimize_prompt',

    # Versioning and hot-reload
    'PromptVersionManager',
    'PromptVersionInfo',
    'ABTestConfig',
    'PromptMetrics',
    'get_version_manager',
    'create_prompt_version',
    'record_prompt_usage',
    'get_ab_test_prompt'
]
