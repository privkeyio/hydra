import tempfile
import os
from pathlib import Path

from hydra.safety.file_guard import FileGuard
from hydra.safety.git_guard import GitGuard


def test_file_guard_sensitive_protection():
    guard = FileGuard()
    
    # Test common sensitive file patterns
    sensitive_files = [
        '.env',
        '.env.production', 
        'id_rsa',
        'server.key',
        'database.keystore'
    ]
    
    for filename in sensitive_files:
        with tempfile.NamedTemporaryFile(suffix=filename, delete=False) as f:
            f.write(b'SECRET_KEY=12345')
            
        allowed, reason = guard.validate_file_access(f.name, 'read')
        assert not allowed
        assert reason is not None
        
        os.unlink(f.name)


def test_file_guard_safe_files():
    guard = FileGuard()
    
    safe_files = [
        'README.md',
        'requirements.txt', 
        'main.py',
        'config.yaml'
    ]
    
    for filename in safe_files:
        with tempfile.NamedTemporaryFile(suffix=filename, delete=False) as f:
            f.write(b'# Safe content')
            
        allowed, reason = guard.validate_file_access(f.name, 'read')
        assert allowed
        assert reason is None
        
        os.unlink(f.name)


def test_file_guard_scan_directory():
    guard = FileGuard()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mix of files
        (Path(tmpdir) / 'safe.py').write_text('print("hello")')
        (Path(tmpdir) / '.env').write_text('SECRET=123')
        (Path(tmpdir) / 'README.md').write_text('# Project')
        
        # Scan for sensitive files
        sensitive = guard.scan_directory_for_sensitive_files(Path(tmpdir))
        
        sensitive_names = [f[0].name for f in sensitive]
        assert '.env' in sensitive_names
        assert 'safe.py' not in sensitive_names
        assert 'README.md' not in sensitive_names


def test_git_guard_dangerous_commands():
    guard = GitGuard()
    
    dangerous_commands = [
        'git push --force origin main',
        'git reset --hard HEAD~5',
        'git clean -xdf',
        'git config --global user.name "hacker"',
        'git config credential.helper store'
    ]
    
    for cmd in dangerous_commands:
        allowed, reason = guard.validate_git_command(cmd)
        assert not allowed
        assert reason is not None


def test_git_guard_safe_commands():
    guard = GitGuard()
    
    safe_commands = [
        'git status',
        'git log --oneline', 
        'git diff HEAD~1',
        'git add .',
        'git commit -m "Fix bug"',
        'git push origin feature'
    ]
    
    for cmd in safe_commands:
        allowed, reason = guard.validate_git_command(cmd)
        assert allowed
        assert reason is None


def test_rate_limiter_basic():
    from hydra.safety.rate_limiter import RateLimiter, CommandCategory
    
    limiter = RateLimiter()
    
    # Test safe command categorization
    category = limiter.categorize_command('git status')
    assert category == CommandCategory.SAFE
    
    # Test destructive command categorization  
    category = limiter.categorize_command('rm -rf /')
    assert category == CommandCategory.CRITICAL


def test_operation_validator():
    from hydra.safety.operation_validator import OperationValidator, OperationType
    
    validator = OperationValidator()
    
    # Test file operation validation
    allowed, reason, rule = validator.validate_operation(
        OperationType.FILE_READ, 
        '/tmp/test.txt'
    )
    
    # Should return validation result
    assert isinstance(allowed, bool)


def test_production_guardrails():
    from hydra.safety.guardrails import ProductionGuardrails
    
    guardrails = ProductionGuardrails()
    
    # Test basic functionality
    assert hasattr(guardrails, 'resource_monitor')
    assert hasattr(guardrails, 'rate_limiter')
    assert hasattr(guardrails, 'cost_controller')