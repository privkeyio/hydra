"""Integration of execution prompts with ticket workflow."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from hydra.prompts.execution_prompts import (
    ExecutionMode,
    ExecutionPriority,
    ExecutionPromptBuilder,
    ExecutionValidator,
    PostExecutionPrompts,
)

logger = logging.getLogger(__name__)


@dataclass
class TicketExecutionContext:
    """Context for ticket execution."""

    ticket_id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    model: str
    priority: str
    dependencies: List[str]
    files_affected: Optional[List[str]] = None
    execution_mode: Optional[ExecutionMode] = None

    def to_prompt_context(self) -> Dict[str, Any]:
        """Convert to prompt context."""
        return {
            "ticket_id": self.ticket_id,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "model": self.model,
            "priority": self.priority,
            "dependencies": self.dependencies,
            "files": self.files_affected or []
        }


class ExecutionPromptInjector:
    """Injects execution prompts into providers."""

    def __init__(self, strict_mode: bool = True):
        """Initialize injector.
        
        Args:
            strict_mode: If True, enforce all quality checks

        """
        self.strict_mode = strict_mode
        self.validator = ExecutionValidator()
        from ..verification_system.ai_detector import AIDetector
        self.ai_detector = AIDetector()

    def inject_execution_prompt(
        self,
        ticket_context: TicketExecutionContext,
        provider_type: str
    ) -> str:
        """Inject appropriate execution prompt for provider.
        
        Args:
            ticket_context: Ticket execution context
            provider_type: Type of provider (claude, venice, etc.)
            
        Returns:
            Generated execution prompt

        """
        # Determine execution mode based on ticket properties
        mode = self._determine_execution_mode(ticket_context)

        # Map priority
        priority = self._map_priority(ticket_context.priority)

        # Build prompt
        builder = ExecutionPromptBuilder()
        prompt = (builder
                 .with_ticket(ticket_context.ticket_id, ticket_context.acceptance_criteria)
                 .with_mode(mode)
                 .with_priority(priority)
                 .build())

        # Add provider-specific modifications
        prompt = self._customize_for_provider(prompt, provider_type)

        # Add post-execution validation requirements
        if self.strict_mode:
            prompt += "\n\n" + PostExecutionPrompts.SELF_REVIEW
            prompt += "\n\n" + PostExecutionPrompts.FINAL_CHECK

        return prompt

    def _determine_execution_mode(self, context: TicketExecutionContext) -> ExecutionMode:
        """Determine execution mode from context."""
        # Check for emergency/hotfix indicators
        if any(word in context.title.lower() or word in context.description.lower()
               for word in ["hotfix", "emergency", "critical bug", "urgent"]):
            return ExecutionMode.HOTFIX

        # Check for performance optimization
        if any(word in context.title.lower() or word in context.description.lower()
               for word in ["performance", "optimize", "speed up", "slow"]):
            return ExecutionMode.PERFORMANCE

        # Check for refactoring
        if any(word in context.title.lower() or word in context.description.lower()
               for word in ["refactor", "cleanup", "reorganize", "restructure"]):
            return ExecutionMode.REFACTOR

        # Check for surgical changes
        if context.files_affected and len(context.files_affected) <= 2:
            return ExecutionMode.SURGICAL

        # Default to comprehensive
        return ExecutionMode.COMPREHENSIVE

    def _map_priority(self, priority: str) -> ExecutionPriority:
        """Map ticket priority to execution priority."""
        priority_map = {
            "critical": ExecutionPriority.EMERGENCY,
            "emergency": ExecutionPriority.EMERGENCY,
            "high": ExecutionPriority.HIGH,
            "medium": ExecutionPriority.NORMAL,
            "normal": ExecutionPriority.NORMAL,
            "low": ExecutionPriority.LOW
        }
        return priority_map.get(priority.lower(), ExecutionPriority.NORMAL)

    def _customize_for_provider(self, prompt: str, provider_type: str) -> str:
        """Customize prompt for specific provider."""
        if provider_type == "claude":
            # Claude-specific optimizations
            prompt = prompt.replace("{", "{{").replace("}", "}}")  # Escape for f-strings
            prompt += "\n\nUse Claude's capabilities for deep code understanding."
        elif provider_type == "venice":
            # Venice-specific optimizations
            prompt += "\n\nExecute with Venice's production deployment focus."
        elif provider_type == "mock":
            # Mock provider for testing
            prompt += "\n\n[MOCK MODE: Simulate production execution]"

        return prompt

    def validate_execution_output(
        self,
        code: str,
        ticket_context: TicketExecutionContext
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Validate execution output against requirements.
        
        Args:
            code: Generated code
            ticket_context: Original ticket context
            
        Returns:
            Tuple of (is_valid, issues, metrics)

        """
        issues = []
        metrics = {
            "lines_of_code": len(code.split('\n')),
            "ai_patterns_detected": False,
            "production_ready": False,
            "all_criteria_met": False
        }

        # Check production quality
        is_production_ready, quality_issues = self.validator.check_production_quality(code)
        if not is_production_ready:
            issues.extend(quality_issues)
        metrics["production_ready"] = is_production_ready

        # Check AI patterns
        has_ai, ai_patterns = self.ai_detector.detect_ai_patterns(code)
        if has_ai:
            issues.extend(ai_patterns)
            metrics["ai_patterns_detected"] = True

        # Check acceptance criteria (simplified check)
        criteria_met = self._check_criteria_implementation(code, ticket_context.acceptance_criteria)
        if not all(criteria_met.values()):
            unmet = [c for c, met in criteria_met.items() if not met]
            issues.extend([f"Criterion not met: {c}" for c in unmet])
        else:
            metrics["all_criteria_met"] = True

        # Calculate overall validity
        is_valid = len(issues) == 0 if self.strict_mode else len(issues) < 3

        return is_valid, issues, metrics

    def _check_criteria_implementation(
        self,
        code: str,
        criteria: List[str]
    ) -> Dict[str, bool]:
        """Check if acceptance criteria are implemented.
        
        Simplified check - in production would use AST analysis.
        """
        results = {}

        for criterion in criteria:
            # Extract key terms from criterion
            key_terms = self._extract_key_terms(criterion)

            # Check if key terms appear in code
            found = sum(1 for term in key_terms if term.lower() in code.lower())

            # Consider met if most key terms are found
            results[criterion] = found >= len(key_terms) * 0.6

        return results

    def _extract_key_terms(self, criterion: str) -> List[str]:
        """Extract key implementation terms from criterion."""
        # Remove common words
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                     "of", "with", "by", "from", "as", "is", "was", "are", "were"}

        words = criterion.lower().split()
        key_terms = [w for w in words if w not in stop_words and len(w) > 2]

        return key_terms


