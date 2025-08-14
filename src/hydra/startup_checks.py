"""Startup checks for Hydra CLI.

Validates tool availability and provides installation guidance.
"""

import subprocess
import sys
from typing import Dict, List, Optional, Tuple


class StartupChecker:
    """Performs startup validation and tool availability checks."""

    def __init__(self):
        self.issues = []
        self.warnings = []

    def check_ruff_installation(self) -> Tuple[bool, Optional[str]]:
        """Check if ruff is available and provide installation guidance.

        Returns:
            Tuple of (is_available, fallback_tool)

        """
        # Check if ruff is available
        if self._command_exists("ruff"):
            return True, None

        # Check for fallback tools
        fallback = self._detect_fallback_linter()

        if fallback:
            self.warnings.append({
                "tool": "ruff",
                "message": f"ruff not found, falling back to {fallback[1]}",
                "installation": self._get_ruff_installation_instructions()
            })
            return False, fallback[1]
        else:
            self.issues.append({
                "tool": "ruff",
                "message": "ruff not found and no fallback linter available",
                "installation": self._get_ruff_installation_instructions(),
                "severity": "warning"
            })
            return False, None

    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            result = subprocess.run(
                ["which", command] if sys.platform != "win32" else ["where", command],
                capture_output=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False

    def _detect_fallback_linter(self) -> Optional[Tuple[List[str], str]]:
        """Detect available fallback linters.

        Returns:
            Tuple of (command_list, tool_name) or None

        """
        fallbacks = [
            (["flake8"], "flake8"),
            (["pylint"], "pylint"),
            (["python", "-m", "flake8"], "flake8"),
            (["python", "-m", "pylint"], "pylint")
        ]

        for cmd, name in fallbacks:
            if self._command_exists(cmd[0]):
                return cmd, name

        return None

    def _get_ruff_installation_instructions(self) -> List[str]:
        """Get installation instructions for ruff."""
        return [
            "Install ruff using one of these methods:",
            "",
            "Via pip:",
            "  pip install ruff",
            "",
            "Via pipx (recommended):",
            "  pipx install ruff",
            "",
            "Via conda:",
            "  conda install -c conda-forge ruff",
            "",
            "Via homebrew (macOS):",
            "  brew install ruff",
            "",
            "Via package manager (Ubuntu/Debian):",
            "  sudo apt install ruff",
            "",
            "For more installation options, visit:",
            "  https://docs.astral.sh/ruff/installation/"
        ]

    def run_startup_checks(self) -> Dict[str, any]:
        """Run all startup checks.

        Returns:
            Dict with check results and any issues found

        """
        results = {
            "success": True,
            "issues": [],
            "warnings": [],
            "tools": {}
        }

        # Check ruff installation
        ruff_available, fallback_tool = self.check_ruff_installation()
        results["tools"]["ruff"] = {
            "available": ruff_available,
            "fallback": fallback_tool
        }

        # Add any collected issues and warnings
        results["issues"] = self.issues
        results["warnings"] = self.warnings

        # Determine overall success
        error_issues = [i for i in self.issues if i.get("severity") == "error"]
        results["success"] = len(error_issues) == 0

        return results

    def print_startup_report(
        self, results: Dict[str, any], verbose: bool = False
    ) -> None:
        """Print startup check results."""
        if not verbose and results["success"] and not results["warnings"]:
            # Silent if everything is good
            return

        self._print_warnings(results["warnings"], verbose)
        self._print_issues(results["issues"], verbose)
        self._print_summary(results, verbose)

    def _print_warnings(self, warnings: List[Dict], verbose: bool) -> None:
        """Print warning messages."""
        for warning in warnings:
            print(f"⚠️  {warning['message']}")
            if verbose:
                print("\n".join([f"   {line}" for line in warning["installation"]]))
                print()

    def _print_issues(self, issues: List[Dict], verbose: bool) -> None:
        """Print issue messages."""
        for issue in issues:
            severity_icon = "❌" if issue.get("severity") == "error" else "⚠️"
            print(f"{severity_icon} {issue['message']}")
            if verbose or issue.get("severity") == "error":
                print("\n".join([f"   {line}" for line in issue["installation"]]))
                print()

    def _print_summary(self, results: Dict[str, any], verbose: bool) -> None:
        """Print final summary."""
        if not results["success"]:
            msg = "❌ Startup checks failed. Please resolve critical issues before proceeding."  # noqa: E501
            print(msg)
        elif results["warnings"] and verbose:
            print("✅ Startup checks completed with warnings.")
        elif verbose:
            print("✅ All startup checks passed.")
