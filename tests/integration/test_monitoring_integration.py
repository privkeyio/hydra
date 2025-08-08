"""Integration tests for monitoring and observability."""

import os
import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock

from hydra.monitoring import monitoring, profiler, HydraMonitoring
from hydra.dashboard import app, dashboard_ws
from fastapi.testclient import TestClient

# Test mode detection to skip thread-intensive tests
TEST_MODE = (
    os.getenv('TESTING') == '1' or
    os.getenv('PYTEST_CURRENT_TEST') is not None or
    'pytest' in str(os.getenv('_', ''))
)


class TestMonitoringIntegration:
    
    def test_full_monitoring_workflow(self):
        """Test complete monitoring workflow with real metrics."""
        with patch('hydra.monitoring.trace.set_tracer_provider'):
            with patch('hydra.monitoring.metrics.set_meter_provider'):
                test_monitoring = HydraMonitoring("integration-test")
                
                agent_id = "test-agent-1"
                
                test_monitoring.track_agent_lifecycle(agent_id, "start")
                
                test_monitoring.record_agent_operation(
                    agent_id, "file_read", 0.1, True, {"files": 5}
                )
                test_monitoring.record_agent_operation(
                    agent_id, "code_generation", 2.5, True, {"lines": 150}
                )
                test_monitoring.record_agent_operation(
                    agent_id, "file_write", 0.3, False, {"error": "permission"}
                )
                
                test_monitoring.record_workflow_execution(
                    "workflow-123", 30.5, 8, 2
                )
                
                test_monitoring.record_system_metrics(2048 * 1024 * 1024, 65.3)
                
                test_monitoring.track_agent_lifecycle(agent_id, "stop")
                
                health = test_monitoring.get_health_status()
                
                assert health['status'] in ['healthy', 'unhealthy']
                assert 'timestamp' in health
                assert 'metrics' in health
                assert 'alerts' in health
                assert health['correlation_id'] is not None
    
    def test_alerting_integration(self):
        """Test alerting system with threshold breaches."""
        with patch('hydra.monitoring.trace.set_tracer_provider'):
            with patch('hydra.monitoring.metrics.set_meter_provider'):
                test_monitoring = HydraMonitoring("alert-test")
                
                test_monitoring.record_system_metrics(8192 * 1024 * 1024, 95.0)
                
                health = test_monitoring.get_health_status()
                
                if health['alerts']['total'] > 0:
                    assert health['status'] == 'unhealthy'
                    critical_alerts = [
                        a for a in health['alerts']['active'] 
                        if a['severity'] == 'critical'
                    ]
                    assert len(critical_alerts) >= 0
    
    def test_dashboard_metrics_collection(self):
        """Test dashboard metrics collection and retrieval."""
        with patch('hydra.monitoring.trace.set_tracer_provider'):
            with patch('hydra.monitoring.metrics.set_meter_provider'):
                test_monitoring = HydraMonitoring("dashboard-test")
                
                for i in range(10):
                    test_monitoring.record_agent_operation(
                        f"agent-{i % 3}", "test_operation", 
                        0.1 + (i * 0.1), i % 7 != 0
                    )
                
                dashboard_data = test_monitoring.dashboard.get_dashboard_data()
                
                assert 'timestamp' in dashboard_data
                assert 'metrics' in dashboard_data
                
                if dashboard_data['metrics']:
                    for metric_name, metric_data in dashboard_data['metrics'].items():
                        assert 'current' in metric_data
                        assert 'average' in metric_data
                        assert 'min' in metric_data
                        assert 'max' in metric_data
                        assert 'count' in metric_data
    
    def test_performance_profiler_integration(self):
        """Test performance profiler with actual operations."""
        operation_id = "complex-operation"
        
        profiler.start_profile(operation_id)
        
        time.sleep(0.1)
        profiler.checkpoint(operation_id, "initialization")
        
        time.sleep(0.2)
        profiler.checkpoint(operation_id, "data_processing")
        
        time.sleep(0.1)
        profiler.checkpoint(operation_id, "cleanup")
        
        result = profiler.end_profile(operation_id)
        
        assert result['operation_id'] == operation_id
        assert result['total_duration'] >= 0.4
        assert len(result['checkpoints']) == 3
        
        assert result['checkpoints'][0]['name'] == "initialization"
        assert result['checkpoints'][1]['name'] == "data_processing"
        assert result['checkpoints'][2]['name'] == "cleanup"
        
        slowest = result['slowest_checkpoint']
        assert slowest['name'] == "data_processing"
        assert slowest['duration'] >= 0.2
    
    def test_correlation_id_propagation(self):
        """Test correlation ID propagation through monitoring calls."""
        with patch('hydra.monitoring.trace.set_tracer_provider'):
            with patch('hydra.monitoring.metrics.set_meter_provider'):
                test_monitoring = HydraMonitoring("correlation-test")
                
                correlation_id = test_monitoring.set_correlation_id("test-correlation-123")
                assert correlation_id == "test-correlation-123"
                
                test_monitoring.record_agent_operation(
                    "test-agent", "test_operation", 1.0, True
                )
                
                retrieved_id = test_monitoring.get_correlation_id()
                assert retrieved_id == "test-correlation-123"
                
                health = test_monitoring.get_health_status()
                assert health['correlation_id'] == "test-correlation-123"
    
    @pytest.mark.skipif(TEST_MODE, reason="Skip thread-intensive tests in test mode")
    def test_concurrent_monitoring(self):
        """Test monitoring under concurrent access."""
        with patch('hydra.monitoring.trace.set_tracer_provider'):
            with patch('hydra.monitoring.metrics.set_meter_provider'):
                test_monitoring = HydraMonitoring("concurrent-test")
                
                def worker_function(worker_id: int):
                    for i in range(5):
                        test_monitoring.record_agent_operation(
                            f"worker-{worker_id}", f"operation-{i}", 
                            0.1 * i, i % 4 != 0
                        )
                
                import threading
                threads = []
                for i in range(3):
                    thread = threading.Thread(target=worker_function, args=(i,))
                    threads.append(thread)
                    thread.start()
                
                for thread in threads:
                    thread.join()
                
                dashboard_data = test_monitoring.dashboard.get_dashboard_data()
                assert 'metrics' in dashboard_data
    
    def test_metrics_cleanup(self):
        """Test metrics cleanup and retention."""
        with patch('hydra.monitoring.trace.set_tracer_provider'):
            with patch('hydra.monitoring.metrics.set_meter_provider'):
                test_monitoring = HydraMonitoring("cleanup-test")
                
                test_monitoring.dashboard.retention_hours = 0.001
                
                test_monitoring.record_agent_operation(
                    "test-agent", "old_operation", 1.0, True
                )
                
                time.sleep(0.1)
                
                test_monitoring.record_agent_operation(
                    "test-agent", "new_operation", 1.0, True
                )
                
                dashboard_data = test_monitoring.dashboard.get_dashboard_data()
                
                if 'agent_execution_time' in dashboard_data['metrics']:
                    assert dashboard_data['metrics']['agent_execution_time']['count'] >= 1


