"""Codebase analyzer for intelligent ticket generation."""

import ast
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class CodebaseAnalyzer:
    """Analyzes codebase structure and complexity for ticket generation."""

    def __init__(self, project_path: str):
        """Initialize analyzer with project path.

        Args:
            project_path: Root path of the project to analyze

        """
        self.project_path = Path(project_path)
        self.file_cache: Dict[str, Any] = {}
        self.dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self.module_complexity: Dict[str, int] = {}
        self.project_type = None
        self.framework = None
        self.test_framework = None

    def analyze(self) -> Dict[str, Any]:
        """Perform comprehensive codebase analysis.

        Returns:
            Analysis results including structure, dependencies, and complexity

        """
        analysis = {
            "project_type": self._detect_project_type(),
            "framework": self._detect_framework(),
            "test_framework": self._detect_test_framework(),
            "structure": self._analyze_structure(),
            "dependencies": self._analyze_dependencies(),
            "complexity": self._analyze_complexity(),
            "size_metrics": self._calculate_size_metrics(),
            "tech_stack": self._detect_tech_stack(),
            "existing_tests": self._find_existing_tests(),
            "ci_cd": self._detect_ci_cd(),
            "documentation": self._analyze_documentation(),
        }
        return analysis

    def _detect_project_type(self) -> str:
        """Detect the type of project (web, cli, library, etc).

        Returns:
            Project type string

        """
        indicators = {
            "web": ["app.py", "app.js", "index.html", "server.py", "server.js"],
            "cli": ["__main__.py", "cli.py", "command.py", "argparse", "click"],
            "library": ["setup.py", "pyproject.toml", "package.json"],
            "desktop": ["electron", "tkinter", "qt", "gtk"],
            "mobile": ["react-native", "flutter", "ionic"],
            "api": ["fastapi", "django", "flask", "express", "restify"],
        }

        scores = defaultdict(int)

        # Check for indicator files
        for project_type, files in indicators.items():
            for file in files:
                if self._file_exists(file):
                    scores[project_type] += 2

        # Check file contents for imports/patterns
        py_files = list(self.project_path.glob("**/*.py"))[:20]  # Sample first 20
        for py_file in py_files:
            try:
                content = py_file.read_text()
                if "fastapi" in content or "flask" in content or "django" in content:
                    scores["api"] += 1
                    scores["web"] += 1
                if "argparse" in content or "click" in content:
                    scores["cli"] += 1
                if "tkinter" in content or "PyQt" in content:
                    scores["desktop"] += 1
            except Exception:
                continue

        if scores:
            self.project_type = max(scores, key=scores.get)
        else:
            self.project_type = "general"

        return self.project_type

    def _detect_framework(self) -> Optional[str]:
        """Detect the main framework used.

        Returns:
            Framework name or None

        """
        framework_indicators = {
            "fastapi": ["fastapi", "FastAPI"],
            "django": ["django", "Django"],
            "flask": ["flask", "Flask"],
            "express": ["express", "Express"],
            "react": ["react", "React"],
            "vue": ["vue", "Vue"],
            "angular": ["angular", "Angular"],
            "nextjs": ["next", "Next.js"],
        }

        # Check package files
        if self._file_exists("package.json"):
            try:
                import json
                with open(self.project_path / "package.json") as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    for framework, indicators in framework_indicators.items():
                        if any(ind.lower() in deps for ind in indicators):
                            self.framework = framework
                            return framework
            except Exception:
                pass

        if self._file_exists("requirements.txt"):
            try:
                content = (self.project_path / "requirements.txt").read_text()
                for framework, indicators in framework_indicators.items():
                    if any(ind.lower() in content.lower() for ind in indicators):
                        self.framework = framework
                        return framework
            except Exception:
                pass

        if self._file_exists("pyproject.toml"):
            try:
                content = (self.project_path / "pyproject.toml").read_text()
                for framework, indicators in framework_indicators.items():
                    if any(ind.lower() in content.lower() for ind in indicators):
                        self.framework = framework
                        return framework
            except Exception:
                pass

        return None

    def _detect_test_framework(self) -> Optional[str]:
        """Detect the test framework used.

        Returns:
            Test framework name or None

        """
        test_indicators = {
            "pytest": ["pytest", "test_*.py", "conftest.py"],
            "unittest": ["unittest", "TestCase"],
            "jest": ["jest", "*.test.js", "*.spec.js"],
            "mocha": ["mocha", "describe", "it"],
            "vitest": ["vitest", "*.test.ts"],
        }

        # Check for test config files
        if self._file_exists("pytest.ini") or self._file_exists("pyproject.toml"):
            content = ""
            if self._file_exists("pytest.ini"):
                content = (self.project_path / "pytest.ini").read_text()
            if self._file_exists("pyproject.toml"):
                content += (self.project_path / "pyproject.toml").read_text()
            if "pytest" in content:
                self.test_framework = "pytest"
                return "pytest"

        if self._file_exists("jest.config.js") or self._file_exists("jest.config.json"):
            self.test_framework = "jest"
            return "jest"

        # Check test files
        test_files = list(self.project_path.glob("**/test*.py")) + \
                    list(self.project_path.glob("**/*test.py"))
        for test_file in test_files[:5]:  # Sample first 5
            try:
                content = test_file.read_text()
                if "pytest" in content or "@pytest" in content:
                    self.test_framework = "pytest"
                    return "pytest"
                if "unittest" in content or "TestCase" in content:
                    self.test_framework = "unittest"
                    return "unittest"
            except Exception:
                continue

        return None

    def _analyze_structure(self) -> Dict[str, Any]:
        """Analyze project directory structure.

        Returns:
            Structure analysis including key directories and patterns

        """
        structure = {
            "directories": [],
            "key_files": [],
            "patterns": [],
            "depth": 0,
        }

        # Find key directories
        for pattern in ["src", "lib", "app", "core", "modules", "components", "tests", "docs"]:
            dirs = list(self.project_path.glob(f"**/{pattern}"))
            if dirs:
                structure["directories"].extend([str(d.relative_to(self.project_path)) for d in dirs[:3]])

        # Find key files
        key_patterns = ["*.py", "*.js", "*.ts", "*.go", "*.rs", "*.java"]
        for pattern in key_patterns:
            files = list(self.project_path.glob(f"**/{pattern}"))
            if files:
                structure["key_files"].extend([str(f.relative_to(self.project_path)) for f in files[:5]])

        # Calculate directory depth
        max_depth = 0
        for root, dirs, files in os.walk(self.project_path):
            # Skip hidden and vendor directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', 'venv', '__pycache__']]
            depth = root.replace(str(self.project_path), '').count(os.sep)
            max_depth = max(max_depth, depth)
        structure["depth"] = max_depth

        # Detect common patterns
        if self._file_exists("src"):
            structure["patterns"].append("src-layout")
        if self._file_exists("tests") or self._file_exists("test"):
            structure["patterns"].append("separate-tests")
        if any(self.project_path.glob("**/models.*")):
            structure["patterns"].append("mvc-pattern")

        return structure

    def _analyze_dependencies(self) -> Dict[str, Set[str]]:
        """Analyze module dependencies using AST.

        Returns:
            Dependency graph mapping modules to their dependencies

        """
        py_files = list(self.project_path.glob("**/*.py"))

        for py_file in py_files:
            if any(part.startswith('.') or part in ['venv', 'node_modules', '__pycache__']
                   for part in py_file.parts):
                continue

            try:
                content = py_file.read_text()
                tree = ast.parse(content)

                module_name = str(py_file.relative_to(self.project_path)).replace('.py', '').replace('/', '.')

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.dependency_graph[module_name].add(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            self.dependency_graph[module_name].add(node.module)

            except Exception:
                continue

        return dict(self.dependency_graph)

    def _analyze_complexity(self) -> Dict[str, int]:
        """Analyze code complexity using AST.

        Returns:
            Complexity scores for each module

        """
        py_files = list(self.project_path.glob("**/*.py"))

        for py_file in py_files:
            if any(part.startswith('.') or part in ['venv', 'node_modules', '__pycache__']
                   for part in py_file.parts):
                continue

            try:
                content = py_file.read_text()
                tree = ast.parse(content)

                module_name = str(py_file.relative_to(self.project_path))
                complexity = self._calculate_ast_complexity(tree)
                self.module_complexity[module_name] = complexity

            except Exception:
                continue

        return self.module_complexity

    def _calculate_ast_complexity(self, tree: ast.AST) -> int:
        """Calculate cyclomatic complexity from AST.

        Args:
            tree: AST tree to analyze

        Returns:
            Complexity score

        """
        complexity = 1  # Base complexity

        for node in ast.walk(tree):
            # Decision points increase complexity
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # Each and/or adds a branch
                complexity += len(node.values) - 1
            elif isinstance(node, ast.Lambda):
                complexity += 1
            elif isinstance(node, ast.ListComp):
                complexity += sum(1 for _ in node.generators)
            elif isinstance(node, ast.DictComp):
                complexity += sum(1 for _ in node.generators)

        return complexity

    def _calculate_size_metrics(self) -> Dict[str, int]:
        """Calculate size metrics for the project.

        Returns:
            Size metrics including LOC, file counts, etc

        """
        metrics = {
            "total_files": 0,
            "python_files": 0,
            "javascript_files": 0,
            "test_files": 0,
            "total_loc": 0,
            "python_loc": 0,
            "javascript_loc": 0,
        }

        for ext, key in [("*.py", "python"), ("*.js", "javascript"), ("*.ts", "javascript")]:
            files = list(self.project_path.glob(f"**/{ext}"))
            files = [f for f in files if not any(
                part in ['venv', 'node_modules', '__pycache__', '.git']
                for part in f.parts
            )]

            if key == "javascript" and ext == "*.js":
                # Don't overwrite javascript_files if already set by .ts files
                metrics[f"{key}_files"] = metrics.get(f"{key}_files", 0) + len(files)
            elif key == "javascript" and ext == "*.ts":
                metrics[f"{key}_files"] = metrics.get(f"{key}_files", 0) + len(files)
            else:
                metrics[f"{key}_files"] = len(files)

            loc = 0
            for f in files:
                try:
                    loc += len(f.read_text().splitlines())
                except Exception:
                    continue
            if key == "javascript":
                metrics[f"{key}_loc"] = metrics.get(f"{key}_loc", 0) + loc
            else:
                metrics[f"{key}_loc"] = loc
            metrics["total_loc"] += loc

        # Count test files
        test_files = list(self.project_path.glob("**/test*.py")) + \
                    list(self.project_path.glob("**/*test.py")) + \
                    list(self.project_path.glob("**/*.test.js")) + \
                    list(self.project_path.glob("**/*.spec.js"))
        metrics["test_files"] = len(test_files)

        metrics["total_files"] = metrics["python_files"] + metrics["javascript_files"]

        return metrics

    def _detect_tech_stack(self) -> List[str]:
        """Detect technologies used in the project.

        Returns:
            List of detected technologies

        """
        tech_stack = []

        # Language detection
        if list(self.project_path.glob("**/*.py")):
            tech_stack.append("Python")
        if list(self.project_path.glob("**/*.js")) or list(self.project_path.glob("**/*.ts")):
            tech_stack.append("JavaScript/TypeScript")
        if list(self.project_path.glob("**/*.go")):
            tech_stack.append("Go")
        if list(self.project_path.glob("**/*.rs")):
            tech_stack.append("Rust")

        # Database detection
        if self._file_exists("docker-compose.yml") or self._file_exists("docker-compose.yaml"):
            try:
                content = (self.project_path / "docker-compose.yml").read_text() if \
                         self._file_exists("docker-compose.yml") else \
                         (self.project_path / "docker-compose.yaml").read_text()
                if "postgres" in content.lower():
                    tech_stack.append("PostgreSQL")
                if "mysql" in content.lower() or "mariadb" in content.lower():
                    tech_stack.append("MySQL/MariaDB")
                if "mongo" in content.lower():
                    tech_stack.append("MongoDB")
                if "redis" in content.lower():
                    tech_stack.append("Redis")
            except Exception:
                pass

        # Check for ORM/database libraries
        if self._check_import_exists("sqlalchemy"):
            tech_stack.append("SQLAlchemy")
        if self._check_import_exists("django.db"):
            tech_stack.append("Django ORM")
        if self._check_import_exists("pymongo"):
            tech_stack.append("MongoDB")

        # Infrastructure
        if self._file_exists("Dockerfile"):
            tech_stack.append("Docker")
        if self._file_exists(".github/workflows") or self._file_exists(".gitlab-ci.yml"):
            tech_stack.append("CI/CD")
        if self._file_exists("terraform") or list(self.project_path.glob("**/*.tf")):
            tech_stack.append("Terraform")
        if self._file_exists("kubernetes") or list(self.project_path.glob("**/*.yaml")):
            yaml_files = list(self.project_path.glob("**/*.yaml"))[:5]
            for f in yaml_files:
                try:
                    content = f.read_text()
                    if "apiVersion" in content and "kind" in content:
                        tech_stack.append("Kubernetes")
                        break
                except Exception:
                    continue

        return list(set(tech_stack))  # Remove duplicates

    def _find_existing_tests(self) -> Dict[str, Any]:
        """Find and analyze existing tests.

        Returns:
            Information about existing tests

        """
        test_info = {
            "test_files": [],
            "test_count": 0,
            "coverage_configured": False,
            "test_directories": [],
        }

        # Find test files
        test_patterns = ["**/test*.py", "**/*test.py", "**/*.test.js", "**/*.spec.js"]
        for pattern in test_patterns:
            files = list(self.project_path.glob(pattern))
            test_info["test_files"].extend([str(f.relative_to(self.project_path)) for f in files])

        test_info["test_count"] = len(test_info["test_files"])

        # Find test directories
        for dir_name in ["tests", "test", "spec", "__tests__"]:
            dirs = list(self.project_path.glob(f"**/{dir_name}"))
            test_info["test_directories"].extend([str(d.relative_to(self.project_path)) for d in dirs])

        # Check for coverage configuration
        coverage_files = [".coveragerc", "coverage.xml", ".coverage", "codecov.yml"]
        test_info["coverage_configured"] = any(self._file_exists(f) for f in coverage_files)

        return test_info

    def _detect_ci_cd(self) -> Dict[str, Any]:
        """Detect CI/CD configuration.

        Returns:
            CI/CD configuration information

        """
        ci_info = {
            "platform": None,
            "workflows": [],
            "automated_tests": False,
            "automated_deployment": False,
        }

        # GitHub Actions
        if self._file_exists(".github/workflows"):
            ci_info["platform"] = "GitHub Actions"
            workflow_files = list((self.project_path / ".github/workflows").glob("*.yml")) + \
                           list((self.project_path / ".github/workflows").glob("*.yaml"))
            ci_info["workflows"] = [f.name for f in workflow_files]

            # Check workflow content
            for wf in workflow_files:
                try:
                    content = wf.read_text()
                    if "pytest" in content or "npm test" in content or "go test" in content:
                        ci_info["automated_tests"] = True
                    if "deploy" in content.lower() or "release" in content.lower():
                        ci_info["automated_deployment"] = True
                except Exception:
                    continue

        # GitLab CI
        elif self._file_exists(".gitlab-ci.yml"):
            ci_info["platform"] = "GitLab CI"
            try:
                content = (self.project_path / ".gitlab-ci.yml").read_text()
                if "test" in content.lower():
                    ci_info["automated_tests"] = True
                if "deploy" in content.lower():
                    ci_info["automated_deployment"] = True
            except Exception:
                pass

        # Jenkins
        elif self._file_exists("Jenkinsfile"):
            ci_info["platform"] = "Jenkins"

        # CircleCI
        elif self._file_exists(".circleci/config.yml"):
            ci_info["platform"] = "CircleCI"

        return ci_info

    def _analyze_documentation(self) -> Dict[str, Any]:
        """Analyze project documentation.

        Returns:
            Documentation analysis

        """
        doc_info = {
            "has_readme": self._file_exists("README.md") or self._file_exists("README.rst"),
            "has_docs_folder": self._file_exists("docs") or self._file_exists("documentation"),
            "has_api_docs": False,
            "has_contributing": self._file_exists("CONTRIBUTING.md"),
            "has_changelog": self._file_exists("CHANGELOG.md") or self._file_exists("HISTORY.md"),
            "docstring_coverage": 0.0,
        }

        # Check for API documentation
        if self._file_exists("openapi.json") or self._file_exists("swagger.json"):
            doc_info["has_api_docs"] = True
        elif self._file_exists("docs"):
            api_files = list((self.project_path / "docs").glob("*api*"))
            if api_files:
                doc_info["has_api_docs"] = True

        # Estimate docstring coverage for Python files
        py_files = list(self.project_path.glob("**/*.py"))[:20]  # Sample first 20
        total_functions = 0
        documented_functions = 0

        for py_file in py_files:
            if any(part in ['venv', 'node_modules', '__pycache__'] for part in py_file.parts):
                continue
            try:
                content = py_file.read_text()
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        total_functions += 1
                        if ast.get_docstring(node):
                            documented_functions += 1
            except Exception:
                continue

        if total_functions > 0:
            doc_info["docstring_coverage"] = documented_functions / total_functions

        return doc_info

    def _file_exists(self, path: str) -> bool:
        """Check if a file or directory exists in the project.

        Args:
            path: Relative path to check

        Returns:
            True if exists

        """
        return (self.project_path / path).exists()

    def _check_import_exists(self, import_name: str) -> bool:
        """Check if an import exists in any Python file.

        Args:
            import_name: Import to search for

        Returns:
            True if found

        """
        py_files = list(self.project_path.glob("**/*.py"))[:20]  # Sample
        for py_file in py_files:
            try:
                content = py_file.read_text()
                if f"import {import_name}" in content or f"from {import_name}" in content:
                    return True
            except Exception:
                continue
        return False

    def generate_complexity_report(self) -> str:
        """Generate a human-readable complexity report.

        Returns:
            Formatted complexity report

        """
        if not self.module_complexity:
            self._analyze_complexity()

        report = ["Code Complexity Analysis", "=" * 40]

        # Sort by complexity
        sorted_modules = sorted(self.module_complexity.items(), key=lambda x: x[1], reverse=True)

        # Categorize
        high_complexity = [(m, c) for m, c in sorted_modules if c > 10]
        medium_complexity = [(m, c) for m, c in sorted_modules if 5 < c <= 10]
        low_complexity = [(m, c) for m, c in sorted_modules if c <= 5]

        if high_complexity:
            report.append("\nHigh Complexity (>10) - Consider refactoring:")
            for module, complexity in high_complexity[:10]:
                report.append(f"  - {module}: {complexity}")

        if medium_complexity:
            report.append("\nMedium Complexity (5-10):")
            for module, complexity in medium_complexity[:5]:
                report.append(f"  - {module}: {complexity}")

        report.append("\nSummary:")
        report.append(f"  Total modules: {len(self.module_complexity)}")
        report.append(f"  High complexity: {len(high_complexity)}")
        report.append(f"  Medium complexity: {len(medium_complexity)}")
        report.append(f"  Low complexity: {len(low_complexity)}")

        avg_complexity = sum(self.module_complexity.values()) / len(self.module_complexity) if self.module_complexity else 0
        report.append(f"  Average complexity: {avg_complexity:.1f}")

        return "\n".join(report)

    def estimate_ticket_complexity(self, file_path: str) -> str:
        """Estimate ticket complexity for a specific file.

        Args:
            file_path: Path to the file

        Returns:
            Complexity category (fast/balanced/smart/coder)

        """
        if file_path not in self.module_complexity:
            # Try to analyze the specific file
            full_path = self.project_path / file_path
            if full_path.exists() and full_path.suffix == '.py':
                try:
                    content = full_path.read_text()
                    tree = ast.parse(content)
                    complexity = self._calculate_ast_complexity(tree)
                    self.module_complexity[file_path] = complexity
                except Exception:
                    return "balanced"  # Default

        complexity = self.module_complexity.get(file_path, 5)

        # Map complexity to model categories
        if complexity <= 3:
            return "fast"
        elif complexity <= 7:
            return "balanced"
        elif complexity <= 15:
            return "smart"
        else:
            return "coder"  # Very complex, needs specialized coding model

    def find_related_files(self, file_path: str) -> List[str]:
        """Find files related to the given file through imports.

        Args:
            file_path: Path to analyze

        Returns:
            List of related file paths

        """
        related = set()

        # Convert file path to module name
        module_name = str(file_path).replace('.py', '').replace('/', '.')

        # Find modules that import this one
        for module, deps in self.dependency_graph.items():
            if module_name in deps or any(module_name in d for d in deps):
                related.add(module.replace('.', '/') + '.py')

        # Find modules this one imports
        if module_name in self.dependency_graph:
            for dep in self.dependency_graph[module_name]:
                # Convert back to file path if it's a local module
                if not dep.startswith(('sys', 'os', 'json', 'typing')):  # Skip stdlib
                    potential_path = dep.replace('.', '/') + '.py'
                    if (self.project_path / potential_path).exists():
                        related.add(potential_path)

        return list(related)
