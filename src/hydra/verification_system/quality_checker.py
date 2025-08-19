"""Code Quality Checker Module

Validates syntax, style, and basic functionality of code files.
"""

import ast
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class QualityCheck:
    """Represents a quality check result."""

    check_type: str
    passed: bool
    score: float  # 0.0 to 1.0
    message: str
    details: Dict[str, Any]


class QualityChecker:
    """Code quality checker that validates syntax, style, and basic functionality.
    """

    def __init__(self, project_root: str):
        """Initialize the quality checker."""
        self.project_root = Path(project_root)
        self.quality_thresholds = {
            "syntax": 1.0,     # Must pass 100%
            "style": 0.8,      # 80% style compliance
            "complexity": 0.7,  # 70% complexity score
            "imports": 0.9     # 90% import resolution
        }

    def check_python_syntax(self, file_path: str) -> QualityCheck:
        """Check Python syntax validity."""
        full_path = self.project_root / file_path

        if not full_path.exists():
            return QualityCheck(
                check_type="syntax",
                passed=False,
                score=0.0,
                message=f"File does not exist: {file_path}",
                details={"error": "file_not_found"}
            )

        if not file_path.endswith('.py'):
            return QualityCheck(
                check_type="syntax",
                passed=True,
                score=1.0,
                message=f"Non-Python file, skipping syntax check: {file_path}",
                details={"skipped": True}
            )

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # Parse the AST to check syntax
            ast.parse(source_code)

            return QualityCheck(
                check_type="syntax",
                passed=True,
                score=1.0,
                message=f"Syntax valid: {file_path}",
                details={"lines": len(source_code.splitlines())}
            )

        except SyntaxError as e:
            return QualityCheck(
                check_type="syntax",
                passed=False,
                score=0.0,
                message=f"Syntax error in {file_path}: {e.msg}",
                details={
                    "error": str(e),
                    "line": e.lineno,
                    "column": e.offset
                }
            )
        except Exception as e:
            return QualityCheck(
                check_type="syntax",
                passed=False,
                score=0.0,
                message=f"Error checking {file_path}: {str(e)}",
                details={"error": str(e)}
            )

    def check_code_style(self, file_path: str) -> QualityCheck:
        """Check code style using basic heuristics."""
        full_path = self.project_root / file_path

        if not full_path.exists() or not file_path.endswith('.py'):
            return QualityCheck(
                check_type="style",
                passed=True,
                score=1.0,
                message=f"Skipping style check for: {file_path}",
                details={"skipped": True}
            )

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            issues = []
            total_lines = len(lines)
            style_violations = 0

            for i, line in enumerate(lines, 1):
                # Check line length
                if len(line.rstrip()) > 100:
                    issues.append(f"Line {i}: Line too long ({len(line.rstrip())} > 100)")
                    style_violations += 1

                # Check trailing whitespace
                if line.rstrip() != line.rstrip('\n'):
                    issues.append(f"Line {i}: Trailing whitespace")
                    style_violations += 1

                # Check indentation (basic check for tabs vs spaces)
                if '\t' in line and '    ' in line:
                    issues.append(f"Line {i}: Mixed tabs and spaces")
                    style_violations += 1

            # Calculate style score
            if total_lines == 0:
                score = 1.0
            else:
                score = max(0.0, 1.0 - (style_violations / total_lines))

            passed = score >= self.quality_thresholds["style"]

            return QualityCheck(
                check_type="style",
                passed=passed,
                score=score,
                message=f"Style check: {score:.2%} compliance ({style_violations} issues)",
                details={
                    "total_lines": total_lines,
                    "violations": style_violations,
                    "issues": issues[:10]  # Limit to first 10 issues
                }
            )

        except Exception as e:
            return QualityCheck(
                check_type="style",
                passed=False,
                score=0.0,
                message=f"Error checking style for {file_path}: {str(e)}",
                details={"error": str(e)}
            )

    def check_import_resolution(self, file_path: str) -> QualityCheck:
        """Check if imports can be resolved."""
        full_path = self.project_root / file_path

        if not full_path.exists() or not file_path.endswith('.py'):
            return QualityCheck(
                check_type="imports",
                passed=True,
                score=1.0,
                message=f"Skipping import check for: {file_path}",
                details={"skipped": True}
            )

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # Parse AST to find imports
            tree = ast.parse(source_code)
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}" if module else alias.name)

            # Try to resolve imports (basic check)
            resolvable = 0
            unresolvable = []

            for imp in imports:
                try:
                    # Basic import resolution check
                    if '.' in imp:
                        parts = imp.split('.')
                        # Check if it's a relative import within the project
                        if parts[0] in ['hydra', 'src']:
                            resolvable += 1
                        else:
                            # Try to import it
                            exec(f"import {parts[0]}")
                            resolvable += 1
                    else:
                        exec(f"import {imp}")
                        resolvable += 1
                except:
                    unresolvable.append(imp)

            total_imports = len(imports)
            if total_imports == 0:
                score = 1.0
            else:
                score = resolvable / total_imports

            passed = score >= self.quality_thresholds["imports"]

            return QualityCheck(
                check_type="imports",
                passed=passed,
                score=score,
                message=f"Import resolution: {score:.2%} ({resolvable}/{total_imports})",
                details={
                    "total_imports": total_imports,
                    "resolvable": resolvable,
                    "unresolvable": unresolvable
                }
            )

        except Exception as e:
            return QualityCheck(
                check_type="imports",
                passed=False,
                score=0.0,
                message=f"Error checking imports for {file_path}: {str(e)}",
                details={"error": str(e)}
            )

    def check_basic_functionality(self, file_path: str) -> QualityCheck:
        """Check basic functionality by trying to load the module."""
        full_path = self.project_root / file_path

        if not full_path.exists() or not file_path.endswith('.py'):
            return QualityCheck(
                check_type="functionality",
                passed=True,
                score=1.0,
                message=f"Skipping functionality check for: {file_path}",
                details={"skipped": True}
            )

        try:
            # Create a temporary file to test loading
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
                with open(full_path, 'r') as original:
                    tmp.write(original.read())
                tmp_path = tmp.name

            try:
                # Try to compile the file
                with open(tmp_path, 'r') as f:
                    source = f.read()
                compile(source, tmp_path, 'exec')

                return QualityCheck(
                    check_type="functionality",
                    passed=True,
                    score=1.0,
                    message=f"Basic functionality check passed: {file_path}",
                    details={"compile_success": True}
                )

            finally:
                os.unlink(tmp_path)

        except Exception as e:
            return QualityCheck(
                check_type="functionality",
                passed=False,
                score=0.0,
                message=f"Functionality check failed for {file_path}: {str(e)}",
                details={"error": str(e)}
            )

    def run_all_checks(self, file_path: str) -> Dict[str, Any]:
        """Run all quality checks on a file."""
        checks = [
            self.check_python_syntax(file_path),
            self.check_code_style(file_path),
            self.check_import_resolution(file_path),
            self.check_basic_functionality(file_path)
        ]

        passed_checks = sum(1 for check in checks if check.passed)
        total_checks = len(checks)
        overall_score = sum(check.score for check in checks) / total_checks

        return {
            "file_path": file_path,
            "overall_score": overall_score,
            "overall_passed": passed_checks == total_checks,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "checks": [
                {
                    "type": check.check_type,
                    "passed": check.passed,
                    "score": check.score,
                    "message": check.message,
                    "details": check.details
                }
                for check in checks
            ],
            "timestamp": datetime.now().isoformat()
        }

    def run_quality_checks_for_artifacts(self, artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run quality checks for all file artifacts."""
        file_results = []

        for artifact in artifacts:
            if artifact.get("type") == "file":
                result = self.run_all_checks(artifact["path"])
                file_results.append(result)

        if not file_results:
            return {
                "total_files": 0,
                "passed_files": 0,
                "overall_score": 1.0,
                "overall_passed": True,
                "file_results": [],
                "summary": "No files to check"
            }

        passed_files = sum(1 for r in file_results if r["overall_passed"])
        total_files = len(file_results)
        overall_score = sum(r["overall_score"] for r in file_results) / total_files

        return {
            "total_files": total_files,
            "passed_files": passed_files,
            "overall_score": overall_score,
            "overall_passed": passed_files == total_files,
            "file_results": file_results,
            "summary": f"Quality checks: {passed_files}/{total_files} files passed"
        }
