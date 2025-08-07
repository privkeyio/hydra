"""Unit tests for production safety guardrails."""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from hydra.safety.guardrails import (
    ResourceQuota, RateLimitConfig, CostBudget, TenantContext,
    ResourceMonitor, RateLimiter, CircuitBreaker, CircuitState,
    SandboxExecutor, CostController, ProductionGuardrails
)


class TestResourceMonitor:
    def test_init(self):
        monitor = ResourceMonitor()
        assert monitor.process is not None
        assert monitor.monitoring is False
        assert len(monitor.violations) == 0

    def test_check_violations_no_issues(self):
        monitor = ResourceMonitor()
        quota = ResourceQuota(cpu_percent=100.0, memory_mb=10000)
        violations = monitor.check_violations(quota)
        assert len(violations) == 0

    def test_check_violations_with_issues(self):
        monitor = ResourceMonitor()
        quota = ResourceQuota(cpu_percent=0.0, memory_mb=1, max_threads=1)
        violations = monitor.check_violations(quota)
        assert len(violations) >= 1
        assert any(v['type'] in ['memory', 'threads', 'cpu'] for v in violations)

    def test_get_current_usage(self):
        monitor = ResourceMonitor()
        usage = monitor.get_current_usage()
        assert 'cpu_percent' in usage
        assert 'memory_mb' in usage
        assert 'threads' in usage
        assert 'open_files' in usage
        assert 'connections' in usage
        assert usage['memory_mb'] > 0
        assert usage['threads'] > 0

    @patch('time.sleep')
    def test_monitoring_lifecycle(self, mock_sleep):
        monitor = ResourceMonitor()
        quota = ResourceQuota()
        
        monitor.start_monitoring(quota, interval=0.1)
        assert monitor.monitoring is True
        
        time.sleep(0.2)
        monitor.stop_monitoring()
        assert monitor.monitoring is False


class TestRateLimiter:
    def test_init(self):
        limiter = RateLimiter()
        assert len(limiter.tenant_limiters) == 0

    def test_first_request_allowed(self):
        limiter = RateLimiter()
        config = RateLimitConfig(requests_per_minute=10)
        allowed, wait_time = limiter.check_rate_limit('tenant1', config)
        assert allowed is True
        assert wait_time is None

    def test_rate_limit_per_minute(self):
        limiter = RateLimiter()
        config = RateLimitConfig(requests_per_minute=2, burst_size=0)
        
        limiter.check_rate_limit('tenant1', config)
        limiter.check_rate_limit('tenant1', config)
        
        allowed, wait_time = limiter.check_rate_limit('tenant1', config)
        assert allowed is False
        assert wait_time is not None
        assert wait_time > 0

    def test_burst_tokens(self):
        limiter = RateLimiter()
        config = RateLimitConfig(requests_per_minute=100, burst_size=3)
        
        for _ in range(3):
            allowed, _ = limiter.check_rate_limit('tenant1', config)
            assert allowed is True
        
        stats = limiter.get_usage_stats('tenant1')
        assert stats['burst_tokens_remaining'] == 0

    def test_multiple_tenants(self):
        limiter = RateLimiter()
        config = RateLimitConfig(requests_per_minute=1)
        
        allowed1, _ = limiter.check_rate_limit('tenant1', config)
        allowed2, _ = limiter.check_rate_limit('tenant2', config)
        
        assert allowed1 is True
        assert allowed2 is True

    def test_usage_stats(self):
        limiter = RateLimiter()
        config = RateLimitConfig()
        
        limiter.check_rate_limit('tenant1', config)
        limiter.check_rate_limit('tenant1', config)
        
        stats = limiter.get_usage_stats('tenant1')
        assert stats['requests_last_minute'] >= 2
        assert stats['requests_last_hour'] >= 2


