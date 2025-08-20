"""Production Quality Metrics Module

Comprehensive metrics system to measure production readiness of generated code.
Analyzes code complexity, test coverage, documentation, error handling, 
performance, and security best practices.
"""

import ast
import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ComplexityMetrics:
    """Code complexity measurements"""

    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    nesting_depth: int = 0
    lines_of_code: int = 0
    number_of_functions: int = 0
    number_of_classes: int = 0
    average_function_length: float = 0.0
    max_function_length: int = 0
    duplicate_code_ratio: float = 0.0


@dataclass
class CoverageMetrics:
    """Test coverage measurements"""

    line_coverage: float = 0.0
    branch_coverage: float = 0.0
    function_coverage: float = 0.0
    statement_coverage: float = 0.0
    covered_lines: int = 0
    total_lines: int = 0
    covered_branches: int = 0
    total_branches: int = 0
    test_files_count: int = 0
    test_to_code_ratio: float = 0.0


@dataclass
class DocumentationMetrics:
    """Documentation completeness measurements"""

    docstring_coverage: float = 0.0
    public_api_documented: float = 0.0
    inline_comment_ratio: float = 0.0
    readme_exists: bool = False
    api_docs_exists: bool = False
    examples_provided: bool = False
    changelog_exists: bool = False
    functions_with_docstrings: int = 0
    total_functions: int = 0
    classes_with_docstrings: int = 0
    total_classes: int = 0


@dataclass
class ErrorHandlingMetrics:
    """Error handling coverage measurements"""

    try_except_coverage: float = 0.0
    unhandled_exceptions: List[str] = field(default_factory=list)
    error_logging_present: bool = False
    custom_exceptions_defined: bool = False
    validation_coverage: float = 0.0
    input_sanitization: bool = False
    graceful_degradation: bool = False
    retry_logic_present: bool = False
    circuit_breaker_present: bool = False


@dataclass
class PerformanceMetrics:
    """Performance benchmark measurements"""

    average_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    database_query_optimization: bool = False
    caching_implemented: bool = False
    async_operations_used: bool = False
    batch_processing_used: bool = False
    connection_pooling: bool = False


@dataclass
class SecurityMetrics:
    """Security best practices measurements"""

    sql_injection_safe: bool = True
    xss_protection: bool = True
    authentication_present: bool = False
    authorization_present: bool = False
    input_validation: bool = False
    output_encoding: bool = False
    secrets_in_code: bool = False
    secure_random_used: bool = False
    encryption_used: bool = False
    audit_logging: bool = False
    rate_limiting: bool = False
    csrf_protection: bool = False


@dataclass
class QualityReport:
    """Complete quality metrics report"""

    complexity: ComplexityMetrics
    coverage: CoverageMetrics
    documentation: DocumentationMetrics
    error_handling: ErrorHandlingMetrics
    performance: PerformanceMetrics
    security: SecurityMetrics
    overall_score: float = 0.0
    production_ready: bool = False
    recommendations: List[str] = field(default_factory=list)


