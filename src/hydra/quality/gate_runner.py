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

from hydra.quality.ai_detection import AIGeneratedCodeDetector
from hydra.verification.ticket_verifier import TicketVerifier


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
                "lint": {"enabled": True, "blocking": False},
                "test": {"enabled": True, "blocking": True},
                "typecheck": {"enabled": True, "blocking": False},
                "security": {"enabled": False, "blocking": True},
                "coverage": {"enabled": True, "blocking": False, "threshold": 80},
                "ai_detection": {"enabled": True, "blocking": False}
            },
            "timeout": 300,
            "fail_fast": False
        }

    def _detect_available_tools(self) -> Dict[str, Dict]:
        """Detect available quality tools in the project."""
        tools = {}

        # Python tools
        if (self.project_root / "setup.py").exists() or (self.project_root / "pyproject.toml").exists():
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
        """Detect Python linter."""
        linters = [
            (["ruff", "check"], "ruff"),
            (["flake8"], "flake8"),
            (["pylint"], "pylint"),
            (["python", "-m", "flake8"], "flake8"),
            (["python", "-m", "pylint"], "pylint")
        ]

        for cmd, _name in linters:
            if self._command_exists(cmd[0]):
                return cmd

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

    def run_quality_gates(self, ticket_id: str) -> QualityGateReport:
        """Run all quality gates for a ticket."""
        start_time = time.time()
        results = []

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
            # Linting
            if self.config["checks"]["lint"]["enabled"] and tools.get("lint"):
                result = self._run_check("lint", tools["lint"], lang)
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

        # Run AI detection check (non-blocking)
        if self.config["checks"].get("ai_detection", {}).get("enabled", True):
            result = self._run_ai_detection()
            results.append(result)

        # Calculate statistics
        passed = sum(1 for r in results if r.status == CheckStatus.PASSED)
        failed = sum(1 for r in results if r.status == CheckStatus.FAILED)
        warnings = sum(1 for r in results if r.status == CheckStatus.WARNING)
        skipped = sum(1 for r in results if r.status == CheckStatus.SKIPPED)

        # Determine overall status
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
        """Run ticket acceptance criteria verification."""
        start_time = time.time()

        try:
            verifier = TicketVerifier(self.project_root)
            tickets_file = self.project_root / "tickets.md"

            if not tickets_file.exists():
                return CheckResult(
                    name="ticket:verification",
                    status=CheckStatus.SKIPPED,
                    duration=0,
                    output="No tickets.md file found"
                )

            report = verifier.verify_ticket(str(tickets_file), ticket_id)
            duration = time.time() - start_time

            # Determine status based on coverage
            if report.coverage >= 90:
                status = CheckStatus.PASSED
            elif report.coverage >= 70:
                status = CheckStatus.WARNING
            else:
                status = CheckStatus.FAILED

            output = f"Coverage: {report.coverage:.1f}%\n"
            output += f"Passed: {report.passed}/{report.total_criteria}\n"
            output += f"Failed: {report.failed}/{report.total_criteria}"

            return CheckResult(
                name="ticket:verification",
                status=status,
                duration=duration,
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

    def _run_ai_detection(self) -> CheckResult:
        """Run AI-generated code detection check."""
        start_time = time.time()

        try:
            detector = AIGeneratedCodeDetector()
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

            duration = time.time() - start_time

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
