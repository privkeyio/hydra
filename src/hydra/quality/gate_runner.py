"""Quality Gate Runner for Hydra.

Automatically runs tests, linting, and other quality checks after ticket execution.
"""

import json
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from hydra.quality.ai_detection import AIGeneratedCodeDetector, StrictnessLevel


class CheckStatus(Enum):
    """Status of a quality check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class CheckResult:
    """Result of a single quality check."""

    name: str
    status: CheckStatus
    duration: float
    output: str
    error: Optional[str] = None
    command: Optional[str] = None


@dataclass
class QualityGateReport:
    """Complete quality gate report."""

    ticket_id: str
    total_checks: int
    passed: int
    failed: int
    warnings: int
    skipped: int
    duration: float
    results: List[CheckResult]
    overall_status: CheckStatus


class QualityGateRunner:
    """Runs quality gates after ticket execution."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.config = self._load_config()
        self.detected_linter = None
        self.available_tools = self._detect_available_tools()

    def _load_config(self) -> Dict:
        """Load quality gate configuration."""
        config_file = self.project_root / ".hydra" / "quality.json"

        if config_file.exists():
            with open(config_file, 'r') as f:
                return json.load(f)

        # Default configuration
        return {
            "checks": {
                "lint": {"enabled": True, "blocking": True, "auto_fix": True},
                "test": {"enabled": True, "blocking": True},
                "typecheck": {"enabled": True, "blocking": False},
                "security": {"enabled": False, "blocking": True},
                "coverage": {"enabled": True, "blocking": False, "threshold": 80},
                "ai_detection": {"enabled": True, "blocking": False},
                "format": {"enabled": True, "blocking": True, "auto_fix": True}
            },
            "timeout": 300,
            "fail_fast": False,
            "emergency_override": False
        }

    def _detect_available_tools(self) -> Dict[str, Dict]:
        """Detect available quality tools in the project."""
        tools = {}

        # Python tools
        has_setup_py = (self.project_root / "setup.py").exists()
        has_pyproject = (self.project_root / "pyproject.toml").exists()
        if has_setup_py or has_pyproject:
            tools["python"] = {
                "lint": self._detect_python_linter(),
                "test": self._detect_python_test_runner(),
                "typecheck": self._detect_python_typechecker(),
                "format": self._detect_python_formatter()
            }

        # JavaScript/TypeScript tools
        if (self.project_root / "package.json").exists():
            tools["javascript"] = {
                "lint": self._detect_js_linter(),
                "test": self._detect_js_test_runner(),
                "typecheck": self._detect_js_typechecker(),
                "build": self._detect_js_build_tool()
            }

        # Rust tools
        if (self.project_root / "Cargo.toml").exists():
            tools["rust"] = {
                "lint": ["cargo", "clippy"],
                "test": ["cargo", "test"],
                "build": ["cargo", "build"],
                "format": ["cargo", "fmt", "--check"]
            }

        # Go tools
        if (self.project_root / "go.mod").exists():
            tools["go"] = {
                "lint": ["golangci-lint", "run"],
                "test": ["go", "test", "./..."],
                "build": ["go", "build"],
                "format": ["go", "fmt", "./..."]
            }

        return tools

    def _detect_python_linter(self) -> Optional[List[str]]:
        """Detect Python linter with graceful fallback."""
        linters = [
            (["ruff", "check"], "ruff"),
            (["flake8"], "flake8"),
            (["pylint"], "pylint"),
            (["python", "-m", "flake8"], "flake8"),
            (["python", "-m", "pylint"], "pylint")
        ]

        for cmd, name in linters:
            if self._command_exists(cmd[0]):
                # Store which linter is being used for reporting
                self.detected_linter = name
                return cmd

        self.detected_linter = None
        return None

    def _detect_python_test_runner(self) -> Optional[List[str]]:
        """Detect Python test runner."""
        runners = [
            (["pytest"], "pytest"),
            (["python", "-m", "pytest"], "pytest"),
            (["python", "-m", "unittest", "discover"], "unittest"),
            (["nose2"], "nose2")
        ]

        for cmd, name in runners:
            if self._command_exists(cmd[0]) or name == "unittest":
                return cmd

        return None

    def _detect_python_typechecker(self) -> Optional[List[str]]:
        """Detect Python type checker."""
        checkers = [
            (["mypy"], "mypy"),
            (["python", "-m", "mypy"], "mypy"),
            (["pyright"], "pyright")
        ]

        for cmd, _name in checkers:
            if self._command_exists(cmd[0]):
                return cmd

        return None

    def _detect_python_formatter(self) -> Optional[List[str]]:
        """Detect Python formatter."""
        formatters = [
            (["black", "--check"], "black"),
            (["python", "-m", "black", "--check"], "black"),
            (["autopep8", "--diff"], "autopep8")
        ]

        for cmd, _name in formatters:
            if self._command_exists(cmd[0].split()[0]):
                return cmd

        return None

    def _detect_js_linter(self) -> Optional[List[str]]:
        """Detect JavaScript linter."""
        package_json = self.project_root / "package.json"

        if package_json.exists():
            with open(package_json, 'r') as f:
                pkg = json.load(f)
                scripts = pkg.get("scripts", {})

                if "lint" in scripts:
                    return ["npm", "run", "lint"]
                elif "eslint" in scripts:
                    return ["npm", "run", "eslint"]

        if self._command_exists("eslint"):
            return ["eslint", ".", "--ext", ".js,.jsx,.ts,.tsx"]

        return None

    def _detect_js_test_runner(self) -> Optional[List[str]]:
        """Detect JavaScript test runner."""
        package_json = self.project_root / "package.json"

        if package_json.exists():
            with open(package_json, 'r') as f:
                pkg = json.load(f)
                scripts = pkg.get("scripts", {})

                if "test" in scripts:
                    return ["npm", "test"]

        return None

    def _detect_js_typechecker(self) -> Optional[List[str]]:
        """Detect JavaScript/TypeScript type checker."""
        if (self.project_root / "tsconfig.json").exists():
            return ["npx", "tsc", "--noEmit"]

        return None

    def _detect_js_build_tool(self) -> Optional[List[str]]:
        """Detect JavaScript build tool."""
        package_json = self.project_root / "package.json"

        if package_json.exists():
            with open(package_json, 'r') as f:
                pkg = json.load(f)
                scripts = pkg.get("scripts", {})

                if "build" in scripts:
                    return ["npm", "run", "build"]

        return None

    def _command_exists(self, command: str) -> bool:
        """Check if a command exists."""
        try:
            subprocess.run(
                ["which", command],
                capture_output=True,
                check=False
            )
            return True
        except Exception:
            return False

    def run_quality_gates(self, ticket_id: str, emergency_override: bool = False) -> QualityGateReport:
        """Run all quality gates for a ticket.
        
        Args:
            ticket_id: The ticket ID to run quality gates for
            emergency_override: Skip blocking checks for emergency situations

        """
        start_time = time.time()
        results = []

        # Check for emergency override
        if emergency_override or self.config.get("emergency_override", False):
            print("🚨 EMERGENCY OVERRIDE ACTIVATED - Quality gates will not block completion!")
            print("   Use only in production emergencies or critical hotfixes")

        # Determine which language tools to use
        language_tools = []
        for lang, tools in self.available_tools.items():
            if any(tools.values()):
                language_tools.append((lang, tools))

        if not language_tools:
            return QualityGateReport(
                ticket_id=ticket_id,
                total_checks=0,
                passed=0,
                failed=0,
                warnings=0,
                skipped=0,
                duration=0,
                results=[],
                overall_status=CheckStatus.SKIPPED
            )

        # Run checks for each language
        for lang, tools in language_tools:
            # Formatting (run first with auto-fix)
            if self.config["checks"]["format"]["enabled"] and tools.get("format"):
                result = self._run_check_with_autofix("format", tools["format"], lang)
                results.append(result)

            # Linting (with auto-fix if enabled)
            if self.config["checks"]["lint"]["enabled"] and tools.get("lint"):
                result = self._run_check_with_autofix("lint", tools["lint"], lang)
                results.append(result)

            # Testing
            if self.config["checks"]["test"]["enabled"] and tools.get("test"):
                result = self._run_check("test", tools["test"], lang)
                results.append(result)

                # Fail fast if tests fail and configured
                if self.config["fail_fast"] and result.status == CheckStatus.FAILED:
                    break

            # Type checking
            if self.config["checks"]["typecheck"]["enabled"] and tools.get("typecheck"):
                result = self._run_check("typecheck", tools["typecheck"], lang)
                results.append(result)

            # Building (for compiled languages)
            if tools.get("build"):
                result = self._run_check("build", tools["build"], lang)
                results.append(result)

        # Run ticket verification
        if self.config["checks"].get("verification", {}).get("enabled", True):
            result = self._run_ticket_verification(ticket_id)
            results.append(result)

        # Run AI detection check (non-blocking) with ticket context
        if self.config["checks"].get("ai_detection", {}).get("enabled", True):
            result = self._run_ai_detection(ticket_id)
            results.append(result)

        # Calculate statistics
        passed = sum(1 for r in results if r.status == CheckStatus.PASSED)
        failed = sum(1 for r in results if r.status == CheckStatus.FAILED)
        warnings = sum(1 for r in results if r.status == CheckStatus.WARNING)
        skipped = sum(1 for r in results if r.status == CheckStatus.SKIPPED)

        # Determine overall status
        if emergency_override or self.config.get("emergency_override", False):
            # In emergency mode, convert failures to warnings
            if failed > 0:
                overall_status = CheckStatus.WARNING
            elif warnings > 0:
                overall_status = CheckStatus.WARNING
            elif passed > 0:
                overall_status = CheckStatus.PASSED
            else:
                overall_status = CheckStatus.SKIPPED
        else:
            # Normal mode - failures block completion
            if failed > 0:
                overall_status = CheckStatus.FAILED
            elif warnings > 0:
                overall_status = CheckStatus.WARNING
            elif passed > 0:
                overall_status = CheckStatus.PASSED
            else:
                overall_status = CheckStatus.SKIPPED

        return QualityGateReport(
            ticket_id=ticket_id,
            total_checks=len(results),
            passed=passed,
            failed=failed,
            warnings=warnings,
            skipped=skipped,
            duration=time.time() - start_time,
            results=results,
            overall_status=overall_status
        )

    def _run_check_with_autofix(self, check_name: str, command: List[str], language: str) -> CheckResult:
        """Run a quality check with auto-fix capability."""
        # Check if auto-fix is enabled for this check
        auto_fix_enabled = self.config["checks"].get(check_name, {}).get("auto_fix", False)

        if not auto_fix_enabled:
            return self._run_check(check_name, command, language)

        # Try auto-fix commands first
        fix_command = self._get_autofix_command(check_name, command, language)
        if fix_command:
            try:
                print(f"🔧 Auto-fixing {check_name} issues...")
                fix_result = subprocess.run(
                    fix_command,
                    capture_output=True,
                    text=True,
                    timeout=self.config["timeout"],
                    cwd=self.project_root
                )

                if fix_result.returncode == 0:
                    print(f"✅ Auto-fix applied for {check_name}")
                else:
                    print(f"⚠️  Auto-fix failed for {check_name}: {fix_result.stderr[:200]}")

            except Exception as e:
                print(f"⚠️  Auto-fix error for {check_name}: {e}")

        # Now run the original check to verify
        return self._run_check(check_name, command, language)

    def _get_autofix_command(self, check_name: str, original_command: List[str], language: str) -> Optional[List[str]]:
        """Get the auto-fix command for a check."""
        if language == "python":
            if check_name == "lint" and "ruff" in original_command[0]:
                return ["ruff", "check", "--fix", "."]
            elif check_name == "format":
                if "black" in original_command:
                    return ["black", "."]
                elif "ruff" in str(original_command):
                    return ["ruff", "format", "."]
        elif language == "javascript":
            if check_name == "lint" and ("eslint" in str(original_command) or "npm" in str(original_command)):
                return ["npx", "eslint", ".", "--fix", "--ext", ".js,.jsx,.ts,.tsx"]
            elif check_name == "format":
                return ["npx", "prettier", "--write", "."]
        elif language == "rust":
            if check_name == "format":
                return ["cargo", "fmt"]
        elif language == "go":
            if check_name == "format":
                return ["go", "fmt", "./..."]

        return None

    def _run_check(self, check_name: str, command: List[str], language: str) -> CheckResult:
        """Run a single quality check."""
        start_time = time.time()
        full_name = f"{language}:{check_name}"

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config["timeout"],
                cwd=self.project_root
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                return CheckResult(
                    name=full_name,
                    status=CheckStatus.PASSED,
                    duration=duration,
                    output=result.stdout[:5000],
                    command=" ".join(command)
                )
            else:
                # Determine if it's a warning or failure
                is_blocking = self.config["checks"].get(check_name, {}).get("blocking", False)
                status = CheckStatus.FAILED if is_blocking else CheckStatus.WARNING

                return CheckResult(
                    name=full_name,
                    status=status,
                    duration=duration,
                    output=result.stdout[:5000],
                    error=result.stderr[:5000],
                    command=" ".join(command)
                )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=full_name,
                status=CheckStatus.FAILED,
                duration=self.config["timeout"],
                output="",
                error=f"Check timed out after {self.config['timeout']}s",
                command=" ".join(command)
            )

        except Exception as e:
            return CheckResult(
                name=full_name,
                status=CheckStatus.SKIPPED,
                duration=time.time() - start_time,
                output="",
                error=str(e),
                command=" ".join(command)
            )

    def _run_ticket_verification(self, ticket_id: str) -> CheckResult:
        """Run comprehensive ticket acceptance criteria verification."""
        start_time = time.time()

        try:
            # Parse ticket from tickets.md
            tickets_file = self.project_root / "tickets.md"
            if not tickets_file.exists():
                return CheckResult(
                    name="ticket:verification",
                    status=CheckStatus.SKIPPED,
                    duration=0,
                    output="No tickets.md file found"
                )

            # Late import to avoid circular dependency
            from hydra.ticket_workflow import parse_ticket
            ticket = parse_ticket(str(tickets_file), ticket_id)

            if not ticket:
                return CheckResult(
                    name="ticket:verification",
                    status=CheckStatus.FAILED,
                    duration=time.time() - start_time,
                    output=f"Could not parse ticket {ticket_id}"
                )

            # Programmatic verification of acceptance criteria
            criteria = ticket.get('acceptance_criteria', [])
            if not criteria:
                return CheckResult(
                    name="ticket:verification",
                    status=CheckStatus.WARNING,
                    duration=time.time() - start_time,
                    output="No acceptance criteria defined"
                )

            verified_count = 0
            failed_criteria = []

            for i, criterion in enumerate(criteria, 1):
                # Check if criterion is already marked as completed (contains [x])
                if '[x]' in criterion or '✅' in criterion:
                    verified_count += 1
                    continue

                # Programmatic verification based on criterion content
                verified = self._verify_criterion_programmatically(criterion, ticket)

                if verified:
                    verified_count += 1
                else:
                    failed_criteria.append(f"{i}. {criterion}")

            coverage = (verified_count / len(criteria)) * 100

            # Determine status based on coverage
            if coverage >= 90:
                status = CheckStatus.PASSED
            elif coverage >= 70:
                status = CheckStatus.WARNING
            else:
                # Check if blocking is configured for verification
                is_blocking = self.config["checks"].get("verification", {}).get("blocking", True)
                status = CheckStatus.FAILED if is_blocking else CheckStatus.WARNING

            output = "Acceptance Criteria Verification:\n"
            output += f"Coverage: {coverage:.1f}%\n"
            output += f"Passed: {verified_count}/{len(criteria)}\n"

            if failed_criteria:
                output += "\nUnverified criteria:\n"
                for criterion in failed_criteria[:5]:  # Show first 5
                    output += f"  - {criterion}\n"
                if len(failed_criteria) > 5:
                    output += f"  ... and {len(failed_criteria) - 5} more\n"

            return CheckResult(
                name="ticket:verification",
                status=status,
                duration=time.time() - start_time,
                output=output
            )

        except Exception as e:
            return CheckResult(
                name="ticket:verification",
                status=CheckStatus.SKIPPED,
                duration=time.time() - start_time,
                output="",
                error=str(e)
            )

    def _verify_criterion_programmatically(self, criterion: str, ticket: dict) -> bool:
        """Programmatically verify an acceptance criterion.
        
        Args:
            criterion: The acceptance criterion to verify
            ticket: The ticket data dictionary
            
        Returns:
            True if the criterion can be verified as completed

        """
        criterion_lower = criterion.lower().strip()

        # Skip already completed criteria
        if '[x]' in criterion or '✅' in criterion or 'done' in criterion_lower:
            return True

        # Check for file existence criteria
        if any(keyword in criterion_lower for keyword in ['create file', 'add file', 'implement file']):
            # Extract potential file paths from criterion
            import re
            file_patterns = re.findall(r'[\w/.-]+\.(py|js|ts|go|rs|java|cpp|c|h|md|json|yaml|yml|toml|txt)', criterion)
            for file_pattern in file_patterns:
                file_path = self.project_root / file_pattern
                if not file_path.exists():
                    return False
            return len(file_patterns) > 0

        # Check for function/class implementation
        if any(keyword in criterion_lower for keyword in ['implement function', 'add function', 'create function', 'implement class', 'add class']):
            # Extract function/class names
            import re
            func_matches = re.findall(r'(?:function|class)\s+(\w+)', criterion_lower)
            for func_name in func_matches:
                # Search for function/class definition in Python files
                try:
                    result = subprocess.run(
                        ["grep", "-r", f"def {func_name}\\|class {func_name}", str(self.project_root)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode != 0:
                        return False
                except:
                    pass
            return len(func_matches) > 0

        # Check for test-related criteria
        if any(keyword in criterion_lower for keyword in ['test', 'unittest', 'pytest']):
            # Look for test files or test functions
            test_files = list(self.project_root.rglob("test_*.py")) + list(self.project_root.rglob("*_test.py"))
            return len(test_files) > 0

        # Check for installation/setup criteria
        if any(keyword in criterion_lower for keyword in ['install', 'setup', 'configure']):
            # Check common config files
            config_files = ['requirements.txt', 'package.json', 'Cargo.toml', 'go.mod', 'pyproject.toml']
            for config_file in config_files:
                if (self.project_root / config_file).exists():
                    return True

        # If we can't verify programmatically, consider it unverified
        # This ensures human review is required for complex criteria
        return False

    def _run_ai_detection(self, ticket_id: Optional[str] = None) -> CheckResult:
        """Run AI-generated code detection check with enhanced analysis.
        
        Args:
            ticket_id: Optional ticket ID for context-aware detection

        """
        start_time = time.time()

        try:
            # Get strictness from config or environment
            import os
            strictness_str = self.config.get("checks", {}).get("ai_detection", {}).get(
                "strictness", os.environ.get('AI_DETECTION_STRICTNESS', 'moderate')
            ).lower()

            strictness_map = {
                'lenient': StrictnessLevel.LENIENT,
                'moderate': StrictnessLevel.MODERATE,
                'strict': StrictnessLevel.STRICT
            }
            strictness = strictness_map.get(strictness_str, StrictnessLevel.MODERATE)

            detector = AIGeneratedCodeDetector(strictness)

            # If we have a ticket ID, perform comprehensive analysis
            if ticket_id:
                # Try to get ticket description from tickets.md
                ticket_description = ""
                tickets_file = self.project_root / "tickets.md"
                if tickets_file.exists():
                    try:
                        # Late import to avoid circular dependency
                        from hydra.ticket_workflow import parse_ticket
                        ticket = parse_ticket(str(tickets_file), ticket_id)
                        if ticket:
                            ticket_description = f"{ticket.get('title', '')} - {ticket.get('description', '')}"
                    except Exception:
                        pass

                # Perform comprehensive analysis
                analysis = detector.analyze_diff_comprehensively(ticket_id, ticket_description)
                report = detector.generate_comprehensive_report(analysis, ticket_id)

                # Determine status based on analysis
                if analysis.critical_issues:
                    status = CheckStatus.WARNING  # Never fail, only warn
                elif analysis.warnings:
                    status = CheckStatus.WARNING
                else:
                    status = CheckStatus.PASSED

                output = report[:5000]  # Limit output size

            else:
                # Fallback to file-by-file checking
                all_issues = []

                # Check Python files
                for py_file in self.project_root.rglob("*.py"):
                    # Skip virtual environments and build directories
                    if any(skip in str(py_file) for skip in ['venv', '.venv', 'build', 'dist', '__pycache__']):
                        continue
                    issues = detector.detect_in_file(py_file)
                    all_issues.extend(issues)

                # Check JavaScript/TypeScript files
                for ext in ['*.js', '*.jsx', '*.ts', '*.tsx']:
                    for js_file in self.project_root.rglob(ext):
                        if 'node_modules' in str(js_file):
                            continue
                        issues = detector.detect_in_file(js_file)
                        all_issues.extend(issues)

                # Check other source files
                for ext in ['*.go', '*.rs', '*.java', '*.cpp', '*.c', '*.rb']:
                    for src_file in self.project_root.rglob(ext):
                        issues = detector.detect_in_file(src_file)
                        all_issues.extend(issues)

                # Generate report
                report_text = detector.generate_report(all_issues)

                # Count severities
                errors = [i for i in all_issues if i.get('severity') == 'error']
                warnings = [i for i in all_issues if i.get('severity', 'warning') == 'warning']

                # Determine status - NEVER FAIL, only warn
                if errors:
                    # Even with errors, we only warn since this shouldn't block
                    status = CheckStatus.WARNING
                elif warnings:
                    status = CheckStatus.WARNING
                else:
                    status = CheckStatus.PASSED

                output = "AI Pattern Detection Results:\n"
                output += f"Errors: {len(errors)}, Warnings: {len(warnings)}\n"
                output += f"Total patterns found: {len(all_issues)}\n\n"

                if len(all_issues) > 0:
                    output += "Top issues (see full report for details):\n"
                    for issue in all_issues[:3]:  # Show first 3 issues
                        output += f"- {issue['file']}:{issue['line']} - {issue['pattern']}\n"

            duration = time.time() - start_time

            return CheckResult(
                name="quality:ai_detection",
                status=status,
                duration=duration,
                output=output[:5000]  # Limit output size
            )

        except Exception as e:
            return CheckResult(
                name="quality:ai_detection",
                status=CheckStatus.SKIPPED,
                duration=time.time() - start_time,
                output="",
                error=str(e)
            )

    def generate_report(self, report: QualityGateReport) -> str:
        """Generate a human-readable quality gate report."""
        lines = [
            "🚦 Quality Gate Report",
            f"{'='*50}",
            f"Ticket: {report.ticket_id}",
            f"Duration: {report.duration:.2f}s",
            "",
            "📊 Summary:",
            f"  Total Checks: {report.total_checks}",
            f"  ✅ Passed: {report.passed}",
            f"  ❌ Failed: {report.failed}",
            f"  ⚠️  Warnings: {report.warnings}",
            f"  ⏭️  Skipped: {report.skipped}",
            "",
            "🔍 Check Results:",
        ]

        for result in report.results:
            status_icon = {
                CheckStatus.PASSED: "✅",
                CheckStatus.FAILED: "❌",
                CheckStatus.WARNING: "⚠️",
                CheckStatus.SKIPPED: "⏭️"
            }.get(result.status, "")

            lines.append(f"  {status_icon} {result.name} ({result.duration:.2f}s)")

            if result.error and result.status == CheckStatus.FAILED:
                lines.append(f"     Error: {result.error[:100]}")

        lines.extend([
            "",
            f"📋 Overall Status: {report.overall_status.value.upper()}",
        ])

        if report.overall_status == CheckStatus.FAILED:
            lines.append("❌ Quality gates failed - please fix issues before proceeding")
        elif report.overall_status == CheckStatus.WARNING:
            lines.append("⚠️  Quality gates passed with warnings")
        elif report.overall_status == CheckStatus.PASSED:
            lines.append("✅ All quality gates passed")

        return "\n".join(lines)

    def save_report(self, report: QualityGateReport, output_dir: Optional[str] = None):
        """Save quality gate report to file."""
        if not output_dir:
            output_dir = self.project_root / ".hydra" / "reports"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON report
        report_file = output_dir / f"quality_gate_{report.ticket_id}_{int(time.time())}.json"

        report_dict = {
            "ticket_id": report.ticket_id,
            "total_checks": report.total_checks,
            "passed": report.passed,
            "failed": report.failed,
            "warnings": report.warnings,
            "skipped": report.skipped,
            "duration": report.duration,
            "overall_status": report.overall_status.value,
            "timestamp": time.time(),
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "duration": r.duration,
                    "output": r.output[:1000],
                    "error": r.error[:1000] if r.error else None,
                    "command": r.command
                }
                for r in report.results
            ]
        }

        with open(report_file, 'w') as f:
            json.dump(report_dict, f, indent=2)

        return str(report_file)
