"""Production-focused execution prompts for Hydra.

Surgical, minimalistic prompts for getting things done without overengineering.
No AI patterns, no fluff, just direct commands for production-quality code.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionMode(Enum):
    """Execution modes for different scenarios."""

    SURGICAL = "surgical"  # Minimal, precise changes
    COMPLETE = "complete"  # Full implementation
    HOTFIX = "hotfix"  # Emergency fixes
    REFACTOR = "refactor"  # Code improvement
    PERFORMANCE = "performance"  # Optimization focus


class ExecutionPriority(Enum):
    """Priority levels for execution."""

    EMERGENCY = "emergency"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class ExecutionContext:
    """Context for execution prompts."""

    ticket_id: str
    acceptance_criteria: List[str]
    files_affected: List[str]
    dependencies: List[str]
    mode: ExecutionMode
    priority: ExecutionPriority
    constraints: Optional[Dict[str, Any]] = None


class ProductionExecutionPrompts:
    """Production-grade execution prompts."""

    MAIN_EXECUTION = """Execute ticket {ticket_id}. GET IT DONE!

Acceptance criteria:
{acceptance_criteria}

CRITICAL RULES - VIOLATIONS = FAILURE:
- Get it done WITHOUT overengineering. Ship working code NOW.
- Write MINIMAL code with MAXIMUM impact. Every line must earn its place.
- PRODUCTION QUALITY ONLY. Zero shortcuts, zero mocks, zero workarounds.
- Run lint, build, and ALL tests before marking complete. NO EXCEPTIONS.
- BANNED: AI patterns, verbose naming, excessive comments, emojis, placeholder text.
- BANNED: Names like "helper", "manager", "handler", "util" without specific purpose.
- BANNED: Comments that explain WHAT instead of WHY.
- BANNED: Any TODO, FIXME, NOTE, HACK comments.

MANDATORY SELF-VERIFICATION CHECKLIST:
□ Every acceptance criterion actually implemented and working?
□ All tests complete, meaningful, and passing?
□ Code looks like experienced human wrote it (terse, practical)?
□ Zero corners cut, zero technical debt added?
□ Actual business value delivered, not just code written?
□ Ready for production deployment RIGHT NOW?
□ Did you run: lint, typecheck, full test suite?

IF ANY CHECKBOX IS NO, YOU HAVE FAILED. FIX IT."""

    SURGICAL_EXECUTION = """Surgical execution for {ticket_id}.

Target files: {files}
Changes required: {changes}

Make ONLY necessary changes.
No refactoring outside scope.
Preserve existing functionality.
Test affected areas only."""

    HOTFIX_EXECUTION = """HOTFIX: {issue}

Immediate action required.
Fix the issue. Nothing else.
Minimal risk. Maximum stability.
Test the fix thoroughly.
Document the change."""

    PERFORMANCE_EXECUTION = """Execute performance optimization for {component}.

Metrics to improve:
{metrics}

Profile first. Optimize second.
Measure and verify improvements.
Avoid premature optimization.
Maintain functionality and test thoroughly."""

    REFACTOR_EXECUTION = """Refactor {component}.

Goals:
{refactor_goals}

Improve without changing behavior.
Simplify complex logic.
Remove duplication.
Enhance readability.
Full regression testing required."""

    BUG_FIX = """Fix bug: {bug_description}

Location: {file_location}
Root cause: {root_cause}

