"""Unit tests for quality metrics module"""

import ast
import tempfile
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch, MagicMock
import subprocess

from hydra.metrics.quality_metrics import (
    QualityMetricsAnalyzer,
    CodeComplexityAnalyzer,
    TestCoverageAnalyzer,
    DocumentationAnalyzer,
    ErrorHandlingAnalyzer,
    PerformanceBenchmarker,
    SecurityAnalyzer,
    ComplexityMetrics,
    CoverageMetrics,
    DocumentationMetrics,
    ErrorHandlingMetrics,
    PerformanceMetrics,
    SecurityMetrics,
    QualityReport,
    analyze_code_quality,
    get_quality_metrics_for_verification
)


class TestCodeComplexityAnalyzer(TestCase):
    """Test code complexity analysis"""
    
    def setUp(self):
        self.analyzer = CodeComplexityAnalyzer()
        self.temp_dir = tempfile.mkdtemp()
        
    def test_simple_function_complexity(self):
        """Test complexity analysis of simple function"""
        code = """
def simple_function(x):
    return x * 2
"""
        file_path = Path(self.temp_dir) / "simple.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_file(file_path)
        
        self.assertEqual(metrics.number_of_functions, 1)
        self.assertEqual(metrics.number_of_classes, 0)
        self.assertEqual(metrics.cyclomatic_complexity, 1)
        self.assertGreater(metrics.lines_of_code, 0)
        
    def test_complex_function_with_conditions(self):
        """Test complexity with conditional statements"""
        code = """
def complex_function(x, y):
    if x > 10:
        if y > 5:
            return x + y
        else:
            return x - y
    elif x < 0:
        return -x
    else:
        for i in range(10):
            if i % 2 == 0:
                x += i
        return x
"""
        file_path = Path(self.temp_dir) / "complex.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_file(file_path)
        
        self.assertEqual(metrics.number_of_functions, 1)
        self.assertGreater(metrics.cyclomatic_complexity, 5)
        self.assertGreater(metrics.cognitive_complexity, 5)
        self.assertGreater(metrics.nesting_depth, 2)
        
    def test_class_analysis(self):
        """Test analysis of classes"""
        code = """
class MyClass:
    def __init__(self):
        self.value = 0
    
    def method1(self):
        return self.value
    
    def method2(self, x):
        if x > 0:
            self.value = x
"""
        file_path = Path(self.temp_dir) / "class.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_file(file_path)
        
        self.assertEqual(metrics.number_of_classes, 1)
        self.assertEqual(metrics.number_of_functions, 3)
        
    def test_duplicate_code_detection(self):
        """Test duplicate code detection"""
        code = """
def func1():
    x = 10
    y = 20
    return x + y
    
def func2():
    x = 10
    y = 20
    return x + y
"""
        file_path = Path(self.temp_dir) / "duplicate.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_file(file_path)
        
        self.assertGreater(metrics.duplicate_code_ratio, 0.0)
        
    def test_max_nesting_depth(self):
        """Test maximum nesting depth calculation"""
        code = """
def deeply_nested():
    if True:
        for i in range(10):
            while i > 0:
                if i % 2:
                    return i
"""
        file_path = Path(self.temp_dir) / "nested.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_file(file_path)
        
        self.assertEqual(metrics.nesting_depth, 4)


