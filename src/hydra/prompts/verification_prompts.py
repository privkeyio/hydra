"""Brutal verification prompts for Hydra.

Boss agent prompts for ruthless quality checks and verification.
No compromises, no excuses, just brutal honesty about code quality.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class VerificationLevel(Enum):
    """Verification strictness levels."""

    LENIENT = "lenient"  # Basic checks
    STANDARD = "standard"  # Normal verification
    STRICT = "strict"  # Thorough verification
    BRUTAL = "brutal"  # No mercy verification


class VerificationResult(Enum):
    """Verification results."""

    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


@dataclass
class VerificationReport:
    """Detailed verification report."""

    result: VerificationResult
    criteria_results: Dict[str, bool]
    quality_score: float
    issues: List[str]
    recommendations: List[str]
    must_fix: List[str]
    retry_guidance: Optional[str] = None


class BrutalVerificationPrompts:
    """Brutal verification prompts for boss agent."""

    BOSS_VERIFICATION = """BOSS AGENT VERIFICATION - BE BRUTAL

Ticket: {ticket_id}
Implementation to verify: {implementation_summary}

CHECK EVERYTHING:

1. Acceptance Criteria:
{acceptance_criteria}
- Is EACH criterion FULLY met?
- No partial credit. Binary: YES or NO.

2. Code Quality:
- Does this look like a human wrote it?
- Any AI patterns (verbose names, excessive comments, emojis)?
- Is it the SIMPLEST solution possible?
- Any overengineering detected?

3. Production Readiness:
- Will this survive in production?
- Proper error handling everywhere?
- No debug code, TODOs, or FIXMEs?
- No hardcoded values or localhost?

4. Testing:
- Are tests ACTUALLY complete?
- Do they test real scenarios, not just happy paths?
- Any tests that just exist to pass?

5. Value Check:
- Does this add REAL value?
- Or is it just boilerplate nonsense?
- Ready to deploy this to YOUR production?

6. Honesty Check:
- Are we lying about completion?
- Any shortcuts taken?
- Anything swept under the rug?

VERDICT: PASS or FAIL

If FAIL, provide:
- Specific failures (no vague criticism)
- EXACTLY what needs fixing
- Priority order for fixes

Be brutal. Be honest. No participation trophies."""

    CRITERIA_VERIFICATION = """Verify acceptance criteria completion.

Criteria to check:
{criteria_list}

For EACH criterion:
- Check implementation evidence
- Verify with actual code/tests
- No assumptions, only facts

Report format:
- [ ] Criterion 1: PASS/FAIL - Reason
- [ ] Criterion 2: PASS/FAIL - Reason

Overall: X of Y criteria met.
Verdict: PASS only if 100% met."""

    AI_PATTERN_DETECTION = """Detect AI-generated code patterns.

Code to analyze:
{code_snippet}

Look for:
1. Variable names:
   - excessively_descriptive_variable_names
   - unnecessary_clarity_in_naming
   - names_that_explain_too_much

2. Comments:
   - Comments explaining obvious things
   - "Helper function to..." patterns
   - Over-documentation of simple logic

3. Structure:
   - Unnecessary abstraction layers
   - Over-engineered simple solutions
   - Boilerplate for no reason

4. Language patterns:
   - Overly agreeable language in strings
   - Emoji usage anywhere
   - Placeholder text like "Your X here"

5. Code smell:
   - Functions that do nothing useful
   - Tests that don't test anything
   - Circular logic implementations

Found patterns:
{report_each_pattern}

AI Probability: 0-100%
Human-looking: YES/NO"""

    PRODUCTION_QUALITY = """Assess production readiness.

Component: {component}
Type: {component_type}

Production Checklist:
- [ ] Error handling: Comprehensive?
- [ ] Edge cases: All covered?
- [ ] Performance: Acceptable for scale?
- [ ] Security: Best practices followed?
- [ ] Monitoring: Logs and metrics?
- [ ] Documentation: Sufficient for ops?
- [ ] Rollback: Can we revert safely?
- [ ] Dependencies: All production-grade?
- [ ] Configuration: Externalized properly?
- [ ] Testing: Ready to bet your job on it?

Issues found:
{list_all_issues}

Production Ready: YES/NO
Confidence: 0-100%"""

    TEST_QUALITY = """Evaluate test quality.