Fix the root cause, not symptoms.
Add test to prevent regression.
Verify fix doesn't break anything else."""

    FEATURE_IMPLEMENTATION = """Implement feature: {feature_name}

Requirements:
{requirements}

Build incrementally.
Test each component.
No placeholder code.
Full error handling.
Production-ready from start."""

    TEST_WRITING = """Write tests for {component}.

Coverage requirements:
- Unit tests for all public methods
- Edge cases and error conditions
- Integration tests for workflows
- Performance tests for critical paths

Use existing test framework.
Follow project conventions.
No test duplication."""

    DEPENDENCY_UPDATE = """Update dependencies.

Updates required:
{dependency_list}

Check compatibility.
Run full test suite.
Update documentation.
Test in isolation first."""

    SECURITY_FIX = """Security fix: {vulnerability}

Severity: {severity}
Impact: {impact}

Fix immediately.
No information leakage.
Full security audit of related code.
Document the fix without exposing details."""

    CODE_CLEANUP = """Clean up {target}.

Focus:
- Remove dead code
- Fix linting issues
- Standardize formatting
- Remove debug statements
- Optimize imports

Don't change functionality."""

    INTEGRATION = """Integrate {component} with {target}.

Interface requirements:
{interface_spec}

Clean integration points.
Proper error handling.
Full integration tests.
Documentation of interfaces."""

    MIGRATION = """Migrate {source} to {target}.

Migration plan:
{plan}

Preserve all functionality.
Maintain data integrity.
Rollback capability required.
Test migration thoroughly."""


class ExecutionPromptBuilder:
    """Builder for execution prompts."""

    def __init__(self):
        self.prompts = ProductionExecutionPrompts()
        self.context = {}

    def with_ticket(self, ticket_id: str, criteria: List[str]) -> "ExecutionPromptBuilder":
        """Add ticket context."""
        self.context["ticket_id"] = ticket_id
        self.context["acceptance_criteria"] = "\n".join(f"- {c}" for c in criteria)
        return self

    def with_mode(self, mode: ExecutionMode) -> "ExecutionPromptBuilder":
        """Set execution mode."""
        self.context["mode"] = mode
        return self

    def with_files(self, files: List[str]) -> "ExecutionPromptBuilder":
        """Add affected files."""
        self.context["files"] = ", ".join(files)
        return self

    def with_priority(self, priority: ExecutionPriority) -> "ExecutionPromptBuilder":
        """Set execution priority."""
        self.context["priority"] = priority
        return self

    def build(self) -> str:
        """Build execution prompt."""
        mode = self.context.get("mode", ExecutionMode.COMPLETE)

        # Select appropriate prompt template
        if mode == ExecutionMode.SURGICAL:
            template = self.prompts.SURGICAL_EXECUTION
        elif mode == ExecutionMode.HOTFIX:
            template = self.prompts.HOTFIX_EXECUTION
        elif mode == ExecutionMode.PERFORMANCE:
            template = self.prompts.PERFORMANCE_EXECUTION
        elif mode == ExecutionMode.REFACTOR:
            template = self.prompts.REFACTOR_EXECUTION
        else:
            template = self.prompts.MAIN_EXECUTION

        # Substitute context
        for key, value in self.context.items():
            template = template.replace(f"{{{key}}}", str(value))

        return template


class ExecutionValidator:
    """Validator for execution completeness."""

    @staticmethod
    def validate_execution(
        criteria: List[str],
        implementation: Dict[str, Any]
    ) -> tuple[bool, List[str]]:
        """Validate execution against criteria.
        
        Args:
            criteria: Acceptance criteria list
            implementation: Implementation details
            
        Returns:
            Tuple of (is_complete, missing_items)

        """
        missing = []

        # Check each criterion
        for criterion in criteria:
            # Simple check - would be more sophisticated in practice
            if not implementation.get(f"criterion_{criteria.index(criterion)}", False):
                missing.append(criterion)

        # Check for required elements
        if "tests" not in implementation or not implementation["tests"]:
            missing.append("No tests provided")

        if "documentation" not in implementation:
            missing.append("No documentation")

        return len(missing) == 0, missing

    @staticmethod
    def check_production_quality(code: str) -> tuple[bool, List[str]]:
        """Check code for production quality.
        
        Args:
            code: Code to check
            
        Returns:
            Tuple of (is_production_ready, issues)

        """
        issues = []

        # Check for common non-production patterns
        bad_patterns = [
            ("TODO", "Unfinished TODO found"),
            ("FIXME", "FIXME comment found"),
            ("console.log", "Debug logging found"),
            ("print(", "Debug print found"),
            ("debugger", "Debugger statement found"),
            ("localhost", "Hardcoded localhost found"),
            ("password =", "Hardcoded password found"),
            ("api_key =", "Hardcoded API key found"),
            ("mock", "Mock code detected"),
            ("stub", "Stub code detected"),
            ("dummy", "Dummy code detected"),
            ("test_", "Test code in production"),
            ("assert ", "Assert in production code")
        ]

        for pattern, message in bad_patterns:
            if pattern in code:
                issues.append(message)

        # Check for proper error handling
        if "try" not in code and "except" not in code and "catch" not in code:
            if len(code) > 100:  # Only for non-trivial code
                issues.append("No error handling found")

        # Check for AI patterns
        has_ai, ai_patterns = AIPatternDetector.detect_ai_patterns(code)
        if has_ai:
            issues.extend(ai_patterns)

        return len(issues) == 0, issues