class CodeComplexityAnalyzer:
    """Analyzes code complexity metrics"""

    def __init__(self):
        self.complexity_score = 0
        self.nesting_level = 0
        self.max_nesting = 0

    def analyze_file(self, filepath: Path) -> ComplexityMetrics:
        """Analyze complexity of a single Python file"""
        metrics = ComplexityMetrics()

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source)
            metrics.lines_of_code = len(source.splitlines())

            # Count functions and classes
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    metrics.number_of_functions += 1
                    func_lines = self._get_function_lines(node)
                    metrics.max_function_length = max(metrics.max_function_length, func_lines)
                elif isinstance(node, ast.ClassDef):
                    metrics.number_of_classes += 1

            # Calculate cyclomatic complexity
            metrics.cyclomatic_complexity = self._calculate_cyclomatic_complexity(tree)

            # Calculate cognitive complexity
            metrics.cognitive_complexity = self._calculate_cognitive_complexity(tree)

            # Calculate nesting depth
            metrics.nesting_depth = self._calculate_max_nesting(tree)

            # Calculate average function length
            if metrics.number_of_functions > 0:
                metrics.average_function_length = metrics.lines_of_code / metrics.number_of_functions

            # Check for duplicate code
            metrics.duplicate_code_ratio = self._detect_duplicates(source)

        except Exception as e:
            logger.warning(f"Error analyzing complexity for {filepath}: {e}")

        return metrics

    def _calculate_cyclomatic_complexity(self, tree: ast.AST) -> int:
        """Calculate McCabe cyclomatic complexity"""
        complexity = 1  # Base complexity

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1

        return complexity

    def _calculate_cognitive_complexity(self, tree: ast.AST) -> int:
        """Calculate cognitive complexity (simplified version)"""
        complexity = 0
        nesting = 0

        class ComplexityVisitor(ast.NodeVisitor):
            def __init__(self):
                self.complexity = 0
                self.nesting = 0

            def visit_If(self, node):
                self.complexity += 1 + self.nesting
                self.nesting += 1
                self.generic_visit(node)
                self.nesting -= 1

            def visit_For(self, node):
                self.complexity += 1 + self.nesting
                self.nesting += 1
                self.generic_visit(node)
                self.nesting -= 1

            def visit_While(self, node):
                self.complexity += 1 + self.nesting
                self.nesting += 1
                self.generic_visit(node)
                self.nesting -= 1

        visitor = ComplexityVisitor()
        visitor.visit(tree)
        return visitor.complexity

    def _calculate_max_nesting(self, tree: ast.AST) -> int:
        """Calculate maximum nesting depth"""
        class NestingVisitor(ast.NodeVisitor):
            def __init__(self):
                self.current_depth = 0
                self.max_depth = 0

            def visit_If(self, node):
                self.current_depth += 1
                self.max_depth = max(self.max_depth, self.current_depth)
                self.generic_visit(node)
                self.current_depth -= 1

            def visit_For(self, node):
                self.current_depth += 1
                self.max_depth = max(self.max_depth, self.current_depth)
                self.generic_visit(node)
                self.current_depth -= 1

            def visit_While(self, node):
                self.current_depth += 1
                self.max_depth = max(self.max_depth, self.current_depth)
                self.generic_visit(node)
                self.current_depth -= 1

        visitor = NestingVisitor()
        visitor.visit(tree)
        return visitor.max_depth

    def _get_function_lines(self, node: ast.FunctionDef) -> int:
        """Get number of lines in a function"""
        if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
            return node.end_lineno - node.lineno + 1
        return 0

    def _detect_duplicates(self, source: str) -> float:
        """Detect duplicate code blocks (simplified)"""
        lines = source.splitlines()
        line_hashes = {}
        duplicate_lines = 0

        # Simple line-based duplicate detection
        for line in lines:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith('#'):
                if cleaned in line_hashes:
                    duplicate_lines += 1
                else:
                    line_hashes[cleaned] = 1

        if len(lines) > 0:
            return duplicate_lines / len(lines)
        return 0.0


