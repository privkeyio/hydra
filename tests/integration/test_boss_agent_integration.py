"""Integration tests for the Boss Agent with ticket workflow."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from hydra.verification_system import (
    BossAgent,
    BossVerificationConfig,
    BossStrictnessLevel,
    VerificationHook,
    register_verification_hooks,
    create_standalone_verifier
)
from hydra.verification_system.workflow_hooks import VerificationHook


class TestBossAgentIntegration:
    """Integration tests for Boss Agent."""
    
    def test_end_to_end_verification_pass(self):
        """Test complete verification flow with passing criteria."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a sample project structure
            src_dir = Path(tmpdir) / 'src'
            src_dir.mkdir()
            
            # Create main module
            main_file = src_dir / 'main.py'
            main_file.write_text('''
def add(a, b):
    """Add two numbers."""
    return a + b

def multiply(a, b):
    """Multiply two numbers."""
    return a * b

class Calculator:
    """Simple calculator class."""
    
    def __init__(self):
        self.history = []
    
    def calculate(self, operation, a, b):
        """Perform calculation."""
        if operation == 'add':
            result = add(a, b)
        elif operation == 'multiply':
            result = multiply(a, b)
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        self.history.append(f"{operation}({a}, {b}) = {result}")
        return result
''')
            
            # Create tests
            test_dir = Path(tmpdir) / 'tests'
            test_dir.mkdir()
            
            test_file = test_dir / 'test_main.py'
            test_file.write_text('''
import sys
sys.path.insert(0, '../src')
from main import add, multiply, Calculator

def test_add():
    assert add(2, 3) == 5
    assert add(0, 0) == 0
    assert add(-1, 1) == 0

def test_multiply():
    assert multiply(2, 3) == 6
    assert multiply(0, 5) == 0
    assert multiply(-2, 3) == -6

def test_calculator():
    calc = Calculator()
    assert calc.calculate('add', 10, 5) == 15
    assert calc.calculate('multiply', 3, 7) == 21
    assert len(calc.history) == 2
''')
            
            # Create ticket data
            ticket_data = {
                'id': '001',
                'title': 'Create calculator module',
                'acceptance_criteria': [
                    'Create src/main.py with calculator functions',
                    'Implement add and multiply functions',
                    'Create Calculator class with history',
                    'Add comprehensive unit tests',
                    'Ensure test coverage above 80%'
                ]
            }
            
            # Create verifier
            config = BossVerificationConfig(
                strictness=BossStrictnessLevel.STRICT,
                min_test_coverage=70.0,
                min_quality_score=6.0,
                check_ai_patterns=True,
                check_production_quality=True
            )
            
            boss = BossAgent(config)
            
            # Run verification
            result = boss.verify_ticket_completion(
                ticket_id='001',
                ticket_data=ticket_data,
                project_path=tmpdir
            )
            
            # Assertions
            assert result.status.value == 'pass'
            assert result.score > 60.0
            assert len(result.passed_criteria) >= 3
    
    def test_end_to_end_verification_fail(self):
        """Test verification flow with failing criteria."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal project (missing tests and functionality)
            src_dir = Path(tmpdir) / 'src'
            src_dir.mkdir()
            
            # Create incomplete main module
            main_file = src_dir / 'main.py'
            main_file.write_text('''
def add(a, b):
    # TODO: implement
    pass
''')
            
            # Create ticket data with strict requirements
            ticket_data = {
                'id': '002',
                'title': 'Create complete calculator',
                'acceptance_criteria': [
                    'Create src/main.py with all functions',
                    'Implement add, subtract, multiply, divide',
                    'Create Calculator class',
                    'Add comprehensive unit tests',
                    'Ensure 90% test coverage'
                ]
            }
            
            # Create strict verifier
            config = BossVerificationConfig(
                strictness=BossStrictnessLevel.BRUTAL,
                min_test_coverage=90.0,
                min_quality_score=8.0
            )
            
            boss = BossAgent(config)
            
            # Run verification
            result = boss.verify_ticket_completion(
                ticket_id='002',
                ticket_data=ticket_data,
                project_path=tmpdir
            )
            
            # Assertions
            assert result.status.value == 'fail'
            assert result.score < 50.0
            assert len(result.failed_criteria) > 0
            assert len(result.failure_reasons) > 0
            assert len(result.suggestions) > 0
    
    def test_verification_hook_integration(self):
        """Test verification hook with workflow."""
        hook = VerificationHook(
            config=BossVerificationConfig(strictness=BossStrictnessLevel.MODERATE),
            auto_retry=True,
            verbose=False
        )
        
        # Mock executor callback
        mock_executor = Mock()
        hook.set_executor_callback(mock_executor)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create simple valid project
            (Path(tmpdir) / 'main.py').write_text('def main():\n    return True\n')
            
            ticket_data = {
                'id': '003',
                'acceptance_criteria': ['Create main.py with main function']
            }
            
            execution_result = {'status': 'completed'}
            
            # Test post-execution hook
            result = hook.post_execution_hook(
                ticket_id='003',
                ticket_data=ticket_data,
                project_path=tmpdir,
                execution_result=execution_result
            )
            
            assert 'verified' in result
            assert 'score' in result
            assert 'status' in result
    
    def test_pre_execution_hook_with_retry_context(self):
        """Test pre-execution hook injecting retry context."""
        hook = VerificationHook()
        
        ticket_data = {
            'id': '004',
            'description': 'Original task description',
            'acceptance_criteria': ['Create feature']
        }
        
        retry_context = {
            'retry_number': 2,
            'previous_failures': ['Tests failed', 'Coverage too low'],
            'failed_criteria': ['Add tests'],
            'suggestions': ['Improve test coverage']
        }
        
        # Test context injection
        enhanced_data = hook.pre_execution_hook(
            ticket_id='004',
            ticket_data=ticket_data,
            retry_context=retry_context
        )
        
        assert 'retry_context' in enhanced_data
        assert 'RETRY ATTEMPT 2' in enhanced_data['description']
        assert 'Tests failed' in enhanced_data['description']
    
    def test_standalone_verifier_creation(self):
        """Test creating standalone verifier."""
        verifier = create_standalone_verifier(
            strictness='brutal',
            min_coverage=95.0,
            min_quality=9.0
        )
        
        assert isinstance(verifier, BossAgent)
        assert verifier.config.strictness == BossStrictnessLevel.BRUTAL
        assert verifier.config.min_test_coverage == 95.0
        assert verifier.config.min_quality_score == 9.0
    
    def test_ai_pattern_detection_integration(self):
        """Test AI pattern detection in verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file with obvious AI patterns
            ai_file = Path(tmpdir) / 'ai_generated.py'
            ai_file.write_text('''
def calculate_the_sum_of_two_numbers_and_return_the_result(first_number_to_add, second_number_to_add):
    """
    This function calculates the sum of two numbers and returns the result.
    
    It takes two parameters:
    - first_number_to_add: The first number that will be added
    - second_number_to_add: The second number that will be added
    
    Returns:
    - The calculated sum of the two input numbers
    
    Example:
        >>> result = calculate_the_sum_of_two_numbers_and_return_the_result(5, 3)
        >>> print(result)  # Output: 8
    """
    # First, we store the first number in a variable
    number_one = first_number_to_add
    
    # Then, we store the second number in another variable
    number_two = second_number_to_add
    
    # Now we calculate the sum of these two numbers
    calculated_sum = number_one + number_two
    
    # Finally, we return the calculated result
    return calculated_sum
''')
            
            ticket_data = {
                'id': '005',
                'acceptance_criteria': ['Create calculation function']
            }
            
            config = BossVerificationConfig(
                strictness=BossStrictnessLevel.STRICT,
                check_ai_patterns=True
            )
            
            boss = BossAgent(config)
            
            # Mock AI detector to always detect patterns
            with patch.object(boss.ai_detector, 'detect_ai_patterns', return_value=(True, ['ai_pattern'])):
                result = boss.verify_ticket_completion(
                    ticket_id='005',
                    ticket_data=ticket_data,
                    project_path=tmpdir
                )
            
            assert result.status.value == 'fail'
            assert any('AI pattern' in reason for reason in result.failure_reasons)
    
    def test_retry_mechanism_with_backoff(self):
        """Test retry mechanism with exponential backoff."""
        config = BossVerificationConfig(
            max_retries=3,
            retry_delay_base=0.01  # Very short for testing
        )
        
        boss = BossAgent(config)
        
        # Create failing verification result
        from hydra.verification_system.boss_agent import VerificationResult, VerificationStatus
        
        fail_result = VerificationResult(
            status=VerificationStatus.FAIL,
            score=30.0,
            failure_reasons=['Test coverage too low'],
            suggestions=['Add more tests']
        )
        
        mock_executor = Mock()
        
        # Test multiple retries
        for i in range(3):
            result = boss.trigger_re_execution('006', fail_result, mock_executor)
            if result is None and i < 3:
                assert boss.retry_count['006'] == i + 1
        
        # Should stop after max retries
        result = boss.trigger_re_execution('006', fail_result, mock_executor)
        assert result is None
        assert mock_executor.call_count == 3
    
    def test_audit_logging_integration(self):
        """Test audit logging during verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / 'audit.log'
            
            config = BossVerificationConfig(
                log_to_file=True,
                audit_log_path=str(audit_path)
            )
            
            boss = BossAgent(config)
            
            # Run multiple verifications
            ticket_data = {'id': '007', 'acceptance_criteria': []}
            
            for i in range(3):
                boss.verify_ticket_completion(
                    ticket_id=f'007-{i}',
                    ticket_data=ticket_data,
                    project_path=tmpdir
                )
            
            # Check audit log
            assert audit_path.exists()
            
            # Read and verify entries
            with open(audit_path) as f:
                lines = f.readlines()
            
            assert len(lines) >= 3
            
            for line in lines:
                line = line.strip()
                if line:  # Skip empty lines
                    try:
                        entry = json.loads(line)
                        assert 'ticket_id' in entry
                        assert 'status' in entry
                        assert 'score' in entry
                        assert 'timestamp' in entry
                    except json.JSONDecodeError:
                        # Skip malformed entries in test
                        continue
    
    def test_quality_metrics_integration(self):
        """Test integration with quality metrics analyzer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create high-quality code
            src_dir = Path(tmpdir) / 'src'
            src_dir.mkdir()
            
            quality_file = src_dir / 'quality.py'
            quality_file.write_text('''
"""High quality module with good practices."""

import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class DataProcessor:
    """Process data with proper error handling."""
    
    def __init__(self, config: dict):
        """Initialize processor with configuration."""
        self.config = config
        self.errors: List[str] = []
    
    def process(self, data: str) -> Optional[str]:
        """Process input data safely."""
        if not data:
            self.errors.append("Empty data received")
            return None
        
        try:
            processed = data.strip().upper()
            logger.info(f"Processed {len(data)} characters")
            return processed
        except Exception as e:
            self.errors.append(f"Processing error: {e}")
            logger.error(f"Failed to process: {e}")
            return None
    
    def get_errors(self) -> List[str]:
        """Get list of processing errors."""
        return self.errors.copy()
''')
            
            ticket_data = {
                'id': '008',
                'acceptance_criteria': [
                    'Create high-quality data processor',
                    'Include error handling',
                    'Add logging'
                ]
            }
            
            config = BossVerificationConfig(
                strictness=BossStrictnessLevel.STRICT,
                check_production_quality=True,
                min_quality_score=7.0
            )
            
            boss = BossAgent(config)
            
            result = boss.verify_ticket_completion(
                ticket_id='008',
                ticket_data=ticket_data,
                project_path=tmpdir
            )
            
            assert 'quality_score' in result.metadata
            # Quality should be decent for this code
            assert result.metadata['quality_score'] >= 5.0
    
    def test_workflow_registration(self):
        """Test registering hooks with workflow manager."""
        # Mock workflow manager
        class MockWorkflowManager:
            def __init__(self):
                self.post_hook = None
                self.pre_hook = None
                
            def register_post_execution_hook(self, hook):
                self.post_hook = hook
                
            def register_pre_execution_hook(self, hook):
                self.pre_hook = hook
                
            def execute_ticket(self, ticket_id, context):
                pass
        
        workflow = MockWorkflowManager()
        
        # Register hooks
        hook = register_verification_hooks(workflow)
        
        assert workflow.post_hook is not None
        assert workflow.pre_hook is not None
        assert hook.executor_callback is not None
        
        # Test that hooks are callable
        with tempfile.TemporaryDirectory() as tmpdir:
            result = workflow.post_hook(
                ticket_id='009',
                ticket_data={'acceptance_criteria': []},
                project_path=tmpdir,
                execution_result={}
            )
            
            assert isinstance(result, dict)
            assert 'status' in result