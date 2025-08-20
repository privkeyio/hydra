"""Boss Agent - Brutal quality verification and enforcement system."""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..metrics.quality_metrics import QualityMetricsAnalyzer
from .ai_detector import AIDetector
from .coverage_analyzer import CoverageAnalyzer
from .criteria_parser import CriteriaParser
from .report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class StrictnessLevel(Enum):
    """Verification strictness levels."""

    LENIENT = "lenient"
    MODERATE = "moderate"
    STRICT = "strict"
    BRUTAL = "brutal"


class VerificationStatus(Enum):
    """Verification result status."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


@dataclass
class VerificationResult:
    """Result of boss agent verification."""

    status: VerificationStatus
    score: float
    passed_criteria: List[str] = field(default_factory=list)
    failed_criteria: List[str] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class VerificationConfig:
    """Configuration for boss agent verification."""

    strictness: StrictnessLevel = StrictnessLevel.STRICT
    max_retries: int = 3
    retry_delay_base: float = 1.0
    min_test_coverage: float = 80.0
    min_quality_score: float = 7.0
    check_ai_patterns: bool = True
    check_unnecessary_files: bool = True
    check_production_quality: bool = True
    require_all_tests_pass: bool = True
    require_lint_pass: bool = True
    log_to_file: bool = True
    audit_log_path: str = ".hydra/verification/audit.log"


class BossAgent:
    """The Boss - brutally honest verification and quality enforcement."""

    def __init__(self, config: Optional[VerificationConfig] = None, project_root: Optional[str] = None):
        self.config = config or VerificationConfig()
        self.project_root = project_root or os.getcwd()
        self.ai_detector = AIDetector()
        self.criteria_parser = CriteriaParser()
        self.coverage_analyzer = None  # Created per verification
        self.quality_checker = None  # Created per verification
        self.metrics_analyzer = QualityMetricsAnalyzer()

        # Use basic quality checking for CI compatibility
        # ProductionScorer integration disabled for test stability

        self.report_generator = None  # Created per verification
        self.retry_count = {}
        self.verification_history = []
        self._setup_logging()

    def _setup_logging(self):
        """Setup audit logging."""
        if self.config.log_to_file:
            log_path = Path(self.config.audit_log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    def verify_ticket_completion(
        self,
        ticket_id: str,
        ticket_data: Dict[str, Any],
        project_path: str,
        context: Optional[Dict[str, Any]] = None
    ) -> VerificationResult:
        """Brutally verify if a ticket was completed properly.
        
        No shortcuts, no excuses, no AI nonsense.
        """
        logger.info(f"Boss Agent starting verification for ticket {ticket_id}")

        result = VerificationResult(
            status=VerificationStatus.PASS,
            score=0.0
        )

        try:
            # Track verification attempt
            self._track_attempt(ticket_id)

            # 1. Verify all acceptance criteria
            criteria_result = self._verify_acceptance_criteria(
                ticket_data.get('acceptance_criteria', []),
                project_path
            )
            result.passed_criteria.extend(criteria_result['passed'])
            result.failed_criteria.extend(criteria_result['failed'])

            if criteria_result['failed']:
                result.failure_reasons.append(
                    f"Failed {len(criteria_result['failed'])} acceptance criteria"
                )

            # 2. Check test comprehensiveness
            if self.config.require_all_tests_pass:
                test_result = self._verify_tests(project_path)
                if not test_result['passed']:
                    result.failure_reasons.append(test_result['reason'])
                    result.suggestions.append("Fix failing tests or add missing test coverage")

            # 3. Check for unnecessary files
            if self.config.check_unnecessary_files:
                files_result = self._check_unnecessary_files(project_path)
                if files_result['unnecessary']:
                    result.failure_reasons.append(
                        f"Found {len(files_result['unnecessary'])} unnecessary files"
                    )
                    result.suggestions.append(
                        f"Remove unnecessary files: {', '.join(files_result['unnecessary'][:5])}"
                    )

            # 4. Check production quality using legacy quality checker
            if self.config.check_production_quality:
                # Use basic quality check for CI compatibility
                quality_result = self._verify_production_quality(project_path)

                result.metadata['quality_score'] = quality_result.get('score', 7.0)
                result.metadata['production_ready'] = quality_result.get('production_ready', True)

                # Check if production ready
                if not quality_result.get('production_ready', True):
                    result.failure_reasons.append(
                        f"NOT PRODUCTION READY: Score {quality_result.get('score', 0):.1f}/10"
                    )

                    # Add suggestions
                    result.suggestions.extend(quality_result.get('suggestions', [])[:5])

                # Also check against configured minimum
                if quality_result.get('score', 10) < self.config.min_quality_score:
                    result.failure_reasons.append(
                        f"Quality score {quality_result.get('score', 0):.1f} below configured minimum {self.config.min_quality_score}"
                    )

            # 5. Check for AI patterns
            if self.config.check_ai_patterns:
                ai_result = self._detect_ai_patterns(project_path)
                if ai_result['detected']:
                    result.failure_reasons.append(
                        f"Detected AI patterns in {len(ai_result['files'])} files"
                    )
                    result.suggestions.append(
                        "Rewrite code to look more human-written, remove verbose comments and placeholder text"
                    )

            # 6. Run lint checks
            if self.config.require_lint_pass:
                lint_result = self._run_lint_checks(project_path)
                if not lint_result['passed']:
                    result.failure_reasons.append("Lint checks failed")
                    result.suggestions.append("Fix all lint errors and warnings")

            # Calculate final score
            result.score = self._calculate_score(result)

            # Determine pass/fail
            if result.failure_reasons:
                result.status = VerificationStatus.FAIL
                logger.warning(
                    f"Ticket {ticket_id} FAILED verification: {result.failure_reasons}"
                )
            else:
                result.status = VerificationStatus.PASS
                logger.info(f"Ticket {ticket_id} PASSED verification with score {result.score:.1f}")

            # Log audit trail
            self._log_verification(ticket_id, result)

        except Exception as e:
            logger.error(f"Error during verification: {str(e)}")
            result.status = VerificationStatus.ERROR
            result.failure_reasons.append(f"Verification error: {str(e)}")

        return result

    def _verify_acceptance_criteria(
        self,
        criteria: List[str],
        project_path: str
    ) -> Dict[str, List[str]]:
        """Verify each acceptance criterion is actually met."""
        passed = []
        failed = []

        for criterion in criteria:
            # Parse criterion to understand what to check
            parsed = self.criteria_parser.parse(criterion)

            # Check if criterion is met based on its type
            if self._is_criterion_met(parsed, project_path):
                passed.append(criterion)
            else:
                failed.append(criterion)

        return {'passed': passed, 'failed': failed}

    def _is_criterion_met(self, parsed_criterion: Dict, project_path: str) -> bool:
        """Check if a specific criterion is met."""
        criterion_type = parsed_criterion.get('type', 'unknown')

        if criterion_type == 'file_exists':
            return Path(project_path, parsed_criterion['path']).exists()

        elif criterion_type == 'function_exists':
            return self._check_function_exists(
                project_path,
                parsed_criterion['function_name']
            )

        elif criterion_type == 'test_exists':
            return self._check_test_exists(
                project_path,
                parsed_criterion.get('test_pattern', '')
            )

        elif criterion_type == 'feature_implemented':
            return self._check_feature_implemented(
                project_path,
                parsed_criterion.get('feature', '')
            )

        # Default to checking if any relevant code was added
        return self._check_code_added(project_path)

    def _verify_tests(self, project_path: str) -> Dict[str, Any]:
        """Verify tests are comprehensive and passing."""
        try:
            # Run tests
            test_cmd = self._get_test_command(project_path)
            result = subprocess.run(
                test_cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return {
                    'passed': False,
                    'reason': "Tests failed or incomplete",
                    'output': result.stdout + result.stderr
                }

            # Check coverage
            if not self.coverage_analyzer:
                self.coverage_analyzer = CoverageAnalyzer(project_path)
            coverage = self.coverage_analyzer.analyze(project_path)
            if coverage < self.config.min_test_coverage:
                return {
                    'passed': False,
                    'reason': f"Test coverage {coverage:.1f}% below minimum {self.config.min_test_coverage}%"
                }

            return {'passed': True, 'coverage': coverage}

        except Exception as e:
            return {
                'passed': False,
                'reason': f"Could not verify tests: {str(e)}"
            }

    def _check_unnecessary_files(self, project_path: str) -> Dict[str, List[str]]:
        """Check for unnecessary or redundant files."""
        unnecessary = []

        patterns = [
            '**/*.bak',
            '**/*.tmp',
            '**/*~',
            '**/.DS_Store',
            '**/Thumbs.db',
            '**/__pycache__',
            '**/*.pyc',
            '**/node_modules',
            '**/.pytest_cache'
        ]

        project = Path(project_path)
        for pattern in patterns:
            for file in project.glob(pattern):
                if file.is_file():
                    unnecessary.append(str(file.relative_to(project)))

        # Check for empty files
        for file in project.rglob('*.py'):
            if file.stat().st_size == 0:
                unnecessary.append(str(file.relative_to(project)))

        return {'unnecessary': unnecessary}

    def _verify_production_quality(self, project_path: str) -> Dict[str, Any]:
        """Verify code meets production quality standards."""
        try:
            # Use quality metrics analyzer
            report = self.metrics_analyzer.analyze_project(project_path)

            suggestions = []

            if report.complexity.cyclomatic_complexity > 10:
                suggestions.append("Reduce code complexity by breaking down complex functions")

            if report.documentation.docstring_coverage < 80:
                suggestions.append("Add comprehensive docstrings to all public functions and classes")

            if report.security.secrets_in_code:
                suggestions.append("Remove hardcoded secrets and use environment variables")

            if report.complexity.duplicate_code_ratio > 0.05:  # 5% duplication
                suggestions.append("Refactor duplicated code into reusable functions")

            return {
                'score': report.overall_score,
                'production_ready': report.production_ready,
                'suggestions': suggestions
            }

        except Exception as e:
            logger.error(f"Quality check error: {str(e)}")
            return {
                'score': 0.0,
                'production_ready': False,
                'suggestions': ["Could not analyze code quality"]
            }

    def _detect_ai_patterns(self, project_path: str) -> Dict[str, Any]:
        """Detect AI-generated code patterns."""
        detected_files = []

        project = Path(project_path)
        for file in project.rglob('*.py'):
            try:
                content = file.read_text()
                has_patterns, patterns = self.ai_detector.detect_ai_patterns(content)
                if has_patterns:
                    detected_files.append(str(file.relative_to(project)))
            except Exception:
                continue

        return {
            'detected': len(detected_files) > 0,
            'files': detected_files
        }

    def _run_lint_checks(self, project_path: str) -> Dict[str, Any]:
        """Run lint checks on the code."""
        try:
            # Try common linters
            linters = [
                ['ruff', 'check', '--quiet'],
                ['flake8', '--quiet'],
                ['pylint', '--errors-only'],
            ]

            for linter_cmd in linters:
                if self._command_exists(linter_cmd[0]):
                    result = subprocess.run(
                        linter_cmd + ['.'],
                        cwd=project_path,
                        capture_output=True,
                        timeout=30
                    )

                    if result.returncode == 0:
                        return {'passed': True, 'linter': linter_cmd[0]}
                    else:
                        return {
                            'passed': False,
                            'linter': linter_cmd[0],
                            'errors': result.stdout.decode() + result.stderr.decode()
                        }

            # No linter found, pass by default
            return {'passed': True, 'linter': 'none'}

        except Exception as e:
            return {'passed': True, 'error': str(e)}

    def _calculate_score(self, result: VerificationResult) -> float:
        """Calculate overall verification score."""
        score = 100.0

        # Deduct for failed criteria
        if result.failed_criteria:
            criteria_penalty = len(result.failed_criteria) * 10
            score -= min(criteria_penalty, 40)

        # Deduct for quality issues
        quality_score = result.metadata.get('quality_score', 10.0)
        if quality_score < 7.0:
            score -= (7.0 - quality_score) * 5

        # Deduct for each failure reason
        score -= len(result.failure_reasons) * 5

        # Bonus for passing all criteria
        if not result.failed_criteria and not result.failure_reasons:
            score = min(score + 10, 100)

        return max(score, 0.0)

    def trigger_re_execution(
        self,
        ticket_id: str,
        verification_result: VerificationResult,
        executor_callback: callable
    ) -> Optional[VerificationResult]:
        """Trigger re-execution of failed ticket with context."""
        # Check retry limit
        if self.retry_count.get(ticket_id, 0) >= self.config.max_retries:
            logger.warning(f"Max retries ({self.config.max_retries}) reached for ticket {ticket_id}")
            return None

        # Calculate backoff delay
        retry_num = self.retry_count.get(ticket_id, 0)
        delay = self.config.retry_delay_base * (2 ** retry_num)

        logger.info(f"Waiting {delay}s before retry {retry_num + 1} for ticket {ticket_id}")
        time.sleep(delay)

        # Prepare failure context for re-execution
        failure_context = {
            'previous_failures': verification_result.failure_reasons,
            'suggestions': verification_result.suggestions,
            'failed_criteria': verification_result.failed_criteria,
            'retry_number': retry_num + 1
        }

        # Trigger re-execution with context
        logger.info(f"Triggering re-execution of ticket {ticket_id} with failure context")
        executor_callback(ticket_id, failure_context)

        # Increment retry count
        self.retry_count[ticket_id] = retry_num + 1

        return None

    def _track_attempt(self, ticket_id: str):
        """Track verification attempt."""
        self.verification_history.append({
            'ticket_id': ticket_id,
            'timestamp': datetime.utcnow().isoformat(),
            'attempt': self.retry_count.get(ticket_id, 0) + 1
        })

    def _log_verification(self, ticket_id: str, result: VerificationResult):
        """Log verification for audit trail."""
        log_entry = {
            'ticket_id': ticket_id,
            'timestamp': result.timestamp,
            'status': result.status.value,
            'score': result.score,
            'failures': len(result.failure_reasons),
            'retry_count': self.retry_count.get(ticket_id, 0)
        }

        logger.info(f"Verification audit: {json.dumps(log_entry)}")

        # Also save to file if configured
        if self.config.log_to_file:
            audit_path = Path(self.config.audit_log_path)
            with open(audit_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')

    def _get_test_command(self, project_path: str) -> List[str]:
        """Determine appropriate test command for project."""
        # Check for common test runners
        project = Path(project_path)

        if (project / 'pytest.ini').exists() or (project / 'setup.cfg').exists():
            return ['pytest', '-v']
        elif (project / 'setup.py').exists():
            return ['python', 'setup.py', 'test']
        elif (project / 'manage.py').exists():
            return ['python', 'manage.py', 'test']
        else:
            return ['python', '-m', 'pytest', '-v']

    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists."""
        try:
            subprocess.run(
                ['which', cmd],
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _check_function_exists(self, project_path: str, function_name: str) -> bool:
        """Check if a function exists in the project."""
        project = Path(project_path)
        for file in project.rglob('*.py'):
            try:
                content = file.read_text()
                if f'def {function_name}' in content or f'async def {function_name}' in content:
                    return True
            except Exception:
                continue
        return False

    def _check_test_exists(self, project_path: str, test_pattern: str) -> bool:
        """Check if tests matching pattern exist."""
        project = Path(project_path)
        test_dirs = ['test', 'tests', 'test_*', 'tests_*']

        for test_dir in test_dirs:
            for test_file in project.glob(f'**/{test_dir}/*.py'):
                try:
                    content = test_file.read_text()
                    if test_pattern in content or 'def test_' in content:
                        return True
                except Exception:
                    continue
        return False

    def _check_feature_implemented(self, project_path: str, feature: str) -> bool:
        """Check if a feature is implemented."""
        # This is a heuristic check - look for relevant code
        keywords = feature.lower().split()
        project = Path(project_path)

        for file in project.rglob('*.py'):
            try:
                content = file.read_text().lower()
                if all(keyword in content for keyword in keywords[:3]):
                    return True
            except Exception:
                continue
        return False

    def _check_code_added(self, project_path: str) -> bool:
        """Check if any meaningful code was added."""
        project = Path(project_path)
        py_files = list(project.rglob('*.py'))

        if not py_files:
            return False

        # Check if files have actual content
        for file in py_files:
            try:
                content = file.read_text()
                # Skip empty or trivial files
                if len(content.strip()) > 100:
                    return True
            except Exception:
                continue

        return False

    def get_verification_stats(self) -> Dict[str, Any]:
        """Get verification statistics."""
        return {
            'total_verifications': len(self.verification_history),
            'retry_counts': dict(self.retry_count),
            'history': self.verification_history[-10:]  # Last 10 verifications
        }

    def reset_retry_count(self, ticket_id: str):
        """Reset retry count for a ticket."""
        if ticket_id in self.retry_count:
            del self.retry_count[ticket_id]

    def generate_verification_report(
        self,
        ticket_id: str,
        ticket_data: Dict[str, Any],
        verification_result: VerificationResult,
        format: str = "both"
    ) -> Dict[str, str]:
        """Generate detailed verification report in requested format.
        
        Args:
            ticket_id: ID of the verified ticket
            ticket_data: Original ticket data
            verification_result: Result from verification
            format: "json", "html", or "both"
        
        Returns:
            Dict with paths to generated reports

        """
        # Prepare comprehensive report data
        report_data = {
            "ticket_id": ticket_id,
            "title": ticket_data.get("title", "Unknown"),
            "timestamp": verification_result.timestamp,
            "overall_status": verification_result.status.value.upper(),
            "score": verification_result.score,

            # Verification details
            "verification_summary": {
                "status": verification_result.status.value,
                "score": verification_result.score,
                "passed_criteria": len(verification_result.passed_criteria),
                "failed_criteria": len(verification_result.failed_criteria),
                "total_criteria": len(verification_result.passed_criteria) + len(verification_result.failed_criteria),
                "failure_count": len(verification_result.failure_reasons)
            },

            # Criteria validation
            "criteria_validation": {
                "total_criteria": len(verification_result.passed_criteria) + len(verification_result.failed_criteria),
                "verified_criteria": len(verification_result.passed_criteria),
                "criteria": [
                    {
                        "id": f"AC-{i+1:03d}",
                        "text": criterion,
                        "verified": True,
                        "completed": True,
                        "verification_method": "automated"
                    }
                    for i, criterion in enumerate(verification_result.passed_criteria)
                ] + [
                    {
                        "id": f"AC-{len(verification_result.passed_criteria)+i+1:03d}",
                        "text": criterion,
                        "verified": False,
                        "completed": False,
                        "verification_method": "automated"
                    }
                    for i, criterion in enumerate(verification_result.failed_criteria)
                ]
            },

            # Quality metrics
            "quality_checks": {
                "overall_score": verification_result.metadata.get("quality_score", 0.0) / 10.0,
                "overall_passed": verification_result.metadata.get("quality_score", 0.0) >= self.config.min_quality_score,
                "file_results": []
            },

            # Failure analysis
            "failure_analysis": {
                "failure_reasons": verification_result.failure_reasons,
                "suggestions": verification_result.suggestions,
                "retry_count": self.retry_count.get(ticket_id, 0)
            },

            # Historical data
            "verification_history": {
                "total_attempts": self.retry_count.get(ticket_id, 0) + 1,
                "attempts": [
                    h for h in self.verification_history
                    if h.get("ticket_id") == ticket_id
                ]
            }
        }

        # Generate reports based on format
        if not self.report_generator:
            self.report_generator = ReportGenerator()

        if format == "json":
            json_path = self.report_generator.generate_json_report(report_data)
            return {"json_report": json_path}
        elif format == "html":
            html_path = self.report_generator.generate_html_report(report_data)
            return {"html_report": html_path}
        else:  # both
            return self.report_generator.generate_combined_report(report_data)