class AIPatternDetector:
    """Detect AI-generated code patterns with ZERO tolerance."""

    # BANNED patterns - immediate failure
    BANNED_PATTERNS = {
        'emojis': ['🎉', '🚀', '✨', '💡', '🔧', '⚡', '🎯', '🏆', '👍', '💪', '📝', '🔥', '⭐'],
        'ai_words': ['comprehensive', 'robust', 'elegant', 'sophisticated', 'delightful',
                     'seamless', 'powerful', 'flexible', 'scalable', 'intuitive', 'innovative'],
        'verbose_patterns': [r'DataManager\w+Helper', r'Process\w+Handler', r'Service\w+Factory'],
        'placeholder': ['TODO', 'FIXME', 'XXX', 'HACK', 'NOTE:', 'placeholder', 'dummy', 'temp'],
        'excessive_comments': [r'#\s*Step \d+:', r'#\s*Initialize', r'#\s*Define', r'#\s*Create instance']
    }

    @staticmethod
    def detect_ai_patterns(code: str) -> tuple[bool, List[str]]:
        """Detect AI-generated code patterns with ZERO tolerance.
        
        Args:
            code: Code to analyze
            
        Returns:
            Tuple of (has_patterns, detected_patterns)

        """
        import re
        patterns = []

        # Check for banned emojis
        for emoji in AIPatternDetector.BANNED_PATTERNS['emojis']:
            if emoji in code:
                patterns.append(f"BANNED: Emoji '{emoji}' detected")

        # Check for banned AI words
        code_lower = code.lower()
        for word in AIPatternDetector.BANNED_PATTERNS['ai_words']:
            if word in code_lower:
                patterns.append(f"BANNED: AI word '{word}' detected")

        # Check for verbose naming patterns
        for pattern_str in AIPatternDetector.BANNED_PATTERNS['verbose_patterns']:
            pattern = re.compile(pattern_str)
            if pattern.search(code):
                patterns.append(f"BANNED: Verbose pattern '{pattern_str}' detected")

        # Check for placeholder text
        for placeholder in AIPatternDetector.BANNED_PATTERNS['placeholder']:
            if placeholder in code or placeholder.lower() in code_lower:
                patterns.append(f"BANNED: Placeholder '{placeholder}' detected")

        # Check for excessive comments
        for comment_pattern_str in AIPatternDetector.BANNED_PATTERNS['excessive_comments']:
            comment_pattern = re.compile(comment_pattern_str, re.IGNORECASE)
            if comment_pattern.search(code):
                patterns.append("BANNED: Excessive comment pattern detected")

        # Additional strict checks
        # Check for verbose generic naming
        generic_names = ["Manager", "Helper", "Processor", "Handler", "Service", "Provider", "Factory", "Utility", "Wrapper", "Adapter"]
        for name in generic_names:
            # Use regex to catch compound names like DataHelper, ServiceManager, etc.
            if (re.search(rf'\b\w*{name}\b', code) or
                f"def {name.lower()}" in code or
                f"{name}(" in code):
                patterns.append(f"Generic naming: {name}")

        # Check for AI-style comments
        ai_comment_patterns = [
            "# Initialize", "# Create the", "# Set up the", "# Define the",
            "This function", "This method", "This class", "This module",
            "# Step 1", "# Step 2", "# First,", "# Next,", "# Finally,",
            "# Main function", "# Helper function", "# Utility function"
        ]
        for pattern in ai_comment_patterns:
            if pattern in code or pattern.lower() in code_lower:
                patterns.append(f"AI comment: {pattern}")

        # Check for excessive commenting (more than 25% of lines)
        lines = code.strip().split('\n')
        if lines:
            comment_lines = sum(1 for line in lines if line.strip().startswith('#') or line.strip().startswith('//'))
            if comment_lines / len(lines) > 0.25:
                patterns.append(f"Excessive commenting: {comment_lines}/{len(lines)} lines ({100*comment_lines/len(lines):.1f}%)")

        # Check for unnecessary docstrings explaining obvious things
        obvious_docstring_patterns = [
            r'""".*[Gg]et.*\."""\.?\s*def get',
            r'""".*[Ss]et.*\."""\.?\s*def set',
            r'""".*[Ii]nitialize.*\."""\.?\s*def __init__',
            r'""".*[Cc]onstructor.*\."""',
            r'""".*[Mm]ain.*function.*\."""'
        ]
        for pattern_str in obvious_docstring_patterns:
            if re.search(pattern_str, code, re.DOTALL):
                patterns.append("Obvious docstring detected")
                break

        return len(patterns) > 0, patterns


