"""OpenTelemetry monitoring and observability for Hydra."""

import logging
import os
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - '
                'request_id=%(request_id)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _log(self, level: str, message: str, **kwargs):
        extra = {'request_id': request_id.get() or 'none'}
        extra.update(kwargs)
        getattr(self.logger, level)(message, extra=extra)

    def info(self, message: str, **kwargs):
        self._log('info', message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log('error', message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log('warning', message, **kwargs)

    def debug(self, message: str, **kwargs):
        self._log('debug', message, **kwargs)


class AlertingManager:
    def __init__(self):
        self.alerts = []
        self.thresholds = {
            'error_rate': 0.05,
            'response_time_p99': 5.0,
            'agent_failure_rate': 0.1,
            'memory_usage': 0.8,
            'cpu_usage': 0.8
        }
        self.alert_window = timedelta(minutes=5)
        self.metrics_history = []

    def check_alerts(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        now = datetime.now()
        triggered_alerts = []

        for metric, threshold in self.thresholds.items():
            if metric in metrics and metrics[metric] > threshold:
                alert = {
                    'id': str(uuid.uuid4()),
                    'metric': metric,
                    'value': metrics[metric],
                    'threshold': threshold,
                    'timestamp': now.isoformat(),
                    'severity': self._get_severity(metric, metrics[metric], threshold)
                }
                triggered_alerts.append(alert)

        self.alerts.extend(triggered_alerts)
        self._cleanup_old_alerts()
        return triggered_alerts

    def _get_severity(self, metric: str, value: float, threshold: float) -> str:
        ratio = value / threshold
        if ratio > 2.0:
            return 'critical'
        elif ratio > 1.5:
            return 'high'
        else:
            return 'warning'

    def _cleanup_old_alerts(self):
        cutoff = datetime.now() - self.alert_window
        self.alerts = [
            alert for alert in self.alerts
            if datetime.fromisoformat(alert['timestamp']) > cutoff
        ]

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        self._cleanup_old_alerts()
        return self.alerts


class DashboardMetrics:
    def __init__(self):
        self.metrics_store = {}
        self.retention_hours = 24

    def record_metric(
        self, name: str, value: float,
        labels: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None
    ):
        if timestamp is None:
            timestamp = datetime.now()

        key = f"{name}_{hash(str(labels or {}))}"
        if key not in self.metrics_store:
            self.metrics_store[key] = {
                'name': name,
                'labels': labels or {},
                'values': []
            }

        self.metrics_store[key]['values'].append({
            'value': value,
            'timestamp': timestamp
        })

        self._cleanup_old_metrics()

    def _cleanup_old_metrics(self):
        cutoff = datetime.now() - timedelta(hours=self.retention_hours)
        for key in self.metrics_store:
            self.metrics_store[key]['values'] = [
                entry for entry in self.metrics_store[key]['values']
                if entry['timestamp'] > cutoff
            ]

    def get_dashboard_data(self) -> Dict[str, Any]:
        now = datetime.now()
        data = {
            'timestamp': now.isoformat(),
            'metrics': {}
        }

        for _key, metric_data in self.metrics_store.items():
            if metric_data['values']:
                recent_values = [entry['value'] for entry in metric_data['values']]
                data['metrics'][metric_data['name']] = {
                    'current': recent_values[-1] if recent_values else 0,
                    'average': sum(recent_values) / len(recent_values),
                    'min': min(recent_values),
                    'max': max(recent_values),
                    'count': len(recent_values),
                    'labels': metric_data['labels']
                }

        return data


class HydraMonitoring:
    def __init__(self, service_name: str = "hydra-api"):
        resource = Resource.create({"service.name": service_name})

        trace.set_tracer_provider(TracerProvider(resource=resource))
        self.tracer = trace.get_tracer(__name__)

        jaeger_host = os.getenv('JAEGER_HOST', 'localhost')
        jaeger_port = int(os.getenv('JAEGER_PORT', '14268'))

        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_host,
            agent_port=jaeger_port,
        )

        span_processor = BatchSpanProcessor(jaeger_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)

        prometheus_reader = PrometheusMetricReader()
        metrics.set_meter_provider(MeterProvider(
            resource=resource,
            metric_readers=[prometheus_reader]
        ))

        self.meter = metrics.get_meter(__name__)
        self._create_metrics()

        self.logger = StructuredLogger(__name__)
        self.alerting = AlertingManager()
        self.dashboard = DashboardMetrics()

    def _create_metrics(self):
        self.request_counter = self.meter.create_counter(
            "hydra_requests_total",
            description="Total number of API requests"
        )

        self.request_duration = self.meter.create_histogram(
            "hydra_request_duration_seconds",
            description="Request duration in seconds"
        )

        self.error_counter = self.meter.create_counter(
            "hydra_errors_total",
            description="Total number of errors"
        )

        self.task_completion_time = self.meter.create_histogram(
            "hydra_task_completion_seconds",
            description="Task completion time in seconds"
        )

        self.code_generation_success = self.meter.create_counter(
            "hydra_code_generation_success_total",
            description="Successful code generations"
        )

        self.code_generation_failure = self.meter.create_counter(
            "hydra_code_generation_failure_total",
            description="Failed code generations"
        )

        self.agent_operations = self.meter.create_counter(
            "hydra_agent_operations_total",
            description="Total agent operations"
        )

        self.agent_execution_time = self.meter.create_histogram(
            "hydra_agent_execution_seconds",
            description="Agent operation execution time"
        )

        self.concurrent_agents = self.meter.create_up_down_counter(
            "hydra_concurrent_agents",
            description="Number of currently active agents"
        )

        self.workflow_execution = self.meter.create_histogram(
            "hydra_workflow_execution_seconds",
            description="Workflow execution time"
        )

        self.memory_usage = self.meter.create_gauge(
            "hydra_memory_usage_bytes",
            description="Memory usage in bytes"
        )

        self.cpu_usage = self.meter.create_gauge(
            "hydra_cpu_usage_percent",
            description="CPU usage percentage"
        )

    def instrument_fastapi(self, app):
        FastAPIInstrumentor.instrument_app(
            app, tracer_provider=trace.get_tracer_provider()
        )

    def instrument_sqlalchemy(self, engine):
        SQLAlchemyInstrumentor().instrument(engine=engine)

    def trace_function(self, operation_name: str):
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with self.tracer.start_as_current_span(operation_name) as span:
                    try:
                        result = await func(*args, **kwargs)
                        span.set_attribute("operation.success", True)
                        return result
                    except Exception as e:
                        span.set_attribute("operation.success", False)
                        span.set_attribute("error.message", str(e))
                        self.error_counter.add(1, {"operation": operation_name})
                        raise

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with self.tracer.start_as_current_span(operation_name) as span:
                    try:
                        result = func(*args, **kwargs)
                        span.set_attribute("operation.success", True)
                        return result
                    except Exception as e:
                        span.set_attribute("operation.success", False)
                        span.set_attribute("error.message", str(e))
                        self.error_counter.add(1, {"operation": operation_name})
                        raise

            return async_wrapper if hasattr(func, '__await__') else sync_wrapper
        return decorator

    def record_request(
        self, method: str, endpoint: str, status_code: int, duration: float
    ):
        labels = {
            "method": method,
            "endpoint": endpoint,
            "status": str(status_code)
        }

        self.request_counter.add(1, labels)
        self.request_duration.record(duration, labels)
        self.dashboard.record_metric('request_duration', duration, labels)

        if status_code >= 400:
            self.error_counter.add(1, labels)

    def record_task_completion(self, task_type: str, duration: float, success: bool):
        labels = {"task_type": task_type, "success": str(success)}
        self.task_completion_time.record(duration, labels)
        self.dashboard.record_metric('task_completion_time', duration, labels)

        if task_type == "code_generation":
            if success:
                self.code_generation_success.add(1, {"task_type": task_type})
                self.dashboard.record_metric(
                    'code_generation_success', 1, {"task_type": task_type}
                )
            else:
                self.code_generation_failure.add(1, {"task_type": task_type})
                self.dashboard.record_metric(
                    'code_generation_failure', 1, {"task_type": task_type}
                )

    def record_agent_operation(
        self, agent_id: str, operation: str, duration: float,
        success: bool, metadata: Optional[Dict[str, Any]] = None
    ):
        labels = {
            "agent_id": agent_id,
            "operation": operation,
            "success": str(success)
        }

        self.agent_operations.add(1, labels)
        self.agent_execution_time.record(duration, labels)
        self.dashboard.record_metric('agent_execution_time', duration, labels)

        if metadata:
            for key, value in metadata.items():
                val = float(value) if isinstance(value, (int, float)) else 1
                self.dashboard.record_metric(f'agent_{key}', val, labels)

        self.logger.info(
            f"Agent operation completed: {operation}",
            agent_id=agent_id,
            operation=operation,
            duration=duration,
            success=success,
            metadata=metadata or {}
        )

    def track_agent_lifecycle(self, agent_id: str, action: str):
        if action == "start":
            self.concurrent_agents.add(1, {"agent_id": agent_id})
            self.dashboard.record_metric('agent_started', 1, {"agent_id": agent_id})
        elif action == "stop":
            self.concurrent_agents.add(-1, {"agent_id": agent_id})
            self.dashboard.record_metric('agent_stopped', 1, {"agent_id": agent_id})

        self.logger.info(f"Agent {action}", agent_id=agent_id, action=action)

    def record_workflow_execution(
        self, workflow_id: str, duration: float,
        tasks_completed: int, tasks_failed: int
    ):
        labels = {"workflow_id": workflow_id}

        self.workflow_execution.record(duration, labels)
        self.dashboard.record_metric('workflow_duration', duration, labels)
        self.dashboard.record_metric(
            'workflow_tasks_completed', tasks_completed, labels
        )
        self.dashboard.record_metric('workflow_tasks_failed', tasks_failed, labels)

        total_tasks = tasks_completed + tasks_failed
        success_rate = tasks_completed / total_tasks if total_tasks > 0 else 1.0
        self.dashboard.record_metric('workflow_success_rate', success_rate, labels)

        self.logger.info(
            "Workflow completed",
            workflow_id=workflow_id,
            duration=duration,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            success_rate=success_rate
        )

    def record_system_metrics(self, memory_bytes: int, cpu_percent: float):
        self.memory_usage.set(memory_bytes)
        self.cpu_usage.set(cpu_percent)

        self.dashboard.record_metric('memory_usage', memory_bytes)
        self.dashboard.record_metric('cpu_usage', cpu_percent)

        metrics = {
            'memory_usage': memory_bytes / (1024 ** 3),
            'cpu_usage': cpu_percent / 100.0
        }

        alerts = self.alerting.check_alerts(metrics)
        if alerts:
            for alert in alerts:
                self.logger.warning(
                    f"Alert triggered: {alert['metric']}",
                    alert_id=alert['id'],
                    metric=alert['metric'],
                    value=alert['value'],
                    threshold=alert['threshold'],
                    severity=alert['severity']
                )

    def get_health_status(self) -> Dict[str, Any]:
        dashboard_data = self.dashboard.get_dashboard_data()
        active_alerts = self.alerting.get_active_alerts()

        critical_alerts = [a for a in active_alerts if a['severity'] == 'critical']

        return {
            'status': 'unhealthy' if critical_alerts else 'healthy',
            'timestamp': datetime.now().isoformat(),
            'metrics': dashboard_data.get('metrics', {}),
            'alerts': {
                'total': len(active_alerts),
                'critical': len(critical_alerts),
                'active': active_alerts
            },
            'correlation_id': self.get_correlation_id()
        }

    def set_correlation_id(self, correlation_id: Optional[str] = None):
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        request_id.set(correlation_id)
        return correlation_id

    def get_correlation_id(self) -> Optional[str]:
        return request_id.get()


class PerformanceProfiler:
    def __init__(self):
        self.profiles = {}
        self.bottlenecks = []

    def start_profile(self, operation_id: str):
        self.profiles[operation_id] = {
            'start_time': time.time(),
            'checkpoints': []
        }

    def checkpoint(self, operation_id: str, name: str):
        if operation_id in self.profiles:
            self.profiles[operation_id]['checkpoints'].append({
                'name': name,
                'timestamp': time.time()
            })

    def end_profile(self, operation_id: str) -> Dict[str, Any]:
        if operation_id not in self.profiles:
            return {}

        profile = self.profiles.pop(operation_id)
        end_time = time.time()
        total_duration = end_time - profile['start_time']

        checkpoint_durations = []
        prev_time = profile['start_time']

        for checkpoint in profile['checkpoints']:
            duration = checkpoint['timestamp'] - prev_time
            checkpoint_durations.append({
                'name': checkpoint['name'],
                'duration': duration
            })
            prev_time = checkpoint['timestamp']

        slowest_checkpoint = (
            max(checkpoint_durations, key=lambda x: x['duration'])
            if checkpoint_durations else None
        )

        if slowest_checkpoint and slowest_checkpoint['duration'] > 1.0:
            self.bottlenecks.append({
                'operation_id': operation_id,
                'bottleneck': slowest_checkpoint['name'],
                'duration': slowest_checkpoint['duration'],
                'timestamp': datetime.now().isoformat()
            })

        return {
            'operation_id': operation_id,
            'total_duration': total_duration,
            'checkpoints': checkpoint_durations,
            'slowest_checkpoint': slowest_checkpoint
        }

    def get_bottlenecks(self, limit: int = 10) -> List[Dict[str, Any]]:
        return sorted(
            self.bottlenecks, key=lambda x: x['duration'], reverse=True
        )[:limit]


monitoring = HydraMonitoring()
profiler = PerformanceProfiler()


def timed_operation(operation_name: str, agent_id: Optional[str] = None):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            operation_agent_id = agent_id or kwargs.get('agent_id', 'unknown')

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                monitoring.record_task_completion(operation_name, duration, True)
                monitoring.record_agent_operation(
                    operation_agent_id, operation_name, duration, True
                )
                return result
            except Exception:
                duration = time.time() - start_time
                monitoring.record_task_completion(operation_name, duration, False)
                monitoring.record_agent_operation(
                    operation_agent_id, operation_name, duration, False
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            operation_agent_id = agent_id or kwargs.get('agent_id', 'unknown')

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                monitoring.record_task_completion(operation_name, duration, True)
                monitoring.record_agent_operation(
                    operation_agent_id, operation_name, duration, True
                )
                return result
            except Exception:
                duration = time.time() - start_time
                monitoring.record_task_completion(operation_name, duration, False)
                monitoring.record_agent_operation(
                    operation_agent_id, operation_name, duration, False
                )
                raise

        return async_wrapper if hasattr(func, '__await__') else sync_wrapper
    return decorator


def agent_trace(operation_name: str):
    return monitoring.trace_function(operation_name)


def health_check() -> Dict[str, Any]:
    return monitoring.get_health_status()