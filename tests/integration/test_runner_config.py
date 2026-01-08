"""
Test runner configuration for deterministic integration tests.

Ensures all integration tests run deterministically in CI environments
by configuring proper timeouts, mock behaviors, and resource management.
"""

import os
import pytest
import tempfile
import time
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch


class DeterministicTestConfig:
    """Configuration for deterministic test execution."""
    
    def __init__(self):
        self.ci_mode = os.getenv("CI", "false").lower() == "true"
        self.timeout_multiplier = 3.0 if self.ci_mode else 1.0
        self.max_workers = 2 if self.ci_mode else 4
        self.retry_attempts = 3 if self.ci_mode else 1
        self.mock_providers = True  # Always use mock providers for determinism
        
    def get_timeout(self, base_timeout: float) -> float:
        """Get adjusted timeout for CI environment."""
        return base_timeout * self.timeout_multiplier
    
    def get_worker_count(self, requested_workers: int) -> int:
        """Get appropriate worker count for environment."""
        return min(requested_workers, self.max_workers)


# Global config instance
test_config = DeterministicTestConfig()


def setup_deterministic_environment():
    """Setup deterministic testing environment."""
    # Set deterministic environment variables
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["HYDRA_TEST_MODE"] = "true"
    os.environ["LLM_PROVIDER"] = "mock"
    
    # Disable real network calls
    os.environ["HYDRA_DISABLE_NETWORK"] = "true"
    
    # Set consistent timezone
    os.environ["TZ"] = "UTC"
    
    # Configure database for testing
    os.environ["DATABASE_URL"] = "sqlite:///test.db"
    os.environ["TESTING"] = "1"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment for all integration tests."""
    setup_deterministic_environment()
    yield
    # Cleanup after tests


@pytest.fixture
def deterministic_temp_project():
    """Create deterministic temporary project."""
    with tempfile.TemporaryDirectory(prefix="hydra_test_") as tmpdir:
        project_path = Path(tmpdir)
        
        # Create consistent directory structure
        directories = [
            ".hydra",
            ".hydra/reports", 
            ".hydra/dashboard",
            ".hydra/locks",
            ".hydra/workers",
            "src",
            "tests",
            "tests/unit",
            "tests/integration", 
            "docs"
        ]
        
        for dir_path in directories:
            (project_path / dir_path).mkdir(parents=True, exist_ok=True)
        
        # Create test configuration file
        config_content = f"""# Hydra Test Configuration
test_mode: true
ci_mode: {test_config.ci_mode}
max_workers: {test_config.max_workers}
timeout_multiplier: {test_config.timeout_multiplier}
mock_providers: {test_config.mock_providers}
"""
        (project_path / ".hydra" / "test_config.yaml").write_text(config_content)
        
        yield project_path


def create_deterministic_mock_provider():
    """Create deterministic mock provider for testing."""
    from hydra.providers.base import LLMConfig
    from hydra.providers.mock_provider import MockProvider
    
    class DeterministicMockProvider(MockProvider):
        """Mock provider with deterministic responses."""
        
        def __init__(self, config: LLMConfig):
            super().__init__(config)
            self.call_count = 0
            self.response_templates = {
                "create": "Created implementation for: {prompt_summary}",
                "implement": "Implemented functionality for: {prompt_summary}",
                "test": "Created tests for: {prompt_summary}",
                "document": "Generated documentation for: {prompt_summary}",
                "default": "Generated response for: {prompt_summary}"
            }
        
        def generate(self, prompt: str, **kwargs) -> str:
            """Generate deterministic response based on prompt."""
            self.call_count += 1
            
            # Create deterministic response based on prompt content
            prompt_lower = prompt.lower()
            prompt_summary = prompt[:50] + "..." if len(prompt) > 50 else prompt
            
            # Determine response type
            if "create" in prompt_lower or "implement" in prompt_lower:
                template_key = "create"
            elif "test" in prompt_lower:
                template_key = "test"
            elif "document" in prompt_lower or "doc" in prompt_lower:
                template_key = "document"
            else:
                template_key = "default"
            
            response_template = self.response_templates[template_key]
            
            # Add deterministic content based on call count
            response = f"""Call #{self.call_count}: {response_template.format(prompt_summary=prompt_summary)}

Generated content:
- Implementation details based on requirements
- Proper error handling included
- Comprehensive testing added
- Documentation provided
- Code follows best practices

