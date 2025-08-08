"""Production safety guardrails and resource management."""

import os
import resource
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

import psutil

# Test mode detection to avoid thread creation issues
TEST_MODE = (
    os.getenv('TESTING') == '1' or
    os.getenv('PYTEST_CURRENT_TEST') is not None or
    'pytest' in str(os.getenv('_', ''))
)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ResourceQuota:
    cpu_percent: float = 80.0
    memory_mb: int = 2048
    disk_io_mb_per_sec: float = 100.0
    network_io_mb_per_sec: float = 50.0
    max_file_handles: int = 1000
    max_threads: int = 50
    max_processes: int = 10
    execution_timeout_seconds: int = 3600


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10
    cooldown_seconds: int = 60


@dataclass
class CostBudget:
    daily_limit_usd: float = 100.0
    monthly_limit_usd: float = 2000.0
    per_request_limit_usd: float = 10.0
    alert_threshold_percent: float = 80.0


@dataclass
class TenantContext:
    tenant_id: str
    quota: ResourceQuota = field(default_factory=ResourceQuota)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    budget: CostBudget = field(default_factory=CostBudget)
    created_at: datetime = field(default_factory=datetime.now)
    request_history: deque = field(default_factory=lambda: deque(maxlen=10000))
    cost_tracking: Dict[str, float] = field(default_factory=dict)
    active_resources: Set[str] = field(default_factory=set)


class ResourceMonitor:
    def __init__(self):
        self.process = psutil.Process()
        self.baseline_memory = self.process.memory_info().rss
        self.monitoring = False
        self.violations = []
        self.monitor_thread = None

    def start_monitoring(self, quota: ResourceQuota, interval: float = 1.0):
        self.monitoring = True
        # Skip thread creation in test mode
        if TEST_MODE:
            return

        try:
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                args=(quota, interval),
                daemon=True
            )
            self.monitor_thread.start()
        except RuntimeError:
            self.monitoring = False

    def stop_monitoring(self):
        self.monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)

    def _monitor_loop(self, quota: ResourceQuota, interval: float):
        while self.monitoring:
            try:
                violations = self.check_violations(quota)
                if violations:
                    self.violations.extend(violations)
                    self._enforce_limits(violations)
                time.sleep(interval)
            except Exception:
                pass

    def check_violations(self, quota: ResourceQuota) -> List[Dict[str, Any]]:
        violations = []

        cpu_percent = self.process.cpu_percent(interval=0.1)
        if cpu_percent > quota.cpu_percent:
            violations.append({
                'type': 'cpu',
                'current': cpu_percent,
                'limit': quota.cpu_percent,
                'timestamp': datetime.now()
            })

        memory_mb = self.process.memory_info().rss / (1024 * 1024)
        if memory_mb > quota.memory_mb:
            violations.append({
                'type': 'memory',
                'current': memory_mb,
                'limit': quota.memory_mb,
                'timestamp': datetime.now()
            })

        num_threads = self.process.num_threads()
        if num_threads > quota.max_threads:
            violations.append({
                'type': 'threads',
                'current': num_threads,
                'limit': quota.max_threads,
                'timestamp': datetime.now()
            })

        try:
            num_fds = self.process.num_fds()
            if num_fds > quota.max_file_handles:
                violations.append({
                    'type': 'file_handles',
                    'current': num_fds,
                    'limit': quota.max_file_handles,
                    'timestamp': datetime.now()
                })
        except AttributeError:
            pass

        return violations

    def _enforce_limits(self, violations: List[Dict[str, Any]]):
        for violation in violations:
            if violation['type'] == 'memory':
                import gc
                gc.collect()
                gc.collect()
                gc.collect()
            elif violation['type'] == 'cpu':
                time.sleep(0.1)

    def get_current_usage(self) -> Dict[str, Any]:
        return {
            'cpu_percent': self.process.cpu_percent(interval=0.1),
            'memory_mb': self.process.memory_info().rss / (1024 * 1024),
            'threads': self.process.num_threads(),
            'open_files': len(self.process.open_files()),
            'connections': len(self.process.connections())
        }