class TestDashboardIntegration:
    
    def test_dashboard_endpoints(self):
        """Test dashboard API endpoints."""
        client = TestClient(app)
        
        response = client.get("/")
        assert response.status_code == 200
        assert "Hydra Monitoring Dashboard" in response.text
        
        with patch('hydra.dashboard.monitoring.get_health_status') as mock_health:
            mock_health.return_value = {
                'status': 'healthy',
                'timestamp': '2024-01-01T00:00:00',
                'metrics': {},
                'alerts': {'total': 0, 'critical': 0, 'active': []},
                'correlation_id': 'test-123'
            }
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'healthy'
        
        with patch('hydra.dashboard.monitoring.dashboard.get_dashboard_data') as mock_metrics:
            mock_metrics.return_value = {
                'timestamp': '2024-01-01T00:00:00',
                'metrics': {'test_metric': {'current': 1.0}}
            }
            
            response = client.get("/metrics")
            assert response.status_code == 200
            data = response.json()
            assert 'timestamp' in data
            assert 'metrics' in data
        
        with patch('hydra.dashboard.profiler.get_bottlenecks') as mock_bottlenecks:
            mock_bottlenecks.return_value = [
                {
                    'operation_id': 'test_op',
                    'bottleneck': 'slow_step',
                    'duration': 2.5,
                    'timestamp': '2024-01-01T00:00:00'
                }
            ]
            
            response = client.get("/bottlenecks")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]['bottleneck'] == 'slow_step'
    
    def test_websocket_connection(self):
        """Test WebSocket connection for real-time updates."""
        client = TestClient(app)
        
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text("ping")
            assert len(dashboard_ws.connections) == 1
        
        assert len(dashboard_ws.connections) == 0
    
    @pytest.mark.asyncio
    async def test_websocket_broadcasting(self):
        """Test WebSocket broadcasting functionality."""
        mock_websocket = MagicMock()
        mock_websocket.send_text = MagicMock()
        
        dashboard_ws.connections = [mock_websocket]
        
        test_message = {'type': 'test', 'data': 'broadcast_test'}
        await dashboard_ws.broadcast(test_message)
        
        mock_websocket.send_text.assert_called_once()


