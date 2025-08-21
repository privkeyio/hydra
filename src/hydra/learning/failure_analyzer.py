"""Intelligent failure analysis and learning system for Hydra.

Analyzes verification failures to improve future executions through
pattern recognition, categorization, and solution suggestions.
"""

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class FailureCategory(Enum):
    """Categories of failures for pattern recognition."""

    MISSING_FILE = "missing_file"
    TEST_FAILURE = "test_failure"
    LINT_ERROR = "lint_error"
    BUILD_ERROR = "build_error"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    AI_PATTERN_DETECTED = "ai_pattern_detected"
    COMPLEXITY_EXCEEDED = "complexity_exceeded"
    COVERAGE_INSUFFICIENT = "coverage_insufficient"
    DOCUMENTATION_MISSING = "documentation_missing"
    SECURITY_ISSUE = "security_issue"
    PERFORMANCE_ISSUE = "performance_issue"
    DEPENDENCY_ERROR = "dependency_error"
    UNKNOWN = "unknown"


@dataclass
class FailurePattern:
    """Represents a recognized failure pattern."""

    pattern_id: str
    category: FailureCategory
    description: str
    regex_patterns: List[str]
    keywords: Set[str]
    frequency: int = 0
    success_rate_after_fix: float = 0.0
    suggested_solutions: List[str] = field(default_factory=list)
    example_failures: List[str] = field(default_factory=list)


@dataclass
class FailureContext:
    """Context extracted from a failure."""

    ticket_id: str
    attempt_number: int
    timestamp: datetime
    category: FailureCategory
    error_message: str
    stack_trace: Optional[str] = None
    affected_files: List[str] = field(default_factory=list)
    failed_criteria: List[str] = field(default_factory=list)
    environment: Dict[str, Any] = field(default_factory=dict)
    pattern_matches: List[str] = field(default_factory=list)


@dataclass
class FailureSolution:
    """Suggested solution for a failure."""

    solution_id: str
    description: str
    commands: List[str]
    code_changes: Dict[str, str]
    confidence: float
    previous_success_rate: float
    estimated_time: int  # seconds