class TestCircuitBreaker:
    def test_init(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_successful_calls(self):
        cb = CircuitBreaker()
        
        def success_func():
            return "success"
        
        for _ in range(10):
            result = cb.call(success_func)
            assert result == "success"
        
        assert cb.state == CircuitState.CLOSED

    def test_failure_trips_circuit(self):
        cb = CircuitBreaker(failure_threshold=2)
        
        def failing_func():
            raise ValueError("test error")
        
        with pytest.raises(ValueError):
            cb.call(failing_func)
        
        with pytest.raises(ValueError):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            cb.call(failing_func)

    def test_half_open_recovery(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
        
        def failing_func():
            raise ValueError("test")
        
        def success_func():
            return "success"
        
        with pytest.raises(ValueError):
            cb.call(failing_func)
        with pytest.raises(ValueError):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        time.sleep(0.1)
        
        result = cb.call(success_func)
        assert result == "success"
        
        result = cb.call(success_func)
        assert result == "success"
        
        assert cb.state == CircuitState.CLOSED

    def test_get_state(self):
        cb = CircuitBreaker()
        state = cb.get_state()
        assert state['state'] == 'closed'
        assert state['failure_count'] == 0


class TestSandboxExecutor:
    def test_init(self):
        quota = ResourceQuota()
        sandbox = SandboxExecutor(quota)
        assert sandbox.quota == quota
        assert sandbox.execution_id is None

    def test_sandboxed_execution_context(self):
        quota = ResourceQuota()
        sandbox = SandboxExecutor(quota)
        
        with sandbox.sandboxed_execution('tenant1') as exec_id:
            assert exec_id is not None
            assert sandbox.execution_id == exec_id
            assert sandbox.start_time is not None

    def test_check_timeout(self):
        quota = ResourceQuota(execution_timeout_seconds=1)
        sandbox = SandboxExecutor(quota)
        
        assert sandbox.check_timeout() is False
        
        sandbox.start_time = time.time() - 2
        assert sandbox.check_timeout() is True

    @patch('resource.setrlimit')
    @patch('resource.getrlimit')
    def test_resource_limits_applied(self, mock_getrlimit, mock_setrlimit):
        mock_getrlimit.return_value = (1000, 1000)
        
        quota = ResourceQuota(memory_mb=512)
        sandbox = SandboxExecutor(quota)
        
        with sandbox.sandboxed_execution('tenant1'):
            pass
        
        assert mock_setrlimit.called


class TestCostController:
    def test_init(self):
        controller = CostController()
        assert len(controller.tenant_costs) == 0

    def test_estimate_cost(self):
        controller = CostController()
        cost = controller.estimate_cost('claude-3-opus', 1000)
        assert cost == 0.015

    def test_check_budget_within_limits(self):
        controller = CostController()
        budget = CostBudget(daily_limit_usd=10.0, per_request_limit_usd=1.0)
        
        allowed, reason = controller.check_budget('tenant1', 0.5, budget)
        assert allowed is True
        assert reason is None

    def test_check_budget_exceeds_per_request(self):
        controller = CostController()
        budget = CostBudget(per_request_limit_usd=1.0)
        
        allowed, reason = controller.check_budget('tenant1', 2.0, budget)
        assert allowed is False
        assert "exceeds limit" in reason

    def test_check_budget_exceeds_daily(self):
        controller = CostController()
        budget = CostBudget(daily_limit_usd=5.0)
        
        controller.record_cost('tenant1', 4.0)
        
        allowed, reason = controller.check_budget('tenant1', 2.0, budget)
        assert allowed is False
        assert "Daily budget exceeded" in reason

    def test_record_cost(self):
        controller = CostController()
        
        controller.record_cost('tenant1', 1.5, {'operation': 'test'})
        controller.record_cost('tenant1', 2.0)
        
        report = controller.get_usage_report('tenant1')
        assert report['total_spent'] == 3.5
        assert report['daily_spent'] == 3.5

    def test_usage_report(self):
        controller = CostController()
        
        controller.record_cost('tenant1', 5.0)
        
        report = controller.get_usage_report('tenant1')
        assert report['daily_spent'] == 5.0
        assert report['monthly_spent'] == 5.0
        assert report['total_spent'] == 5.0


class TestProductionGuardrails:
    def test_init(self):
        guardrails = ProductionGuardrails()
        assert len(guardrails.tenants) == 0
        assert guardrails.shutdown_event.is_set() is False

    def test_register_tenant(self):
        guardrails = ProductionGuardrails()
        
        tenant = guardrails.register_tenant('tenant1')
        assert tenant.tenant_id == 'tenant1'
        assert tenant.quota is not None
        assert tenant.rate_limit is not None
        assert tenant.budget is not None

    def test_register_tenant_with_custom_config(self):
        guardrails = ProductionGuardrails()
        
        quota = ResourceQuota(cpu_percent=50.0)
        rate_limit = RateLimitConfig(requests_per_minute=30)
        budget = CostBudget(daily_limit_usd=50.0)
        
        tenant = guardrails.register_tenant(
            'tenant1',
            quota=quota,
            rate_limit=rate_limit,
            budget=budget
        )
        
        assert tenant.quota.cpu_percent == 50.0
        assert tenant.rate_limit.requests_per_minute == 30
        assert tenant.budget.daily_limit_usd == 50.0

    def test_check_request_unregistered_tenant(self):
        guardrails = ProductionGuardrails()
        
        allowed, reason = guardrails.check_request('unknown')
        assert allowed is False
        assert "not registered" in reason

    def test_check_request_allowed(self):
        guardrails = ProductionGuardrails()
        guardrails.register_tenant('tenant1')
        
        allowed, reason = guardrails.check_request('tenant1')
        assert allowed is True
        assert reason is None

    def test_protected_execution_success(self):
        guardrails = ProductionGuardrails()
        guardrails.register_tenant('tenant1')
        
        with guardrails.protected_execution(
            'tenant1', 'test_operation', estimated_tokens=100
        ) as exec_id:
            assert exec_id is not None

    def test_protected_execution_unregistered_tenant(self):
        guardrails = ProductionGuardrails()
        
        with pytest.raises(ValueError, match="not registered"):
            with guardrails.protected_execution('unknown', 'test'):
                pass

    def test_protected_execution_budget_exceeded(self):
        guardrails = ProductionGuardrails()
        budget = CostBudget(per_request_limit_usd=0.01)
        guardrails.register_tenant('tenant1', budget=budget)
        
        with pytest.raises(ValueError, match="Budget check failed"):
            with guardrails.protected_execution(
                'tenant1', 'test', estimated_tokens=10000
            ):
                pass

    def test_get_tenant_status(self):
        guardrails = ProductionGuardrails()
        guardrails.register_tenant('tenant1')
        
        status = guardrails.get_tenant_status('tenant1')
        assert status['tenant_id'] == 'tenant1'
        assert 'created_at' in status
        assert 'rate_limit_usage' in status
        assert 'cost_usage' in status
        assert 'resource_usage' in status

    def test_get_tenant_status_unknown(self):
        guardrails = ProductionGuardrails()
        
        status = guardrails.get_tenant_status('unknown')
        assert 'error' in status

    def test_emergency_shutdown_specific_tenant(self):
        guardrails = ProductionGuardrails()
        tenant = guardrails.register_tenant('tenant1')
        tenant.active_resources.add('resource1')
        
        guardrails.emergency_shutdown('tenant1')
        assert len(tenant.active_resources) == 0
        assert guardrails.shutdown_event.is_set()

    def test_emergency_shutdown_all_tenants(self):
        guardrails = ProductionGuardrails()
        tenant1 = guardrails.register_tenant('tenant1')
        tenant2 = guardrails.register_tenant('tenant2')
        
        tenant1.active_resources.add('resource1')
        tenant2.active_resources.add('resource2')
        
        guardrails.emergency_shutdown()
        
        assert len(tenant1.active_resources) == 0
        assert len(tenant2.active_resources) == 0
        assert guardrails.shutdown_event.is_set()

    def test_cleanup_old_data(self):
        guardrails = ProductionGuardrails()
        tenant = guardrails.register_tenant('tenant1')
        
        old_request = {
            'execution_id': 'old',
            'timestamp': (datetime.now() - timedelta(days=40)).isoformat()
        }
        recent_request = {
            'execution_id': 'recent',
            'timestamp': datetime.now().isoformat()
        }
        
        tenant.request_history.append(old_request)
        tenant.request_history.append(recent_request)
        
        guardrails.cleanup_old_data(days_to_keep=30)
        
        assert len(tenant.request_history) == 1
        assert tenant.request_history[0]['execution_id'] == 'recent'