class ExecutionStrategies:
    """Different execution strategies."""

    @staticmethod
    def get_strategy(mode: ExecutionMode) -> Dict[str, Any]:
        """Get execution strategy for mode.
        
        Args:
            mode: Execution mode
            
        Returns:
            Strategy configuration

        """
        strategies = {
            ExecutionMode.SURGICAL: {
                "scope": "minimal",
                "testing": "targeted",
                "refactoring": "none",
                "documentation": "inline"
            },
            ExecutionMode.COMPLETE: {
                "scope": "full",
                "testing": "thorough",
                "refactoring": "allowed",
                "documentation": "full"
            },
            ExecutionMode.HOTFIX: {
                "scope": "critical_only",
                "testing": "regression",
                "refactoring": "forbidden",
                "documentation": "changelog"
            },
            ExecutionMode.REFACTOR: {
                "scope": "component",
                "testing": "full_regression",
                "refactoring": "primary",
                "documentation": "updated"
            },
            ExecutionMode.PERFORMANCE: {
                "scope": "hot_paths",
                "testing": "performance",
                "refactoring": "optimization",
                "documentation": "benchmarks"
            }
        }

        return strategies.get(mode, strategies[ExecutionMode.COMPLETE])


def generate_execution_prompt(
    operation: str,
    context: Dict[str, Any]
) -> str:
    """Generate execution prompt for operation.
    
    Args:
        operation: Operation type
        context: Execution context
        
    Returns:
        Generated prompt

    """
    prompts = ProductionExecutionPrompts()

    operation_map = {
        "main": prompts.MAIN_EXECUTION,
        "surgical": prompts.SURGICAL_EXECUTION,
        "hotfix": prompts.HOTFIX_EXECUTION,
        "performance": prompts.PERFORMANCE_EXECUTION,
        "refactor": prompts.REFACTOR_EXECUTION,
        "bug_fix": prompts.BUG_FIX,
        "feature": prompts.FEATURE_IMPLEMENTATION,
        "test": prompts.TEST_WRITING,
        "dependency": prompts.DEPENDENCY_UPDATE,
        "security": prompts.SECURITY_FIX,
        "cleanup": prompts.CODE_CLEANUP,
        "integration": prompts.INTEGRATION,
        "migration": prompts.MIGRATION
    }

    template = operation_map.get(operation, prompts.MAIN_EXECUTION)

    # Substitute context
    for key, value in context.items():
        if isinstance(value, list):
            value = "\n".join(f"- {v}" for v in value)
        template = template.replace(f"{{{key}}}", str(value))

    return template