class ProductionQualityEnforcer:
    """Enforces production quality standards."""

    def __init__(self):
        self.validator = ExecutionValidator()
        from ..verification_system.ai_detector import AIDetector
        self.ai_detector = AIDetector()

    def enforce_quality(
        self,
        code: str,
        auto_fix: bool = False
    ) -> Tuple[str, List[str]]:
        """Enforce production quality standards.
        
        Args:
            code: Code to check
            auto_fix: Attempt to auto-fix issues
            
        Returns:
            Tuple of (possibly fixed code, remaining issues)

        """
        issues = []
        fixed_code = code

        # Check and potentially fix issues
        is_ready, quality_issues = self.validator.check_production_quality(code)

        if not is_ready and auto_fix:
            fixed_code = self._auto_fix_issues(fixed_code, quality_issues)
            # Re-check after fixes
            is_ready, remaining_issues = self.validator.check_production_quality(fixed_code)
            issues = remaining_issues
        else:
            issues = quality_issues

        return fixed_code, issues

    def _auto_fix_issues(self, code: str, issues: List[str]) -> str:
        """Attempt to auto-fix common issues."""
        fixed = code

        for issue in issues:
            if "Debug print" in issue:
                # Remove print statements
                lines = fixed.split('\n')
                lines = [l for l in lines if not l.strip().startswith('print(')]
                fixed = '\n'.join(lines)

            elif "TODO" in issue or "FIXME" in issue:
                # Remove TODO/FIXME comments
                import re
                fixed = re.sub(r'#.*(?:TODO|FIXME).*\n?', '', fixed)
                fixed = re.sub(r'//.*(?:TODO|FIXME).*\n?', '', fixed)

            elif "console.log" in issue:
                # Remove console.log statements
                import re
                fixed = re.sub(r'console\.log\([^)]*\);?\n?', '', fixed)

        return fixed


