"""OpenTelemetry monitoring and observability for Hydra."""

import logging
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Callable, Optional

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

class HydraMonitoring:
    def __init__(self, service_name: str = "hydra-api"):
        resource = Resource.create({"service.name": service_name})

        trace.set_tracer_provider(TracerProvider(resource=resource))
        self.tracer = trace.get_tracer(__name__)

        jaeger_exporter = JaegerExporter(
            agent_host_name="localhost",
            agent_port=14268,
        )

        span_processor = BatchSpanProcessor(jaeger_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)

        prometheus_reader = PrometheusMetricReader()
        metrics.set_meter_provider(MeterProvider(
            resource=resource,
            metric_readers=[prometheus_reader]
        ))

        self.meter = metrics.get_meter(__name__)

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

        self.logger = StructuredLogger(__name__)

    def instrument_fastapi(self, app):
        FastAPIInstrumentor.instrument_app(app, tracer_provider=trace.get_tracer_provider())

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

    def record_request(self, method: str, endpoint: str, status_code: int, duration: float):
        labels = {
            "method": method,
            "endpoint": endpoint,
            "status": str(status_code)
        }

        self.request_counter.add(1, labels)
        self.request_duration.record(duration, labels)

        if status_code >= 400:
            self.error_counter.add(1, labels)

    def record_task_completion(self, task_type: str, duration: float, success: bool):
        labels = {"task_type": task_type, "success": str(success)}
        self.task_completion_time.record(duration, labels)

        if task_type == "code_generation":
            if success:
                self.code_generation_success.add(1, {"task_type": task_type})
            else:
                self.code_generation_failure.add(1, {"task_type": task_type})

    def set_correlation_id(self, correlation_id: Optional[str] = None):
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        request_id.set(correlation_id)
        return correlation_id

    def get_correlation_id(self) -> Optional[str]:
        return request_id.get()

monitoring = HydraMonitoring()

def timed_operation(operation_name: str):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                monitoring.record_task_completion(operation_name, duration, True)
                return result
            except Exception:
                duration = time.time() - start_time
                monitoring.record_task_completion(operation_name, duration, False)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                monitoring.record_task_completion(operation_name, duration, True)
                return result
            except Exception:
                duration = time.time() - start_time
                monitoring.record_task_completion(operation_name, duration, False)
                raise

        return async_wrapper if hasattr(func, '__await__') else sync_wrapper
    return decorator
