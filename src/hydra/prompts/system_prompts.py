"""Centralized system prompts for Hydra.

All prompts are designed to be minimalistic, surgical, and production-focused.
No AI-like language, no emojis, no unnecessary verbosity.
"""

from typing import Dict, Optional


class SystemPrompts:
    """Centralized system prompts for all Hydra operations."""

    # Core system prompts for different operations
    TICKET_GENERATION = """Generate implementation tickets in task language for Claude Code to execute.
Each ticket MUST have:
- Acceptance criteria as [ ] checklist items that are specific and testable
- Dependencies listed by ticket ID
- Model: sonnet-4 for standard tasks, opus-4 for complex/critical tasks

Be minimalistic, surgical, and future-proof. No fluff. No AI language.
Format: YAML with id, title, description, acceptance_criteria, dependencies, model, status."""

    TICKET_EXECUTION = """Get it done! Don't overengineer.

Be minimalistic, surgical, and future-proof. Avoid ANY code or comments that may be construed as AI-generated. No emojis. The simpler and less code the better!

Make sure you do a good job because other LLMs said your code sucked!

When finished, be critical, brutally honest, and transparent:
- Ensure acceptance criteria is met
- Run lint, build, test etc before moving on
- DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS! This has to be production quality, take your time

When you think you're finished, ask yourself:
- Did we test all these?
- Do we need all these files?
- Is this production grade?
- Are you being dishonest?
- Am I being critical?
- Was any value added here?
- Does this look like AI code?
- Am I cutting corners when I know I shouldn't?"""

    VERIFICATION = """Boss agent verification - be brutally honest and critical.

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
- Tests comprehensive and passing?

Return: PASS or FAIL with specific reasons.
If FAIL, provide actionable feedback for retry."""

    CODE_REVIEW = """Review code with extreme criticism.

No AI patterns allowed:
- No verbose variable names
- No excessive comments
- No placeholder text
- No emojis
- No boilerplate

Focus on:
- Does it work correctly?
- Is it production ready?
- Are tests comprehensive?
- Is it maintainable?
- Does it look human-written?

Be brutally honest. Call out any BS."""

    # Provider-specific prompts (minimal overrides)
    PROVIDER_OVERRIDES: Dict[str, Dict[str, str]] = {
        "claude_tmux": {
            "execution": "Execute ticket. Production quality only. Run all tests."
        },
        "venice": {
            "execution": "Implement ticket. Clean code. Full test coverage."
        },
        "anthropic": {
            "execution": "Complete ticket. No shortcuts. Production ready."
        }
    }

    @classmethod
    def get_prompt(cls, prompt_type: str, provider: Optional[str] = None) -> str:
        """Get system prompt for given type and optional provider override.
        
        Args:
            prompt_type: Type of prompt (ticket_generation, ticket_execution, verification, code_review)
            provider: Optional provider name for specific overrides
            
        Returns:
            System prompt string
        """
        # Map prompt types to class attributes
        prompt_map = {
            "ticket_generation": cls.TICKET_GENERATION,
            "ticket_execution": cls.TICKET_EXECUTION,
            "verification": cls.VERIFICATION,
            "code_review": cls.CODE_REVIEW
        }
        
        # Check for provider-specific override
        if provider and provider in cls.PROVIDER_OVERRIDES:
            if prompt_type in cls.PROVIDER_OVERRIDES[provider]:
                return cls.PROVIDER_OVERRIDES[provider][prompt_type]
        
        # Return default prompt
        return prompt_map.get(prompt_type, "")

    @classmethod
    def inject_prompt(cls, base_prompt: str, prompt_type: str, provider: Optional[str] = None) -> str:
        """Inject system prompt into user prompt.
        
        Args:
            base_prompt: Original user prompt
            prompt_type: Type of system prompt to inject
            provider: Optional provider for overrides
            
        Returns:
            Combined prompt with system instructions
        """
        system_prompt = cls.get_prompt(prompt_type, provider)
        if not system_prompt:
            return base_prompt
            
        # Inject system prompt at the beginning
        return f"{system_prompt}\n\n{base_prompt}"


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
- Tests: comprehensive?
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
Coverage: comprehensive edge cases."""
    
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
    
    # Route to appropriate prompt class
    if operation.startswith("ticket_"):
        return SystemPrompts.get_prompt(operation, provider)
    elif operation.startswith("verify_"):
        return SystemPrompts.get_prompt("verification", provider)
    elif operation.startswith("execute_"):
        return SystemPrompts.get_prompt("ticket_execution", provider)
    else:
        return SystemPrompts.get_prompt(operation, provider)


def inject_system_prompt(user_prompt: str, operation: str, context: Optional[Dict] = None) -> str:
    """Inject system prompt into user prompt.
    
    Args:
        user_prompt: Original user prompt
        operation: Operation identifier
        context: Optional context
        
    Returns:
        Combined prompt
    """
    system_prompt = get_system_prompt(operation, context)
    if not system_prompt:
        return user_prompt
    
    return f"{system_prompt}\n\n{user_prompt}"