def create_execution_checklist(
    ticket_id: str,
    criteria: List[str]
) -> List[str]:
    """Create execution checklist.
    
    Args:
        ticket_id: Ticket identifier
        criteria: Acceptance criteria
        
    Returns:
        Execution checklist

    """
    checklist = [
        f"Read and understand ticket {ticket_id}",
        "Identify affected files and components",
        "Plan implementation approach",
        "Write implementation code",
        "Add complete test coverage",
        "Run linting and formatting",
        "Execute full test suite",
        "Verify all acceptance criteria met",
        "Check for production readiness",
        "Document changes if needed"
    ]

    # Add specific criteria checks
    for criterion in criteria:
        checklist.append(f"Verify: {criterion}")

    return checklist


class PostExecutionPrompts:
    """Prompts for post-execution validation."""

    SELF_REVIEW = """BRUTAL SELF-REVIEW - BE HONEST OR FAIL

CRITICAL QUESTIONS (Answer each one):
1. Does it meet ALL acceptance criteria COMPLETELY? Not partially, COMPLETELY.
2. Are tests COMPLETE? Do they test real scenarios, edge cases, errors?
3. Is the code PRODUCTION-READY right now? Could you deploy it TODAY?
4. Did you take ANY shortcuts, use ANY workarounds, or cut ANY corners?
5. Does the code look like an EXPERIENCED HUMAN wrote it? Not an AI?
6. Is there ACTUAL BUSINESS VALUE delivered? Not just code for code's sake?
7. Did you run lint, typecheck, and FULL test suite? Did they ALL pass?
8. Would you stake your reputation on this code working in production?
9. Is every line of code necessary? Could you remove anything?
10. Are there zero AI patterns (verbose names, excessive comments, emojis)?

IF ANY ANSWER IS NO, YOU HAVE FAILED. FIX IT NOW."""

    FINAL_CHECK = """FINAL PRODUCTION GATE CHECK

HARD REQUIREMENTS (ALL must be YES):
□ Zero debug code (no console.log, print, debugger)
□ Zero hardcoded values (no localhost, passwords, keys)
□ Proper error handling (try/catch where needed)
□ Security best practices (input validation, SQL injection prevention)
□ Performance acceptable (no O(n²) where O(n) possible)
□ Code follows project conventions exactly
□ Tests cover happy path AND failure cases
□ No placeholder or temporary code
□ No TODO, FIXME, HACK comments
□ Code is DRY - no copy-paste duplication

PRODUCTION READY? If even ONE box unchecked: NO - FIX IT."""

    ROLLBACK_CHECK = """ROLLBACK SAFETY CHECK

VERIFY ALL:
□ Database migrations have DOWN migration?
□ API changes are backward compatible?
□ Feature flags can disable this feature?
□ No destructive operations without backup?
□ Rollback tested and documented?

Can this be rolled back safely without data loss? YES/NO"""

    QUALITY_GATES = """QUALITY GATE CHECKLIST

MUST PASS ALL:
□ Cyclomatic complexity < 10 per function
□ No functions > 50 lines
□ No files > 500 lines
□ Test coverage > 80%
□ Zero linting errors
□ Zero type errors
□ All tests passing
□ Build succeeds
□ No security vulnerabilities
□ Documentation updated if needed

ALL GATES PASSED? Ship it. ANY FAILED? Fix it."""

    HUMAN_CODE_CHECK = """DOES THIS LOOK HUMAN-WRITTEN?

CHECK:
- Variable names: short, practical (not verboseDescriptiveNames)
- Comments: sparse, explain WHY not WHAT
- Code structure: pragmatic, not over-architected
- No unnecessary abstractions or design patterns
- No "clever" code - straightforward is better
- Looks like code from experienced developer, not junior or AI

Pass the "Would a senior dev write this?" test? YES/NO"""