class TestTestCoverageAnalyzer(TestCase):
    """Test coverage analysis"""
    
    def setUp(self):
        self.analyzer = TestCoverageAnalyzer()
        self.temp_dir = tempfile.mkdtemp()
        
    def test_analyze_test_files(self):
        """Test analysis of test files"""
        # Create test file
        test_file = Path(self.temp_dir) / "test_example.py"
        test_file.write_text("def test_something(): pass")
        
        # Create code file
        code_file = Path(self.temp_dir) / "example.py"
        code_file.write_text("def function(): pass")
        
        metrics = self.analyzer._analyze_test_files(Path(self.temp_dir))
        
        self.assertEqual(metrics.test_files_count, 1)
        self.assertGreater(metrics.test_to_code_ratio, 0)
        
    @patch('subprocess.run')
    def test_parse_coverage_report(self, mock_run):
        """Test parsing coverage.py report"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            'totals': {
                'percent_covered': 85.5,
                'covered_lines': 850,
                'num_statements': 1000
            }
        })
        mock_run.return_value = mock_result
        
        # Create .coverage file
        coverage_file = Path(self.temp_dir) / ".coverage"
        coverage_file.touch()
        
        metrics = self.analyzer.analyze_coverage(Path(self.temp_dir))
        
        self.assertEqual(metrics.line_coverage, 85.5)
        self.assertEqual(metrics.covered_lines, 850)
        self.assertEqual(metrics.total_lines, 1000)
        
    def test_no_coverage_file(self):
        """Test when no coverage file exists"""
        metrics = self.analyzer.analyze_coverage(Path(self.temp_dir))
        
        self.assertEqual(metrics.test_files_count, 0)
        self.assertEqual(metrics.line_coverage, 0.0)


class TestDocumentationAnalyzer(TestCase):
    """Test documentation analysis"""
    
    def setUp(self):
        self.analyzer = DocumentationAnalyzer()
        self.temp_dir = tempfile.mkdtemp()
        
    def test_readme_detection(self):
        """Test README file detection"""
        # Create README
        readme = Path(self.temp_dir) / "README.md"
        readme.write_text("# Project README")
        
        metrics = self.analyzer.analyze_documentation(Path(self.temp_dir))
        
        self.assertTrue(metrics.readme_exists)
        
    def test_docstring_coverage(self):
        """Test docstring coverage calculation"""
        code = '''
def documented_function():
    """This function has a docstring"""
    pass
    
def undocumented_function():
    pass
    
class DocumentedClass:
    """This class has a docstring"""
    pass
    
class UndocumentedClass:
    pass
'''
        file_path = Path(self.temp_dir) / "module.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_documentation(Path(self.temp_dir))
        
        self.assertEqual(metrics.total_functions, 2)
        self.assertEqual(metrics.functions_with_docstrings, 1)
        self.assertEqual(metrics.total_classes, 2)
        self.assertEqual(metrics.classes_with_docstrings, 1)
        self.assertEqual(metrics.docstring_coverage, 50.0)
        self.assertEqual(metrics.public_api_documented, 50.0)
        
    def test_examples_and_docs_detection(self):
        """Test detection of examples and docs directories"""
        # Create directories
        (Path(self.temp_dir) / "examples").mkdir()
        (Path(self.temp_dir) / "docs").mkdir()
        
        metrics = self.analyzer.analyze_documentation(Path(self.temp_dir))
        
        self.assertTrue(metrics.examples_provided)
        self.assertTrue(metrics.api_docs_exists)
        
    def test_inline_comments(self):
        """Test inline comment ratio calculation"""
        code = """
# Module comment
def function():
    x = 10  # Inline comment
    y = 20
    return x + y  # Return sum
"""
        file_path = Path(self.temp_dir) / "commented.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_documentation(Path(self.temp_dir))
        
        self.assertGreater(metrics.inline_comment_ratio, 0)


class TestErrorHandlingAnalyzer(TestCase):
    """Test error handling analysis"""
    
    def setUp(self):
        self.analyzer = ErrorHandlingAnalyzer()
        self.temp_dir = tempfile.mkdtemp()
        
    def test_try_except_detection(self):
        """Test detection of try/except blocks"""
        code = """
def safe_function():
    try:
        result = risky_operation()
    except Exception as e:
        logger.error(f"Error: {e}")
        return None
    return result
    
def unsafe_function():
    return risky_operation()
"""
        file_path = Path(self.temp_dir) / "error_handling.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_error_handling(Path(self.temp_dir))
        
        self.assertGreater(metrics.try_except_coverage, 0)
        
    def test_logging_detection(self):
        """Test detection of logging"""
        code = """
import logging

logger = logging.getLogger(__name__)

def function():
    logger.info("Processing")
"""
        file_path = Path(self.temp_dir) / "logging.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_error_handling(Path(self.temp_dir))
        
        self.assertTrue(metrics.error_logging_present)
        
    def test_custom_exception_detection(self):
        """Test detection of custom exceptions"""
        code = """
class CustomError(Exception):
    pass
    
class ValidationError(ValueError):
    pass
"""
        file_path = Path(self.temp_dir) / "exceptions.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_error_handling(Path(self.temp_dir))
        
        self.assertTrue(metrics.custom_exceptions_defined)
        
    def test_validation_detection(self):
        """Test detection of validation logic"""
        code = """
def validate_input(value):
    assert value > 0, "Value must be positive"
    if not isinstance(value, int):
        raise TypeError("Value must be integer")
    return value
"""
        file_path = Path(self.temp_dir) / "validation.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_error_handling(Path(self.temp_dir))
        
        self.assertGreater(metrics.validation_coverage, 0)
        
    def test_retry_and_circuit_breaker(self):
        """Test detection of retry and circuit breaker patterns"""
        code = """
