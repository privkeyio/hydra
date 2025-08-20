"""Prompt injection framework for Hydra.

Provides a unified system for injecting prompts into providers
with context management, variable substitution, and validation.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional


class InjectionPoint(Enum):
    """Points where prompts can be injected."""

    SYSTEM = "system"  # System message
    PREFIX = "prefix"  # Before user message
    SUFFIX = "suffix"  # After user message
    WRAPPER = "wrapper"  # Wrap entire message
    INLINE = "inline"  # Inline replacement


class InjectionPriority(Enum):
    """Priority for injection order."""

    CRITICAL = 0  # Always inject first
    HIGH = 1
    NORMAL = 2
    LOW = 3
    OPTIONAL = 4  # May be skipped if needed


@dataclass
class InjectionRule:
    """Rule for prompt injection."""

    name: str
    pattern: str  # Pattern to match for injection
    prompt: str  # Prompt to inject
    point: InjectionPoint
    priority: InjectionPriority = InjectionPriority.NORMAL
    condition: Optional[Callable[[Dict], bool]] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class InjectionContext:
    """Context for prompt injection."""

    operation: str
    provider: str
    model: str
    user_prompt: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)


class PromptInjector:
    """Main prompt injection system."""

    def __init__(self):
        self.rules: List[InjectionRule] = []
        self.global_variables: Dict[str, Any] = {}
        self.validators: List[Callable] = []
        self.transformers: List[Callable] = []

    def register_rule(self, rule: InjectionRule) -> None:
        """Register an injection rule."""
        self.rules.append(rule)
        # Sort by priority
        self.rules.sort(key=lambda r: r.priority.value)

    def register_validator(self, validator: Callable[[str], tuple[bool, str]]) -> None:
        """Register a prompt validator."""
        self.validators.append(validator)

    def register_transformer(self, transformer: Callable[[str], str]) -> None:
        """Register a prompt transformer."""
        self.transformers.append(transformer)

    def set_global_variable(self, name: str, value: Any) -> None:
        """Set a global variable for substitution."""
        self.global_variables[name] = value

    def inject(self, context: InjectionContext) -> str:
        """Inject prompts based on context and rules.
        
        Args:
            context: Injection context
            
        Returns:
            Modified prompt with injections

        """
        result = context.user_prompt
        applied_rules = []

        # Apply matching rules
        for rule in self.rules:
            if not rule.enabled:
                continue

            if not self._matches_rule(rule, context):
                continue

            if rule.condition and not rule.condition(context.metadata):
                continue

            result = self._apply_injection(result, rule, context)
            applied_rules.append(rule.name)

        # Apply transformers
        for transformer in self.transformers:
            result = transformer(result)

        # Validate final prompt
        for validator in self.validators:
            is_valid, message = validator(result)
            if not is_valid:
                raise ValueError(f"Prompt validation failed: {message}")

        return result

    def _matches_rule(self, rule: InjectionRule, context: InjectionContext) -> bool:
        """Check if rule matches context."""
        # Check pattern matching
        if rule.pattern == "*":
            return True

        # Check operation pattern
        if rule.pattern.startswith("operation:"):
            operation_pattern = rule.pattern[10:]
            return re.match(operation_pattern, context.operation) is not None

        # Check provider pattern
        if rule.pattern.startswith("provider:"):
            provider_pattern = rule.pattern[9:]
            return context.provider == provider_pattern

        # Check model pattern
        if rule.pattern.startswith("model:"):
            model_pattern = rule.pattern[6:]
            return context.model == model_pattern

        # Default regex pattern matching on operation
        return re.match(rule.pattern, context.operation) is not None

    def _apply_injection(
        self,
        prompt: str,
        rule: InjectionRule,
        context: InjectionContext
    ) -> str:
        """Apply injection rule to prompt."""
        # Prepare injection text with variable substitution
        injection_text = self._substitute_variables(
            rule.prompt,
            {**self.global_variables, **context.variables, **rule.variables}
        )

        # Apply based on injection point
        if rule.point == InjectionPoint.SYSTEM:
            # System messages handled separately by provider
            return prompt
        elif rule.point == InjectionPoint.PREFIX:
            return f"{injection_text}\n\n{prompt}"
        elif rule.point == InjectionPoint.SUFFIX:
            return f"{prompt}\n\n{injection_text}"
        elif rule.point == InjectionPoint.WRAPPER:
            return injection_text.replace("{content}", prompt)
        elif rule.point == InjectionPoint.INLINE:
            return prompt.replace(f"{{{rule.name}}}", injection_text)

        return prompt

    def _substitute_variables(self, text: str, variables: Dict[str, Any]) -> str:
        """Substitute variables in text."""
        for key, value in variables.items():
            # Handle list variables
            if isinstance(value, list):
                value = "\n".join(f"- {v}" for v in value)
            # Handle dict variables
            elif isinstance(value, dict):
                value = "\n".join(f"{k}: {v}" for k, v in value.items())

            text = text.replace(f"{{{key}}}", str(value))

        return text


class PromptInjectorBuilder:
    """Builder for configuring prompt injector."""

    def __init__(self):
        self.injector = PromptInjector()

    def with_rule(
        self,
        name: str,
        pattern: str,
        prompt: str,
        point: InjectionPoint = InjectionPoint.PREFIX,
        priority: InjectionPriority = InjectionPriority.NORMAL,
        **kwargs
    ) -> "PromptInjectorBuilder":
        """Add injection rule."""
        rule = InjectionRule(
            name=name,
            pattern=pattern,
            prompt=prompt,
            point=point,
            priority=priority,
            **kwargs
        )
        self.injector.register_rule(rule)
        return self

    def with_validator(self, validator: Callable) -> "PromptInjectorBuilder":
        """Add validator."""
        self.injector.register_validator(validator)
        return self

    def with_transformer(self, transformer: Callable) -> "PromptInjectorBuilder":
        """Add transformer."""
        self.injector.register_transformer(transformer)
        return self

    def with_global(self, name: str, value: Any) -> "PromptInjectorBuilder":
        """Add global variable."""
        self.injector.set_global_variable(name, value)
        return self

    def build(self) -> PromptInjector:
        """Build configured injector."""
        return self.injector


# Pre-configured injectors for common scenarios

def create_production_injector() -> PromptInjector:
    """Create injector for production execution."""
    return (
        PromptInjectorBuilder()
        .with_rule(
            name="no_ai_patterns",
            pattern="operation:.*execution.*",
            prompt="Avoid ANY code or comments that look AI-generated. No emojis. No verbose names.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.HIGH
        )
        .with_rule(
            name="production_quality",
            pattern="operation:.*execution.*",
            prompt="Production quality only. No shortcuts, mocks, or workarounds.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.HIGH
        )
        .with_rule(
            name="test_requirement",
            pattern="operation:.*execution.*",
            prompt="Run ALL tests before marking complete. No exceptions.",
            point=InjectionPoint.SUFFIX,
            priority=InjectionPriority.CRITICAL
        )
        .with_validator(validate_no_ai_patterns)
        .with_transformer(minimize_verbosity)
        .build()
    )


def create_verification_injector() -> PromptInjector:
    """Create injector for verification."""
    return (
        PromptInjectorBuilder()
        .with_rule(
            name="brutal_honesty",
            pattern="operation:.*verification.*",
            prompt="Be brutally honest. No participation trophies. Call out any BS.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.CRITICAL
        )
        .with_rule(
            name="comprehensive_check",
            pattern="operation:.*verification.*",
            prompt="Check EVERYTHING. Assume nothing. Verify with evidence.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.HIGH
        )
        .with_validator(validate_verification_prompt)
        .build()
    )


def create_ticket_injector() -> PromptInjector:
    """Create injector for ticket generation."""
    return (
        PromptInjectorBuilder()
        .with_rule(
            name="ticket_format",
            pattern="operation:.*ticket.*",
            prompt="Format: YAML with id, title, description, acceptance_criteria, dependencies, model, status",
            point=InjectionPoint.SUFFIX,
            priority=InjectionPriority.NORMAL
        )
        .with_rule(
            name="criteria_format",
            pattern="operation:.*ticket.*",
            prompt="Acceptance criteria as [ ] checklist items. Specific and testable only.",
            point=InjectionPoint.PREFIX,
            priority=InjectionPriority.HIGH
        )
        .with_transformer(clean_ticket_language)
        .build()
    )


# Validators

def validate_no_ai_patterns(prompt: str) -> tuple[bool, str]:
    """Validate prompt has no AI patterns."""
    ai_patterns = [
        "certainly", "absolutely", "delighted", "wonderful",
        "please note", "it's important", "feel free"
    ]

    prompt_lower = prompt.lower()
    for pattern in ai_patterns:
        if pattern in prompt_lower:
            return False, f"AI pattern detected: {pattern}"

    # Check for emojis (broader range including all common emoji blocks)
    if any(ord(char) > 127 for char in prompt):
        emoji_chars = [char for char in prompt if ord(char) > 127]
        # Check various emoji ranges
        for char in emoji_chars:
            code = ord(char)
            if (0x1F600 <= code <= 0x1F64F or  # emoticons
                0x1F300 <= code <= 0x1F5FF or  # misc symbols
                0x1F680 <= code <= 0x1F6FF or  # transport
                0x1F1E0 <= code <= 0x1F1FF or  # flags
                0x2600 <= code <= 0x26FF or    # misc symbols
                0x2700 <= code <= 0x27BF):     # dingbats
                return False, "Emoji detected in prompt"

    return True, "No AI patterns detected"


def validate_verification_prompt(prompt: str) -> tuple[bool, str]:
    """Validate verification prompt."""
    required_elements = ["check", "verify", "pass", "fail"]

    prompt_lower = prompt.lower()
    missing = [elem for elem in required_elements if elem not in prompt_lower]

    if missing:
        return False, f"Missing verification elements: {missing}"

    return True, "Valid verification prompt"


# Transformers

def minimize_verbosity(prompt: str) -> str:
    """Minimize prompt verbosity."""
    # Remove excessive whitespace
    prompt = re.sub(r'\n{3,}', '\n\n', prompt)

    # Remove filler words (case-insensitive)
    filler_words = [
        "please ", "kindly ", "would you ",
        "could you ", "it would be great if "
    ]

    for filler in filler_words:
        # Remove both lowercase and capitalized versions
        prompt = prompt.replace(filler, "")
        prompt = prompt.replace(filler.capitalize(), "")

    return prompt.strip()


def clean_ticket_language(prompt: str) -> str:
    """Clean ticket generation language."""
    # Remove flowery language
    replacements = {
        "create a ticket for": "ticket:",
        "generate a ticket for": "ticket:",
        "please generate": "generate",
        "would like to": "must",
        "should probably": "must",
        "it might be good to": "requirement:"
    }

    for old, new in replacements.items():
        prompt = prompt.replace(old, new)

    return prompt


# Decorators for easy injection

def inject_prompts(injector: PromptInjector):
    """Decorator to inject prompts into function calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract context from kwargs if present
            if "prompt" in kwargs and "context" in kwargs:
                context = kwargs["context"]
                if isinstance(context, dict):
                    injection_context = InjectionContext(
                        operation=context.get("operation", ""),
                        provider=context.get("provider", ""),
                        model=context.get("model", ""),
                        user_prompt=kwargs["prompt"],
                        metadata=context
                    )
                    kwargs["prompt"] = injector.inject(injection_context)

            return func(*args, **kwargs)
        return wrapper
    return decorator


# Global injector registry

class InjectorRegistry:
    """Registry for managing multiple injectors."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.injectors = {}
        return cls._instance

    def register(self, name: str, injector: PromptInjector) -> None:
        """Register an injector."""
        self.injectors[name] = injector

    def get(self, name: str) -> Optional[PromptInjector]:
        """Get injector by name."""
        return self.injectors.get(name)

    def inject_all(self, context: InjectionContext) -> str:
        """Apply all registered injectors."""
        result = context.user_prompt

        for injector in self.injectors.values():
            context.user_prompt = result
            result = injector.inject(context)

        return result


# Initialize default injectors
def initialize_default_injectors():
    """Initialize and register default injectors."""
    registry = InjectorRegistry()

    registry.register("production", create_production_injector())
    registry.register("verification", create_verification_injector())
    registry.register("ticket", create_ticket_injector())

    return registry
