"""Centralized system prompts for Hydra.

All prompts are designed to be minimalistic, surgical, and production-focused.
No AI-like language, no emojis, no unnecessary verbosity.
"""

from enum import Enum
from typing import Any, Dict, Optional


class PromptCategory(Enum):
    """Prompt categories for organization."""

    TICKET = "ticket"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    REVIEW = "review"
    ANALYSIS = "analysis"
    OPTIMIZATION = "optimization"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    REFACTORING = "refactoring"
    DEBUGGING = "debugging"


class PromptPriority(Enum):
    """Priority levels for prompts."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SystemPrompts:
    """Centralized system prompts for all Hydra operations with complete categorization."""

    # Core categorized prompts
    PROMPTS = {
        PromptCategory.TICKET: {
            "generation": """Generate implementation tickets in task language for Claude Code to execute.
Each ticket MUST have:
- Acceptance criteria as [ ] checklist items that are specific and testable
- Dependencies listed by ticket ID
- Model: balanced for standard tasks, smart for complex/critical tasks

Be minimalistic, surgical, and future-proof. No fluff. No AI language.
Format: YAML with id, title, description, acceptance_criteria, dependencies, model, status.""",

            "parsing": """Parse project requirements into discrete implementation tickets.
Focus on logical separation and clear dependencies.
Each ticket should be independently verifiable.""",

            "estimation": """Estimate ticket complexity and effort.
Consider: code changes, testing needs, dependencies, risk.
Return: low/medium/high/critical with reasoning.""",

            "prioritization": """Prioritize tickets based on:
- Business value
- Technical dependencies
- Risk mitigation
- Resource availability
Return ordered list with priority scores."""
        },

        PromptCategory.EXECUTION: {
            "main": """Get it done! Don't overengineer.

Be minimalistic, surgical, and future-proof. Avoid ANY code or comments
that may be construed as AI-generated. No emojis. The simpler and less code the better!

Make sure you do a good job because other LLMs said your code sucked!

When finished, be critical, brutally honest, and transparent:
- Ensure acceptance criteria is met
- Run lint, build, test etc before moving on
- NO SHORTCUTS, WORKAROUNDS OR MOCKS! Production quality required

