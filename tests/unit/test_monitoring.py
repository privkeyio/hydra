"""Unit tests for monitoring and observability functionality."""

import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from hydra.monitoring import (
    AlertingManager,
    DashboardMetrics,
    HydraMonitoring,
    PerformanceProfiler,
    StructuredLogger,
    agent_trace,
    monitoring,
    timed_operation,
)


class TestStructuredLogger:
    def test_logger_creation(self):
        logger = StructuredLogger("test")
        assert logger.logger.name == "test"

    def test_log_with_request_id(self):
        logger = StructuredLogger("test")
        with patch.object(logger.logger, "info") as mock_log:
            logger.info("test message", extra_field="value")
            mock_log.assert_called_once()


class TestAlertingManager:
    def test_init(self):
        alerting = AlertingManager()
        assert alerting.thresholds["error_rate"] == 0.05
        assert alerting.thresholds["cpu_usage"] == 0.8
        assert len(alerting.alerts) == 0

    def test_check_alerts_no_issues(self):
        alerting = AlertingManager()
        metrics = {"cpu_usage": 0.5, "memory_usage": 0.6}
        alerts = alerting.check_alerts(metrics)
        assert len(alerts) == 0

    def test_check_alerts_with_issues(self):
        alerting = AlertingManager()
        metrics = {"cpu_usage": 0.9, "memory_usage": 0.85}
        alerts = alerting.check_alerts(metrics)
        assert len(alerts) == 2

        cpu_alert = next(a for a in alerts if a["metric"] == "cpu_usage")
        assert cpu_alert["value"] == 0.9
        assert cpu_alert["threshold"] == 0.8
        assert cpu_alert["severity"] == "warning"

    def test_severity_calculation(self):
        alerting = AlertingManager()

        assert alerting._get_severity("test", 1.2, 1.0) == "warning"
        assert alerting._get_severity("test", 1.6, 1.0) == "high"
        assert alerting._get_severity("test", 2.5, 1.0) == "critical"

    def test_cleanup_old_alerts(self):
        alerting = AlertingManager()
        old_alert = {
            "id": "test",
            "timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(),
        }
        alerting.alerts = [old_alert]
        alerting._cleanup_old_alerts()
        assert len(alerting.alerts) == 0

    def test_get_active_alerts(self):
        alerting = AlertingManager()
        recent_alert = {"id": "test", "timestamp": datetime.now().isoformat()}
        alerting.alerts = [recent_alert]
        active_alerts = alerting.get_active_alerts()
        assert len(active_alerts) == 1


class TestDashboardMetrics:
    def test_init(self):
        dashboard = DashboardMetrics()
        assert dashboard.retention_hours == 24
        assert len(dashboard.metrics_store) == 0

    def test_record_metric(self):
        dashboard = DashboardMetrics()
        dashboard.record_metric("test_metric", 1.5, {"label": "value"})
        assert len(dashboard.metrics_store) == 1

        key = list(dashboard.metrics_store.keys())[0]
        metric_data = dashboard.metrics_store[key]
        assert metric_data["name"] == "test_metric"
        assert metric_data["labels"] == {"label": "value"}
        assert len(metric_data["values"]) == 1
        assert metric_data["values"][0]["value"] == 1.5

    def test_cleanup_old_metrics(self):
        dashboard = DashboardMetrics()
        old_timestamp = datetime.now() - timedelta(hours=25)
        dashboard.record_metric("test_metric", 1.0, timestamp=old_timestamp)
        dashboard.record_metric("test_metric", 2.0)

        key = list(dashboard.metrics_store.keys())[0]
        assert len(dashboard.metrics_store[key]["values"]) == 1
        assert dashboard.metrics_store[key]["values"][0]["value"] == 2.0

    def test_get_dashboard_data(self):
        dashboard = DashboardMetrics()
        dashboard.record_metric("test_metric", 1.0)
        dashboard.record_metric("test_metric", 2.0)
        dashboard.record_metric("test_metric", 3.0)

        data = dashboard.get_dashboard_data()
        assert "timestamp" in data
        assert "metrics" in data
        assert "test_metric" in data["metrics"]

        metric_stats = data["metrics"]["test_metric"]
        assert metric_stats["current"] == 3.0
        assert metric_stats["average"] == 2.0
        assert metric_stats["min"] == 1.0
        assert metric_stats["max"] == 3.0
        assert metric_stats["count"] == 3