from retrying import retry

@retry(max_retries=3)
def retryable_function():
    pass
    
class CircuitBreaker:
    def __init__(self):
        self.failures = 0
"""
        file_path = Path(self.temp_dir) / "resilience.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_error_handling(Path(self.temp_dir))
        
        self.assertTrue(metrics.retry_logic_present)
        self.assertTrue(metrics.circuit_breaker_present)


class TestPerformanceBenchmarker(TestCase):
    """Test performance benchmarking"""
    
    def setUp(self):
        self.benchmarker = PerformanceBenchmarker()
        self.temp_dir = tempfile.mkdtemp()
        
    def test_caching_detection(self):
        """Test detection of caching implementations"""
        code = """
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_function(x):
    return expensive_operation(x)
    
cache = {}
def manual_cache(key):
    if key not in cache:
        cache[key] = compute(key)
    return cache[key]
"""
        file_path = Path(self.temp_dir) / "caching.py"
        file_path.write_text(code)
        
        metrics = self.benchmarker.analyze_performance(Path(self.temp_dir))
        
        self.assertTrue(metrics.caching_implemented)
        
    def test_async_detection(self):
        """Test detection of async operations"""
        code = """
import asyncio

async def async_function():
    await asyncio.sleep(1)
    return "result"
    
async def main():
    result = await async_function()
    print(result)
"""
        file_path = Path(self.temp_dir) / "async.py"
        file_path.write_text(code)
        
        metrics = self.benchmarker.analyze_performance(Path(self.temp_dir))
        
        self.assertTrue(metrics.async_operations_used)
        
    def test_batch_processing_detection(self):
        """Test detection of batch processing"""
        code = """
def process_batch(items):
    batch_size = 100
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        process_chunk(batch)
        
def bulk_insert(records):
    db.bulk_create(records)
"""
        file_path = Path(self.temp_dir) / "batch.py"
        file_path.write_text(code)
        
        metrics = self.benchmarker.analyze_performance(Path(self.temp_dir))
        
        self.assertTrue(metrics.batch_processing_used)
        
    def test_connection_pooling_detection(self):
        """Test detection of connection pooling"""
        code = """
from sqlalchemy.pool import QueuePool

connection_pool = QueuePool(
    create_connection,
    max_overflow=10,
    pool_size=5
)

class ConnectionPool:
    def __init__(self):
        self.pool = []
"""
        file_path = Path(self.temp_dir) / "pooling.py"
        file_path.write_text(code)
        
        metrics = self.benchmarker.analyze_performance(Path(self.temp_dir))
        
        self.assertTrue(metrics.connection_pooling)
        
    @patch('subprocess.run')
    def test_benchmark_execution(self, mock_run):
        """Test benchmark execution"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        # Create a test file
        test_file = Path(self.temp_dir) / "test_bench.py"
        test_file.write_text("def test(): pass")
        
        with patch('time.time', side_effect=[0, 0.1]):
            metrics = self.benchmarker.analyze_performance(Path(self.temp_dir))
            
        self.assertGreater(metrics.average_response_time, 0)
        self.assertGreater(metrics.p95_response_time, metrics.average_response_time)
        self.assertGreater(metrics.p99_response_time, metrics.p95_response_time)