class TestCoverageAnalyzer:
    """Analyzes test coverage metrics"""

    def analyze_coverage(self, project_path: Path) -> CoverageMetrics:
        """Analyze test coverage for a project"""
        metrics = CoverageMetrics()

        try:
            # Try to get coverage data from coverage.py
            coverage_file = project_path / '.coverage'
            if coverage_file.exists():
                metrics = self._parse_coverage_report(project_path)
            else:
                # Fallback to analyzing test files directly
                metrics = self._analyze_test_files(project_path)

        except Exception as e:
            logger.warning(f"Error analyzing coverage: {e}")

        return metrics

    def _parse_coverage_report(self, project_path: Path) -> CoverageMetrics:
        """Parse coverage.py report"""
        metrics = CoverageMetrics()

        try:
            # Run coverage report command
            result = subprocess.run(
                ['coverage', 'report', '--format=json'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                metrics.line_coverage = data.get('totals', {}).get('percent_covered', 0.0)
                metrics.covered_lines = data.get('totals', {}).get('covered_lines', 0)
                metrics.total_lines = data.get('totals', {}).get('num_statements', 0)

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
            pass

        return metrics

    def _analyze_test_files(self, project_path: Path) -> CoverageMetrics:
        """Analyze test files to estimate coverage"""
        metrics = CoverageMetrics()

        test_files = list(project_path.glob('**/test_*.py'))
        test_files.extend(project_path.glob('**/*_test.py'))

        metrics.test_files_count = len(test_files)

        # Count test lines vs code lines
        test_lines = 0
        code_lines = 0

        for test_file in test_files:
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    test_lines += len(f.readlines())
            except:
                pass

        # Count non-test Python files
        for py_file in project_path.glob('**/*.py'):
            if not any(p in str(py_file) for p in ['test_', '_test.py', '__pycache__']):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        code_lines += len(f.readlines())
                except:
                    pass

        if code_lines > 0:
            metrics.test_to_code_ratio = test_lines / code_lines
            # Estimate coverage based on test-to-code ratio
            metrics.line_coverage = min(metrics.test_to_code_ratio * 100, 100.0)

        return metrics


class DocumentationAnalyzer:
    """Analyzes documentation completeness"""

    def analyze_documentation(self, project_path: Path) -> DocumentationMetrics:
        """Analyze documentation metrics for a project"""
        metrics = DocumentationMetrics()

        # Check for standard documentation files
        metrics.readme_exists = (project_path / 'README.md').exists() or \
                               (project_path / 'README.rst').exists() or \
                               (project_path / 'README.txt').exists()

        metrics.api_docs_exists = (project_path / 'docs').exists()
        metrics.changelog_exists = (project_path / 'CHANGELOG.md').exists() or \
                                  (project_path / 'CHANGELOG.rst').exists()

        # Check for examples
        metrics.examples_provided = (project_path / 'examples').exists() or \
                                   (project_path / 'example').exists()

        # Analyze Python files for docstrings
        for py_file in project_path.glob('**/*.py'):
            if '__pycache__' not in str(py_file):
                self._analyze_file_documentation(py_file, metrics)

        # Calculate coverage percentages
        if metrics.total_functions > 0:
            metrics.docstring_coverage = (metrics.functions_with_docstrings /
                                         metrics.total_functions) * 100

        if metrics.total_classes > 0:
            metrics.public_api_documented = (metrics.classes_with_docstrings /
                                            metrics.total_classes) * 100

        return metrics

    def _analyze_file_documentation(self, filepath: Path, metrics: DocumentationMetrics):
        """Analyze documentation in a single file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    metrics.total_functions += 1
                    if ast.get_docstring(node):
                        metrics.functions_with_docstrings += 1

                elif isinstance(node, ast.ClassDef):
                    metrics.total_classes += 1
                    if ast.get_docstring(node):
                        metrics.classes_with_docstrings += 1

            # Count inline comments
            lines = source.splitlines()
            comment_lines = sum(1 for line in lines if '#' in line)
            if len(lines) > 0:
                metrics.inline_comment_ratio = comment_lines / len(lines)

        except Exception as e:
            logger.warning(f"Error analyzing documentation for {filepath}: {e}")


class ErrorHandlingAnalyzer:
    """Analyzes error handling coverage"""

    def analyze_error_handling(self, project_path: Path) -> ErrorHandlingMetrics:
        """Analyze error handling metrics for a project"""
        metrics = ErrorHandlingMetrics()

        total_functions = 0
        functions_with_error_handling = 0

        for py_file in project_path.glob('**/*.py'):
            if '__pycache__' not in str(py_file):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        source = f.read()

                    tree = ast.parse(source)

                    # Check for try/except blocks
                    has_try_except = False
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Try):
                            has_try_except = True
                            functions_with_error_handling += 1

                        elif isinstance(node, ast.FunctionDef):
                            total_functions += 1

                        # Check for logging
                        elif isinstance(node, ast.Import):
                            for alias in node.names:
                                if 'logging' in alias.name:
                                    metrics.error_logging_present = True

                        # Check for custom exceptions
                        elif isinstance(node, ast.ClassDef):
                            for base in node.bases:
                                if hasattr(base, 'id') and 'Exception' in getattr(base, 'id', ''):
                                    metrics.custom_exceptions_defined = True

                    # Check for validation patterns
                    if re.search(r'assert\s+|raise\s+ValueError|raise\s+TypeError', source):
                        metrics.validation_coverage = 50.0  # Simplified

                    # Check for input sanitization
                    if re.search(r'sanitize|escape|clean|validate', source, re.IGNORECASE):
                        metrics.input_sanitization = True

                    # Check for retry logic
                    if re.search(r'retry|@retry|RetryError|max_retries', source, re.IGNORECASE):
                        metrics.retry_logic_present = True

                    # Check for circuit breaker
                    if re.search(r'circuit.?breaker|CircuitBreaker', source, re.IGNORECASE):
                        metrics.circuit_breaker_present = True

                except Exception as e:
                    logger.warning(f"Error analyzing error handling for {py_file}: {e}")

        if total_functions > 0:
            metrics.try_except_coverage = (functions_with_error_handling / total_functions) * 100

        return metrics


class PerformanceBenchmarker:
    """Analyzes performance characteristics"""

    def analyze_performance(self, project_path: Path) -> PerformanceMetrics:
        """Analyze performance metrics for a project"""
        metrics = PerformanceMetrics()

        # Check for performance optimizations in code
        for py_file in project_path.glob('**/*.py'):
            if '__pycache__' not in str(py_file):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        source = f.read()

                    # Check for caching
                    if re.search(r'@cache|@lru_cache|cache\s*=|Cache\(', source):
                        metrics.caching_implemented = True

                    # Check for async operations
                    if re.search(r'async\s+def|await\s+|asyncio', source):
                        metrics.async_operations_used = True

                    # Check for batch processing
                    if re.search(r'batch|chunk|bulk', source, re.IGNORECASE):
                        metrics.batch_processing_used = True

                    # Check for connection pooling
                    if re.search(r'pool|Pool\(|connection_pool|pooling', source, re.IGNORECASE):
                        metrics.connection_pooling = True

                    # Check for database optimization
                    if re.search(r'select_related|prefetch_related|bulk_create|bulk_update', source):
                        metrics.database_query_optimization = True

                except Exception as e:
                    logger.warning(f"Error analyzing performance for {py_file}: {e}")

        # Run simple benchmark if test files exist
        test_files = list(project_path.glob('**/test_*.py'))
        if test_files:
            metrics = self._run_benchmark(project_path, metrics)

        return metrics

    def _run_benchmark(self, project_path: Path, metrics: PerformanceMetrics) -> PerformanceMetrics:
        """Run simple performance benchmark"""
        try:
            # Measure memory usage of importing the module
            import tracemalloc
            tracemalloc.start()

            # Simple timing benchmark
            start_time = time.time()
            # Run a simple test command
            result = subprocess.run(
                ['python', '-c', 'import sys'],
                cwd=project_path,
                capture_output=True,
                timeout=5
            )
            end_time = time.time()

            metrics.average_response_time = (end_time - start_time) * 1000  # Convert to ms
            metrics.p95_response_time = metrics.average_response_time * 1.5  # Estimate
            metrics.p99_response_time = metrics.average_response_time * 2.0  # Estimate

            current, peak = tracemalloc.get_traced_memory()
            metrics.memory_usage_mb = peak / 1024 / 1024
            tracemalloc.stop()

        except Exception as e:
            logger.warning(f"Error running benchmark: {e}")

        return metrics


class SecurityAnalyzer:
    """Analyzes security best practices"""

    def analyze_security(self, project_path: Path) -> SecurityMetrics:
        """Analyze security metrics for a project"""
        metrics = SecurityMetrics()

        for py_file in project_path.glob('**/*.py'):
            if '__pycache__' not in str(py_file):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        source = f.read()

                    # Check for SQL injection vulnerabilities
                    # Look for f-strings with execute, format strings, or string interpolation
                    sql_injection_patterns = [
                        r'execute\s*\(\s*f["\']',  # execute(f"...")
                        r'execute\s*\(\s*["\'].*\.format\(',  # execute("...".format(...))
                        r'cursor\.execute\s*\(\s*f["\']',  # cursor.execute(f"...")
                        r'execute\s*\(\s*["\'].*\{.*\}',  # execute("...{...}")
                        r'f["\'].*SELECT.*["\']',  # f"SELECT ..." anywhere
                        r'["\'].*\{.*\}.*SELECT.*["\']',  # "...{...}...SELECT..."
                    ]
                    if any(re.search(pattern, source, re.IGNORECASE) for pattern in sql_injection_patterns):
                        metrics.sql_injection_safe = False

                    # Check for XSS protection
                    if re.search(r'render_template|render\(|innerHTML', source):
                        if not re.search(r'escape|sanitize|safe', source):
                            metrics.xss_protection = False

                    # Check for authentication
                    if re.search(r'@login_required|authenticate|check_auth|verify_token', source):
                        metrics.authentication_present = True

                    # Check for authorization
                    if re.search(r'@permission_required|check_permission|has_permission|authorize', source):
                        metrics.authorization_present = True

                    # Check for input validation
                    if re.search(r'validate|validator|schema|ValidationError', source):
                        metrics.input_validation = True

                    # Check for output encoding
                    if re.search(r'encode|escape|quote|sanitize', source):
                        metrics.output_encoding = True

                    # Check for secrets in code
                    secret_pattern = r'(password|secret|key|token)\s*=\s*["\'][^"\']{3,}["\']'
                    if re.search(secret_pattern, source, re.IGNORECASE):
                        # Check if it's not just placeholders
                        placeholder_pattern = r'(password|secret|key|token)\s*=\s*["\'](<.*?>|\$\{.*\}|xxx|placeholder|test|example|dummy|env_)["\']'
                        # If we find secrets but they're not ALL placeholders, flag as having secrets
                        all_matches = re.findall(secret_pattern, source, re.IGNORECASE)
                        placeholder_matches = re.findall(placeholder_pattern, source, re.IGNORECASE) 
                        # If we have fewer placeholders than total matches, there are real secrets
                        if len(placeholder_matches) < len(all_matches):
                            metrics.secrets_in_code = True

                    # Check for secure random
                    if re.search(r'secrets\.|SystemRandom|urandom', source):
                        metrics.secure_random_used = True

                    # Check for encryption
                    if re.search(r'encrypt|decrypt|cipher|crypto|hashlib', source, re.IGNORECASE):
                        metrics.encryption_used = True

                    # Check for audit logging
                    if re.search(r'audit|audit_log|security_log|track_action', source, re.IGNORECASE):
                        metrics.audit_logging = True

                    # Check for rate limiting
                    if re.search(r'rate_limit|ratelimit|throttle|RateLimit|@.*limit|limiter', source, re.IGNORECASE):
                        metrics.rate_limiting = True

                    # Check for CSRF protection
                    if re.search(r'csrf|CSRF|csrf_token|csrf_exempt', source):
                        metrics.csrf_protection = True

                except Exception as e:
                    logger.warning(f"Error analyzing security for {py_file}: {e}")

        return metrics


class QualityMetricsAnalyzer:
    """Main quality metrics analyzer coordinating all sub-analyzers"""

    def __init__(self):
        self.complexity_analyzer = CodeComplexityAnalyzer()
        self.coverage_analyzer = TestCoverageAnalyzer()
        self.documentation_analyzer = DocumentationAnalyzer()
        self.error_handling_analyzer = ErrorHandlingAnalyzer()
        self.performance_benchmarker = PerformanceBenchmarker()
        self.security_analyzer = SecurityAnalyzer()

    def analyze_project(self, project_path: str) -> QualityReport:
        """Analyze complete project quality metrics"""
        path = Path(project_path)

        # Collect all metrics
        complexity_metrics = self._aggregate_complexity_metrics(path)
        coverage_metrics = self.coverage_analyzer.analyze_coverage(path)
        documentation_metrics = self.documentation_analyzer.analyze_documentation(path)
        error_handling_metrics = self.error_handling_analyzer.analyze_error_handling(path)
        performance_metrics = self.performance_benchmarker.analyze_performance(path)
        security_metrics = self.security_analyzer.analyze_security(path)

        # Create report
        report = QualityReport(
            complexity=complexity_metrics,
            coverage=coverage_metrics,
            documentation=documentation_metrics,
            error_handling=error_handling_metrics,
            performance=performance_metrics,
            security=security_metrics
        )

        # Calculate overall score
        report.overall_score = self._calculate_overall_score(report)

        # Determine if production ready
        report.production_ready = self._is_production_ready(report)

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        return report

    def _aggregate_complexity_metrics(self, project_path: Path) -> ComplexityMetrics:
        """Aggregate complexity metrics for all Python files"""
        total_metrics = ComplexityMetrics()
        file_count = 0

        for py_file in project_path.glob('**/*.py'):
            if '__pycache__' not in str(py_file):
                file_metrics = self.complexity_analyzer.analyze_file(py_file)

                # Aggregate metrics
                total_metrics.cyclomatic_complexity += file_metrics.cyclomatic_complexity
                total_metrics.cognitive_complexity += file_metrics.cognitive_complexity
                total_metrics.nesting_depth = max(total_metrics.nesting_depth, file_metrics.nesting_depth)
                total_metrics.lines_of_code += file_metrics.lines_of_code
                total_metrics.number_of_functions += file_metrics.number_of_functions
                total_metrics.number_of_classes += file_metrics.number_of_classes
                total_metrics.max_function_length = max(total_metrics.max_function_length, file_metrics.max_function_length)
                total_metrics.duplicate_code_ratio += file_metrics.duplicate_code_ratio

                file_count += 1

        # Calculate averages
        if file_count > 0:
            total_metrics.cyclomatic_complexity //= file_count
            total_metrics.cognitive_complexity //= file_count
            total_metrics.duplicate_code_ratio /= file_count

        if total_metrics.number_of_functions > 0:
            total_metrics.average_function_length = total_metrics.lines_of_code / total_metrics.number_of_functions

        return total_metrics

    def _calculate_overall_score(self, report: QualityReport) -> float:
        """Calculate overall quality score (0-100)"""
        scores = []

        # Complexity score (lower is better)
        complexity_score = 100
        if report.complexity.cyclomatic_complexity > 10:
            complexity_score -= (report.complexity.cyclomatic_complexity - 10) * 2
        if report.complexity.cognitive_complexity > 15:
            complexity_score -= (report.complexity.cognitive_complexity - 15) * 2
        if report.complexity.nesting_depth > 4:
            complexity_score -= (report.complexity.nesting_depth - 4) * 5
        scores.append(max(0, complexity_score))

        # Coverage score
        scores.append(report.coverage.line_coverage)

        # Documentation score
        scores.append(report.documentation.docstring_coverage)

        # Error handling score
        scores.append(report.error_handling.try_except_coverage)

        # Performance score
        perf_score = 0
        if report.performance.caching_implemented:
            perf_score += 20
        if report.performance.async_operations_used:
            perf_score += 20
        if report.performance.connection_pooling:
            perf_score += 20
        if report.performance.database_query_optimization:
            perf_score += 20
        if report.performance.batch_processing_used:
            perf_score += 20
        scores.append(perf_score)

        # Security score
        sec_score = 100
        if report.security.secrets_in_code:
            sec_score -= 30
        if not report.security.sql_injection_safe:
            sec_score -= 20
        if not report.security.xss_protection:
            sec_score -= 20
        if not report.security.input_validation:
            sec_score -= 15
        if not report.security.authentication_present:
            sec_score -= 15
        scores.append(max(0, sec_score))

        # Calculate weighted average
        weights = [0.15, 0.25, 0.15, 0.15, 0.15, 0.15]  # Adjust weights as needed
        weighted_score = sum(s * w for s, w in zip(scores, weights, strict=False))

        return round(weighted_score, 2)

    def _is_production_ready(self, report: QualityReport) -> bool:
        """Determine if code is production ready"""
        # Critical requirements
        if report.security.secrets_in_code:
            return False
        if not report.security.sql_injection_safe:
            return False
        if report.coverage.line_coverage < 60:
            return False
        if report.complexity.cyclomatic_complexity > 20:
            return False
        if report.error_handling.try_except_coverage < 50:
            return False
        if report.overall_score < 70:
            return False

        return True

    def _generate_recommendations(self, report: QualityReport) -> List[str]:
        """Generate improvement recommendations"""
        recommendations = []

        # Complexity recommendations
        if report.complexity.cyclomatic_complexity > 10:
            recommendations.append(f"Reduce cyclomatic complexity (current: {report.complexity.cyclomatic_complexity}, target: <10)")
        if report.complexity.nesting_depth > 4:
            recommendations.append(f"Reduce nesting depth (current: {report.complexity.nesting_depth}, target: <4)")
        if report.complexity.duplicate_code_ratio > 0.1:
            recommendations.append(f"Remove duplicate code (current: {report.complexity.duplicate_code_ratio:.1%})")

        # Coverage recommendations
        if report.coverage.line_coverage < 80:
            recommendations.append(f"Increase test coverage (current: {report.coverage.line_coverage:.1f}%, target: >80%)")
        if report.coverage.test_to_code_ratio < 1.0:
            recommendations.append("Write more comprehensive tests")

        # Documentation recommendations
        if report.documentation.docstring_coverage < 80:
            recommendations.append(f"Add docstrings to functions (current: {report.documentation.docstring_coverage:.1f}%)")
        if not report.documentation.readme_exists:
            recommendations.append("Create README documentation")

        # Error handling recommendations
        if report.error_handling.try_except_coverage < 70:
            recommendations.append("Add more error handling")
        if not report.error_handling.error_logging_present:
            recommendations.append("Implement error logging")
        if not report.error_handling.retry_logic_present:
            recommendations.append("Consider adding retry logic for network operations")

        # Performance recommendations
        if not report.performance.caching_implemented:
            recommendations.append("Implement caching for frequently accessed data")
        if not report.performance.async_operations_used:
            recommendations.append("Consider using async operations for I/O")
        if not report.performance.connection_pooling:
            recommendations.append("Implement connection pooling for database/API calls")

        # Security recommendations
        if report.security.secrets_in_code:
            recommendations.append("CRITICAL: Remove hardcoded secrets from code")
        if not report.security.input_validation:
            recommendations.append("Add input validation")
        if not report.security.authentication_present:
            recommendations.append("Implement authentication mechanism")
        if not report.security.rate_limiting:
            recommendations.append("Add rate limiting to prevent abuse")

        return recommendations


def analyze_code_quality(project_path: str) -> Dict[str, Any]:
    """Main entry point for quality analysis"""
    analyzer = QualityMetricsAnalyzer()
    report = analyzer.analyze_project(project_path)

    return {
        'overall_score': report.overall_score,
        'production_ready': report.production_ready,
        'complexity': {
            'cyclomatic': report.complexity.cyclomatic_complexity,
            'cognitive': report.complexity.cognitive_complexity,
            'nesting_depth': report.complexity.nesting_depth,
            'lines_of_code': report.complexity.lines_of_code
        },
        'coverage': {
            'line_coverage': report.coverage.line_coverage,
            'test_files': report.coverage.test_files_count,
            'test_to_code_ratio': report.coverage.test_to_code_ratio
        },
        'documentation': {
            'docstring_coverage': report.documentation.docstring_coverage,
            'readme_exists': report.documentation.readme_exists,
            'api_docs_exists': report.documentation.api_docs_exists
        },
        'error_handling': {
            'try_except_coverage': report.error_handling.try_except_coverage,
            'error_logging': report.error_handling.error_logging_present,
            'retry_logic': report.error_handling.retry_logic_present
        },
        'performance': {
            'caching': report.performance.caching_implemented,
            'async_operations': report.performance.async_operations_used,
            'connection_pooling': report.performance.connection_pooling
        },
        'security': {
            'sql_injection_safe': report.security.sql_injection_safe,
            'xss_protection': report.security.xss_protection,
            'secrets_in_code': report.security.secrets_in_code,
            'input_validation': report.security.input_validation
        },
        'recommendations': report.recommendations
    }


# Integration with verification system
def get_quality_metrics_for_verification(project_path: str,
                                        strict_mode: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """Get quality metrics for verification system integration
    
    Args:
        project_path: Path to project to analyze
        strict_mode: If True, apply stricter thresholds
        
    Returns:
        Tuple of (pass/fail, detailed metrics)

    """
    metrics = analyze_code_quality(project_path)

    # Apply strict mode thresholds if requested
    if strict_mode:
        passing = (
            metrics['overall_score'] >= 80 and
            metrics['coverage']['line_coverage'] >= 80 and
            metrics['complexity']['cyclomatic'] <= 10 and
            not metrics['security']['secrets_in_code']
        )
    else:
        passing = metrics['production_ready']

    return passing, metrics