Tests to review:
{test_files}

Check:
1. Coverage:
   - Line coverage %
   - Branch coverage %
   - Edge case coverage

2. Quality:
   - Do tests actually test?
   - Any useless assertions?
   - Proper test isolation?

3. Scenarios:
   - Happy path: covered
   - Error cases?
   - Boundary conditions?
   - Concurrent access?
   - Performance limits?

4. Maintenance:
   - Will tests break easily?
   - Clear failure messages?
   - Fast execution?

Test Quality Score: 0-100
Recommendation: ACCEPT/REJECT/IMPROVE"""

    PERFORMANCE_CHECK = """Performance verification.

Component: {component}
Expected load: {load_profile}

Verify:
- Response time < {threshold}ms
- Memory usage < {memory_limit}
- CPU usage reasonable
- No obvious bottlenecks
- No N+1 queries
- Proper caching implemented
- Connection pooling used

Performance issues:
{issues_found}

Meets requirements: YES/NO"""

    SECURITY_AUDIT = """Security verification.

Code to audit:
{code_location}

Check for:
- Input validation on ALL inputs
- SQL injection vulnerabilities
- XSS vulnerabilities
- Authentication bypasses
- Authorization checks
- Sensitive data exposure
- Insecure dependencies
- Hardcoded secrets
- Weak cryptography
- CORS misconfigurations

Vulnerabilities found:
{vulnerability_list}

Security Status: SECURE/VULNERABLE/NEEDS_REVIEW"""

    DEPENDENCY_CHECK = """Verify dependencies are production-appropriate.

Dependencies:
{dependency_list}

For each dependency:
- Is it necessary?
- Is it maintained?
- Any known vulnerabilities?
- License compatible?
- Size reasonable?
- Better alternative exists?

Problematic dependencies:
{problems_found}

Dependencies OK: YES/NO"""

    CODE_REVIEW = """Brutal code review.

Files changed:
{changed_files}

Review:
1. Functionality:
   - Does it work correctly?
   - All requirements met?

2. Maintainability:
   - Can another dev understand this?
   - Proper abstractions?
   - DRY principle followed?

3. Performance:
   - Any obvious inefficiencies?
   - Premature optimization?

4. Style:
   - Follows project conventions?
   - Consistent formatting?

5. Testing:
   - Adequate test coverage?
   - Tests actually test?

Critical issues:
{critical_issues}

Must fix before merge: YES/NO"""

    RECURSIVE_VERIFICATION = """Re-verification after fixes.

Previous failures:
{previous_issues}

Fixes claimed:
{fixes_made}

Verify:
- Are ALL previous issues ACTUALLY fixed?
- No new issues introduced?
- No quick workarounds used?
- Fixes are proper solutions?

Still failing:
{remaining_issues}