class TestSecurityAnalyzer(TestCase):
    """Test security analysis"""
    
    def setUp(self):
        self.analyzer = SecurityAnalyzer()
        self.temp_dir = tempfile.mkdtemp()
        
    def test_sql_injection_detection(self):
        """Test detection of SQL injection vulnerabilities"""
        code = """
def unsafe_query(user_input):
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    cursor.execute(query)
    
def safe_query(user_input):
    query = "SELECT * FROM users WHERE name = ?"
    cursor.execute(query, (user_input,))
"""
        file_path = Path(self.temp_dir) / "sql.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_security(Path(self.temp_dir))
        
        self.assertFalse(metrics.sql_injection_safe)
        
    def test_xss_detection(self):
        """Test detection of XSS vulnerabilities"""
        code = """
def render_unsafe(user_input):
    return render_template('page.html', content=user_input)
    
def render_safe(user_input):
    from markupsafe import escape
    return render_template('page.html', content=escape(user_input))
"""
        file_path = Path(self.temp_dir) / "xss.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_security(Path(self.temp_dir))
        
        # Should detect escape function
        self.assertTrue(metrics.output_encoding)
        
    def test_authentication_detection(self):
        """Test detection of authentication"""
        code = """
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated
    
@login_required
def protected_view():
    return "Protected content"
"""
        file_path = Path(self.temp_dir) / "auth.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_security(Path(self.temp_dir))
        
        self.assertTrue(metrics.authentication_present)
        
    def test_secrets_detection(self):
        """Test detection of hardcoded secrets"""
        code = """
API_KEY = "sk-1234567890abcdef"
PASSWORD = "admin123"
SECRET = "placeholder"  # This should be ignored
TOKEN = "${ENV_TOKEN}"  # This should be ignored
"""
        file_path = Path(self.temp_dir) / "secrets.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_security(Path(self.temp_dir))
        
        self.assertTrue(metrics.secrets_in_code)
        
    def test_encryption_detection(self):
        """Test detection of encryption usage"""
        code = """
from cryptography.fernet import Fernet
import hashlib

def encrypt_data(data, key):
    f = Fernet(key)
    return f.encrypt(data.encode())
    
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()
"""
        file_path = Path(self.temp_dir) / "crypto.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_security(Path(self.temp_dir))
        
        self.assertTrue(metrics.encryption_used)
        
    def test_rate_limiting_detection(self):
        """Test detection of rate limiting"""
        code = """
from flask_limiter import Limiter

limiter = Limiter(
    app,
    key_func=lambda: get_remote_address(),
    default_limits=["100 per hour"]
)

@app.route('/api')
@limiter.limit("10 per minute")
def api_endpoint():
    return jsonify({"status": "ok"})
"""
        file_path = Path(self.temp_dir) / "rate_limit.py"
        file_path.write_text(code)
        
        metrics = self.analyzer.analyze_security(Path(self.temp_dir))
        
        self.assertTrue(metrics.rate_limiting)


class TestQualityMetricsAnalyzer(TestCase):
    """Test main quality metrics analyzer"""
    
    def setUp(self):
        self.analyzer = QualityMetricsAnalyzer()
        self.temp_dir = tempfile.mkdtemp()
        
    def test_complete_analysis(self):
        """Test complete project analysis"""
        # Create sample project structure
        code = """
def example_function(x):
    \"\"\"Example function with docstring\"\"\"
    try:
        if x > 0:
            return x * 2
        else:
            return 0
    except Exception as e:
        print(f"Error: {e}")
        return None
"""
        file_path = Path(self.temp_dir) / "example.py"
        file_path.write_text(code)
        
        # Create test file
        test_code = """
def test_example():
    assert example_function(5) == 10
"""
        test_path = Path(self.temp_dir) / "test_example.py"
        test_path.write_text(test_code)
        
        # Create README
        readme = Path(self.temp_dir) / "README.md"
        readme.write_text("# Example Project")
        
        report = self.analyzer.analyze_project(str(self.temp_dir))
        
        self.assertIsInstance(report, QualityReport)
        self.assertIsInstance(report.complexity, ComplexityMetrics)
        self.assertIsInstance(report.coverage, CoverageMetrics)
        self.assertIsInstance(report.documentation, DocumentationMetrics)
        self.assertIsInstance(report.error_handling, ErrorHandlingMetrics)
        self.assertIsInstance(report.performance, PerformanceMetrics)
        self.assertIsInstance(report.security, SecurityMetrics)
        self.assertIsInstance(report.overall_score, float)
        self.assertIsInstance(report.production_ready, bool)
        self.assertIsInstance(report.recommendations, list)
        
    def test_overall_score_calculation(self):
        """Test overall score calculation"""
        report = QualityReport(
            complexity=ComplexityMetrics(cyclomatic_complexity=5),
            coverage=CoverageMetrics(line_coverage=80),
            documentation=DocumentationMetrics(docstring_coverage=90),
            error_handling=ErrorHandlingMetrics(try_except_coverage=70),
            performance=PerformanceMetrics(caching_implemented=True, async_operations_used=True),
            security=SecurityMetrics(sql_injection_safe=True, input_validation=True)
        )
        
        score = self.analyzer._calculate_overall_score(report)
        
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)
        
    def test_production_readiness_check(self):
        """Test production readiness determination"""
        # Not production ready due to low coverage (even in test mode)
        report = QualityReport(
            complexity=ComplexityMetrics(cyclomatic_complexity=5),
            coverage=CoverageMetrics(line_coverage=20),  # Below test mode threshold of 30
            documentation=DocumentationMetrics(),
            error_handling=ErrorHandlingMetrics(try_except_coverage=60),
            performance=PerformanceMetrics(),
            security=SecurityMetrics(sql_injection_safe=True)
        )
        report.overall_score = 75
        
        is_ready = self.analyzer._is_production_ready(report)
        
        self.assertFalse(is_ready)
        
        # Production ready
        report.coverage.line_coverage = 80
        is_ready = self.analyzer._is_production_ready(report)
        
        self.assertTrue(is_ready)
        
    def test_recommendations_generation(self):
        """Test generation of recommendations"""
        report = QualityReport(
            complexity=ComplexityMetrics(cyclomatic_complexity=15, nesting_depth=6),
            coverage=CoverageMetrics(line_coverage=50),
            documentation=DocumentationMetrics(docstring_coverage=40, readme_exists=False),
            error_handling=ErrorHandlingMetrics(try_except_coverage=30),
            performance=PerformanceMetrics(caching_implemented=False),
            security=SecurityMetrics(secrets_in_code=True, input_validation=False)
        )
        
        recommendations = self.analyzer._generate_recommendations(report)
        
        self.assertGreater(len(recommendations), 0)
        self.assertTrue(any("complexity" in r.lower() for r in recommendations))
        self.assertTrue(any("coverage" in r.lower() for r in recommendations))
        self.assertTrue(any("secret" in r.lower() for r in recommendations))


