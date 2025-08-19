"""
CI-specific test runner for integration tests.

Ensures all integration tests run reliably in CI environments with
proper configuration, timeouts, and error handling.
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from typing import List, Dict, Any


class CITestRunner:
    """CI-optimized test runner for integration tests."""
    
    def __init__(self):
        self.ci_mode = os.getenv("CI", "false").lower() == "true"
        self.test_results = {}
        self.failed_tests = []
        self.setup_ci_environment()
    
    def setup_ci_environment(self):
        """Setup CI environment for testing."""
        # Set CI-specific environment variables
        env_vars = {
            "CI": "true",
            "PYTHONHASHSEED": "0",
            "HYDRA_TEST_MODE": "true",
            "LLM_PROVIDER": "mock",
            "HYDRA_DISABLE_NETWORK": "true",
            "DATABASE_URL": "sqlite:///test.db",
            "TESTING": "1",
            "REDIS_URL": "redis://localhost:6379/0",
            "TZ": "UTC",
            "PYTHONUNBUFFERED": "1"
        }
        
        for key, value in env_vars.items():
            os.environ[key] = value
        
        print(f"🔧 CI Environment configured")
        print(f"   CI Mode: {self.ci_mode}")
        print(f"   Python Hash Seed: {os.environ.get('PYTHONHASHSEED')}")
        print(f"   Provider: {os.environ.get('LLM_PROVIDER')}")
    
    def get_integration_test_files(self) -> List[Path]:
        """Get all integration test files."""
        test_dir = Path(__file__).parent
        test_files = []
        
        # Get all test files
        for test_file in test_dir.glob("test_*.py"):
            if test_file.name not in ["test_runner_config.py", "test_suite_validation.py"]:
                test_files.append(test_file)
        
        return sorted(test_files)
    
    def run_single_test_file(self, test_file: Path, timeout: int = 600) -> Dict[str, Any]:
        """Run a single test file with CI optimizations."""
        print(f"🧪 Running {test_file.name}...")
        
        # Prepare pytest command with CI optimizations
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_file),
            "-v",
            "--tb=short",
            "--timeout=60",  # 1 minute timeout per test
            "--disable-warnings",
            "--maxfail=3",  # Stop after 3 failures
            "-x"  # Stop on first failure for faster feedback
        ]
        
        if self.ci_mode:
            cmd.extend([
                "--no-cov",  # Disable coverage in CI for speed
                "-q"  # Quiet mode
            ])
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy()
            )
            
            duration = time.time() - start_time
            
            # Parse pytest output
            output_lines = result.stdout.split('\n')
            error_lines = result.stderr.split('\n')
            
            # Count test results
            passed_count = 0
            failed_count = 0
            
            for line in output_lines:
                if " PASSED " in line:
                    passed_count += 1
                elif " FAILED " in line:
                    failed_count += 1
            
            test_result = {
                "file": test_file.name,
                "success": result.returncode == 0,
                "duration": duration,
                "passed_tests": passed_count,
                "failed_tests": failed_count,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode
            }
            
            if result.returncode == 0:
                print(f"   ✅ Passed ({duration:.1f}s, {passed_count} tests)")
            else:
                print(f"   ❌ Failed ({duration:.1f}s, {failed_count} failures)")
                self.failed_tests.append(test_file.name)
            
            return test_result
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f"   ⏰ Timeout ({duration:.1f}s)")
            
            return {
                "file": test_file.name,
                "success": False,
                "duration": duration,
                "error": "Test timeout",
                "timeout": True
            }
        
        except Exception as e:
            duration = time.time() - start_time
            print(f"   💥 Error: {e}")
            
            return {
                "file": test_file.name,
                "success": False,
                "duration": duration,
                "error": str(e),
                "exception": True
            }
    
    def run_all_integration_tests(self) -> Dict[str, Any]:
        """Run all integration tests."""
        print("🚀 Starting Integration Test Suite")
        print("=" * 50)
        
        test_files = self.get_integration_test_files()
        print(f"Found {len(test_files)} test files")
        
        suite_start_time = time.time()
        all_results = {}
        
        for test_file in test_files:
            result = self.run_single_test_file(test_file)
            all_results[test_file.name] = result
            
            # Small delay between tests for stability
            time.sleep(1)
        
        suite_duration = time.time() - suite_start_time
        
        # Calculate summary statistics
        successful_files = sum(1 for r in all_results.values() if r["success"])
        total_files = len(all_results)
        total_passed_tests = sum(r.get("passed_tests", 0) for r in all_results.values())
        total_failed_tests = sum(r.get("failed_tests", 0) for r in all_results.values())
        
        summary = {
            "total_files": total_files,
            "successful_files": successful_files,
            "failed_files": total_files - successful_files,
            "success_rate": successful_files / total_files if total_files > 0 else 0,
            "total_passed_tests": total_passed_tests,
            "total_failed_tests": total_failed_tests,
            "total_duration": suite_duration,
            "failed_test_files": self.failed_tests
        }
        
        print("\n📊 Integration Test Summary")
        print("=" * 30)
        print(f"Files Run: {total_files}")
        print(f"Successful: {successful_files}")
        print(f"Failed: {summary['failed_files']}")
        print(f"Success Rate: {summary['success_rate']:.1%}")
        print(f"Total Tests Passed: {total_passed_tests}")
        print(f"Total Tests Failed: {total_failed_tests}")
        print(f"Total Duration: {suite_duration:.1f}s")
        
        if self.failed_tests:
            print(f"\n❌ Failed Test Files:")
            for failed_file in self.failed_tests:
                print(f"   - {failed_file}")
        
        return {
            "summary": summary,
            "results": all_results,
            "environment": {
                "ci_mode": self.ci_mode,
                "python_version": sys.version,
                "environment_vars": {
                    k: v for k, v in os.environ.items() 
                    if k.startswith(("HYDRA_", "CI", "PYTHON", "LLM_"))
                }
            }
        }
    
    def run_validation_suite(self) -> Dict[str, Any]:
        """Run the test validation suite."""
        print("\n🔍 Running Test Validation Suite")
        print("=" * 40)
        
        validation_file = Path(__file__).parent / "test_suite_validation.py"
        
        if not validation_file.exists():
            return {
                "success": False,
                "error": "Validation suite not found"
            }
        
        try:
            result = subprocess.run(
                [sys.executable, str(validation_file)],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
                env=os.environ.copy()
            )
            
            validation_result = {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode
            }
            
            if result.returncode == 0:
                print("✅ Validation suite passed")
            else:
                print("❌ Validation suite failed")
                print(f"Error: {result.stderr}")
            
            return validation_result
            
        except subprocess.TimeoutExpired:
            print("⏰ Validation suite timeout")
            return {
                "success": False,
                "error": "Validation timeout"
            }
        
        except Exception as e:
            print(f"💥 Validation error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_ci_report(self, test_results: Dict[str, Any], 
                          validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive CI report."""
        
        report = {
            "ci_test_run": {
                "timestamp": time.time(),
                "ci_mode": self.ci_mode,
                "environment": test_results.get("environment", {}),
                "integration_tests": test_results,
                "validation_suite": validation_results
            },
            "overall_status": {
                "integration_tests_passed": test_results["summary"]["success_rate"] >= 0.8,
                "validation_passed": validation_results.get("success", False),
                "ready_for_production": False
            },
            "recommendations": []
        }
        
        # Determine overall status
        integration_success = report["overall_status"]["integration_tests_passed"]
        validation_success = report["overall_status"]["validation_passed"]
        
        report["overall_status"]["ready_for_production"] = integration_success and validation_success
        
        # Add recommendations
        if not integration_success:
            report["recommendations"].append("Fix failing integration tests before deployment")
        
        if not validation_success:
            report["recommendations"].append("Address test validation issues for better reliability")
        
        if test_results["summary"]["total_failed_tests"] > 0:
            report["recommendations"].append("Investigate and fix individual test failures")
        
        if test_results["summary"]["total_duration"] > 600:  # 10 minutes
            report["recommendations"].append("Consider optimizing test performance")
        
        return report
    
    def save_ci_artifacts(self, report: Dict[str, Any]):
        """Save CI artifacts for analysis."""
        # Save main report
        report_file = "ci_integration_test_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 CI report saved to: {report_file}")
        
        # Save individual test outputs for failed tests
        if self.failed_tests:
            failed_outputs_dir = Path("failed_test_outputs")
            failed_outputs_dir.mkdir(exist_ok=True)
            
            for failed_test in self.failed_tests:
                test_result = report["ci_test_run"]["integration_tests"]["results"].get(failed_test)
                if test_result:
                    output_file = failed_outputs_dir / f"{failed_test}_output.txt"
                    with open(output_file, 'w') as f:
                        f.write(f"=== STDOUT ===\n{test_result.get('stdout', '')}\n")
                        f.write(f"=== STDERR ===\n{test_result.get('stderr', '')}\n")
            
            print(f"💾 Failed test outputs saved to: {failed_outputs_dir}")
    
    def run_complete_ci_suite(self) -> bool:
        """Run complete CI test suite and return success status."""
        print("🔥 Starting Complete CI Integration Test Suite")
        print("=" * 60)
        
        # Run integration tests
        test_results = self.run_all_integration_tests()
        
        # Run validation suite
        validation_results = self.run_validation_suite()
        
        # Generate report
        report = self.generate_ci_report(test_results, validation_results)
        
        # Save artifacts
        self.save_ci_artifacts(report)
        
        # Print final status
        print("\n🏁 Final CI Status")
        print("=" * 20)
        
        if report["overall_status"]["ready_for_production"]:
            print("🎉 ALL TESTS PASSED - Ready for production!")
            return True
        else:
            print("❌ TESTS FAILED - Not ready for production")
            print("\nRecommendations:")
            for rec in report["recommendations"]:
                print(f"   - {rec}")
            return False


def main():
    """Main entry point for CI test runner."""
    runner = CITestRunner()
    
    try:
        success = runner.run_complete_ci_suite()
        exit_code = 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n⏹️  Test run interrupted")
        exit_code = 130
        
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        exit_code = 1
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()