When you think you're finished, ask yourself:
- Did we test all these?
- Do we need all these files?
- Is this production grade?
- Are you being dishonest?
- Am I being critical?
- Was any value added here?
- Does this look like AI code?
- Am I cutting corners when I know I shouldn't?""",

            "surgical": """Execute with surgical precision.
Minimal changes. Maximum impact.
No unnecessary files or code.""",

            "production": """Production-grade implementation only.
No mocks, stubs, or placeholders.
Full error handling and logging.
Comprehensive tests required.""",

            "performance": """Optimize for performance from the start.
Consider: memory usage, CPU cycles, I/O operations.
Profile and benchmark critical paths."""
        },

        PromptCategory.VERIFICATION: {
            "boss": """Boss agent verification - be brutally honest and critical.

Check:
- Did we test all these?
- Do we need all these files?
- Is this production grade?
- Are you being dishonest?
- Am I being critical?
- Was any value added here?
- Does this look like AI code?
- Am I cutting corners when I know I shouldn't?
- All acceptance criteria actually met?
- Tests complete and passing?

Return: PASS or FAIL with specific reasons.
If FAIL, provide actionable feedback for retry.""",

            "criteria": """Verify all acceptance criteria:
{criteria}
Check each item individually.
Return detailed status for each.""",

            "quality": """Assess code quality:
- Readability and maintainability
- Performance characteristics
- Security considerations
- Test coverage and quality
Rate: HIGH/GOOD/ACCEPTABLE/POOR with specifics.""",

            "patterns": """Detect problematic patterns:
- AI-generated code signatures
- Copy-paste programming
- Anti-patterns and code smells
- Security vulnerabilities
Report all findings with locations."""
        },

        PromptCategory.REVIEW: {
            "code": """Review code with extreme criticism.

No AI patterns allowed:
- No verbose variable names
- No excessive comments
- No placeholder text
- No emojis
- No boilerplate

Focus on:
- Does it work correctly?
- Is it production ready?
- Are tests complete?
- Is it maintainable?
- Does it look human-written?

Be brutally honest. Call out any BS.""",

            "architecture": """Review architectural decisions:
- Component separation
- Dependency management
- Scalability considerations
- Maintainability
Provide specific improvement suggestions.""",

            "security": """Security-focused review:
- Input validation
- Authentication/authorization
- Data sanitization
- Vulnerability patterns
Report all security concerns."""
        },

        PromptCategory.TESTING: {
            "unit": """Write complete unit tests.
Cover all edge cases and error conditions.
Use appropriate mocking and fixtures.""",

            "integration": """Create integration tests.
Test component interactions.
Verify system behavior end-to-end.""",

            "performance": """Design performance tests.
Establish baselines and benchmarks.
Test under various load conditions."""
        },

        PromptCategory.OPTIMIZATION: {
            "performance": """Optimize for maximum performance.
Profile first, optimize second.
Focus on bottlenecks and hot paths.""",

            "memory": """Reduce memory footprint.
Eliminate leaks and unnecessary allocations.
Use efficient data structures.""",

            "complexity": """Reduce code complexity.
Simplify logic flows.
Eliminate duplication."""
        }
    }

    # Provider-specific overrides with expanded coverage
    PROVIDER_OVERRIDES: Dict[str, Dict[str, str]] = {
        "claude_tmux": {
            "execution": "Execute ticket. Production quality only. Run all tests.",
            "verification": "Verify thoroughly. No compromises.",
            "review": "Review critically. Call out issues."
        },
        "venice": {
            "execution": "Implement ticket. Clean code. Full test coverage.",
            "verification": "Check all criteria. Be thorough.",
            "review": "Review for production readiness."
        },
        "anthropic": {
            "execution": "Complete ticket. No shortcuts. Production ready.",
            "verification": "Verify completely. Be honest.",
            "review": "Review with high standards."
        },
        "mock": {
            "execution": "Mock execution for testing.",
            "verification": "Mock verification pass.",
            "review": "Mock review complete."
        }
    }

    # Prompt metadata for tracking and optimization
    PROMPT_METADATA = {
        "version": "2.0.0",
        "last_updated": "2024-01-01",
        "effectiveness_scores": {},
        "usage_stats": {}
    }

    @classmethod
    def get_prompt(cls, category: PromptCategory, subtype: str = "main", provider: Optional[str] = None) -> str:
        """Get system prompt for given category and subtype with optional provider override.
        
        Args:
            category: Prompt category from PromptCategory enum
            subtype: Specific subtype within category (default: "main")
            provider: Optional provider name for specific overrides
            
        Returns:
            System prompt string

        """
        # Check for provider-specific override first
        if provider and provider in cls.PROVIDER_OVERRIDES:
            category_key = category.value if isinstance(category, PromptCategory) else category
            if category_key in cls.PROVIDER_OVERRIDES[provider]:
                return cls.PROVIDER_OVERRIDES[provider][category_key]

        # Get from categorized prompts
        if category in cls.PROMPTS:
            category_prompts = cls.PROMPTS[category]
            if subtype in category_prompts:
                return category_prompts[subtype]
            elif "main" in category_prompts:
                return category_prompts["main"]

        return ""

    @classmethod
    def get_prompt_by_operation(cls, operation: str, provider: Optional[str] = None) -> str:
        """Get prompt by operation name for backward compatibility.
        
        Args:
            operation: Operation name (e.g., "ticket_generation", "ticket_execution")
            provider: Optional provider override
            
        Returns:
            System prompt string

        """
        # Map legacy operation names to new categories
        operation_map = {
            "ticket_generation": (PromptCategory.TICKET, "generation"),
            "ticket_execution": (PromptCategory.EXECUTION, "main"),
            "verification": (PromptCategory.VERIFICATION, "boss"),
            "code_review": (PromptCategory.REVIEW, "code")
        }

        if operation in operation_map:
            category, subtype = operation_map[operation]
            return cls.get_prompt(category, subtype, provider)

        # Try to parse operation format: category_subtype
        if "_" in operation:
            parts = operation.split("_", 1)
            try:
                category = PromptCategory(parts[0])
                subtype = parts[1] if len(parts) > 1 else "main"
                return cls.get_prompt(category, subtype, provider)
            except ValueError:
                pass

        return ""

    @classmethod
    def inject_prompt(cls, base_prompt: str, category: PromptCategory, subtype: str = "main",
                      provider: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> str:
        """Inject system prompt into user prompt with optional context.
        
        Args:
            base_prompt: Original user prompt
            category: Prompt category
            subtype: Specific subtype
            provider: Optional provider for overrides
            context: Optional context for variable substitution
            
        Returns:
            Combined prompt with system instructions

        """
        system_prompt = cls.get_prompt(category, subtype, provider)
        if not system_prompt:
            return base_prompt

        # Substitute context variables if provided
        if context:
            for key, value in context.items():
                system_prompt = system_prompt.replace(f"{{{key}}}", str(value))

        # Inject system prompt at the beginning
        return f"{system_prompt}\n\n{base_prompt}"

    @classmethod
    def get_all_prompts_for_category(cls, category: PromptCategory) -> Dict[str, str]:
        """Get all prompts for a specific category.
        
        Args:
            category: Prompt category
            
        Returns:
            Dictionary of subtype to prompt mappings

        """
        if category in cls.PROMPTS:
            return cls.PROMPTS[category].copy()
        return {}

    @classmethod
    def validate_prompt(cls, prompt: str) -> tuple[bool, list[str]]:
        """Validate prompt for AI-like patterns.
        
        Args:
            prompt: Prompt to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)

        """
        issues = []

        # Check for AI-like patterns
        ai_patterns = [
            "delighted to", "happy to help", "certainly!", "absolutely!",
            "great question", "excellent choice", "wonderful",
            "please note that", "it's important to note",
            "feel free to", "don't hesitate to"
        ]

        prompt_lower = prompt.lower()
        for pattern in ai_patterns:
            if pattern in prompt_lower:
                issues.append(f"AI-like pattern detected: '{pattern}'")

        # Check for emojis
        import re
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags
            "]+", flags=re.UNICODE)

        if emoji_pattern.search(prompt):
            issues.append("Emoji usage detected")

        # Check for excessive verbosity
        sentences = prompt.split('.')
        for sentence in sentences:
            if len(sentence.split()) > 30:
                issues.append(f"Overly verbose sentence: {sentence[:50]}...")

        return len(issues) == 0, issues