This is a deterministic mock response for testing purposes.
Response generated at call #{self.call_count}.
"""
            
            # Simulate some processing time (deterministic)
            if not test_config.ci_mode:
                time.sleep(0.01)  # Very short delay for non-CI
            
            return response
    
    config = LLMConfig(
        provider_type="deterministic_mock",
        model="test-model",
        api_key="test-key"
    )
    
    return DeterministicMockProvider(config)


def run_with_timeout(func, timeout: float, *args, **kwargs):
    """Run function with timeout, adjusted for CI environment."""
    import threading
    import queue
    
    adjusted_timeout = test_config.get_timeout(timeout)
    result_queue = queue.Queue()
    exception_queue = queue.Queue()
    
    def target():
        try:
            result = func(*args, **kwargs)
            result_queue.put(result)
        except Exception as e:
            exception_queue.put(e)
    
    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=adjusted_timeout)
    
    if thread.is_alive():
        # Timeout occurred
        raise TimeoutError(f"Function timed out after {adjusted_timeout} seconds")
    
    if not exception_queue.empty():
        raise exception_queue.get()
    
    if not result_queue.empty():
        return result_queue.get()
    
    raise RuntimeError("Function completed but no result available")


class DeterministicTestResults:
    """Collect and validate test results for determinism."""
    
    def __init__(self):
        self.test_results = {}
        self.timing_results = {}
        self.resource_usage = {}
    
    def record_test_result(self, test_name: str, result: Dict[str, Any]):
        """Record test result for validation."""
        self.test_results[test_name] = {
            "timestamp": time.time(),
            "success": result.get("success", False),
            "duration": result.get("duration", 0),
            "details": result.get("details", {})
        }
    
    def record_timing(self, operation: str, duration: float):
        """Record timing for performance validation."""
        if operation not in self.timing_results:
            self.timing_results[operation] = []
        self.timing_results[operation].append(duration)
    
    def validate_determinism(self) -> Dict[str, Any]:
        """Validate that results are deterministic."""
        validation_report = {
            "total_tests": len(self.test_results),
            "successful_tests": sum(1 for r in self.test_results.values() if r["success"]),
            "timing_consistency": {},
            "determinism_score": 0.0
        }
        
        # Check timing consistency
        for operation, times in self.timing_results.items():
            if len(times) > 1:
                import statistics
                mean_time = statistics.mean(times)
                std_dev = statistics.stdev(times) if len(times) > 1 else 0
                coefficient_of_variation = std_dev / mean_time if mean_time > 0 else 0
                
                validation_report["timing_consistency"][operation] = {
                    "mean": mean_time,
                    "std_dev": std_dev,
                    "cv": coefficient_of_variation,
                    "consistent": coefficient_of_variation < 0.3  # 30% variation threshold
                }
        
        # Calculate overall determinism score
        success_rate = validation_report["successful_tests"] / validation_report["total_tests"]
        timing_consistency = sum(
            1 for tc in validation_report["timing_consistency"].values() if tc["consistent"]
        ) / max(1, len(validation_report["timing_consistency"]))
        
        validation_report["determinism_score"] = (success_rate + timing_consistency) / 2
        
        return validation_report


# Global results collector
test_results = DeterministicTestResults()


def ensure_test_isolation():
    """Ensure test isolation between runs."""
    # Clear any global state
    import sys
    
    # Remove test modules from cache
    modules_to_remove = [
        name for name in sys.modules.keys() 
        if "test_" in name and "hydra" in name
    ]
    
    for module_name in modules_to_remove:
        if module_name in sys.modules:
            del sys.modules[module_name]
    
    # Reset environment variables that might affect tests
    test_env_vars = [
        "HYDRA_CURRENT_TICKET",
        "HYDRA_EXECUTION_ID", 
        "HYDRA_WORKER_ID"
    ]
    
    for var in test_env_vars:
        if var in os.environ:
            del os.environ[var]


@pytest.fixture(autouse=True)
def test_isolation():
    """Ensure test isolation for each test."""
    ensure_test_isolation()
    yield
    ensure_test_isolation()


def create_test_markers():
    """Create pytest markers for different test categories."""
    return {
        "integration": pytest.mark.integration,
        "slow": pytest.mark.slow,
        "deterministic": pytest.mark.deterministic,
        "ci_safe": pytest.mark.ci_safe,
        "requires_resources": pytest.mark.requires_resources
    }


# Export markers for use in tests
markers = create_test_markers()


def validate_ci_environment():
    """Validate CI environment setup."""
    required_env_vars = [
        "PYTHONHASHSEED",
        "HYDRA_TEST_MODE", 
        "LLM_PROVIDER",
        "DATABASE_URL"
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if var not in os.environ:
            missing_vars.append(var)
    
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {missing_vars}")
    
    # Validate CI-specific settings
    if test_config.ci_mode:
        assert os.environ.get("LLM_PROVIDER") == "mock", "CI must use mock provider"
        assert os.environ.get("HYDRA_TEST_MODE") == "true", "CI must enable test mode"


def generate_test_report(output_file: str = "integration_test_report.json"):
    """Generate comprehensive test report."""
    import json
    
    validation_results = test_results.validate_determinism()
    
    report = {
        "test_environment": {
            "ci_mode": test_config.ci_mode,
            "timeout_multiplier": test_config.timeout_multiplier,
            "max_workers": test_config.max_workers,
            "mock_providers": test_config.mock_providers
        },
        "test_results": test_results.test_results,
        "validation": validation_results,
        "recommendations": []
    }
    
    # Add recommendations based on results
    if validation_results["determinism_score"] < 0.8:
        report["recommendations"].append("Consider reducing test complexity for better determinism")
    
    if test_config.ci_mode and validation_results["successful_tests"] < validation_results["total_tests"]:
        report["recommendations"].append("Some tests failed in CI - check for environment-specific issues")
    
    for operation, timing in validation_results["timing_consistency"].items():
        if not timing["consistent"]:
            report["recommendations"].append(f"Timing for {operation} is inconsistent - consider mocking time-dependent operations")
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


if __name__ == "__main__":
    # Run validation when executed directly
    validate_ci_environment()
    print("✅ CI environment validation passed")
    print(f"CI Mode: {test_config.ci_mode}")
    print(f"Max Workers: {test_config.max_workers}")
    print(f"Timeout Multiplier: {test_config.timeout_multiplier}")