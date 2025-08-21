"""
Integration tests for dashboard real-time updates.

Tests the dashboard's ability to provide real-time updates for ticket execution,
progress tracking, status changes, and live metrics visualization.
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import threading
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

import pytest

from hydra.dashboard.database import get_db_manager, Ticket, Project, Execution
from hydra.ticket_workflow import update_ticket_in_database


class MockWebSocketConnection:
    """Mock WebSocket connection for testing real-time updates."""
    
    def __init__(self):
        self.messages_sent = []
        self.connected = True
        self.client_id = f"test_client_{int(time.time())}"
    
    async def send(self, message: str):
        """Mock sending message to WebSocket client."""
        self.messages_sent.append({
            "timestamp": time.time(),
            "message": message,
            "client_id": self.client_id
        })
    
    def get_messages_by_type(self, message_type: str) -> List[Dict]:
        """Get messages of specific type."""
        matching_messages = []
        for msg_info in self.messages_sent:
            try:
                message_data = json.loads(msg_info["message"])
                if message_data.get("type") == message_type:
                    matching_messages.append({**message_data, **msg_info})
            except json.JSONDecodeError:
                continue
        return matching_messages


class RealTimeDashboard:
    """Mock dashboard with real-time update capabilities."""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.websocket_connections = []
        self.update_queue = asyncio.Queue()
        self.running = False
        self.database_path = project_path / ".hydra" / "dashboard" / "hydra.db"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup database
        self._setup_database()
    
    def _setup_database(self):
        """Setup dashboard database."""
        # Create a temporary database in a writable location
        db_file = tempfile.mktemp(suffix='.db')
        os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
        
        # Force reset the global database manager to pick up new URL
        from hydra.dashboard import database
        database._db_manager = None
        
        # Initialize database with test data
        db_manager = get_db_manager()
        with db_manager.get_session() as db:
            # Create project if not exists
            project = db.query(Project).filter(Project.name == "Realtime Test Project").first()
            if not project:
                project = Project(
                    name="Realtime Test Project",
                    description="Testing real-time dashboard updates",
                    repository_url=str(self.project_path),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(project)
                db.commit()
                self.project_id = project.id
            else:
                self.project_id = project.id
    
    def add_websocket_connection(self, ws_connection: MockWebSocketConnection):
        """Add WebSocket connection for real-time updates."""
        self.websocket_connections.append(ws_connection)
    
    async def broadcast_update(self, update_data: Dict):
        """Broadcast update to all connected WebSocket clients."""
        message = json.dumps(update_data)
        
        for ws in self.websocket_connections:
            if ws.connected:
                await ws.send(message)
    
    async def start_update_processor(self):
        """Start processing real-time updates."""
        self.running = True
        
        while self.running:
            try:
                # Process updates from queue
                update = await asyncio.wait_for(self.update_queue.get(), timeout=0.1)
                await self.broadcast_update(update)
                self.update_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Error processing update: {e}")
    
    def stop_update_processor(self):
        """Stop processing updates."""
        self.running = False
    
    async def notify_ticket_status_change(self, ticket_id: str, old_status: str, new_status: str):
        """Notify about ticket status change."""
        update = {
            "type": "ticket_status_change",
            "timestamp": time.time(),
            "data": {
                "ticket_id": ticket_id,
                "old_status": old_status,
                "new_status": new_status,
                "project_id": self.project_id
            }
        }
        await self.update_queue.put(update)
    
    async def notify_execution_progress(self, ticket_id: str, progress: float, details: str):
        """Notify about execution progress."""
        update = {
            "type": "execution_progress",
            "timestamp": time.time(),
            "data": {
                "ticket_id": ticket_id,
                "progress": progress,
                "details": details,
                "project_id": self.project_id
            }
        }
        await self.update_queue.put(update)
    
    async def notify_metrics_update(self, metrics: Dict):
        """Notify about metrics update."""
        update = {
            "type": "metrics_update",
            "timestamp": time.time(),
            "data": {
                "metrics": metrics,
                "project_id": self.project_id
            }
        }
        await self.update_queue.put(update)
    
    async def notify_error(self, ticket_id: str, error_message: str, error_type: str):
        """Notify about execution error."""
        update = {
            "type": "execution_error",
            "timestamp": time.time(),
            "data": {
                "ticket_id": ticket_id,
                "error_message": error_message,
                "error_type": error_type,
                "project_id": self.project_id
            }
        }
        await self.update_queue.put(update)
    
    def get_current_project_status(self) -> Dict:
        """Get current project status from database."""
        db_manager = get_db_manager()
        with db_manager.get_session() as db:
            tickets = db.query(Ticket).filter(Ticket.project_id == self.project_id).all()
            
            status_counts = {}
            for ticket in tickets:
                status = ticket.status
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_tickets": len(tickets),
                "status_breakdown": status_counts,
                "project_id": self.project_id
            }


class TestDashboardRealTime:
    """Test dashboard real-time update functionality."""
    
    @pytest.fixture
    def temp_project(self):
        """Create temporary project for dashboard testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            (project_path / ".hydra").mkdir()
            (project_path / ".hydra" / "dashboard").mkdir()
            (project_path / "src").mkdir()
            (project_path / "tests").mkdir()
            yield project_path
    
    @pytest.fixture
    def dashboard(self, temp_project):
        """Create dashboard instance for testing."""
        return RealTimeDashboard(temp_project)
    
    def _create_test_tickets(self) -> Dict:
        """Create test tickets for dashboard testing."""
        return {
            "version": "1.0",
            "project": {
                "name": "Realtime Test Project",
                "description": "Testing real-time dashboard functionality"
            },
            "tickets": [
                {
                    "id": "dash_001",
                    "title": "Create Real-time Module",
                    "status": "TODO",
                    "priority": 1,
                    "model": "balanced",
                    "description": "Create module for real-time testing",
                    "acceptance_criteria": [
                        "Create src/realtime_module.py",
                        "Add real-time functionality",
                        "Create comprehensive tests"
                    ]
                },
                {
                    "id": "dash_002",
                    "title": "Implement Dashboard Updates",
                    "status": "TODO", 
                    "priority": 2,
                    "model": "smart",
                    "description": "Implement dashboard update mechanisms",
                    "acceptance_criteria": [
                        "Create dashboard update logic",
                        "Add WebSocket integration",
                        "Implement progress tracking"
                    ]
                },
                {
                    "id": "dash_003",
                    "title": "Add Metrics Collection",
                    "status": "TODO",
                    "priority": 3,
                    "model": "fast",
                    "description": "Add comprehensive metrics collection",
                    "acceptance_criteria": [
                        "Implement metrics gathering",
                        "Add performance monitoring",
                        "Create metrics dashboard"
                    ]
                }
            ]
        }

    @pytest.mark.integration
    def test_ticket_status_updates(self, temp_project, dashboard):
        """Test real-time ticket status updates."""
        # Setup WebSocket connections
        client1 = MockWebSocketConnection()
        client2 = MockWebSocketConnection()
        
        dashboard.add_websocket_connection(client1)
        dashboard.add_websocket_connection(client2)
        
        # Create test tickets in database
        yaml_data = self._create_test_tickets()
        
        db_manager = get_db_manager()
        with db_manager.get_session() as db:
            for ticket_data in yaml_data["tickets"]:
                ticket = Ticket(
                    ticket_number=ticket_data["id"],
                    title=ticket_data["title"],
                    description=ticket_data["description"],
                    status=ticket_data["status"],
                    priority=ticket_data.get("priority", "medium"),
                    model=ticket_data.get("model", "balanced"),
                    project_id=dashboard.project_id,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(ticket)
            db.commit()
        
        async def test_status_updates():
            # Start update processor
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            
            try:
                # Simulate ticket status changes
                await dashboard.notify_ticket_status_change("dash_001", "TODO", "IN_PROGRESS")
                await asyncio.sleep(0.1)
                
                await dashboard.notify_ticket_status_change("dash_001", "IN_PROGRESS", "DONE")
                await asyncio.sleep(0.1)
                
                await dashboard.notify_ticket_status_change("dash_002", "TODO", "IN_PROGRESS")
                await asyncio.sleep(0.1)
                
                # Allow time for processing
                await asyncio.sleep(0.2)
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
        
        # Run the test
        asyncio.run(test_status_updates())
        
        # Verify status update messages were sent
        client1_status_messages = client1.get_messages_by_type("ticket_status_change")
        client2_status_messages = client2.get_messages_by_type("ticket_status_change")
        
        assert len(client1_status_messages) == 3, "Client 1 should receive 3 status updates"
        assert len(client2_status_messages) == 3, "Client 2 should receive 3 status updates"
        
        # Verify specific status changes
        dash_001_updates = [
            msg for msg in client1_status_messages 
            if msg["data"]["ticket_id"] == "dash_001"
        ]
        assert len(dash_001_updates) == 2, "Should have 2 updates for dash_001"
        
        # Check status progression
        assert dash_001_updates[0]["data"]["old_status"] == "TODO"
        assert dash_001_updates[0]["data"]["new_status"] == "IN_PROGRESS"
        assert dash_001_updates[1]["data"]["old_status"] == "IN_PROGRESS"
        assert dash_001_updates[1]["data"]["new_status"] == "DONE"

    @pytest.mark.integration
    def test_execution_progress_tracking(self, temp_project, dashboard):
        """Test real-time execution progress tracking."""
        client = MockWebSocketConnection()
        dashboard.add_websocket_connection(client)
        
        async def test_progress_tracking():
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            
            try:
                # Simulate execution progress updates
                progress_steps = [
                    (0.0, "Starting ticket execution"),
                    (0.2, "Analyzing requirements"),
                    (0.4, "Creating files"),
                    (0.6, "Implementing functionality"),
                    (0.8, "Running tests"),
                    (1.0, "Execution completed")
                ]
                
                for progress, details in progress_steps:
                    await dashboard.notify_execution_progress("dash_001", progress, details)
                    await asyncio.sleep(0.05)
                
                await asyncio.sleep(0.1)
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
        
        asyncio.run(test_progress_tracking())
        
        # Verify progress messages
        progress_messages = client.get_messages_by_type("execution_progress")
        assert len(progress_messages) == 6, "Should receive 6 progress updates"
        
        # Verify progress sequence
        for i, msg in enumerate(progress_messages):
            expected_progress = i * 0.2
            assert abs(msg["data"]["progress"] - expected_progress) < 0.01
            assert len(msg["data"]["details"]) > 0
            assert msg["data"]["ticket_id"] == "dash_001"

    @pytest.mark.integration
    def test_metrics_updates(self, temp_project, dashboard):
        """Test real-time metrics updates."""
        client = MockWebSocketConnection()
        dashboard.add_websocket_connection(client)
        
        async def test_metrics():
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            
            try:
                # Simulate metrics updates
                metrics_updates = [
                    {
                        "tickets_completed": 1,
                        "tickets_in_progress": 2,
                        "total_execution_time": 150.5,
                        "average_completion_time": 75.25,
                        "success_rate": 0.95
                    },
                    {
                        "tickets_completed": 2,
                        "tickets_in_progress": 1,
                        "total_execution_time": 285.3,
                        "average_completion_time": 142.65,
                        "success_rate": 0.97
                    },
                    {
                        "tickets_completed": 3,
                        "tickets_in_progress": 0,
                        "total_execution_time": 412.8,
                        "average_completion_time": 137.6,
                        "success_rate": 1.0
                    }
                ]
                
                for metrics in metrics_updates:
                    await dashboard.notify_metrics_update(metrics)
                    await asyncio.sleep(0.1)
                
                await asyncio.sleep(0.1)
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
        
        asyncio.run(test_metrics())
        
        # Verify metrics messages
        metrics_messages = client.get_messages_by_type("metrics_update")
        assert len(metrics_messages) == 3, "Should receive 3 metrics updates"
        
        # Verify metrics progression
        for i, msg in enumerate(metrics_messages):
            metrics = msg["data"]["metrics"]
            assert metrics["tickets_completed"] == i + 1
            assert metrics["tickets_in_progress"] == 2 - i
            assert metrics["success_rate"] >= 0.95

    @pytest.mark.integration
    def test_error_notifications(self, temp_project, dashboard):
        """Test real-time error notifications."""
        client = MockWebSocketConnection()
        dashboard.add_websocket_connection(client)
        
        async def test_error_notifications():
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            
            try:
                # Simulate various error types
                errors = [
                    ("dash_001", "File not found: config.yaml", "FileNotFoundError"),
                    ("dash_002", "Provider connection timeout", "TimeoutError"),
                    ("dash_003", "Invalid syntax in generated code", "SyntaxError"),
                    ("dash_001", "Permission denied writing to file", "PermissionError")
                ]
                
                for ticket_id, error_msg, error_type in errors:
                    await dashboard.notify_error(ticket_id, error_msg, error_type)
                    await asyncio.sleep(0.05)
                
                await asyncio.sleep(0.1)
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
        
        asyncio.run(test_error_notifications())
        
        # Verify error messages
        error_messages = client.get_messages_by_type("execution_error")
        assert len(error_messages) == 4, "Should receive 4 error notifications"
        
        # Verify error details
        for msg in error_messages:
            assert "ticket_id" in msg["data"]
            assert "error_message" in msg["data"]
            assert "error_type" in msg["data"]
            assert len(msg["data"]["error_message"]) > 0

    @pytest.mark.integration
    def test_concurrent_client_updates(self, temp_project, dashboard):
        """Test updates to multiple concurrent clients."""
        # Create multiple clients
        clients = [MockWebSocketConnection() for _ in range(5)]
        
        for client in clients:
            dashboard.add_websocket_connection(client)
        
        async def test_concurrent_updates():
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            
            try:
                # Send various types of updates concurrently
                update_tasks = [
                    dashboard.notify_ticket_status_change("dash_001", "TODO", "IN_PROGRESS"),
                    dashboard.notify_execution_progress("dash_002", 0.5, "Halfway done"),
                    dashboard.notify_metrics_update({"active_tickets": 2, "completed": 1}),
                    dashboard.notify_error("dash_003", "Test error", "TestError"),
                    dashboard.notify_ticket_status_change("dash_002", "TODO", "DONE")
                ]
                
                await asyncio.gather(*update_tasks)
                await asyncio.sleep(0.2)  # Allow processing
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
        
        asyncio.run(test_concurrent_updates())
        
        # Verify all clients received all updates
        for i, client in enumerate(clients):
            total_messages = len(client.messages_sent)
            assert total_messages == 5, f"Client {i} should receive 5 messages, got {total_messages}"
            
            # Verify message types
            status_msgs = client.get_messages_by_type("ticket_status_change")
            progress_msgs = client.get_messages_by_type("execution_progress")
            metrics_msgs = client.get_messages_by_type("metrics_update")
            error_msgs = client.get_messages_by_type("execution_error")
            
            assert len(status_msgs) == 2, "Should have 2 status messages"
            assert len(progress_msgs) == 1, "Should have 1 progress message"
            assert len(metrics_msgs) == 1, "Should have 1 metrics message"
            assert len(error_msgs) == 1, "Should have 1 error message"

    @pytest.mark.integration
    def test_database_integration_with_updates(self, temp_project, dashboard):
        """Test database integration with real-time updates."""
        client = MockWebSocketConnection()
        dashboard.add_websocket_connection(client)
        
        # Create tickets file
        yaml_data = self._create_test_tickets()
        tickets_file = temp_project / "tickets.yaml"
        with open(tickets_file, 'w') as f:
            yaml.dump(yaml_data, f)
        
        async def test_database_integration():
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            
            try:
                # Simulate ticket execution with database updates
                for ticket_data in yaml_data["tickets"]:
                    ticket_id = ticket_data["id"]
                    
                    # Update to IN_PROGRESS
                    update_ticket_in_database(ticket_id, "IN_PROGRESS", str(temp_project))
                    await dashboard.notify_ticket_status_change(ticket_id, "TODO", "IN_PROGRESS")
                    
                    # Simulate progress
                    await dashboard.notify_execution_progress(ticket_id, 0.5, "Processing")
                    
                    # Update to DONE
                    update_ticket_in_database(ticket_id, "DONE", str(temp_project))
                    await dashboard.notify_ticket_status_change(ticket_id, "IN_PROGRESS", "DONE")
                    
                    await asyncio.sleep(0.1)
                
                await asyncio.sleep(0.2)
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
        
        asyncio.run(test_database_integration())
        
        # Verify database state
        db_manager = get_db_manager()
        with db_manager.get_session() as db:
            tickets = db.query(Ticket).filter(Ticket.project_id == dashboard.project_id).all()
            
            # All tickets should be DONE
            done_tickets = [t for t in tickets if t.status == "DONE"]
            assert len(done_tickets) == 3, "All 3 tickets should be marked as DONE"
        
        # Verify real-time updates matched database changes
        status_messages = client.get_messages_by_type("ticket_status_change")
        progress_messages = client.get_messages_by_type("execution_progress")
        
        assert len(status_messages) == 6, "Should have 6 status change messages (2 per ticket)"
        assert len(progress_messages) == 3, "Should have 3 progress messages"
        
        # Verify current project status
        current_status = dashboard.get_current_project_status()
        assert current_status["total_tickets"] == 3
        assert current_status["status_breakdown"].get("DONE", 0) == 3

    @pytest.mark.integration
    def test_performance_under_load(self, temp_project, dashboard):
        """Test dashboard performance under high update load."""
        # Create many clients
        num_clients = 20
        clients = [MockWebSocketConnection() for _ in range(num_clients)]
        
        for client in clients:
            dashboard.add_websocket_connection(client)
        
        async def test_high_load():
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            start_time = time.time()
            
            try:
                # Generate many concurrent updates
                update_tasks = []
                
                for i in range(100):  # 100 updates
                    ticket_id = f"load_test_{i % 10}"  # 10 different tickets
                    
                    if i % 4 == 0:
                        task = dashboard.notify_ticket_status_change(
                            ticket_id, "TODO", "IN_PROGRESS"
                        )
                    elif i % 4 == 1:
                        task = dashboard.notify_execution_progress(
                            ticket_id, i / 100.0, f"Progress {i}"
                        )
                    elif i % 4 == 2:
                        task = dashboard.notify_metrics_update({
                            "update_count": i,
                            "timestamp": time.time()
                        })
                    else:
                        task = dashboard.notify_error(
                            ticket_id, f"Test error {i}", "TestError"
                        )
                    
                    update_tasks.append(task)
                
                # Send all updates concurrently
                await asyncio.gather(*update_tasks)
                
                # Wait for processing
                await asyncio.sleep(1.0)
                
                end_time = time.time()
                total_time = end_time - start_time
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
            
            return total_time
        
        total_processing_time = asyncio.run(test_high_load())
        
        # Verify performance
        assert total_processing_time < 5.0, f"Processing took too long: {total_processing_time:.2f}s"
        
        # Verify all clients received messages
        for i, client in enumerate(clients):
            assert len(client.messages_sent) == 100, f"Client {i} should receive 100 messages"
        
        # Calculate throughput
        total_messages = sum(len(client.messages_sent) for client in clients)
        expected_messages = num_clients * 100  # 20 clients * 100 updates each
        
        assert total_messages == expected_messages, f"Expected {expected_messages}, got {total_messages}"
        
        throughput = total_messages / total_processing_time
        assert throughput > 500, f"Throughput too low: {throughput:.2f} messages/second"

    @pytest.mark.integration
    def test_websocket_disconnection_handling(self, temp_project, dashboard):
        """Test handling of WebSocket disconnections."""
        # Create clients, some will disconnect
        stable_client = MockWebSocketConnection()
        disconnecting_clients = [MockWebSocketConnection() for _ in range(3)]
        
        dashboard.add_websocket_connection(stable_client)
        for client in disconnecting_clients:
            dashboard.add_websocket_connection(client)
        
        async def test_disconnection_handling():
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            
            try:
                # Send initial update
                await dashboard.notify_ticket_status_change("test_001", "TODO", "IN_PROGRESS")
                await asyncio.sleep(0.1)
                
                # Simulate client disconnections
                for client in disconnecting_clients:
                    client.connected = False
                
                # Send updates after disconnections
                await dashboard.notify_execution_progress("test_001", 0.5, "Progress update")
                await dashboard.notify_metrics_update({"disconnection_test": True})
                await asyncio.sleep(0.1)
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
        
        asyncio.run(test_disconnection_handling())
        
        # Verify stable client received all updates
        stable_messages = stable_client.messages_sent
        assert len(stable_messages) == 3, "Stable client should receive all 3 updates"
        
        # Verify disconnected clients stopped receiving updates after disconnection
        for client in disconnecting_clients:
            # Should only have the first message (before disconnection)
            assert len(client.messages_sent) == 1, "Disconnected clients should only have first message"

    @pytest.mark.integration
    def test_update_queue_overflow_handling(self, temp_project, dashboard):
        """Test handling of update queue overflow."""
        client = MockWebSocketConnection()
        dashboard.add_websocket_connection(client)
        
        # Override queue with smaller size for testing
        original_queue = dashboard.update_queue
        dashboard.update_queue = asyncio.Queue(maxsize=5)  # Small queue
        
        async def test_queue_overflow():
            # Don't start processor to cause queue overflow
            
            try:
                # Fill queue beyond capacity
                for i in range(10):  # More than queue size
                    try:
                        await asyncio.wait_for(
                            dashboard.notify_ticket_status_change(
                                f"overflow_test_{i}", "TODO", "IN_PROGRESS"
                            ),
                            timeout=0.1
                        )
                    except asyncio.TimeoutError:
                        # Expected for overflow
                        break
                
                # Now start processor to drain queue
                processor_task = asyncio.create_task(dashboard.start_update_processor())
                await asyncio.sleep(0.5)  # Let it process
                
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
                
            finally:
                # Restore original queue
                dashboard.update_queue = original_queue
        
        asyncio.run(test_queue_overflow())
        
        # Verify that some messages were processed (up to queue capacity)
        messages_received = len(client.messages_sent)
        assert 0 <= messages_received <= 5, f"Should receive 0-5 messages, got {messages_received}"

    @pytest.mark.integration
    def test_real_time_dashboard_integration(self, temp_project, dashboard):
        """Test complete real-time dashboard integration scenario."""
        # Setup multiple clients with different roles
        admin_client = MockWebSocketConnection()
        admin_client.client_id = "admin_dashboard"
        
        developer_client = MockWebSocketConnection()
        developer_client.client_id = "developer_view"
        
        monitor_client = MockWebSocketConnection()
        monitor_client.client_id = "monitoring_system"
        
        dashboard.add_websocket_connection(admin_client)
        dashboard.add_websocket_connection(developer_client)
        dashboard.add_websocket_connection(monitor_client)
        
        # Create comprehensive ticket scenario
        yaml_data = self._create_test_tickets()
        tickets_file = temp_project / "tickets.yaml"
        with open(tickets_file, 'w') as f:
            yaml.dump(yaml_data, f)
        
        # Insert tickets into database
        db_manager = get_db_manager()
        with db_manager.get_session() as db:
            for ticket_data in yaml_data["tickets"]:
                ticket = Ticket(
                    ticket_number=ticket_data["id"],
                    title=ticket_data["title"],
                    description=ticket_data["description"],
                    status=ticket_data["status"],
                    priority=ticket_data.get("priority", "medium"),
                    model=ticket_data.get("model", "balanced"),
                    project_id=dashboard.project_id,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(ticket)
            db.commit()
        
        async def test_complete_integration():
            processor_task = asyncio.create_task(dashboard.start_update_processor())
            
            try:
                # Simulate complete project lifecycle with real-time updates
                project_start_time = time.time()
                
                # Initialize project metrics
                await dashboard.notify_metrics_update({
                    "project_start_time": project_start_time,
                    "total_tickets": 3,
                    "tickets_todo": 3,
                    "tickets_in_progress": 0,
                    "tickets_done": 0
                })
                
                # Execute each ticket with detailed progress tracking
                for i, ticket_data in enumerate(yaml_data["tickets"]):
                    ticket_id = ticket_data["id"]
                    
                    # Start ticket
                    await dashboard.notify_ticket_status_change(ticket_id, "TODO", "IN_PROGRESS")
                    
                    # Progress through execution phases
                    execution_phases = [
                        (0.1, "Analyzing requirements"),
                        (0.3, "Planning implementation"),
                        (0.5, "Creating files"),
                        (0.7, "Implementing functionality"),
                        (0.9, "Running tests"),
                        (1.0, "Finalizing")
                    ]
                    
                    for progress, phase in execution_phases:
                        await dashboard.notify_execution_progress(ticket_id, progress, phase)
                        await asyncio.sleep(0.02)
                    
                    # Complete ticket
                    await dashboard.notify_ticket_status_change(ticket_id, "IN_PROGRESS", "DONE")
                    
                    # Update database to match notification
                    db_manager = get_db_manager()
                    with db_manager.get_session() as db:
                        ticket_record = db.query(Ticket).filter(
                            Ticket.ticket_number == ticket_id
                        ).first()
                        if ticket_record:
                            ticket_record.status = "DONE"
                            ticket_record.completed_at = datetime.now(timezone.utc)
                        db.commit()
                    
                    # Update project metrics
                    await dashboard.notify_metrics_update({
                        "project_start_time": project_start_time,
                        "total_tickets": 3,
                        "tickets_todo": 2 - i,
                        "tickets_in_progress": 0,
                        "tickets_done": i + 1,
                        "completion_percentage": ((i + 1) / 3) * 100
                    })
                    
                    # Simulate occasional errors
                    if i == 1:  # Error on second ticket
                        await dashboard.notify_error(
                            ticket_id, 
                            "Temporary network timeout, retrying...", 
                            "NetworkTimeout"
                        )
                
                # Final project completion
                project_end_time = time.time()
                project_duration = project_end_time - project_start_time
                
                await dashboard.notify_metrics_update({
                    "project_completed": True,
                    "project_duration": project_duration,
                    "total_tickets": 3,
                    "tickets_done": 3,
                    "success_rate": 1.0,
                    "completion_percentage": 100
                })
                
                await asyncio.sleep(0.2)  # Final processing
                
            finally:
                dashboard.stop_update_processor()
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
        
        asyncio.run(test_complete_integration())
        
        # Verify comprehensive real-time updates for all clients
        all_clients = [admin_client, developer_client, monitor_client]
        
        for client in all_clients:
            # Should receive all types of updates
            status_updates = client.get_messages_by_type("ticket_status_change")
            progress_updates = client.get_messages_by_type("execution_progress")
            metrics_updates = client.get_messages_by_type("metrics_update")
            error_updates = client.get_messages_by_type("execution_error")
            
            assert len(status_updates) == 6, "Should have 6 status updates (2 per ticket)"
            assert len(progress_updates) == 18, "Should have 18 progress updates (6 per ticket)"
            assert len(metrics_updates) == 5, "Should have 5 metrics updates (1 initial + 3 per ticket + 1 final)"
            assert len(error_updates) == 1, "Should have 1 error update"
        
        # Verify final project state in database
        final_status = dashboard.get_current_project_status()
        assert final_status["total_tickets"] == 3
        assert final_status["status_breakdown"].get("DONE", 0) == 3
        assert final_status["status_breakdown"].get("TODO", 0) == 0
        assert final_status["status_breakdown"].get("IN_PROGRESS", 0) == 0
        
        # Generate integration report
        integration_report = {
            "test_summary": {
                "clients_tested": len(all_clients),
                "total_updates_sent": sum(len(client.messages_sent) for client in all_clients),
                "update_types": {
                    "status_changes": len(admin_client.get_messages_by_type("ticket_status_change")),
                    "progress_updates": len(admin_client.get_messages_by_type("execution_progress")),
                    "metrics_updates": len(admin_client.get_messages_by_type("metrics_update")),
                    "error_notifications": len(admin_client.get_messages_by_type("execution_error"))
                }
            },
            "final_project_state": final_status
        }
        
        report_file = temp_project / "dashboard_integration_report.json"
        with open(report_file, 'w') as f:
            json.dump(integration_report, f, indent=2)
        
        assert report_file.exists()
        assert integration_report["test_summary"]["total_updates_sent"] > 0