class TestIntegrationFunctions(TestCase):
    """Test integration functions"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def test_analyze_code_quality(self):
        """Test main entry point function"""
        # Create minimal project
        code = "def test(): pass"
        file_path = Path(self.temp_dir) / "test.py"
        file_path.write_text(code)
        
        result = analyze_code_quality(str(self.temp_dir))
        
        self.assertIn('overall_score', result)
        self.assertIn('production_ready', result)
        self.assertIn('complexity', result)
        self.assertIn('coverage', result)
        self.assertIn('documentation', result)
        self.assertIn('error_handling', result)
        self.assertIn('performance', result)
        self.assertIn('security', result)
        self.assertIn('recommendations', result)
        
    def test_get_quality_metrics_for_verification(self):
        """Test verification system integration"""
        # Create sample project
        code = """
def function():
    try:
        return "result"
    except:
        return None
"""
        file_path = Path(self.temp_dir) / "module.py"
        file_path.write_text(code)
        
        # Test normal mode
        passing, metrics = get_quality_metrics_for_verification(str(self.temp_dir))
        
        self.assertIsInstance(passing, bool)
        self.assertIsInstance(metrics, dict)
        
        # Test strict mode
        passing_strict, metrics_strict = get_quality_metrics_for_verification(
            str(self.temp_dir), 
            strict_mode=True
        )
        
        self.assertIsInstance(passing_strict, bool)
        self.assertIsInstance(metrics_strict, dict)


class TestEdgeCases(TestCase):
    """Test edge cases and error handling"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def test_empty_project(self):
        """Test analysis of empty project"""
        analyzer = QualityMetricsAnalyzer()
        report = analyzer.analyze_project(str(self.temp_dir))
        
        self.assertEqual(report.complexity.lines_of_code, 0)
        self.assertEqual(report.coverage.test_files_count, 0)
        
    def test_invalid_python_file(self):
        """Test handling of invalid Python files"""
        code = "This is not valid Python code {{"
        file_path = Path(self.temp_dir) / "invalid.py"
        file_path.write_text(code)
        
        analyzer = CodeComplexityAnalyzer()
        metrics = analyzer.analyze_file(file_path)
        
        # Should handle gracefully
        self.assertEqual(metrics.number_of_functions, 0)
        
    def test_non_existent_path(self):
        """Test handling of non-existent paths"""
        analyzer = QualityMetricsAnalyzer()
        report = analyzer.analyze_project("/non/existent/path")
        
        # Should return empty metrics
        self.assertEqual(report.complexity.lines_of_code, 0)
        
    def test_unicode_in_files(self):
        """Test handling of Unicode characters"""
        code = """
def función():
    \"\"\"Function with émojis 😀\"\"\"
    return "Hello 世界"
"""
        file_path = Path(self.temp_dir) / "unicode.py"
        file_path.write_text(code, encoding='utf-8')
        
        analyzer = DocumentationAnalyzer()
        metrics = analyzer.analyze_documentation(Path(self.temp_dir))
        
        self.assertEqual(metrics.functions_with_docstrings, 1)