class ExecutionMetrics:
    """Track execution metrics."""

    def __init__(self):
        self.executions = []
        self.failures = []
        self.ai_pattern_detections = []

    def record_execution(
        self,
        ticket_id: str,
        success: bool,
        metrics: Dict[str, Any],
        issues: List[str]
    ):
        """Record execution metrics."""
        record = {
            "ticket_id": ticket_id,
            "success": success,
            "metrics": metrics,
            "issues": issues,
            "timestamp": self._get_timestamp()
        }

        self.executions.append(record)

        if not success:
            self.failures.append(record)

        if metrics.get("ai_patterns_detected"):
            self.ai_pattern_detections.append(record)

    def get_success_rate(self) -> float:
        """Get overall success rate."""
        if not self.executions:
            return 0.0

        successful = sum(1 for e in self.executions if e["success"])
        return successful / len(self.executions)

    def get_common_issues(self, top_n: int = 5) -> List[Tuple[str, int]]:
        """Get most common issues."""
        issue_counts = {}

        for execution in self.executions:
            for issue in execution["issues"]:
                # Normalize issue for grouping
                normalized = self._normalize_issue(issue)
                issue_counts[normalized] = issue_counts.get(normalized, 0) + 1

        # Sort by count
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_issues[:top_n]

    def get_ai_pattern_rate(self) -> float:
        """Get rate of AI pattern detection."""
        if not self.executions:
            return 0.0

        return len(self.ai_pattern_detections) / len(self.executions)

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat()

    def _normalize_issue(self, issue: str) -> str:
        """Normalize issue for grouping."""
        # Extract issue type
        if "TODO" in issue or "FIXME" in issue:
            return "Unfinished TODO/FIXME"
        elif "Debug" in issue or "print" in issue or "console.log" in issue:
            return "Debug code present"
        elif "AI" in issue or "pattern" in issue:
            return "AI pattern detected"
        elif "error handling" in issue.lower():
            return "Missing error handling"
        elif "Mock" in issue or "Stub" in issue:
            return "Mock/Stub code"
        else:
            return issue.split(':')[0] if ':' in issue else issue


def create_execution_prompt_for_ticket(
    ticket_data: Dict[str, Any],
    provider_type: str = "claude",
    strict_mode: bool = True
) -> str:
    """Create execution prompt for a ticket.
    
    Args:
        ticket_data: Ticket data dictionary
        provider_type: Provider type
        strict_mode: Enable strict quality enforcement
        
    Returns:
        Generated execution prompt

    """
    # Create context
    context = TicketExecutionContext(
        ticket_id=ticket_data.get("id", "UNKNOWN"),
        title=ticket_data.get("title", ""),
        description=ticket_data.get("description", ""),
        acceptance_criteria=ticket_data.get("acceptance_criteria", []),
        model=ticket_data.get("model", "balanced"),
        priority=ticket_data.get("priority", "normal"),
        dependencies=ticket_data.get("dependencies", []),
        files_affected=ticket_data.get("files_affected")
    )

    # Create injector and generate prompt
    injector = ExecutionPromptInjector(strict_mode=strict_mode)
    prompt = injector.inject_execution_prompt(context, provider_type)

    return prompt


def validate_ticket_execution(
    code: str,
    ticket_data: Dict[str, Any],
    strict_mode: bool = True
) -> Tuple[bool, List[str]]:
    """Validate ticket execution output.
    
    Args:
        code: Generated code
        ticket_data: Original ticket data
        strict_mode: Enable strict validation
        
    Returns:
        Tuple of (is_valid, issues)

    """
    # Create context
    context = TicketExecutionContext(
        ticket_id=ticket_data.get("id", "UNKNOWN"),
        title=ticket_data.get("title", ""),
        description=ticket_data.get("description", ""),
        acceptance_criteria=ticket_data.get("acceptance_criteria", []),
        model=ticket_data.get("model", "balanced"),
        priority=ticket_data.get("priority", "normal"),
        dependencies=ticket_data.get("dependencies", [])
    )

    # Validate
    injector = ExecutionPromptInjector(strict_mode=strict_mode)
    is_valid, issues, metrics = injector.validate_execution_output(code, context)

    # Log metrics
    logger.info(f"Validation metrics for {ticket_data.get('id')}: {metrics}")

    return is_valid, issues
