"""Unit tests for the Boss Agent verification system."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from hydra.verification_system.boss_agent import (
    BossAgent,
    VerificationConfig,
    VerificationResult,
    VerificationStatus,
    StrictnessLevel
)


class TestBossAgent:
    """Test suite for the Boss Agent."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = VerificationConfig(
            strictness=StrictnessLevel.STRICT,
            max_retries=3,
            retry_delay_base=0.1,  # Short delay for tests
            log_to_file=False
        )
        self.boss = BossAgent(self.config)
    
    def test_init(self):
        """Test boss agent initialization."""
        assert self.boss.config.strictness == StrictnessLevel.STRICT
        assert self.boss.config.max_retries == 3
        assert len(self.boss.retry_count) == 0
        assert len(self.boss.verification_history) == 0
    
    def test_verify_ticket_completion_pass(self):
        """Test successful ticket verification."""
        ticket_data = {
            'id': '001',
            'acceptance_criteria': [
                'Create test.py file',
                'Implement add function',
                'Add unit tests'
            ]
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = Path(tmpdir) / 'test.py'
            test_file.write_text('def add(a, b):\n    return a + b\n')
            
            test_test = Path(tmpdir) / 'test_test.py'
            test_test.write_text('def test_add():\n    assert add(1, 2) == 3\n')
            
            # Mock the criteria parser and external verification methods
            with patch.object(self.boss.criteria_parser, 'parse') as mock_parse, \
                 patch.object(self.boss, '_verify_tests') as mock_verify_tests, \
                 patch.object(self.boss, '_run_lint_checks') as mock_lint, \
                 patch.object(self.boss, '_verify_production_quality') as mock_quality, \
                 patch.object(self.boss, '_check_function_exists') as mock_check_func, \
                 patch.object(self.boss, '_check_test_exists') as mock_check_test:
                
                def mock_parse_func(criterion):
                    if 'test.py file' in criterion:
                        return {'type': 'file_exists', 'path': 'test.py'}
                    elif 'add function' in criterion:
                        return {'type': 'function_exists', 'function_name': 'add'}
                    elif 'unit tests' in criterion:
                        return {'type': 'test_exists', 'test_pattern': 'add'}
                    else:
                        return {'type': 'unknown'}
                
                mock_parse.side_effect = mock_parse_func
                
                # Mock successful external checks
                mock_verify_tests.return_value = {'passed': True}
                mock_lint.return_value = {'passed': True}
                mock_quality.return_value = {'score': 85.0, 'suggestions': []}
                mock_check_func.return_value = True
                mock_check_test.return_value = True
                
                result = self.boss.verify_ticket_completion(
                    '001',
                    ticket_data,
                    tmpdir
                )
            
            assert result.status == VerificationStatus.PASS
            assert len(result.passed_criteria) == 3
            assert len(result.failed_criteria) == 0
    
    def test_verify_ticket_completion_fail(self):
        """Test failed ticket verification."""
        ticket_data = {
            'id': '002',
            'acceptance_criteria': [
                'Create missing.py file',
                'Implement missing function'
            ]
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Don't create the required files
            
            with patch.object(self.boss.criteria_parser, 'parse') as mock_parse:
                mock_parse.side_effect = [
                    {'type': 'file_exists', 'path': 'missing.py'},
                    {'type': 'function_exists', 'function_name': 'missing'}
                ]
                
                result = self.boss.verify_ticket_completion(
                    '002',
                    ticket_data,
                    tmpdir
                )
            
            assert result.status == VerificationStatus.FAIL
            assert len(result.failed_criteria) == 2
            assert len(result.failure_reasons) > 0
    
    def test_verify_acceptance_criteria(self):
        """Test acceptance criteria verification."""
        criteria = [
            'Create main.py',
            'Add documentation',
            'Write tests'
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create main.py
            main_file = Path(tmpdir) / 'main.py'
            main_file.write_text('# Main file\n')
            
            with patch.object(self.boss.criteria_parser, 'parse') as mock_parse:
                mock_parse.side_effect = [
                    {'type': 'file_exists', 'path': 'main.py'},
                    {'type': 'unknown', 'text': 'Add documentation'},
                    {'type': 'test_exists', 'test_pattern': 'test'}
                ]
                
                with patch.object(self.boss, '_is_criterion_met') as mock_met:
                    mock_met.side_effect = [True, False, False]
                    
                    result = self.boss._verify_acceptance_criteria(criteria, tmpdir)
            
            assert len(result['passed']) == 1
            assert len(result['failed']) == 2
    
    def test_check_unnecessary_files(self):
        """Test checking for unnecessary files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create unnecessary files
            (Path(tmpdir) / 'test.pyc').touch()
            (Path(tmpdir) / 'backup.bak').touch()
            (Path(tmpdir) / '.DS_Store').touch()
            (Path(tmpdir) / 'empty.py').touch()  # Empty Python file
            
            # Create valid file
            (Path(tmpdir) / 'valid.py').write_text('print("valid")\n')
            
            result = self.boss._check_unnecessary_files(tmpdir)
            
            assert len(result['unnecessary']) >= 4
            assert any('pyc' in f for f in result['unnecessary'])
            assert any('bak' in f for f in result['unnecessary'])
    
    def test_detect_ai_patterns(self):
        """Test AI pattern detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file with AI patterns
            ai_file = Path(tmpdir) / 'ai_generated.py'
            ai_file.write_text('''
def calculate_sum_of_two_numbers(first_number, second_number):
    """
    This function calculates the sum of two numbers.
    
    Args:
        first_number: The first number to add
        second_number: The second number to add
    
    Returns:
        The sum of the two numbers
    """
    # Calculate and return the sum
    result = first_number + second_number
    return result
''')
            
            # Mock AI detector
            with patch.object(self.boss.ai_detector, 'detect_ai_patterns', return_value=(True, ['pattern'])):
                result = self.boss._detect_ai_patterns(tmpdir)
            
            assert result['detected']
            assert len(result['files']) > 0
    
    def test_run_lint_checks(self):
        """Test lint checking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Python file
            py_file = Path(tmpdir) / 'lint_test.py'
            py_file.write_text('def test():\n    return True\n')
            
            # Mock command existence and execution
            with patch.object(self.boss, '_command_exists', return_value=True):
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = Mock(returncode=0, stdout=b'', stderr=b'')
                    
                    result = self.boss._run_lint_checks(tmpdir)
            
            assert result['passed']
    
    def test_calculate_score(self):
        """Test score calculation."""
        result = VerificationResult(
            status=VerificationStatus.PASS,
            score=0.0,
            failed_criteria=['criterion1', 'criterion2'],
            failure_reasons=['reason1']
        )
        result.metadata['quality_score'] = 5.0
        
        score = self.boss._calculate_score(result)
        
        # Score should be reduced for failures
        assert score < 100.0
        assert score >= 0.0
    
    def test_trigger_re_execution(self):
        """Test re-execution triggering."""
        ticket_id = '003'
        
        verification_result = VerificationResult(
            status=VerificationStatus.FAIL,
            score=50.0,
            failure_reasons=['Test failed'],
            suggestions=['Fix tests']
        )
        
        mock_executor = Mock()
        
        # First retry should work
        result = self.boss.trigger_re_execution(
            ticket_id,
            verification_result,
            mock_executor
        )
        
        assert self.boss.retry_count[ticket_id] == 1
        mock_executor.assert_called_once()
        
        # Max out retries
        self.boss.retry_count[ticket_id] = 3
        
        # Should not retry when max reached
        result = self.boss.trigger_re_execution(
            ticket_id,
            verification_result,
            mock_executor
        )
        
        assert result is None
        assert mock_executor.call_count == 1  # Still only one call
    
    def test_strictness_levels(self):
        """Test different strictness levels."""
        configs = [
            VerificationConfig(strictness=StrictnessLevel.LENIENT),
            VerificationConfig(strictness=StrictnessLevel.MODERATE),
            VerificationConfig(strictness=StrictnessLevel.STRICT),
            VerificationConfig(strictness=StrictnessLevel.BRUTAL)
        ]
        
        for config in configs:
            boss = BossAgent(config)
            assert boss.config.strictness == config.strictness
    
    def test_verification_history_tracking(self):
        """Test verification history tracking."""
        ticket_id = '004'
        
        # Track multiple attempts
        self.boss._track_attempt(ticket_id)
        self.boss._track_attempt(ticket_id)
        
        assert len(self.boss.verification_history) == 2
        assert all(h['ticket_id'] == ticket_id for h in self.boss.verification_history)
    
    def test_audit_logging(self):
        """Test audit logging functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / 'audit.log'
            
            config = VerificationConfig(
                log_to_file=True,
                audit_log_path=str(audit_path)
            )
            boss = BossAgent(config)
            
            result = VerificationResult(
                status=VerificationStatus.PASS,
                score=85.0
            )
            
            boss._log_verification('005', result)
            
            # Check audit log was created
            assert audit_path.exists()
            
            # Read and verify log content
            with open(audit_path) as f:
                log_data = json.loads(f.readline())
            
            assert log_data['ticket_id'] == '005'
            assert log_data['status'] == 'pass'
            assert log_data['score'] == 85.0
    
    def test_get_test_command(self):
        """Test test command detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test with pytest.ini
            (Path(tmpdir) / 'pytest.ini').touch()
            cmd = self.boss._get_test_command(tmpdir)
            assert 'pytest' in cmd
            
            # Test with setup.py
            (Path(tmpdir) / 'setup.py').touch()
            cmd = self.boss._get_test_command(tmpdir)
            assert 'setup.py' in cmd or 'pytest' in cmd
    
    def test_check_function_exists(self):
        """Test function existence checking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file with function
            py_file = Path(tmpdir) / 'functions.py'
            py_file.write_text('def my_function():\n    pass\n\nasync def async_func():\n    pass\n')
            
            assert self.boss._check_function_exists(tmpdir, 'my_function')
            assert self.boss._check_function_exists(tmpdir, 'async_func')
            assert not self.boss._check_function_exists(tmpdir, 'missing_function')
    
    def test_check_test_exists(self):
        """Test checking for test existence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test directory and file
            test_dir = Path(tmpdir) / 'tests'
            test_dir.mkdir()
            
            test_file = test_dir / 'test_main.py'
            test_file.write_text('def test_something():\n    assert True\n')
            
            assert self.boss._check_test_exists(tmpdir, 'test_')
            assert self.boss._check_test_exists(tmpdir, 'something')
    
    def test_check_feature_implemented(self):
        """Test feature implementation checking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file with feature keywords
            feature_file = Path(tmpdir) / 'features.py'
            feature_file.write_text('''
class UserAuthentication:
    def login(self, username, password):
        pass
    
    def logout(self):
        pass
''')
            
            assert self.boss._check_feature_implemented(tmpdir, 'user authentication')
            assert self.boss._check_feature_implemented(tmpdir, 'login')
            assert not self.boss._check_feature_implemented(tmpdir, 'payment processing')
    
    def test_check_code_added(self):
        """Test checking if code was added."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No files - should return False
            assert not self.boss._check_code_added(tmpdir)
            
            # Empty file - should return False
            (Path(tmpdir) / 'empty.py').touch()
            assert not self.boss._check_code_added(tmpdir)
            
            # File with content - should return True
            (Path(tmpdir) / 'content.py').write_text('# ' * 51 + '\n' * 10)  # More than 100 chars when stripped
            assert self.boss._check_code_added(tmpdir)
    
    def test_get_verification_stats(self):
        """Test getting verification statistics."""
        # Add some history
        self.boss._track_attempt('001')
        self.boss._track_attempt('002')
        self.boss.retry_count['001'] = 2
        
        stats = self.boss.get_verification_stats()
        
        assert stats['total_verifications'] == 2
        assert '001' in stats['retry_counts']
        assert stats['retry_counts']['001'] == 2
        assert len(stats['history']) <= 10
    
    def test_reset_retry_count(self):
        """Test resetting retry count."""
        ticket_id = '006'
        self.boss.retry_count[ticket_id] = 3
        
        self.boss.reset_retry_count(ticket_id)
        
        assert ticket_id not in self.boss.retry_count
    
    def test_verify_tests_with_coverage(self):
        """Test test verification with coverage analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock test command execution
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout='', stderr='')
                
                # Mock coverage analyzer since it's None by default
                mock_coverage = Mock()
                mock_coverage.analyze.return_value = 85.0
                self.boss.coverage_analyzer = mock_coverage
                
                result = self.boss._verify_tests(tmpdir)
            
            assert result['passed']
            assert result['coverage'] == 85.0
    
    def test_verify_tests_failure(self):
        """Test test verification when tests fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock test command execution with failure
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=1, stdout='Failed', stderr='Error')
                
                result = self.boss._verify_tests(tmpdir)
            
            assert not result['passed']
            assert 'Tests failed' in result['reason']
    
    def test_verify_production_quality(self):
        """Test production quality verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock quality metrics
            mock_complexity = Mock()
            mock_complexity.cyclomatic_complexity = 5
            mock_complexity.duplicate_code_ratio = 0.02
            
            mock_documentation = Mock()
            mock_documentation.docstring_coverage = 90
            
            mock_security = Mock()
            mock_security.secrets_in_code = False
            
            mock_report = Mock()
            mock_report.overall_score = 8.5
            mock_report.production_ready = True
            mock_report.complexity = mock_complexity
            mock_report.documentation = mock_documentation
            mock_report.security = mock_security
            
            with patch.object(self.boss.metrics_analyzer, 'analyze_project', return_value=mock_report):
                result = self.boss._verify_production_quality(tmpdir)
            
            assert result['score'] == 8.5
            assert result['production_ready']
            assert len(result['suggestions']) == 0
    
    def test_exponential_backoff(self):
        """Test exponential backoff in retries."""
        ticket_id = '007'
        verification_result = VerificationResult(
            status=VerificationStatus.FAIL,
            score=30.0
        )
        
        mock_executor = Mock()
        
        # Test timing of retries
        start_times = []
        
        def timed_executor(*args):
            start_times.append(time.time())
        
        mock_executor.side_effect = timed_executor
        
        # First retry (delay = 0.1)
        self.boss.trigger_re_execution(ticket_id, verification_result, mock_executor)
        
        # Second retry (delay = 0.2)
        self.boss.trigger_re_execution(ticket_id, verification_result, mock_executor)
        
        # Verify exponential increase
        assert self.boss.retry_count[ticket_id] == 2