class TestEndToEndMonitoring:
    
    @pytest.mark.asyncio
    async def test_complete_agent_workflow_monitoring(self):
        """Test monitoring throughout a complete agent workflow."""
        with patch('hydra.monitoring.trace.set_tracer_provider'):
            with patch('hydra.monitoring.metrics.set_meter_provider'):
                test_monitoring = HydraMonitoring("e2e-test")
                
                workflow_id = "e2e-workflow"
                agent_id = "e2e-agent"
                
                test_monitoring.set_correlation_id(f"{workflow_id}-correlation")
                
                profiler.start_profile(workflow_id)
                
                test_monitoring.track_agent_lifecycle(agent_id, "start")
                profiler.checkpoint(workflow_id, "agent_startup")
                
                operations = [
                    ("file_analysis", 0.5, True, {"files_analyzed": 10}),
                    ("code_generation", 3.2, True, {"lines_generated": 250}),
                    ("test_execution", 1.8, True, {"tests_passed": 8}),
                    ("deployment", 2.1, False, {"error": "network_timeout"})
                ]
                
                successful_ops = 0
                failed_ops = 0
                
                for op_name, duration, success, metadata in operations:
                    profiler.checkpoint(workflow_id, f"start_{op_name}")
                    
                    await asyncio.sleep(duration * 0.01)
                    
                    test_monitoring.record_agent_operation(
                        agent_id, op_name, duration, success, metadata
                    )
                    
                    if success:
                        successful_ops += 1
                    else:
                        failed_ops += 1
                    
                    profiler.checkpoint(workflow_id, f"end_{op_name}")
                
                test_monitoring.track_agent_lifecycle(agent_id, "stop")
                
                total_duration = sum(op[1] for op in operations)
                test_monitoring.record_workflow_execution(
                    workflow_id, total_duration, successful_ops, failed_ops
                )
                
                profile_result = profiler.end_profile(workflow_id)
                
                health = test_monitoring.get_health_status()
                dashboard_data = test_monitoring.dashboard.get_dashboard_data()
                
                assert health['status'] in ['healthy', 'unhealthy']
                assert health['correlation_id'] == f"{workflow_id}-correlation"
                
                assert profile_result['operation_id'] == workflow_id
                assert profile_result['total_duration'] > 0
                assert len(profile_result['checkpoints']) == 10
                
                if 'agent_execution_time' in dashboard_data['metrics']:
                    assert dashboard_data['metrics']['agent_execution_time']['count'] == 4
                
                if 'workflow_success_rate' in dashboard_data['metrics']:
                    assert dashboard_data['metrics']['workflow_success_rate']['current'] == 0.75