class RateLimiter:
    def __init__(self):
        self.tenant_limiters = {}
        self.lock = threading.Lock()

    def check_rate_limit(
        self, tenant_id: str, config: RateLimitConfig
    ) -> tuple[bool, Optional[float]]:
        with self.lock:
            if tenant_id not in self.tenant_limiters:
                self.tenant_limiters[tenant_id] = {
                    'minute_window': deque(maxlen=config.requests_per_minute),
                    'hour_window': deque(maxlen=config.requests_per_hour),
                    'burst_tokens': config.burst_size,
                    'last_refill': time.time()
                }

            limiter = self.tenant_limiters[tenant_id]
            now = time.time()

            time_since_refill = now - limiter['last_refill']
            if time_since_refill >= 1.0:
                tokens_to_add = min(
                    int(time_since_refill),
                    config.burst_size - limiter['burst_tokens']
                )
                limiter['burst_tokens'] += tokens_to_add
                limiter['last_refill'] = now

            minute_ago = now - 60
            limiter['minute_window'] = deque(
                (t for t in limiter['minute_window'] if t > minute_ago),
                maxlen=config.requests_per_minute
            )

            hour_ago = now - 3600
            limiter['hour_window'] = deque(
                (t for t in limiter['hour_window'] if t > hour_ago),
                maxlen=config.requests_per_hour
            )

            if len(limiter['minute_window']) >= config.requests_per_minute:
                wait_time = 60 - (now - limiter['minute_window'][0])
                return False, wait_time

            if len(limiter['hour_window']) >= config.requests_per_hour:
                wait_time = 3600 - (now - limiter['hour_window'][0])
                return False, wait_time

            if limiter['burst_tokens'] <= 0:
                return False, 1.0

            limiter['burst_tokens'] -= 1
            limiter['minute_window'].append(now)
            limiter['hour_window'].append(now)

            return True, None

    def record_request(self, tenant_id: str, timestamp: Optional[float] = None):
        if timestamp is None:
            timestamp = time.time()

        with self.lock:
            if tenant_id in self.tenant_limiters:
                limiter = self.tenant_limiters[tenant_id]
                limiter['minute_window'].append(timestamp)
                limiter['hour_window'].append(timestamp)

    def get_usage_stats(self, tenant_id: str) -> Dict[str, Any]:
        with self.lock:
            if tenant_id not in self.tenant_limiters:
                return {'requests_last_minute': 0, 'requests_last_hour': 0}

            limiter = self.tenant_limiters[tenant_id]
            now = time.time()
            minute_ago = now - 60
            hour_ago = now - 3600

            minute_count = sum(1 for t in limiter['minute_window'] if t > minute_ago)
            hour_count = sum(1 for t in limiter['hour_window'] if t > hour_ago)

            return {
                'requests_last_minute': minute_count,
                'requests_last_hour': hour_count,
                'burst_tokens_remaining': limiter['burst_tokens']
            }


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        self.lock = threading.Lock()
        self.success_count = 0
        self.half_open_requests = 0

    def call(self, func: Callable, *args, **kwargs) -> Any:
        with self.lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_requests = 0
                else:
                    raise Exception("Circuit breaker is OPEN")

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_requests >= 3:
                    if self.success_count >= 2:
                        self._reset()
                    else:
                        self._trip()
                        raise Exception("Circuit breaker is OPEN")
                self.half_open_requests += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        return (
            self.last_failure_time and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )

    def _on_success(self):
        with self.lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= 2:
                    self._reset()

    def _on_failure(self):
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == CircuitState.HALF_OPEN:
                self._trip()
            elif self.failure_count >= self.failure_threshold:
                self._trip()

    def _trip(self):
        self.state = CircuitState.OPEN
        self.success_count = 0

    def _reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.success_count = 0

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            return {
                'state': self.state.value,
                'failure_count': self.failure_count,
                'last_failure_time': self.last_failure_time
            }


class SandboxExecutor:
    def __init__(self, quota: ResourceQuota):
        self.quota = quota
        self.execution_id = None
        self.start_time = None

    @contextmanager
    def sandboxed_execution(self, tenant_id: str):
        self.execution_id = str(uuid4())
        self.start_time = time.time()

        original_limits = self._get_current_limits()
        resource_monitor = ResourceMonitor()

        try:
            self._apply_resource_limits()
            resource_monitor.start_monitoring(self.quota)

            yield self.execution_id

        finally:
            resource_monitor.stop_monitoring()
            self._restore_limits(original_limits)

            violations = resource_monitor.violations
            if violations:
                self._handle_violations(tenant_id, violations)

    def _apply_resource_limits(self):
        try:
            if hasattr(resource, 'RLIMIT_AS'):
                resource.setrlimit(
                    resource.RLIMIT_AS,
                    (self.quota.memory_mb * 1024 * 1024,
                     self.quota.memory_mb * 1024 * 1024)
                )

            resource.setrlimit(
                resource.RLIMIT_CPU,
                (self.quota.execution_timeout_seconds,
                 self.quota.execution_timeout_seconds)
            )

            resource.setrlimit(
                resource.RLIMIT_NOFILE,
                (self.quota.max_file_handles,
                 self.quota.max_file_handles)
            )

            if hasattr(resource, 'RLIMIT_NPROC'):
                resource.setrlimit(
                    resource.RLIMIT_NPROC,
                    (self.quota.max_processes,
                     self.quota.max_processes)
                )
        except (ValueError, OSError):
            pass

    def _get_current_limits(self) -> Dict[str, tuple]:
        limits = {}
        for limit_name in dir(resource):
            if limit_name.startswith('RLIMIT_'):
                try:
                    limit_const = getattr(resource, limit_name)
                    limits[limit_name] = resource.getrlimit(limit_const)
                except (ValueError, OSError):
                    pass
        return limits

    def _restore_limits(self, original_limits: Dict[str, tuple]):
        for limit_name, limit_value in original_limits.items():
            try:
                limit_const = getattr(resource, limit_name)
                resource.setrlimit(limit_const, limit_value)
            except (ValueError, OSError):
                pass

    def _handle_violations(self, tenant_id: str, violations: List[Dict[str, Any]]):
        for violation in violations:
            print(f"Resource violation for tenant {tenant_id}: {violation}")

    def check_timeout(self) -> bool:
        if self.start_time:
            elapsed = time.time() - self.start_time
            return elapsed > self.quota.execution_timeout_seconds
        return False