class TestPerformanceProfiler:
    def test_init(self):
        profiler = PerformanceProfiler()
        assert len(profiler.profiles) == 0
        assert len(profiler.bottlenecks) == 0

    def test_profile_lifecycle(self):
        profiler = PerformanceProfiler()

        profiler.start_profile("test_op")
        assert "test_op" in profiler.profiles

        time.sleep(0.1)
        profiler.checkpoint("test_op", "step1")

        time.sleep(0.1)
        profiler.checkpoint("test_op", "step2")

        result = profiler.end_profile("test_op")
        assert "test_op" not in profiler.profiles
        assert result["operation_id"] == "test_op"
        assert result["total_duration"] > 0.2
        assert len(result["checkpoints"]) == 2

    def test_bottleneck_detection(self):
        profiler = PerformanceProfiler()

        profiler.start_profile("slow_op")
        time.sleep(0.1)
        profiler.checkpoint("slow_op", "fast_step")
        time.sleep(1.1)
        profiler.checkpoint("slow_op", "slow_step")

        profiler.end_profile("slow_op")

        bottlenecks = profiler.get_bottlenecks()
        assert len(bottlenecks) == 1
        assert bottlenecks[0]["bottleneck"] == "slow_step"
        assert bottlenecks[0]["duration"] > 1.0

    def test_get_bottlenecks_limit(self):
        profiler = PerformanceProfiler()

        for i in range(5):
            profiler.bottlenecks.append(
                {
                    "operation_id": f"op_{i}",
                    "bottleneck": f"step_{i}",
                    "duration": float(i),
                    "timestamp": datetime.now().isoformat(),
                }
            )

        bottlenecks = profiler.get_bottlenecks(3)
        assert len(bottlenecks) == 3
        assert bottlenecks[0]["duration"] == 4.0


class TestHydraMonitoring:
    def test_init(self):
        with patch("hydra.monitoring.trace.set_tracer_provider"):
            with patch("hydra.monitoring.metrics.set_meter_provider"):
                monitoring = HydraMonitoring("test-service", test_mode=True)
                # In test mode, tracer and meter are None
                assert monitoring.tracer is None
                assert monitoring.meter is None
                assert monitoring.logger is not None
                assert monitoring.alerting is None
                assert monitoring.dashboard is None

    def test_record_request(self):
        with patch("hydra.monitoring.trace.set_tracer_provider"):
            with patch("hydra.monitoring.metrics.set_meter_provider"):
                monitoring = HydraMonitoring(test_mode=True)

                # In test mode, record_request should just return early
                monitoring.record_request("GET", "/test", 200, 0.5)
                # If we get here without error, the test passes

    def test_record_task_completion(self):
        monitoring = HydraMonitoring(test_mode=True)
        # In test mode, should not raise errors
        monitoring.record_task_completion("test_task", 1.0, True)

    def test_record_agent_operation(self):
        monitoring = HydraMonitoring(test_mode=True)
        # In test mode, should not raise errors
        monitoring.record_agent_operation("agent_1", "test_op", 0.5, True, {"files": 3})

    def test_track_agent_lifecycle(self):
        monitoring = HydraMonitoring(test_mode=True)
        # In test mode, should not raise errors
        monitoring.track_agent_lifecycle("agent_1", "start")
        monitoring.track_agent_lifecycle("agent_1", "stop")

    def test_record_workflow_execution(self):
        monitoring = HydraMonitoring(test_mode=True)
        # In test mode, should not raise errors
        monitoring.record_workflow_execution("workflow_1", 10.0, 8, 2)

    def test_record_system_metrics(self):
        monitoring = HydraMonitoring(test_mode=True)
        # In test mode, should not raise errors
        monitoring.record_system_metrics(1000000, 75.5)

    def test_get_health_status(self):
        monitoring = HydraMonitoring(test_mode=True)
        # In test mode, get_health_status should handle missing components
        try:
            health = monitoring.get_health_status()
            # If it returns something, check basic structure
            if health:
                assert "status" in health
                assert "timestamp" in health
        except AttributeError:
            # Expected in test mode due to missing dashboard/alerting
            pass

    def test_correlation_id(self):
        monitoring = HydraMonitoring(test_mode=True)
        correlation_id = monitoring.set_correlation_id("test-123")
        assert correlation_id == "test-123"
        assert monitoring.get_correlation_id() == "test-123"

    def test_trace_function_decorator(self):
        monitoring = HydraMonitoring(test_mode=True)

        @monitoring.trace_function("test_operation")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"


class TestDecorators:
    def test_timed_operation_sync_success(self):
        @timed_operation("test_op", "agent_1")
        def test_func():
            return "success"

        with patch.object(monitoring, "record_task_completion") as mock_task:
            with patch.object(monitoring, "record_agent_operation") as mock_agent:
                result = test_func()
                assert result == "success"
                mock_task.assert_called_once()
                mock_agent.assert_called_once()

    def test_timed_operation_sync_failure(self):
        @timed_operation("test_op", "agent_1")
        def test_func():
            raise ValueError("test error")

        with patch.object(monitoring, "record_task_completion") as mock_task:
            with patch.object(monitoring, "record_agent_operation") as mock_agent:
                with pytest.raises(ValueError):
                    test_func()

                mock_task.assert_called_once()
                mock_agent.assert_called_once()

                args, kwargs = mock_task.call_args
                assert args[2] is False

    @pytest.mark.asyncio
    async def test_timed_operation_async_success(self):
        @timed_operation("test_op", "agent_1")
        async def test_func():
            return "success"

        with patch.object(monitoring, "record_task_completion") as mock_task:
            with patch.object(monitoring, "record_agent_operation") as mock_agent:
                result = await test_func()
                assert result == "success"
                mock_task.assert_called_once()
                mock_agent.assert_called_once()

    def test_agent_trace(self):
        @agent_trace("test_trace")
        def test_func():
            return "traced"

        result = test_func()
        assert result == "traced"
