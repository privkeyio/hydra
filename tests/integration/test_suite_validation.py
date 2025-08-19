"""
Integration test suite validation.

Validates that all integration tests are deterministic, properly isolated,
and will pass consistently in CI environments.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import patch

import pytest

from test_runner_config import (
    test_config, 
    DeterministicTestResults, 
    deterministic_temp_project,
    create_deterministic_mock_provider,
    run_with_timeout,
    ensure_test_isolation
)


class IntegrationTestValidator:
    """Validates integration test suite for deterministic behavior."""
    
    def __init__(self):
        self.test_results = DeterministicTestResults()
        self.failed_tests = []
        self.flaky_tests = []
        self.performance_metrics = {}
        
    def run_test_multiple_times(self, test_function, test_name: str, iterations: int = 3) -> Dict[str, Any]:
        """Run a test multiple times to check for flakiness."""
        results = []
        
        for i in range(iterations):
            ensure_test_isolation()  # Ensure clean state
            
            start_time = time.time()
            try:
                # Run test with timeout
                result = run_with_timeout(test_function, 30.0)  # 30 second timeout
                duration = time.time() - start_time
                
                results.append({
                    "iteration": i + 1,
                    "success": True,
                    "duration": duration,
                    "result": result
                })
                
            except Exception as e:
                duration = time.time() - start_time
                results.append({
                    "iteration": i + 1,
                    "success": False,
                    "duration": duration,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
        
        # Analyze results
        successful_runs = [r for r in results if r["success"]]
        success_rate = len(successful_runs) / len(results)
        
        durations = [r["duration"] for r in results]
        avg_duration = sum(durations) / len(durations)
        
        # Check for consistency
        if len(durations) > 1:
            import statistics
            duration_std = statistics.stdev(durations)
            duration_cv = duration_std / avg_duration if avg_duration > 0 else 0
        else:
            duration_cv = 0
        
        test_analysis = {
            "test_name": test_name,
            "iterations": iterations,
            "success_rate": success_rate,
            "avg_duration": avg_duration,
            "duration_consistency": duration_cv < 0.5,  # 50% variation threshold
            "is_deterministic": success_rate == 1.0 and duration_cv < 0.5,
            "results": results
        }
        
        return test_analysis


class TestIntegrationSuite:
    """Test the integration test suite itself."""
    
    def __init__(self):
        self.validator = IntegrationTestValidator()
    
    @pytest.mark.integration
    def test_comprehensive_workflow_determinism(self, deterministic_temp_project):
        """Test that comprehensive workflow tests are deterministic."""
        from test_comprehensive_workflow import TestComprehensiveWorkflow
        
        test_instance = TestComprehensiveWorkflow()
        
        def run_workflow_test():
            return test_instance.test_full_ticket_creation_to_execution_workflow(deterministic_temp_project)
        
        analysis = self.validator.run_test_multiple_times(
            run_workflow_test, 
            "comprehensive_workflow", 
            iterations=3
        )
        
        assert analysis["is_deterministic"], f"Comprehensive workflow test is not deterministic: {analysis}"
        assert analysis["success_rate"] >= 0.8, f"Success rate too low: {analysis['success_rate']}"
    
    @pytest.mark.integration
    def test_parallel_execution_determinism(self, deterministic_temp_project):
        """Test that parallel execution tests are deterministic."""
        from test_parallel_execution import TestParallelExecution
        
        test_instance = TestParallelExecution()
        
        def run_parallel_test():
            return test_instance.test_basic_parallel_execution(deterministic_temp_project)
        
        analysis = self.validator.run_test_multiple_times(
            run_parallel_test,
            "parallel_execution",
            iterations=3
        )
        
        assert analysis["is_deterministic"], f"Parallel execution test is not deterministic: {analysis}"
        assert analysis["success_rate"] >= 0.8, f"Success rate too low: {analysis['success_rate']}"
    
    @pytest.mark.integration
    def test_provider_failover_determinism(self, deterministic_temp_project):
        """Test that provider failover tests are deterministic."""
        from test_provider_failover import TestProviderFailover
        
        test_instance = TestProviderFailover()
        
        def run_failover_test():
            return test_instance.test_simple_provider_failover(deterministic_temp_project)
        
        analysis = self.validator.run_test_multiple_times(
            run_failover_test,
            "provider_failover", 
            iterations=3
        )
        
        assert analysis["is_deterministic"], f"Provider failover test is not deterministic: {analysis}"
        assert analysis["success_rate"] >= 0.8, f"Success rate too low: {analysis['success_rate']}"
    
    @pytest.mark.integration
    def test_dashboard_realtime_determinism(self, deterministic_temp_project):
        """Test that dashboard real-time tests are deterministic."""
        from test_dashboard_realtime import TestDashboardRealTime, RealTimeDashboard
        
        test_instance = TestDashboardRealTime()
        
        def run_dashboard_test():
            dashboard = RealTimeDashboard(deterministic_temp_project)
            return test_instance.test_ticket_status_updates(deterministic_temp_project, dashboard)
        
        analysis = self.validator.run_test_multiple_times(
            run_dashboard_test,
            "dashboard_realtime",
            iterations=3
        )
        
        assert analysis["is_deterministic"], f"Dashboard real-time test is not deterministic: {analysis}"
        assert analysis["success_rate"] >= 0.8, f"Success rate too low: {analysis['success_rate']}"
    
    @pytest.mark.integration
    def test_mock_provider_consistency(self, deterministic_temp_project):
        """Test that mock providers behave consistently."""
        provider = create_deterministic_mock_provider()
        
        # Test same prompt multiple times
        test_prompt = "Create a Python module with basic functionality"
        responses = []
        
        for i in range(5):
            response = provider.generate(test_prompt)
            responses.append(response)
        
        # Responses should be deterministic but unique (due to call count)
        assert len(responses) == 5
        assert all(len(response) > 0 for response in responses)
        
        # Each response should contain call number
        for i, response in enumerate(responses):
            assert f"Call #{i + 1}" in response
        
        # Provider state should be consistent
        assert provider.call_count == 5
    
    @pytest.mark.integration 
    def test_test_isolation_effectiveness(self, deterministic_temp_project):
        """Test that test isolation prevents state leakage."""
        # Set some global state
        os.environ["TEST_ISOLATION_CHECK"] = "value1"
        
        # Simulate test execution
        ensure_test_isolation()
        
        # State should be cleaned
        test_modules_before = len([
            name for name in sys.modules.keys() 
            if "test_" in name and "hydra" in name
        ])
        
        # Import a test module
        from test_comprehensive_workflow import TestComprehensiveWorkflow
        
        test_modules_after_import = len([
            name for name in sys.modules.keys()
            if "test_" in name and "hydra" in name  
        ])
        
        # Clean up
        ensure_test_isolation()
        
        test_modules_after_cleanup = len([
            name for name in sys.modules.keys()
            if "test_" in name and "hydra" in name
        ])
        
        # Verify isolation worked
        assert test_modules_after_import > test_modules_before
        assert test_modules_after_cleanup <= test_modules_before
    
    @pytest.mark.integration
    def test_timeout_handling(self, deterministic_temp_project):
        """Test that timeouts are handled correctly."""
        def slow_function():
            time.sleep(2.0)  # 2 second delay
            return "completed"
        
        # Should complete with sufficient timeout
        result = run_with_timeout(slow_function, 3.0)
        assert result == "completed"
        
        # Should timeout with insufficient time
        with pytest.raises(TimeoutError):
            run_with_timeout(slow_function, 0.5)
    
    @pytest.mark.integration
    def test_ci_environment_compatibility(self, deterministic_temp_project):
        """Test compatibility with CI environment constraints."""
        # Test with CI constraints
        original_ci_mode = test_config.ci_mode
        test_config.ci_mode = True
        
        try:
            # Worker count should be limited in CI
            worker_count = test_config.get_worker_count(8)
            assert worker_count <= test_config.max_workers
            
            # Timeouts should be increased in CI
            timeout = test_config.get_timeout(1.0)
            assert timeout >= 1.0 * test_config.timeout_multiplier
            
            # Mock providers should always be used
            assert test_config.mock_providers is True
            
        finally:
            test_config.ci_mode = original_ci_mode
    
    @pytest.mark.integration
    def test_resource_management(self, deterministic_temp_project):
        """Test proper resource management in tests."""
        import tempfile
        import threading
        
        # Track resource usage
        initial_thread_count = threading.active_count()
        temp_dirs_created = []
        
        # Simulate resource-intensive test
        for i in range(3):
            temp_dir = tempfile.mkdtemp(prefix="resource_test_")
            temp_dirs_created.append(temp_dir)
            
            # Create some threads
            thread = threading.Thread(target=lambda: time.sleep(0.1))
            thread.start()
            thread.join()
        
        # Clean up
        for temp_dir in temp_dirs_created:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Check resource cleanup
        final_thread_count = threading.active_count()
        assert final_thread_count <= initial_thread_count + 2  # Allow some variance
        
        # Verify temp directories are cleaned
        for temp_dir in temp_dirs_created:
            assert not Path(temp_dir).exists()
    
    @pytest.mark.integration
    def test_async_operations_determinism(self, deterministic_temp_project):
        """Test that async operations behave deterministically."""
        
        async def async_test_function():
            results = []
            
            # Run multiple async operations
            tasks = []
            for i in range(5):
                async def async_task(task_id):
                    await asyncio.sleep(0.01)  # Small delay
                    return f"task_{task_id}_completed"
                
                tasks.append(async_task(i))
            
            # Gather results
            task_results = await asyncio.gather(*tasks)
            return sorted(task_results)  # Sort for determinism
        
        # Run async test multiple times
        results = []
        for i in range(3):
            result = asyncio.run(async_test_function())
            results.append(result)
        
        # Results should be identical
        assert all(result == results[0] for result in results)
        assert len(results[0]) == 5
        assert all("task_" in item for item in results[0])
    
    @pytest.mark.integration
    def test_database_state_isolation(self, deterministic_temp_project):
        """Test that database state is properly isolated between tests."""
        from hydra.dashboard.database import get_db_manager, Project
        
        # Set up database in test project
        os.environ["DATABASE_URL"] = f"sqlite:///{deterministic_temp_project}/.hydra/test.db"
        
        # Create some data
        db_manager = get_db_manager()
        with db_manager.get_session() as db:
            project = Project(
                name="Test Isolation Project",
                description="Testing database isolation",
                repository_url=str(deterministic_temp_project)
            )
            db.add(project)
            db.commit()
            project_id = project.id
        
        # Verify data exists
        with db_manager.get_session() as db:
            found_project = db.query(Project).filter(Project.id == project_id).first()
            assert found_project is not None
            assert found_project.name == "Test Isolation Project"
        
        # Simulate test cleanup (would normally happen between tests)
        # In real tests, each test gets a fresh temp directory
        
        # Create new database instance (simulating new test)
        new_db_path = deterministic_temp_project / ".hydra" / "test2.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{new_db_path}"
        
        new_db_manager = get_db_manager()
        with new_db_manager.get_session() as db:
            # Should not find the previous project
            projects = db.query(Project).all()
            assert len(projects) == 0  # Fresh database
    
    @pytest.mark.integration
    def test_error_handling_consistency(self, deterministic_temp_project):
        """Test that error handling is consistent across runs."""
        
        def error_prone_function(should_fail: bool):
            if should_fail:
                raise ValueError("Consistent test error")
            return "success"
        
        # Test consistent success
        success_results = []
        for i in range(3):
            result = error_prone_function(False)
            success_results.append(result)
        
        assert all(result == "success" for result in success_results)
        
        # Test consistent failure
        error_results = []
        for i in range(3):
            try:
                error_prone_function(True)
                error_results.append("no_error")
            except ValueError as e:
                error_results.append(str(e))
            except Exception as e:
                error_results.append(f"unexpected_error_{type(e).__name__}")
        
        assert all(result == "Consistent test error" for result in error_results)
    
    def generate_validation_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report."""
        validation_results = self.validator.test_results.validate_determinism()
        
        report = {
            "validation_summary": {
                "total_validation_tests": len(validation_results.get("test_results", {})),
                "determinism_score": validation_results.get("determinism_score", 0.0),
                "ci_compatible": test_config.ci_mode,
                "environment": {
                    "ci_mode": test_config.ci_mode,
                    "max_workers": test_config.max_workers,
                    "timeout_multiplier": test_config.timeout_multiplier,
                    "mock_providers": test_config.mock_providers
                }
            },
            "test_categories": {
                "comprehensive_workflow": "Tests complete ticket workflows",
                "parallel_execution": "Tests multi-worker parallel execution",
                "provider_failover": "Tests provider failure and recovery",
                "dashboard_realtime": "Tests real-time dashboard updates"
            },
            "determinism_factors": {
                "mock_providers": "Using deterministic mock providers",
                "isolated_environments": "Each test gets fresh temporary directory",
                "controlled_timing": "Timeouts adjusted for CI environment",
                "state_isolation": "Global state cleaned between tests",
                "consistent_configuration": "Standardized test configuration"
            },
            "validation_results": validation_results,
            "recommendations": []
        }
        
        # Add specific recommendations
        if validation_results.get("determinism_score", 0) < 0.9:
            report["recommendations"].append("Consider additional mocking for better determinism")
        
        if test_config.ci_mode:
            report["recommendations"].append("Running in CI mode - using conservative timeouts and resource limits")
        
        return report