class CostController:
    def __init__(self):
        self.tenant_costs = defaultdict(lambda: {
            'daily': defaultdict(float),
            'monthly': defaultdict(float),
            'total': 0.0
        })
        self.lock = threading.Lock()
        self.cost_models = {
            'claude-3-opus': 0.015,
            'claude-3-sonnet': 0.003,
            'claude-4-sonnet': 0.004,
            'claude-4-opus': 0.020
        }

    def check_budget(
        self,
        tenant_id: str,
        estimated_cost: float,
        budget: CostBudget
    ) -> tuple[bool, Optional[str]]:
        with self.lock:
            costs = self.tenant_costs[tenant_id]
            today = datetime.now().date()
            month = today.strftime('%Y-%m')

            daily_spent = costs['daily'][str(today)]
            monthly_spent = costs['monthly'][month]

            if estimated_cost > budget.per_request_limit_usd:
                return False, f"Request cost ${estimated_cost:.2f} exceeds limit"

            if daily_spent + estimated_cost > budget.daily_limit_usd:
                return False, (
                    f"Daily budget exceeded: ${daily_spent:.2f} of "
                    f"${budget.daily_limit_usd:.2f}"
                )

            if monthly_spent + estimated_cost > budget.monthly_limit_usd:
                return False, (
                    f"Monthly budget exceeded: ${monthly_spent:.2f} of "
                    f"${budget.monthly_limit_usd:.2f}"
                )

            alert_daily = daily_spent / budget.daily_limit_usd * 100
            alert_monthly = monthly_spent / budget.monthly_limit_usd * 100

            if alert_daily > budget.alert_threshold_percent:
                print(f"Budget alert: {alert_daily:.1f}% of daily budget used")

            if alert_monthly > budget.alert_threshold_percent:
                print(f"Budget alert: {alert_monthly:.1f}% of monthly budget used")

            return True, None

    def record_cost(self, tenant_id: str, cost: float, metadata: Optional[Dict] = None):
        with self.lock:
            costs = self.tenant_costs[tenant_id]
            today = datetime.now().date()
            month = today.strftime('%Y-%m')

            costs['daily'][str(today)] += cost
            costs['monthly'][month] += cost
            costs['total'] += cost

            if metadata:
                costs.setdefault('breakdown', []).append({
                    'timestamp': datetime.now().isoformat(),
                    'cost': cost,
                    'metadata': metadata
                })

    def estimate_cost(self, model: str, tokens: int) -> float:
        cost_per_1k = self.cost_models.get(model, 0.01)
        return (tokens / 1000) * cost_per_1k

    def get_usage_report(self, tenant_id: str) -> Dict[str, Any]:
        with self.lock:
            costs = self.tenant_costs[tenant_id]
            today = datetime.now().date()
            month = today.strftime('%Y-%m')

            return {
                'daily_spent': costs['daily'][str(today)],
                'monthly_spent': costs['monthly'][month],
                'total_spent': costs['total'],
                'breakdown': costs.get('breakdown', [])[-10:]
            }