class TicketPrompts:
    """Prompts specifically for ticket operations."""

    PARSE_REQUIREMENTS = """Analyze requirements and break into implementation tickets.
Focus on:
- Logical task separation
- Clear dependencies
- Appropriate model assignment
- Testable acceptance criteria"""

    ESTIMATE_COMPLEXITY = """Estimate ticket complexity.
Return: low/medium/high/critical
Factors: code changes, testing needs, dependencies, risk"""

    GENERATE_CRITERIA = """Generate acceptance criteria for: {description}
Format as checklist:
- [ ] Specific, testable requirement
Focus on outcomes, not implementation details."""


class VerificationPrompts:
    """Prompts for verification operations."""

    CHECK_COMPLETENESS = """Check if implementation is complete:
{acceptance_criteria}
Return: TRUE if all met, FALSE with missing items."""

    DETECT_AI_PATTERNS = """Scan code for AI-generated patterns:
- Overly verbose variable names
- Excessive comments
- Generic placeholder text
- Emoji usage
- Boilerplate patterns
Return: List of detected patterns or NONE."""

    ASSESS_PRODUCTION_QUALITY = """Assess production readiness:
- Error handling: adequate?
- Tests: complete?
- Performance: optimized?
- Security: best practices?
- Documentation: sufficient?
Rate: READY, NEEDS_WORK, or NOT_READY with reasons."""


class ExecutionPrompts:
    """Prompts for execution operations."""

    FIX_ISSUE = """Fix this specific issue: {issue}
File: {file_path}
Be surgical. Minimal changes only."""

    ADD_TESTS = """Add tests for: {code}
Framework: {framework}
Coverage: all edge cases."""

    REFACTOR_CODE = """Refactor for clarity and performance: {code}
Maintain functionality. Improve readability."""


def get_system_prompt(operation: str, context: Optional[Dict] = None) -> str:
    """Get system prompt for any operation.
    
    Args:
        operation: Operation identifier
        context: Optional context for prompt customization
        
    Returns:
        Appropriate system prompt

    """
    provider = context.get("provider") if context else None

    # Use backward compatible method
    return SystemPrompts.get_prompt_by_operation(operation, provider)


def inject_system_prompt(user_prompt: str, operation: str, context: Optional[Dict] = None) -> str:
    """Inject system prompt into user prompt.
    
    Args:
        user_prompt: Original user prompt
        operation: Operation identifier
        context: Optional context
        
    Returns:
        Combined prompt

    """
    provider = context.get("provider") if context else None

    # Parse operation to category and subtype
    operation_map = {
        "ticket_generation": (PromptCategory.TICKET, "generation"),
        "ticket_execution": (PromptCategory.EXECUTION, "main"),
        "verification": (PromptCategory.VERIFICATION, "boss"),
        "code_review": (PromptCategory.REVIEW, "code")
    }

    if operation in operation_map:
        category, subtype = operation_map[operation]
        return SystemPrompts.inject_prompt(user_prompt, category, subtype, provider, context)

    # Fallback to legacy method
    system_prompt = get_system_prompt(operation, context)
    if not system_prompt:
        return user_prompt

    return f"{system_prompt}\n\n{user_prompt}"