class FailureAnalyzer:
    """Analyzes failures and learns from patterns to improve future executions."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize failure analyzer with optional database for persistence."""
        self.db_path = db_path or Path.home() / ".hydra" / "failure_history.db"
        self.patterns = self._load_patterns()
        self.failure_history: List[FailureContext] = []
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for failure history."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failure_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    category TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    stack_trace TEXT,
                    affected_files TEXT,
                    failed_criteria TEXT,
                    environment TEXT,
                    pattern_matches TEXT,
                    solution_applied TEXT,
                    success_after_solution BOOLEAN,
                    UNIQUE(ticket_id, attempt_number)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS pattern_statistics (
                    pattern_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    frequency INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 0.0,
                    last_seen TIMESTAMP,
                    solutions_applied TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category 
                ON failure_history(category)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ticket 
                ON failure_history(ticket_id)
            """)

    @contextmanager
    def _get_db(self):
        """Get database connection with automatic cleanup."""
        conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _load_patterns(self) -> Dict[str, FailurePattern]:
        """Load predefined failure patterns."""
        patterns = {
            "missing_import": FailurePattern(
                pattern_id="missing_import",
                category=FailureCategory.BUILD_ERROR,
                description="Missing module import",
                regex_patterns=[
                    r"ModuleNotFoundError: No module named '([^']+)'",
                    r"ImportError: cannot import name '([^']+)'",
                    r"Cannot find module '([^']+)'"
                ],
                keywords={"ModuleNotFoundError", "ImportError", "cannot import"},
                suggested_solutions=[
                    "Install missing module: pip install {module}",
                    "Check if module is installed: pip list | grep {module}",
                    "Check import path and module name spelling",
                    "Verify PYTHONPATH includes required directories"
                ]
            ),
            "test_assertion": FailurePattern(
                pattern_id="test_assertion",
                category=FailureCategory.TEST_FAILURE,
                description="Test assertion failure",
                regex_patterns=[
                    r"AssertionError: (.+)",
                    r"assert (.+) == (.+)",
                    r"Expected: (.+), Got: (.+)"
                ],
                keywords={"AssertionError", "assert", "Expected", "Got"},
                suggested_solutions=[
                    "Review test expectations vs actual implementation",
                    "Check edge cases in implementation",
                    "Verify test data is correct",
                    "Debug the specific assertion that failed"
                ]
            ),
            "file_not_found": FailurePattern(
                pattern_id="file_not_found",
                category=FailureCategory.MISSING_FILE,
                description="Required file not found",
                regex_patterns=[
                    r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'",
                    r"Cannot find file: ([^\s]+)",
                    r"File '([^']+)' does not exist"
                ],
                keywords={"FileNotFoundError", "No such file", "does not exist"},
                suggested_solutions=[
                    "Create the missing file: touch {file}",
                    "Check file path spelling and case sensitivity",
                    "Verify working directory is correct",
                    "Check if file should be generated by previous step"
                ]
            ),
            "lint_violation": FailurePattern(
                pattern_id="lint_violation",
                category=FailureCategory.LINT_ERROR,
                description="Code style/lint violation",
                regex_patterns=[
                    r"(\w+:\d+:\d+): ([EWF]\d+) (.+)",
                    r"Lint failed with \d+ errors?",
                    r"Code style violations found"
                ],
                keywords={"pylint", "flake8", "black", "ruff", "lint", "style"},
                suggested_solutions=[
                    "Run auto-formatter: black {file}",
                    "Fix lint errors: ruff check --fix {file}",
                    "Review and fix style violations manually",
                    "Update lint configuration if too strict"
                ]
            ),
            "ai_pattern": FailurePattern(
                pattern_id="ai_pattern",
                category=FailureCategory.AI_PATTERN_DETECTED,
                description="AI-generated code patterns detected",
                regex_patterns=[
                    r"AI pattern detected: (.+)",
                    r"Found (\d+) AI patterns",
                    r"Emoji detected in code"
                ],
                keywords={"AI pattern", "emoji", "verbose naming", "placeholder"},
                suggested_solutions=[
                    "Remove verbose/generic variable names",
                    "Remove unnecessary comments explaining 'what' instead of 'why'",
                    "Remove emoji from code and comments",
                    "Replace placeholder text with actual implementation",
                    "Use more specific, concise naming"
                ]
            ),
            "coverage_low": FailurePattern(
                pattern_id="coverage_low",
                category=FailureCategory.COVERAGE_INSUFFICIENT,
                description="Test coverage below threshold",
                regex_patterns=[
                    r"Coverage: (\d+)% \(minimum: (\d+)%\)",
                    r"Test coverage (\d+)% is below threshold",
                    r"Branch coverage insufficient"
                ],
                keywords={"coverage", "below threshold", "insufficient"},
                suggested_solutions=[
                    "Add unit tests for uncovered functions",
                    "Add edge case tests",
                    "Test error handling paths",
                    "Add integration tests for main workflows"
                ]
            )
        }

        return patterns

    def analyze_failure(self,
                        ticket_id: str,
                        attempt_number: int,
                        error_message: str,
                        stack_trace: Optional[str] = None,
                        failed_criteria: Optional[List[str]] = None,
                        environment: Optional[Dict[str, Any]] = None) -> FailureContext:
        """Analyze a failure and extract context."""
        # Categorize the failure
        category = self._categorize_failure(error_message, stack_trace)

        # Extract affected files
        affected_files = self._extract_files(error_message, stack_trace)

        # Find matching patterns
        pattern_matches = self._find_pattern_matches(error_message, stack_trace)

        context = FailureContext(
            ticket_id=ticket_id,
            attempt_number=attempt_number,
            timestamp=datetime.now(),
            category=category,
            error_message=error_message,
            stack_trace=stack_trace,
            affected_files=affected_files,
            failed_criteria=failed_criteria or [],
            environment=environment or {},
            pattern_matches=pattern_matches
        )

        # Store in history
        self._store_failure(context)
        self.failure_history.append(context)

        return context

    def _categorize_failure(self, error_message: str, stack_trace: Optional[str]) -> FailureCategory:
        """Categorize failure based on error message and stack trace."""
        text = f"{error_message} {stack_trace or ''}"

        # Check each pattern category
        category_keywords = {
            FailureCategory.MISSING_FILE: ["FileNotFoundError", "No such file", "does not exist"],
            FailureCategory.TEST_FAILURE: ["AssertionError", "test failed", "FAILED"],
            FailureCategory.LINT_ERROR: ["lint", "flake8", "black", "ruff", "style"],
            FailureCategory.BUILD_ERROR: ["ModuleNotFoundError", "ImportError", "SyntaxError", "compilation"],
            FailureCategory.ACCEPTANCE_CRITERIA: ["acceptance criteria", "criteria not met", "requirement"],
            FailureCategory.AI_PATTERN_DETECTED: ["AI pattern", "emoji", "verbose naming"],
            FailureCategory.COMPLEXITY_EXCEEDED: ["complexity", "cyclomatic", "too complex"],
            FailureCategory.COVERAGE_INSUFFICIENT: ["coverage", "below threshold"],
            FailureCategory.DOCUMENTATION_MISSING: ["documentation", "docstring", "missing docs"],
            FailureCategory.SECURITY_ISSUE: ["security", "vulnerability", "SQL injection", "XSS"],
            FailureCategory.PERFORMANCE_ISSUE: ["performance", "timeout", "slow", "memory"],
            FailureCategory.DEPENDENCY_ERROR: ["dependency", "version conflict", "incompatible"]
        }

        for category, keywords in category_keywords.items():
            if any(keyword.lower() in text.lower() for keyword in keywords):
                return category

        return FailureCategory.UNKNOWN

    def _extract_files(self, error_message: str, stack_trace: Optional[str]) -> List[str]:
        """Extract file paths mentioned in error."""
        files = []
        text = f"{error_message} {stack_trace or ''}"

        # Common file path patterns
        patterns = [
            r"File ['\"]([^'\"]+)['\"]",
            r"in ([^\s]+\.py)",
            r"([^\s]+\.(py|js|ts|jsx|tsx|css|html|md|yaml|yml|json))",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                file_path = match[0] if isinstance(match, tuple) else match
                if file_path and not file_path.startswith("<"):
                    files.append(file_path)

        return list(set(files))

    def _find_pattern_matches(self, error_message: str, stack_trace: Optional[str]) -> List[str]:
        """Find matching failure patterns."""
        matches = []
        text = f"{error_message} {stack_trace or ''}"

        for pattern_id, pattern in self.patterns.items():
            # Check regex patterns
            for regex in pattern.regex_patterns:
                if re.search(regex, text):
                    matches.append(pattern_id)
                    break

            # Check keywords
            if not matches or pattern_id not in matches:
                if any(keyword.lower() in text.lower() for keyword in pattern.keywords):
                    matches.append(pattern_id)

        return list(set(matches))

    def suggest_solutions(self, context: FailureContext) -> List[FailureSolution]:
        """Suggest solutions based on failure context and history."""
        solutions = []

        # Get solutions from matching patterns
        for pattern_id in context.pattern_matches:
            if pattern_id in self.patterns:
                pattern = self.patterns[pattern_id]
                for i, suggestion in enumerate(pattern.suggested_solutions):
                    solutions.append(FailureSolution(
                        solution_id=f"{pattern_id}_{i}",
                        description=suggestion,
                        commands=self._extract_commands(suggestion),
                        code_changes={},
                        confidence=0.8 - (i * 0.1),  # Decrease confidence for later suggestions
                        previous_success_rate=pattern.success_rate_after_fix,
                        estimated_time=60 * (i + 1)  # Rough estimate
                    ))

        # Look for similar historical failures
        similar_failures = self._find_similar_failures(context)
        for failure, solution, success in similar_failures:
            if solution and success:
                solutions.append(FailureSolution(
                    solution_id=f"historical_{failure['id']}",
                    description=f"Previously successful: {solution}",
                    commands=[],
                    code_changes={},
                    confidence=0.9,
                    previous_success_rate=1.0,
                    estimated_time=120
                ))

        # Sort by confidence
        solutions.sort(key=lambda s: s.confidence, reverse=True)

        return solutions[:5]  # Return top 5 suggestions

    def _extract_commands(self, suggestion: str) -> List[str]:
        """Extract executable commands from suggestion text."""
        commands = []

        # Look for command patterns
        patterns = [
            r"`([^`]+)`",  # Backtick commands
            r"(?:Run|Execute|Use):\s*(.+?)(?:\n|$)",  # Command instructions
            r"(\w+(?:\s+[\w\-\.\/]+)+)",  # General command pattern
        ]

        for pattern in patterns:
            matches = re.findall(pattern, suggestion)
            for match in matches:
                cmd = match.strip()
                # Filter out obvious non-commands
                if not any(skip in cmd.lower() for skip in ["check", "review", "verify", "the", "and", "or"]):
                    if len(cmd.split()) >= 2:  # At least command + argument
                        commands.append(cmd)

        return commands

    def _find_similar_failures(self, context: FailureContext, limit: int = 5) -> List[Tuple[Dict, str, bool]]:
        """Find similar historical failures and their solutions."""
        with self._get_db() as conn:
            # Find failures with same category and similar patterns
            cursor = conn.execute("""
                SELECT * FROM failure_history
                WHERE category = ? 
                AND ticket_id != ?
                AND solution_applied IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT ?
            """, (context.category.value, context.ticket_id, limit))

            results = []
            for row in cursor:
                results.append((
                    dict(row),
                    row["solution_applied"],
                    row["success_after_solution"]
                ))

            return results

    def _store_failure(self, context: FailureContext):
        """Store failure context in database."""
        with self._get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO failure_history (
                    ticket_id, attempt_number, timestamp, category,
                    error_message, stack_trace, affected_files,
                    failed_criteria, environment, pattern_matches
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                context.ticket_id,
                context.attempt_number,
                context.timestamp,
                context.category.value,
                context.error_message,
                context.stack_trace,
                json.dumps(context.affected_files),
                json.dumps(context.failed_criteria),
                json.dumps(context.environment),
                json.dumps(context.pattern_matches)
            ))

            # Update pattern statistics
            for pattern_id in context.pattern_matches:
                conn.execute("""
                    INSERT INTO pattern_statistics (pattern_id, category, frequency, last_seen)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(pattern_id) DO UPDATE SET
                        frequency = frequency + 1,
                        last_seen = ?
                """, (
                    pattern_id,
                    context.category.value,
                    context.timestamp,
                    context.timestamp
                ))

    def record_solution_result(self,
                               ticket_id: str,
                               attempt_number: int,
                               solution: str,
                               success: bool):
        """Record whether a solution was successful."""
        with self._get_db() as conn:
            conn.execute("""
                UPDATE failure_history
                SET solution_applied = ?, success_after_solution = ?
                WHERE ticket_id = ? AND attempt_number = ?
            """, (solution, success, ticket_id, attempt_number))

            # Update pattern success rates
            if success:
                cursor = conn.execute("""
                    SELECT pattern_matches FROM failure_history
                    WHERE ticket_id = ? AND attempt_number = ?
                """, (ticket_id, attempt_number))

                row = cursor.fetchone()
                if row and row["pattern_matches"]:
                    patterns = json.loads(row["pattern_matches"])
                    for pattern_id in patterns:
                        self._update_pattern_success_rate(pattern_id, success)

    def _update_pattern_success_rate(self, pattern_id: str, success: bool):
        """Update success rate for a pattern."""
        with self._get_db() as conn:
            cursor = conn.execute("""
                SELECT frequency, success_rate FROM pattern_statistics
                WHERE pattern_id = ?
            """, (pattern_id,))

            row = cursor.fetchone()
            if row:
                frequency = row["frequency"]
                current_rate = row["success_rate"]

                # Weighted average
                new_rate = (current_rate * (frequency - 1) + (1.0 if success else 0.0)) / frequency

                conn.execute("""
                    UPDATE pattern_statistics
                    SET success_rate = ?
                    WHERE pattern_id = ?
                """, (new_rate, pattern_id))

    def get_failure_report(self, ticket_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate failure analysis report."""
        with self._get_db() as conn:
            if ticket_id:
                cursor = conn.execute("""
                    SELECT * FROM failure_history
                    WHERE ticket_id = ?
                    ORDER BY attempt_number
                """, (ticket_id,))
                failures = [dict(row) for row in cursor]
            else:
                # Overall statistics
                cursor = conn.execute("""
                    SELECT category, COUNT(*) as count,
                           AVG(CASE WHEN success_after_solution THEN 1.0 ELSE 0.0 END) as success_rate
                    FROM failure_history
                    GROUP BY category
                """)
                category_stats = [dict(row) for row in cursor]

                cursor = conn.execute("""
                    SELECT pattern_id, category, frequency, success_rate
                    FROM pattern_statistics
                    ORDER BY frequency DESC
                    LIMIT 10
                """)
                top_patterns = [dict(row) for row in cursor]

                return {
                    "category_statistics": category_stats,
                    "top_patterns": top_patterns,
                    "total_failures": sum(s["count"] for s in category_stats),
                    "overall_resolution_rate": sum(s["success_rate"] * s["count"] for s in category_stats) /
                                              max(sum(s["count"] for s in category_stats), 1)
                }

        return {"ticket_failures": failures}

    def predict_failure_likelihood(self, ticket_description: str) -> float:
        """Predict likelihood of failure based on ticket description (ML placeholder)."""
        # Simple heuristic for now - can be replaced with ML model
        risk_keywords = [
            "complex", "refactor", "migration", "performance", "security",
            "integration", "third-party", "api", "concurrent", "parallel"
        ]

        risk_score = 0.1  # Base risk

        for keyword in risk_keywords:
            if keyword.lower() in ticket_description.lower():
                risk_score += 0.1

        # Check historical failure rate for similar tickets
        with self._get_db() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN success_after_solution THEN 0 ELSE 1 END) as failures
                FROM failure_history
            """)

            row = cursor.fetchone()
            if row and row["total"] > 0:
                historical_rate = row["failures"] / row["total"]
                risk_score = (risk_score + historical_rate) / 2

        return min(risk_score, 1.0)

    def create_feedback_for_prompt(self, context: FailureContext, solutions: List[FailureSolution]) -> str:
        """Create feedback text to inject into execution prompt for retry."""
        feedback = f"""