def run_full_validation_suite():
    """Run the complete validation suite."""
    print("🧪 Running Integration Test Suite Validation")
    print("=" * 50)
    
    # Setup
    from test_runner_config import setup_deterministic_environment
    setup_deterministic_environment()
    
    # Run validation tests
    test_suite = TestIntegrationSuite()
    
    validation_methods = [
        "test_comprehensive_workflow_determinism",
        "test_parallel_execution_determinism", 
        "test_provider_failover_determinism",
        "test_dashboard_realtime_determinism",
        "test_mock_provider_consistency",
        "test_test_isolation_effectiveness",
        "test_timeout_handling",
        "test_ci_environment_compatibility",
        "test_resource_management",
        "test_async_operations_determinism",
        "test_database_state_isolation",
        "test_error_handling_consistency"
    ]
    
    results = {}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_project = Path(tmpdir)
        
        for method_name in validation_methods:
            print(f"🔍 Running {method_name}...")
            
            try:
                method = getattr(test_suite, method_name)
                start_time = time.time()
                
                if "deterministic_temp_project" in method.__code__.co_varnames:
                    method(temp_project)
                else:
                    method()
                
                duration = time.time() - start_time
                results[method_name] = {
                    "success": True,
                    "duration": duration
                }
                print(f"   ✅ Passed ({duration:.2f}s)")
                
            except Exception as e:
                results[method_name] = {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
                print(f"   ❌ Failed: {e}")
    
    # Generate report
    report = test_suite.generate_validation_report()
    report["validation_test_results"] = results
    
    # Summary
    successful_validations = sum(1 for r in results.values() if r["success"])
    total_validations = len(results)
    success_rate = successful_validations / total_validations
    
    print("\n📊 Validation Summary")
    print("=" * 30)
    print(f"Tests Run: {total_validations}")
    print(f"Successful: {successful_validations}")
    print(f"Success Rate: {success_rate:.1%}")
    print(f"Determinism Score: {report['validation_summary']['determinism_score']:.1%}")
    
    if success_rate >= 0.9:
        print("🎉 Integration test suite is ready for CI!")
    else:
        print("⚠️  Integration test suite needs improvement for CI reliability")
    
    # Save report
    report_file = "integration_test_validation_report.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"📄 Detailed report saved to: {report_file}")
    
    return report


if __name__ == "__main__":
    report = run_full_validation_suite()