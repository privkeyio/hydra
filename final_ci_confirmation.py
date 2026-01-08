#!/usr/bin/env python3
"""
Final confirmation that the previously failing CI tests now pass.
"""

import os
import sys
import subprocess

# Set test environment variables
os.environ.update({
    'TESTING': '1',
    'CI': 'true', 
    'LLM_PROVIDER': 'mock',
    'REDIS_URL': 'redis://localhost:6379/0',
    'DATABASE_URL': 'sqlite:///test.db',
    'PYTHONPATH': 'src'
})

def run_test(test_path, timeout=300):
    """Run a specific test and return success status."""
    cmd = [
        '/home/kyle/.local/share/pipx/venvs/hydra-agents/bin/python', '-m', 'pytest', 
        test_path, '-v', '--tb=short', '--timeout=60', '--disable-warnings'
    ]
    
    print(f"Running: {test_path}")
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            cwd='/home/kyle/Documents/GitHub/hydra'
        )
        
        if result.returncode == 0:
            print(f"✅ PASSED: {test_path}")
            return True
        else:
            print(f"❌ FAILED: {test_path}")
            print("STDOUT:", result.stdout[-500:])  # Last 500 chars
            print("STDERR:", result.stderr[-500:])
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ TIMEOUT: {test_path}")
        return False
    except Exception as e:
        print(f"🔥 ERROR: {test_path} - {e}")
        return False

def main():
    """Test the 4 specific tests that were previously failing."""
    
    # The 4 integration tests that were fixed
    failing_tests = [
        'tests/integration/test_complete_workflow.py::TestCompleteWorkflow::test_ticket_generation_complex_project',
        'tests/integration/test_complete_workflow.py::TestCompleteWorkflow::test_verification_pass_scenario', 
        'tests/integration/test_complete_workflow.py::TestCompleteWorkflow::test_quality_metrics_coverage',
        'tests/integration/test_boss_agent_integration.py::TestBossAgentIntegration::test_end_to_end_verification_pass'
    ]
    
    print("🧪 Final confirmation of CI fixes...")
    print("=" * 60)
    
    passed = 0
    total = len(failing_tests)
    
    for test in failing_tests:
        if run_test(test):
            passed += 1
        print("-" * 40)
    
    print("=" * 60)
    print(f"📊 Final Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! CI is fixed and ready.")
        return 0
    else:
        print("💥 Some tests still failing.")
        return 1

if __name__ == '__main__':
    sys.exit(main())