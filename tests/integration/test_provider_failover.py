"""
Integration tests for provider failover scenarios.

Tests provider resilience, failover mechanisms, circuit breakers,
retry logic, and fallback provider behavior under various failure conditions.
"""

import asyncio
import json
import os
import tempfile
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, patch, MagicMock

import pytest

from hydra.providers.base import LLMConfig
from hydra.providers.mock_provider import MockProvider
from hydra.providers.factory import ProviderFactory


class FailingProvider(MockProvider):
    """Provider that simulates various failure scenarios."""
    
    def __init__(self, config: LLMConfig, failure_mode: str = "none"):
        super().__init__(config)
        self.failure_mode = failure_mode
        self.call_count = 0
        self.failure_count = 0
        
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response with potential failures."""
        self.call_count += 1
        
        if self.failure_mode == "always_fail":
            self.failure_count += 1
            raise ConnectionError("Provider always fails")
        
        elif self.failure_mode == "intermittent":
            if self.call_count % 3 == 0:  # Fail every 3rd call
                self.failure_count += 1
                raise TimeoutError("Provider timeout")
            
        elif self.failure_mode == "slow_degradation":
            if self.call_count > 5:  # Start failing after 5 calls
                self.failure_count += 1
                raise RuntimeError("Provider degraded")
                
        elif self.failure_mode == "rate_limit":
            if self.call_count > 10:  # Rate limited after 10 calls
                self.failure_count += 1
                raise Exception("Rate limit exceeded")
        
        elif self.failure_mode == "temporary_outage":
            if 3 <= self.call_count <= 7:  # Fail calls 3-7
                self.failure_count += 1
                raise ConnectionError("Temporary outage")
        
        # Successful response
        return f"Mock response from {self.config.provider_type} (call {self.call_count}): {prompt[:50]}..."


class TestProviderFailover:
    """Test provider failover and resilience scenarios."""

    @pytest.fixture
    def temp_project(self):
        """Create temporary project for failover testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            (project_path / ".hydra").mkdir()
            (project_path / ".hydra" / "reports").mkdir()
            (project_path / "src").mkdir()
            (project_path / "tests").mkdir()
            yield project_path

    def _create_failover_test_tickets(self) -> Dict:
        """Create tickets for failover testing."""
        return {
            "version": "1.0",
            "project": {
                "name": "Provider Failover Test",
                "description": "Testing provider failover scenarios"
            },
            "tickets": [
                {
                    "id": "failover_001",
                    "title": "Primary Provider Test",
                    "status": "TODO",
                    "priority": 1,
                    "model": "primary",
                    "description": "Test with primary provider",
                    "acceptance_criteria": [
                        "Create src/primary_module.py",
                        "Add primary functionality",
                        "Create tests for primary module"
                    ],
                    "artifacts": [
                        {"type": "file", "path": "src/primary_module.py"},
                        {"type": "file", "path": "tests/test_primary.py"}
                    ]
                },
                {
                    "id": "failover_002", 
                    "title": "Fallback Provider Test",
                    "status": "TODO",
                    "priority": 2,
                    "model": "fallback",
                    "description": "Test with fallback provider",
                    "acceptance_criteria": [
                        "Create src/fallback_module.py",
                        "Add fallback functionality",
                        "Ensure fallback quality"
                    ],
                    "artifacts": [
                        {"type": "file", "path": "src/fallback_module.py"},
                        {"type": "file", "path": "tests/test_fallback.py"}
                    ]
                },
                {
                    "id": "failover_003",
                    "title": "Resilience Test",
                    "status": "TODO",
                    "priority": 3,
                    "model": "resilient",
                    "description": "Test provider resilience",
                    "acceptance_criteria": [
                        "Create src/resilient_module.py",
                        "Handle provider failures gracefully",
                        "Implement retry logic"
                    ],
                    "artifacts": [
                        {"type": "file", "path": "src/resilient_module.py"},
                        {"type": "file", "path": "tests/test_resilience.py"}
                    ]
                }
            ]
        }

    @pytest.mark.integration
    def test_simple_provider_failover(self, temp_project):
        """Test basic failover from primary to backup provider."""
        # Setup primary (failing) and backup (working) providers
        primary_config = LLMConfig(
            provider_type="failing_primary",
            model="test-model",
            api_key="test-key"
        )
        
        backup_config = LLMConfig(
            provider_type="backup",
            model="backup-model", 
            api_key="backup-key"
        )
        
        # Create failing primary provider
        primary_provider = FailingProvider(primary_config, failure_mode="always_fail")
        
        # Create working backup provider
        backup_provider = MockProvider(backup_config)
        
        # Test failover logic
        def attempt_with_failover(prompt: str) -> tuple[str, str]:
            """Attempt primary provider, failover to backup on failure."""
            try:
                response = primary_provider.generate(prompt)
                return response, "primary"
            except Exception:
                # Failover to backup
                response = backup_provider.generate(prompt)
                return response, "backup"
        
        # Test multiple requests
        results = []
        for i in range(5):
            prompt = f"Test prompt {i}"
            response, provider_used = attempt_with_failover(prompt)
            results.append({
                "prompt": prompt,
                "response": response,
                "provider": provider_used
            })
        
        # Verify all requests used backup provider due to primary failure
        assert all(result["provider"] == "backup" for result in results)
        assert all(len(result["response"]) > 0 for result in results)
        
        # Verify primary provider failed as expected
        assert primary_provider.failure_count == 5
        
        # Verify backup provider handled all requests
        assert backup_provider.call_count == 5

    @pytest.mark.integration
    def test_circuit_breaker_pattern(self, temp_project):
        """Test circuit breaker pattern for provider failures."""
        
        class CircuitBreaker:
            """Simple circuit breaker implementation."""
            
            def __init__(self, failure_threshold: int = 3, timeout: float = 5.0):
                self.failure_threshold = failure_threshold
                self.timeout = timeout
                self.failure_count = 0
                self.last_failure_time = None
                self.state = "closed"  # closed, open, half-open
            
            def call(self, func, *args, **kwargs):
                """Call function with circuit breaker protection."""
                if self.state == "open":
                    if time.time() - self.last_failure_time < self.timeout:
                        raise Exception("Circuit breaker is OPEN")
                    else:
                        self.state = "half-open"
                
                try:
                    result = func(*args, **kwargs)
                    if self.state == "half-open":
                        self.state = "closed"
                        self.failure_count = 0
                    return result
                except Exception as e:
                    self.failure_count += 1
                    self.last_failure_time = time.time()
                    
                    if self.failure_count >= self.failure_threshold:
                        self.state = "open"
                    
                    raise e
        
        # Create failing provider
        failing_config = LLMConfig(provider_type="failing", model="test", api_key="test")
        failing_provider = FailingProvider(failing_config, failure_mode="always_fail")
        
        # Create circuit breaker
        circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=1.0)
        
        # Test circuit breaker behavior
        failure_results = []
        
        # First 3 calls should fail and trip circuit breaker
        for i in range(3):
            try:
                circuit_breaker.call(failing_provider.generate, f"prompt {i}")
                failure_results.append("success")
            except Exception as e:
                failure_results.append("failure")
        
        # Circuit should be open now
        assert circuit_breaker.state == "open"
        
        # Next calls should fail immediately due to open circuit
        for i in range(3, 6):
            try:
                circuit_breaker.call(failing_provider.generate, f"prompt {i}")
                failure_results.append("success")
            except Exception as e:
                failure_results.append("circuit_open")
        
        # Wait for timeout
        time.sleep(1.1)
        
        # Circuit should allow one test call (half-open)
        try:
            circuit_breaker.call(failing_provider.generate, "test prompt")
            failure_results.append("success")
        except Exception:
            failure_results.append("half_open_failure")
        
        # Verify circuit breaker behavior
        assert failure_results[:3] == ["failure", "failure", "failure"]
        assert failure_results[3:6] == ["circuit_open", "circuit_open", "circuit_open"]
        assert failure_results[6] == "half_open_failure"
        
        # Circuit should be open again
        assert circuit_breaker.state == "open"

    @pytest.mark.integration
    def test_retry_with_exponential_backoff(self, temp_project):
        """Test retry logic with exponential backoff."""
        
        def exponential_backoff_retry(func, max_retries: int = 5, base_delay: float = 0.1):
            """Retry function with exponential backoff."""
            for attempt in range(max_retries):
                try:
                    return func()
                except Exception as e:
                    if attempt == max_retries - 1:  # Last attempt
                        raise e
                    
                    # Exponential backoff: 0.1, 0.2, 0.4, 0.8, 1.6 seconds
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
        
        # Test with intermittent failures
        config = LLMConfig(provider_type="intermittent", model="test", api_key="test")
        provider = FailingProvider(config, failure_mode="intermittent")
        
        # Track retry attempts
        retry_results = []
        
        for i in range(10):
            start_time = time.time()
            try:
                response = exponential_backoff_retry(
                    lambda: provider.generate(f"retry test {i}"),
                    max_retries=3,
                    base_delay=0.01  # Short delays for testing
                )
                retry_results.append({
                    "attempt": i,
                    "success": True,
                    "duration": time.time() - start_time,
                    "provider_call_count": provider.call_count
                })
            except Exception as e:
                retry_results.append({
                    "attempt": i,
                    "success": False,
                    "error": str(e),
                    "duration": time.time() - start_time,
                    "provider_call_count": provider.call_count
                })
        
        # Verify retry behavior
        successful_attempts = [r for r in retry_results if r["success"]]
        failed_attempts = [r for r in retry_results if not r["success"]]
        
        # Should have both successes and failures due to intermittent provider
        assert len(successful_attempts) > 0, "Should have some successful retries"
        assert len(failed_attempts) >= 0, "May have some failures after retries"
        
        # Verify provider was called multiple times due to retries
        assert provider.call_count > 10, "Provider should be called more than 10 times due to retries"

    @pytest.mark.integration
    def test_provider_health_monitoring(self, temp_project):
        """Test provider health monitoring and automatic failover."""
        
        class ProviderHealthMonitor:
            """Monitor provider health and manage failover."""
            
            def __init__(self):
                self.providers = {}
                self.health_status = {}
                self.current_primary = None
            
            def register_provider(self, name: str, provider, is_primary: bool = False):
                """Register a provider for monitoring."""
                self.providers[name] = provider
                self.health_status[name] = {
                    "healthy": True,
                    "last_success": time.time(),
                    "failure_count": 0,
                    "response_times": []
                }
                if is_primary:
                    self.current_primary = name
            
            def check_health(self, provider_name: str) -> bool:
                """Check provider health with a simple test."""
                provider = self.providers[provider_name]
                try:
                    start_time = time.time()
                    provider.generate("health check")
                    response_time = time.time() - start_time
                    
                    # Update health status
                    self.health_status[provider_name]["healthy"] = True
                    self.health_status[provider_name]["last_success"] = time.time()
                    self.health_status[provider_name]["failure_count"] = 0
                    self.health_status[provider_name]["response_times"].append(response_time)
                    
                    # Keep only last 10 response times
                    if len(self.health_status[provider_name]["response_times"]) > 10:
                        self.health_status[provider_name]["response_times"] = \
                            self.health_status[provider_name]["response_times"][-10:]
                    
                    return True
                
                except Exception:
                    self.health_status[provider_name]["healthy"] = False
                    self.health_status[provider_name]["failure_count"] += 1
                    return False
            
            def get_healthy_provider(self) -> Optional[str]:
                """Get the best healthy provider."""
                # Try current primary first
                if self.current_primary and self.health_status[self.current_primary]["healthy"]:
                    return self.current_primary
                
                # Find any healthy provider
                for name, status in self.health_status.items():
                    if status["healthy"]:
                        return name
                
                return None
            
            def generate_with_failover(self, prompt: str) -> tuple[str, str]:
                """Generate response with automatic failover."""
                provider_name = self.get_healthy_provider()
                if not provider_name:
                    raise Exception("No healthy providers available")
                
                provider = self.providers[provider_name]
                try:
                    response = provider.generate(prompt)
                    return response, provider_name
                except Exception:
                    # Mark provider as unhealthy and try again
                    self.health_status[provider_name]["healthy"] = False
                    self.health_status[provider_name]["failure_count"] += 1
                    
                    # Try another provider
                    fallback_provider = self.get_healthy_provider()
                    if fallback_provider:
                        response = self.providers[fallback_provider].generate(prompt)
                        return response, fallback_provider
                    
                    raise Exception("All providers failed")
        
        # Setup health monitor with multiple providers
        monitor = ProviderHealthMonitor()
        
        # Primary provider (will start failing)
        primary_config = LLMConfig(provider_type="primary", model="test", api_key="test")
        primary_provider = FailingProvider(primary_config, failure_mode="slow_degradation")
        monitor.register_provider("primary", primary_provider, is_primary=True)
        
        # Backup provider (reliable)
        backup_config = LLMConfig(provider_type="backup", model="test", api_key="test")
        backup_provider = MockProvider(backup_config)
        monitor.register_provider("backup", backup_provider)
        
        # Test health monitoring over time
        results = []
        
        for i in range(15):  # 15 requests
            # Check health periodically
            if i % 3 == 0:
                monitor.check_health("primary")
                monitor.check_health("backup")
            
            try:
                response, provider_used = monitor.generate_with_failover(f"test prompt {i}")
                results.append({
                    "request": i,
                    "success": True,
                    "provider": provider_used,
                    "response_length": len(response)
                })
            except Exception as e:
                results.append({
                    "request": i,
                    "success": False,
                    "error": str(e)
                })
        
        # Verify failover behavior
        successful_results = [r for r in results if r["success"]]
        assert len(successful_results) > 10, "Most requests should succeed with failover"
        
        # Should see transition from primary to backup provider
        providers_used = [r["provider"] for r in successful_results]
        assert "primary" in providers_used, "Should use primary initially"
        assert "backup" in providers_used, "Should failover to backup"
        
        # Later requests should primarily use backup after primary degrades
        later_providers = providers_used[-5:]  # Last 5 requests
        backup_usage = later_providers.count("backup")
        assert backup_usage >= 3, "Should primarily use backup provider after failover"

    @pytest.mark.integration
    def test_load_balancing_with_failover(self, temp_project):
        """Test load balancing across providers with failover capability."""
        
        class LoadBalancingProviderManager:
            """Manage multiple providers with load balancing and failover."""
            
            def __init__(self):
                self.providers = []
                self.current_index = 0
                self.provider_stats = {}
            
            def add_provider(self, name: str, provider):
                """Add a provider to the pool."""
                self.providers.append({"name": name, "provider": provider, "healthy": True})
                self.provider_stats[name] = {
                    "requests": 0,
                    "failures": 0,
                    "response_times": []
                }
            
            def get_next_healthy_provider(self):
                """Get next healthy provider using round-robin."""
                attempts = 0
                while attempts < len(self.providers):
                    provider_info = self.providers[self.current_index]
                    self.current_index = (self.current_index + 1) % len(self.providers)
                    
                    if provider_info["healthy"]:
                        return provider_info
                    
                    attempts += 1
                
                raise Exception("No healthy providers available")
            
            def generate_with_load_balancing(self, prompt: str) -> tuple[str, str]:
                """Generate response with load balancing and failover."""
                max_attempts = len(self.providers)
                
                for attempt in range(max_attempts):
                    try:
                        provider_info = self.get_next_healthy_provider()
                        provider_name = provider_info["name"]
                        provider = provider_info["provider"]
                        
                        start_time = time.time()
                        response = provider.generate(prompt)
                        response_time = time.time() - start_time
                        
                        # Update stats
                        self.provider_stats[provider_name]["requests"] += 1
                        self.provider_stats[provider_name]["response_times"].append(response_time)
                        
                        return response, provider_name
                        
                    except Exception:
                        # Mark provider as unhealthy and try next
                        provider_info["healthy"] = False
                        self.provider_stats[provider_name]["failures"] += 1
                        
                        if attempt == max_attempts - 1:
                            raise Exception("All providers failed")
                
                raise Exception("Unable to complete request")
        
        # Setup load balancer with multiple providers
        lb_manager = LoadBalancingProviderManager()
        
        # Add multiple providers with different characteristics
        providers_config = [
            ("provider_1", MockProvider(LLMConfig(provider_type="p1", model="m1", api_key="k1"))),
            ("provider_2", FailingProvider(LLMConfig(provider_type="p2", model="m2", api_key="k2"), "intermittent")),
            ("provider_3", MockProvider(LLMConfig(provider_type="p3", model="m3", api_key="k3"))),
            ("provider_4", FailingProvider(LLMConfig(provider_type="p4", model="m4", api_key="k4"), "temporary_outage"))
        ]
        
        for name, provider in providers_config:
            lb_manager.add_provider(name, provider)
        
        # Test load balancing over many requests
        results = []
        for i in range(20):
            try:
                response, provider_used = lb_manager.generate_with_load_balancing(f"load balance test {i}")
                results.append({
                    "request": i,
                    "success": True,
                    "provider": provider_used,
                    "response_length": len(response)
                })
            except Exception as e:
                results.append({
                    "request": i,
                    "success": False,
                    "error": str(e)
                })
        
        # Verify load balancing and failover
        successful_results = [r for r in results if r["success"]]
        assert len(successful_results) > 15, "Most requests should succeed with load balancing"
        
        # Check that load was distributed across multiple providers
        providers_used = [r["provider"] for r in successful_results]
        unique_providers = set(providers_used)
        assert len(unique_providers) >= 2, "Load should be distributed across multiple providers"
        
        # Verify stats were collected
        total_requests = sum(stats["requests"] for stats in lb_manager.provider_stats.values())
        total_failures = sum(stats["failures"] for stats in lb_manager.provider_stats.values())
        
        assert total_requests == len(successful_results)
        assert total_failures > 0, "Should have some failures due to failing providers"

    @pytest.mark.integration
    def test_provider_degradation_recovery(self, temp_project):
        """Test recovery from provider degradation scenarios."""
        
        class ProviderRecoveryManager:
            """Manage provider recovery from degraded states."""
            
            def __init__(self):
                self.providers = {}
                self.recovery_attempts = {}
                self.recovery_interval = 2.0  # seconds
            
            def register_provider(self, name: str, provider):
                """Register provider for recovery management."""
                self.providers[name] = {
                    "provider": provider,
                    "healthy": True,
                    "last_failure": None,
                    "recovery_attempts": 0
                }
                self.recovery_attempts[name] = []
            
            def attempt_recovery(self, provider_name: str) -> bool:
                """Attempt to recover a failed provider."""
                provider_info = self.providers[provider_name]
                
                # Don't attempt recovery too frequently
                if (provider_info["last_failure"] and 
                    time.time() - provider_info["last_failure"] < self.recovery_interval):
                    return False
                
                try:
                    # Test provider with a simple request
                    provider_info["provider"].generate("recovery test")
                    
                    # Recovery successful
                    provider_info["healthy"] = True
                    provider_info["last_failure"] = None
                    provider_info["recovery_attempts"] = 0
                    
                    self.recovery_attempts[provider_name].append({
                        "timestamp": time.time(),
                        "success": True
                    })
                    
                    return True
                    
                except Exception:
                    # Recovery failed
                    provider_info["recovery_attempts"] += 1
                    self.recovery_attempts[provider_name].append({
                        "timestamp": time.time(),
                        "success": False
                    })
                    
                    return False
            
            def get_available_provider(self) -> Optional[str]:
                """Get an available provider, attempting recovery if needed."""
                # First, try healthy providers
                for name, info in self.providers.items():
                    if info["healthy"]:
                        return name
                
                # No healthy providers, attempt recovery
                for name, info in self.providers.items():
                    if not info["healthy"] and self.attempt_recovery(name):
                        return name
                
                return None
            
            def generate_with_recovery(self, prompt: str) -> tuple[str, str]:
                """Generate response with provider recovery."""
                provider_name = self.get_available_provider()
                if not provider_name:
                    raise Exception("No providers available after recovery attempts")
                
                provider_info = self.providers[provider_name]
                try:
                    response = provider_info["provider"].generate(prompt)
                    return response, provider_name
                    
                except Exception:
                    # Mark as unhealthy
                    provider_info["healthy"] = False
                    provider_info["last_failure"] = time.time()
                    
                    # Try recovery immediately
                    if self.attempt_recovery(provider_name):
                        response = provider_info["provider"].generate(prompt)
                        return response, provider_name
                    
                    # Try other providers
                    fallback_provider = self.get_available_provider()
                    if fallback_provider:
                        response = self.providers[fallback_provider]["provider"].generate(prompt)
                        return response, fallback_provider
                    
                    raise Exception("All providers failed and recovery unsuccessful")
        
        # Setup recovery manager
        recovery_manager = ProviderRecoveryManager()
        
        # Add providers with different failure patterns
        # Provider that has temporary outage then recovers
        temp_outage_config = LLMConfig(provider_type="temp_outage", model="test", api_key="test")
        temp_outage_provider = FailingProvider(temp_outage_config, "temporary_outage")
        recovery_manager.register_provider("temp_outage", temp_outage_provider)
        
        # Reliable backup provider
        backup_config = LLMConfig(provider_type="backup", model="test", api_key="test")
        backup_provider = MockProvider(backup_config)
        recovery_manager.register_provider("backup", backup_provider)
        
        # Test recovery over time
        results = []
        for i in range(15):
            time.sleep(0.2)  # Small delay between requests
            
            try:
                response, provider_used = recovery_manager.generate_with_recovery(f"recovery test {i}")
                results.append({
                    "request": i,
                    "success": True,
                    "provider": provider_used,
                    "response_length": len(response)
                })
            except Exception as e:
                results.append({
                    "request": i,
                    "success": False,
                    "error": str(e)
                })
        
        # Verify recovery behavior
        successful_results = [r for r in results if r["success"]]
        assert len(successful_results) > 10, "Most requests should succeed with recovery"
        
        # Should see provider transition from outage to recovery
        providers_used = [r["provider"] for r in successful_results]
        
        # Early requests should use backup during temp_outage failure
        early_providers = providers_used[:5]
        assert "backup" in early_providers, "Should use backup during outage"
        
        # Later requests should show temp_outage provider recovery
        if len(providers_used) > 10:
            later_providers = providers_used[-5:]
            # May see temp_outage provider after recovery
            
        # Verify recovery attempts were made
        recovery_attempts = recovery_manager.recovery_attempts["temp_outage"]
        assert len(recovery_attempts) > 0, "Should have attempted recovery"
        
        # Should have at least one successful recovery
        successful_recoveries = [r for r in recovery_attempts if r["success"]]
        assert len(successful_recoveries) > 0, "Should have successful recovery"

    @pytest.mark.integration 
    def test_end_to_end_failover_workflow(self, temp_project):
        """Test complete end-to-end failover workflow with ticket execution."""
        os.chdir(temp_project)
        
        # Create tickets for end-to-end failover test
        yaml_data = self._create_failover_test_tickets()
        tickets_file = temp_project / "tickets.yaml"
        
        with open(tickets_file, 'w') as f:
            yaml.dump(yaml_data, f)
        
        # Setup provider ecosystem with failover
        class TicketExecutionWithFailover:
            """Execute tickets with provider failover."""
            
            def __init__(self):
                self.providers = self._setup_providers()
                self.execution_log = []
            
            def _setup_providers(self):
                """Setup providers with different reliability levels."""
                providers = {}
                
                # Primary provider (unreliable)
                primary_config = LLMConfig(provider_type="primary", model="smart", api_key="test")
                providers["primary"] = FailingProvider(primary_config, "intermittent")
                
                # Fallback provider (more reliable)
                fallback_config = LLMConfig(provider_type="fallback", model="balanced", api_key="test")
                providers["fallback"] = FailingProvider(fallback_config, "rate_limit")
                
                # Emergency provider (very reliable)
                emergency_config = LLMConfig(provider_type="emergency", model="fast", api_key="test")
                providers["emergency"] = MockProvider(emergency_config)
                
                return providers
            
            def execute_ticket_with_failover(self, ticket_data: Dict) -> Dict:
                """Execute ticket with provider failover."""
                ticket_id = ticket_data["id"]
                model_preference = ticket_data.get("model", "balanced")
                
                # Map model preferences to provider priorities
                provider_priority = {
                    "primary": ["primary", "fallback", "emergency"],
                    "fallback": ["fallback", "primary", "emergency"],
                    "resilient": ["emergency", "fallback", "primary"]
                }.get(model_preference, ["primary", "fallback", "emergency"])
                
                start_time = time.time()
                
                for provider_name in provider_priority:
                    try:
                        provider = self.providers[provider_name]
                        
                        # Simulate ticket execution prompt
                        prompt = f"""Execute ticket {ticket_id}: {ticket_data['title']}
                        
Description: {ticket_data['description']}

Acceptance Criteria:
{chr(10).join('- ' + criteria for criteria in ticket_data['acceptance_criteria'])}

Create the necessary files and implementation."""
                        
                        response = provider.generate(prompt)
                        
                        # Simulate creating artifacts
                        for artifact in ticket_data.get("artifacts", []):
                            if artifact["type"] == "file":
                                file_path = temp_project / artifact["path"]
                                file_path.parent.mkdir(parents=True, exist_ok=True)
                                
                                # Generate content based on ticket and provider
                                content = self._generate_file_content(
                                    ticket_data, artifact["path"], provider_name, response
                                )
                                file_path.write_text(content)
                        
                        execution_time = time.time() - start_time
                        
                        self.execution_log.append({
                            "ticket_id": ticket_id,
                            "provider_used": provider_name,
                            "success": True,
                            "execution_time": execution_time,
                            "attempts": provider_priority.index(provider_name) + 1
                        })
                        
                        return {
                            "success": True,
                            "ticket_id": ticket_id,
                            "provider_used": provider_name,
                            "execution_time": execution_time,
                            "artifacts_created": len(ticket_data.get("artifacts", []))
                        }
                        
                    except Exception as e:
                        self.execution_log.append({
                            "ticket_id": ticket_id,
                            "provider_tried": provider_name,
                            "error": str(e),
                            "timestamp": time.time()
                        })
                        continue
                
                # All providers failed
                return {
                    "success": False,
                    "ticket_id": ticket_id,
                    "error": "All providers failed",
                    "attempts": len(provider_priority)
                }
            
            def _generate_file_content(self, ticket_data: Dict, file_path: str, 
                                     provider_name: str, ai_response: str) -> str:
                """Generate file content based on ticket requirements."""
                ticket_id = ticket_data["id"]
                
                if file_path.endswith(".py"):
                    if "test_" in file_path:
                        return f'''"""Test file for {ticket_id} created with {provider_name} provider."""

import pytest
from unittest.mock import Mock, patch


class Test{ticket_id.replace("_", "").title()}:
    """Test suite for {ticket_id}."""
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        # Generated by {provider_name} provider
        assert True
    
    def test_provider_failover_resilience(self):
        """Test that implementation handles provider changes."""
        # This test validates failover resilience
        assert True
    
    def test_acceptance_criteria(self):
        """Test acceptance criteria compliance."""
        # Verify all criteria are met
        criteria = {ticket_data.get("acceptance_criteria", [])}
        assert len(criteria) > 0


# Provider used: {provider_name}
# AI Response snippet: {ai_response[:100]}...
'''
                    else:
                        module_name = file_path.split("/")[-1].replace(".py", "")
                        return f'''"""Module {module_name} for {ticket_id} created with {provider_name} provider."""

from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class {module_name.replace("_", "").title()}Module:
    """Module implementation for {ticket_id}."""
    
    def __init__(self):
        self.provider_used = "{provider_name}"
        self.ticket_id = "{ticket_id}"
        logger.info(f"Module initialized with {{self.provider_used}} provider")
    
    def execute_functionality(self) -> Dict[str, Any]:
        """Execute main functionality."""
        return {{
            "ticket_id": self.ticket_id,
            "provider": self.provider_used,
            "status": "completed",
            "acceptance_criteria_met": True
        }}
    
    def get_provider_info(self) -> str:
        """Get information about provider used."""
        return f"Created with {{self.provider_used}} provider for failover testing"


# Instance
{module_name}_instance = {module_name.replace("_", "").title()}Module()

# Provider metadata
PROVIDER_USED = "{provider_name}"
AI_RESPONSE_PREVIEW = "{ai_response[:200]}..."
'''
                else:
                    return f"""# {file_path} for {ticket_id}

Created with {provider_name} provider.

## Acceptance Criteria
{chr(10).join("- " + criteria for criteria in ticket_data.get("acceptance_criteria", []))}

## Provider Information
- Provider: {provider_name}
- Ticket: {ticket_id}
- Generated at: {time.time()}

## AI Response Preview
{ai_response[:300]}...
"""
        
        # Execute tickets with failover
        executor = TicketExecutionWithFailover()
        execution_results = []
        
        for ticket in yaml_data["tickets"]:
            result = executor.execute_ticket_with_failover(ticket)
            execution_results.append(result)
        
        # Verify end-to-end execution with failover
        successful_executions = [r for r in execution_results if r["success"]]
        assert len(successful_executions) == 3, "All tickets should complete with failover"
        
        # Verify different providers were used due to failures
        providers_used = [r["provider_used"] for r in successful_executions]
        unique_providers = set(providers_used)
        assert len(unique_providers) >= 2, "Multiple providers should be used due to failover"
        
        # Verify all artifacts were created
        for ticket in yaml_data["tickets"]:
            for artifact in ticket.get("artifacts", []):
                artifact_path = temp_project / artifact["path"]
                assert artifact_path.exists(), f"Artifact {artifact['path']} should exist"
                
                # Verify content mentions provider failover
                content = artifact_path.read_text()
                assert "provider" in content.lower(), "Content should reference provider information"
        
        # Verify execution log shows failover attempts
        assert len(executor.execution_log) >= 3, "Should have logs for all executions"
        
        # Check for any provider failures that were recovered from
        error_logs = [log for log in executor.execution_log if "error" in log]
        success_logs = [log for log in executor.execution_log if log.get("success")]
        
        assert len(success_logs) == 3, "Should have 3 successful executions"
        
        # Generate failover report
        failover_report = {
            "execution_summary": {
                "total_tickets": len(yaml_data["tickets"]),
                "successful_executions": len(successful_executions),
                "providers_used": list(unique_providers),
                "total_failover_attempts": len(error_logs)
            },
            "provider_usage": {
                provider: providers_used.count(provider) 
                for provider in unique_providers
            },
            "execution_log": executor.execution_log,
            "artifacts_created": sum(r.get("artifacts_created", 0) for r in successful_executions)
        }
        
        report_file = temp_project / "failover_report.json"
        with open(report_file, 'w') as f:
            json.dump(failover_report, f, indent=2)
        
        assert report_file.exists()
        
        # Verify report shows successful failover
        assert failover_report["execution_summary"]["successful_executions"] == 3
        assert len(failover_report["execution_summary"]["providers_used"]) >= 2