class ProductionGuardrails:
    def __init__(self):
        self.tenants = {}
        self.resource_monitor = ResourceMonitor()
        self.rate_limiter = RateLimiter()
        self.cost_controller = CostController()
        self.circuit_breakers = {}
        self.global_lock = threading.Lock()
        self.shutdown_event = threading.Event()

    def register_tenant(
        self,
        tenant_id: str,
        quota: Optional[ResourceQuota] = None,
        rate_limit: Optional[RateLimitConfig] = None,
        budget: Optional[CostBudget] = None
    ) -> TenantContext:
        with self.global_lock:
            if tenant_id not in self.tenants:
                self.tenants[tenant_id] = TenantContext(
                    tenant_id=tenant_id,
                    quota=quota or ResourceQuota(),
                    rate_limit=rate_limit or RateLimitConfig(),
                    budget=budget or CostBudget()
                )
            return self.tenants[tenant_id]

    def check_request(self, tenant_id: str) -> tuple[bool, Optional[str]]:
        if tenant_id not in self.tenants:
            return False, "Tenant not registered"

        tenant = self.tenants[tenant_id]

        allowed, wait_time = self.rate_limiter.check_rate_limit(
            tenant_id, tenant.rate_limit
        )
        if not allowed:
            return False, f"Rate limit exceeded. Retry after {wait_time:.1f} seconds"

        usage = self.resource_monitor.get_current_usage()
        if usage['cpu_percent'] > tenant.quota.cpu_percent:
            return False, f"CPU limit exceeded: {usage['cpu_percent']:.1f}%"

        if usage['memory_mb'] > tenant.quota.memory_mb:
            return False, f"Memory limit exceeded: {usage['memory_mb']:.1f} MB"

        return True, None

    @contextmanager
    def protected_execution(
        self,
        tenant_id: str,
        operation_name: str,
        estimated_tokens: int = 1000,
        model: str = 'claude-3-sonnet'
    ):
        if tenant_id not in self.tenants:
            raise ValueError(f"Tenant {tenant_id} not registered")

        tenant = self.tenants[tenant_id]
        execution_id = str(uuid4())

        estimated_cost = self.cost_controller.estimate_cost(model, estimated_tokens)
        allowed, reason = self.cost_controller.check_budget(
            tenant_id, estimated_cost, tenant.budget
        )
        if not allowed:
            raise ValueError(f"Budget check failed: {reason}")

        allowed, reason = self.check_request(tenant_id)
        if not allowed:
            raise ValueError(f"Request check failed: {reason}")

        if operation_name not in self.circuit_breakers:
            self.circuit_breakers[operation_name] = CircuitBreaker()

        _ = self.circuit_breakers[operation_name]

        sandbox = SandboxExecutor(tenant.quota)

        with sandbox.sandboxed_execution(tenant_id) as sandbox_id:
            tenant.active_resources.add(sandbox_id)

            try:
                start_time = time.time()

                yield execution_id

                duration = time.time() - start_time
                actual_cost = estimated_cost

                self.cost_controller.record_cost(
                    tenant_id, actual_cost,
                    {'operation': operation_name, 'duration': duration}
                )

                tenant.request_history.append({
                    'execution_id': execution_id,
                    'operation': operation_name,
                    'timestamp': datetime.now().isoformat(),
                    'duration': duration,
                    'cost': actual_cost,
                    'success': True
                })

            except Exception as e:
                tenant.request_history.append({
                    'execution_id': execution_id,
                    'operation': operation_name,
                    'timestamp': datetime.now().isoformat(),
                    'error': str(e),
                    'success': False
                })
                raise

            finally:
                tenant.active_resources.discard(sandbox_id)

    def get_tenant_status(self, tenant_id: str) -> Dict[str, Any]:
        if tenant_id not in self.tenants:
            return {'error': 'Tenant not found'}

        tenant = self.tenants[tenant_id]

        return {
            'tenant_id': tenant_id,
            'created_at': tenant.created_at.isoformat(),
            'rate_limit_usage': self.rate_limiter.get_usage_stats(tenant_id),
            'cost_usage': self.cost_controller.get_usage_report(tenant_id),
            'resource_usage': self.resource_monitor.get_current_usage(),
            'active_resources': len(tenant.active_resources),
            'recent_requests': list(tenant.request_history)[-10:],
            'circuit_breakers': {
                name: cb.get_state()
                for name, cb in self.circuit_breakers.items()
            }
        }

    def emergency_shutdown(self, tenant_id: Optional[str] = None):
        self.shutdown_event.set()

        if tenant_id:
            if tenant_id in self.tenants:
                tenant = self.tenants[tenant_id]
                tenant.active_resources.clear()
                print(f"Emergency shutdown for tenant {tenant_id}")
        else:
            for tenant in self.tenants.values():
                tenant.active_resources.clear()
            print("Emergency shutdown for all tenants")

    def cleanup_old_data(self, days_to_keep: int = 30):
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with self.global_lock:
            for tenant in self.tenants.values():
                tenant.request_history = deque(
                    (req for req in tenant.request_history
                     if datetime.fromisoformat(req['timestamp']) > cutoff_date),
                    maxlen=10000
                )


guardrails = ProductionGuardrails()