PREVIOUS ATTEMPT FAILED - CONTEXT FOR RETRY:

Failure Category: {context.category.value}
Error: {context.error_message}

Failed Acceptance Criteria:
{chr(10).join(f'- {c}' for c in context.failed_criteria)}

Suggested Fixes (in order of confidence):
"""

        for i, solution in enumerate(solutions[:3], 1):
            feedback += f"\n{i}. {solution.description}"
            if solution.commands:
                feedback += f"\n   Commands: {'; '.join(solution.commands)}"

        feedback += """

CRITICAL: Address the above issues before marking complete.
Focus on the specific failures and implement the suggested fixes.
"""

        return feedback


# Public API functions
def analyze_failure(ticket_id: str, error_message: str, **kwargs) -> Tuple[FailureContext, List[FailureSolution]]:
    """Analyze a failure and get solution suggestions."""
    analyzer = FailureAnalyzer()
    context = analyzer.analyze_failure(ticket_id, kwargs.get("attempt", 1), error_message, **kwargs)
    solutions = analyzer.suggest_solutions(context)
    return context, solutions


def get_retry_feedback(ticket_id: str, error_message: str, **kwargs) -> str:
    """Get feedback text for retry attempt."""
    context, solutions = analyze_failure(ticket_id, error_message, **kwargs)
    analyzer = FailureAnalyzer()
    return analyzer.create_feedback_for_prompt(context, solutions)
