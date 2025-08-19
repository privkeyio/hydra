"""Test Coverage Analyzer Module

Ensures minimum test coverage for new code by analyzing test files and execution.
"""

import ast
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CoverageResult:
    """Represents test coverage analysis result."""

    file_path: str
    line_coverage: float
    branch_coverage: float
    function_coverage: float
    total_lines: int
    covered_lines: int
    missing_lines: List[int]
    has_tests: bool


class CoverageAnalyzer:
    """Test coverage analyzer that ensures minimum test coverage for new code.
    """

    def __init__(self, project_root: str, min_coverage: float = 0.8):
        """Initialize the coverage analyzer."""
        self.project_root = Path(project_root)
        self.min_coverage = min_coverage
        self.test_patterns = [
            "**/test_*.py",
            "**/tests/*.py",
            "**/*_test.py"
        ]

    def find_test_files(self) -> List[Path]:
        """Find all test files in the project."""
        test_files = []

        for pattern in self.test_patterns:
            test_files.extend(self.project_root.glob(pattern))

        return list(set(test_files))  # Remove duplicates

    def extract_functions_and_classes(self, file_path: str) -> Dict[str, List[str]]:
        """Extract function and class names from a Python file."""
        full_path = self.project_root / file_path

        if not full_path.exists() or not file_path.endswith('.py'):
            return {"functions": [], "classes": []}

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source)
            functions = []
            classes = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)

            return {"functions": functions, "classes": classes}

        except Exception as e:
            return {"functions": [], "classes": [], "error": str(e)}

    def find_corresponding_test_file(self, source_file: str) -> Optional[str]:
        """Find the corresponding test file for a source file."""
        source_path = Path(source_file)
        source_name = source_path.stem

        # Common test file patterns
        test_patterns = [
            f"test_{source_name}.py",
            f"{source_name}_test.py",
            f"tests/test_{source_name}.py",
            f"tests/unit/test_{source_name}.py",
            f"tests/integration/test_{source_name}.py"
        ]

        for pattern in test_patterns:
            test_path = self.project_root / pattern
            if test_path.exists():
                return str(test_path.relative_to(self.project_root))

        return None

    def analyze_test_coverage_static(self, source_file: str, test_file: str) -> Dict[str, Any]:
        """Analyze test coverage using static analysis."""
        source_info = self.extract_functions_and_classes(source_file)
        test_info = self.extract_functions_and_classes(test_file)

        source_functions = set(source_info.get("functions", []))
        source_classes = set(source_info.get("classes", []))
        test_functions = set(test_info.get("functions", []))

        # Find tested functions (heuristic: test functions that contain source function names)
        tested_functions = set()
        tested_classes = set()

        for test_func in test_functions:
            test_func_lower = test_func.lower()

            for source_func in source_functions:
                if source_func.lower() in test_func_lower:
                    tested_functions.add(source_func)

            for source_class in source_classes:
                if source_class.lower() in test_func_lower:
                    tested_classes.add(source_class)

        # Calculate coverage percentages
        function_coverage = (
            len(tested_functions) / len(source_functions)
            if source_functions else 1.0
        )

        class_coverage = (
            len(tested_classes) / len(source_classes)
            if source_classes else 1.0
        )

        return {
            "source_functions": list(source_functions),
            "source_classes": list(source_classes),
            "tested_functions": list(tested_functions),
            "tested_classes": list(tested_classes),
            "function_coverage": function_coverage,
            "class_coverage": class_coverage,
            "untested_functions": list(source_functions - tested_functions),
            "untested_classes": list(source_classes - tested_classes)
        }

    def estimate_line_coverage(self, file_path: str) -> Dict[str, Any]:
        """Estimate line coverage using basic heuristics."""
        full_path = self.project_root / file_path

        if not full_path.exists() or not file_path.endswith('.py'):
            return {
                "total_lines": 0,
                "executable_lines": 0,
                "estimated_coverage": 1.0,
                "has_tests": False
            }

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            total_lines = len(lines)
            executable_lines = 0

            for line in lines:
                stripped = line.strip()
                # Count lines that are likely executable (not comments, docstrings, etc.)
                if (stripped and
                    not stripped.startswith('#') and
                    not stripped.startswith('"""') and
                    not stripped.startswith("'''") and
                    stripped != '"""' and
                    stripped != "'''" and
                    not stripped.startswith('import') and
                    not stripped.startswith('from')):
                    executable_lines += 1

            # Check if corresponding test file exists
            test_file = self.find_corresponding_test_file(file_path)
            has_tests = test_file is not None

            # Estimate coverage based on test presence and file characteristics
            if has_tests and test_file:
                test_analysis = self.analyze_test_coverage_static(file_path, test_file)
                estimated_coverage = (
                    test_analysis["function_coverage"] * 0.6 +
                    test_analysis["class_coverage"] * 0.4
                )
            else:
                estimated_coverage = 0.0

            return {
                "total_lines": total_lines,
                "executable_lines": executable_lines,
                "estimated_coverage": estimated_coverage,
                "has_tests": has_tests,
                "test_file": test_file
            }

        except Exception as e:
            return {
                "total_lines": 0,
                "executable_lines": 0,
                "estimated_coverage": 0.0,
                "has_tests": False,
                "error": str(e)
            }

    def run_coverage_analysis(self, artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run coverage analysis for all Python file artifacts."""
        file_results = []
        total_files = 0
        files_with_tests = 0
        total_coverage = 0.0

        for artifact in artifacts:
            if artifact.get("type") == "file" and artifact["path"].endswith('.py'):
                total_files += 1

                result = self.estimate_line_coverage(artifact["path"])
                result["file_path"] = artifact["path"]
                result["meets_threshold"] = result["estimated_coverage"] >= self.min_coverage

                if result["has_tests"]:
                    files_with_tests += 1

                total_coverage += result["estimated_coverage"]
                file_results.append(result)

        if total_files == 0:
            return {
                "total_files": 0,
                "files_with_tests": 0,
                "average_coverage": 1.0,
                "meets_threshold": True,
                "file_results": [],
                "summary": "No Python files to analyze"
            }

        average_coverage = total_coverage / total_files
        meets_threshold = average_coverage >= self.min_coverage

        return {
            "total_files": total_files,
            "files_with_tests": files_with_tests,
            "average_coverage": average_coverage,
            "meets_threshold": meets_threshold,
            "min_coverage_threshold": self.min_coverage,
            "file_results": file_results,
            "summary": f"Coverage analysis: {average_coverage:.1%} average coverage ({files_with_tests}/{total_files} files have tests)"
        }

    def generate_coverage_recommendations(self, analysis_result: Dict[str, Any]) -> List[str]:
        """Generate recommendations to improve test coverage."""
        recommendations = []

        if not analysis_result["meets_threshold"]:
            recommendations.append(
                f"Overall coverage ({analysis_result['average_coverage']:.1%}) "
                f"is below minimum threshold ({self.min_coverage:.1%})"
            )

        for file_result in analysis_result["file_results"]:
            if not file_result["has_tests"]:
                recommendations.append(
                    f"Create test file for {file_result['file_path']}"
                )
            elif not file_result["meets_threshold"]:
                recommendations.append(
                    f"Improve test coverage for {file_result['file_path']} "
                    f"(current: {file_result['estimated_coverage']:.1%})"
                )

        if analysis_result["files_with_tests"] == 0:
            recommendations.append(
                "No test files found. Consider adding a comprehensive test suite."
            )

        return recommendations

    def try_run_pytest_coverage(self) -> Optional[Dict[str, Any]]:
        """Try to run pytest with coverage if available."""
        try:
            # Check if pytest and coverage are available
            subprocess.run(['python', '-m', 'pytest', '--version'],
                         capture_output=True, check=True, cwd=self.project_root)
            subprocess.run(['python', '-m', 'coverage', '--version'],
                         capture_output=True, check=True, cwd=self.project_root)

            # Run pytest with coverage
            result = subprocess.run([
                'python', '-m', 'pytest', '--cov=src', '--cov-report=json',
                '--cov-report=term-missing', '-q'
            ], capture_output=True, text=True, cwd=self.project_root, timeout=60)

            if result.returncode == 0:
                # Try to read coverage.json if it exists
                coverage_file = self.project_root / 'coverage.json'
                if coverage_file.exists():
                    import json
                    with open(coverage_file, 'r') as f:
                        coverage_data = json.load(f)

                    return {
                        "available": True,
                        "coverage_data": coverage_data,
                        "summary": coverage_data.get("totals", {})
                    }

            return {"available": True, "coverage_data": None, "output": result.stdout}

        except (subprocess.SubprocessError, subprocess.TimeoutExpired, FileNotFoundError):
            return {"available": False, "reason": "pytest or coverage not available"}

    def comprehensive_coverage_analysis(self, artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run comprehensive coverage analysis combining static and dynamic methods."""
        static_analysis = self.run_coverage_analysis(artifacts)
        pytest_result = self.try_run_pytest_coverage()
        recommendations = self.generate_coverage_recommendations(static_analysis)

        return {
            "static_analysis": static_analysis,
            "pytest_coverage": pytest_result,
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat(),
            "overall_assessment": {
                "has_adequate_coverage": static_analysis["meets_threshold"],
                "coverage_score": static_analysis["average_coverage"],
                "test_presence": static_analysis["files_with_tests"] > 0
            }
        }