All fixed: YES/NO
Retry needed: YES/NO"""


class VerificationChain:
    """Chain of verification checks."""

    def __init__(self, level: VerificationLevel = VerificationLevel.STANDARD):
        self.level = level
        self.checks = []
        self.results = {}

    def add_check(self, name: str, prompt: str, critical: bool = False):
        """Add verification check to chain."""
        self.checks.append({
            "name": name,
            "prompt": prompt,
            "critical": critical
        })

    def execute(self, context: Dict[str, Any]) -> VerificationReport:
        """Execute verification chain."""
        failed_checks = []
        passed_checks = []

        for check in self.checks:
            # Substitute context into prompt
            prompt = check["prompt"]
            for key, value in context.items():
                prompt = prompt.replace(f"{{{key}}}", str(value))

            # Here you would actually run the check
            # For now, this is a placeholder
            result = self._run_check(prompt)

            if result:
                passed_checks.append(check["name"])
            else:
                failed_checks.append(check["name"])
                if check["critical"]:
                    # Critical failure, stop chain
                    break

        # Calculate results
        total_checks = len(self.checks)
        passed = len(passed_checks)
        quality_score = (passed / total_checks) * 100 if total_checks > 0 else 0

        if len(failed_checks) == 0:
            result = VerificationResult.PASS
        elif len(passed_checks) == 0:
            result = VerificationResult.FAIL
        else:
            result = VerificationResult.PARTIAL

        return VerificationReport(
            result=result,
            criteria_results={check: check in passed_checks for check in [c["name"] for c in self.checks]},
            quality_score=quality_score,
            issues=failed_checks,
            recommendations=self._generate_recommendations(failed_checks),
            must_fix=failed_checks if result == VerificationResult.FAIL else [],
            retry_guidance=self._generate_retry_guidance(failed_checks) if result != VerificationResult.PASS else None
        )

    def _run_check(self, prompt: str) -> bool:
        """Run individual check (placeholder)."""
        # In practice, this would call the LLM with the prompt
        # and parse the response
        return True  # Placeholder

    def _generate_recommendations(self, failed_checks: List[str]) -> List[str]:
        """Generate recommendations based on failures."""
        recommendations = []

        if "ai_patterns" in failed_checks:
            recommendations.append("Rewrite code to look more human-written")
        if "tests" in failed_checks:
            recommendations.append("Add complete tests with edge cases")
        if "production" in failed_checks:
            recommendations.append("Add proper error handling and remove debug code")

        return recommendations

    def _generate_retry_guidance(self, failed_checks: List[str]) -> str:
        """Generate retry guidance."""
        if not failed_checks:
            return None

        guidance = f"Fix these {len(failed_checks)} issues:\n"
        for i, check in enumerate(failed_checks, 1):
            guidance += f"{i}. {check}: [specific fix needed]\n"

        return guidance


def create_verification_prompt(
    verification_type: str,
    context: Dict[str, Any],
    level: VerificationLevel = VerificationLevel.STANDARD
) -> str:
    """Create verification prompt.
    
    Args:
        verification_type: Type of verification
        context: Context for verification
        level: Strictness level
        
    Returns:
        Generated verification prompt

    """
    prompts = BrutalVerificationPrompts()

    type_map = {
        "boss": prompts.BOSS_VERIFICATION,
        "criteria": prompts.CRITERIA_VERIFICATION,
        "ai_detection": prompts.AI_PATTERN_DETECTION,
        "production": prompts.PRODUCTION_QUALITY,
        "tests": prompts.TEST_QUALITY,
        "performance": prompts.PERFORMANCE_CHECK,
        "security": prompts.SECURITY_AUDIT,
        "dependencies": prompts.DEPENDENCY_CHECK,
        "code_review": prompts.CODE_REVIEW,
        "recursive": prompts.RECURSIVE_VERIFICATION
    }

    base_prompt = type_map.get(verification_type, prompts.BOSS_VERIFICATION)

    # Adjust based on level
    if level == VerificationLevel.BRUTAL:
        base_prompt = f"BRUTAL MODE ACTIVATED\n\n{base_prompt}\n\nNO MERCY. FIND EVERYTHING WRONG."
    elif level == VerificationLevel.LENIENT:
        base_prompt = f"Standard verification:\n\n{base_prompt}"

    # Substitute context
    for key, value in context.items():
        if isinstance(value, list):
            value = "\n".join(f"- {v}" for v in value)
        base_prompt = base_prompt.replace(f"{{{key}}}", str(value))

    return base_prompt


class VerificationDecisionEngine:
    """Engine for making verification decisions."""

    @staticmethod
    def make_decision(
        report: VerificationReport,
        retry_count: int = 0,
        max_retries: int = 3
    ) -> Tuple[str, Optional[str]]:
        """Make verification decision.
        
        Args:
            report: Verification report
            retry_count: Current retry count
            max_retries: Maximum retries allowed
            
        Returns:
            Tuple of (decision, action)

        """
        if report.result == VerificationResult.PASS:
            return "ACCEPT", None

        if report.result == VerificationResult.BLOCKED:
            return "BLOCKED", "Resolve blockers before continuing"

        if retry_count >= max_retries:
            return "REJECT", "Maximum retries exceeded"

        if report.quality_score < 50:
            return "RETRY", "Quality too low. Major rework needed."

        if len(report.must_fix) > 0:
            return "RETRY", f"Fix {len(report.must_fix)} critical issues"

        if report.result == VerificationResult.PARTIAL and report.quality_score > 80:
            return "CONDITIONAL_ACCEPT", "Accept with minor fixes required"

        return "RETRY", report.retry_guidance or "Fix issues and retry"
