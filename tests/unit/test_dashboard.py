"""Unit tests for dashboard module."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hydra.dashboard import DashboardServer, DashboardState, TicketStatus


class TestDashboardState(unittest.TestCase):
    """Test dashboard state management."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.state = DashboardState(state_dir=self.temp_dir)

    def test_init(self):
        """Test state initialization."""
        self.assertIsNotNone(self.state)
        self.assertEqual(len(self.state.tickets), 0)
        self.assertIsNone(self.state.session)

    def test_start_session(self):
        """Test starting a session."""
        self.state.start_session(
            session_id="test-001",
            tickets_path="tickets.md",
            total_tickets=5,
            total_waves=3,
            workers=2
        )
        
        self.assertIsNotNone(self.state.session)
        self.assertEqual(self.state.session.session_id, "test-001")
        self.assertEqual(self.state.session.total_tickets, 5)
        self.assertEqual(self.state.session.total_waves, 3)
        self.assertEqual(self.state.session.workers, 2)

    def test_add_ticket(self):
        """Test adding a ticket."""
        self.state.add_ticket("001", "Test ticket", "sonnet", ["002"])
        
        self.assertEqual(len(self.state.tickets), 1)
        self.assertIn("001", self.state.tickets)
        ticket = self.state.tickets["001"]
        self.assertEqual(ticket.title, "Test ticket")
        self.assertEqual(ticket.model, "sonnet")
        self.assertEqual(ticket.dependencies, ["002"])
        self.assertEqual(ticket.status, TicketStatus.PENDING)

    def test_update_ticket_status(self):
        """Test updating ticket status."""
        self.state.add_ticket("001", "Test ticket", "sonnet", [])
        
        # Update to running
        self.state.update_ticket_status("001", TicketStatus.RUNNING)
        ticket = self.state.tickets["001"]
        self.assertEqual(ticket.status, TicketStatus.RUNNING)
        self.assertIsNotNone(ticket.start_time)
        
        # Update to completed
        self.state.update_ticket_status("001", TicketStatus.COMPLETED)
        ticket = self.state.tickets["001"]
        self.assertEqual(ticket.status, TicketStatus.COMPLETED)
        self.assertIsNotNone(ticket.end_time)

    def test_add_ticket_log(self):
        """Test adding log entries."""
        self.state.add_ticket("001", "Test ticket", "sonnet", [])
        self.state.add_ticket_log("001", "Starting execution")
        self.state.add_ticket_log("001", "Task completed")
        
        ticket = self.state.tickets["001"]
        self.assertEqual(len(ticket.logs), 2)
        self.assertIn("Starting execution", ticket.logs)
        self.assertIn("Task completed", ticket.logs)

    def test_get_state(self):
        """Test getting state as dictionary."""
        self.state.start_session(
            session_id="test-001",
            tickets_path="tickets.md",
            total_tickets=2,
            total_waves=1,
            workers=1
        )
        self.state.add_ticket("001", "Ticket 1", "sonnet", [])
        self.state.add_ticket("002", "Ticket 2", "opus", ["001"])
        
        state_dict = self.state.get_state()
        
        self.assertIn("session", state_dict)
        self.assertIn("tickets", state_dict)
        self.assertEqual(len(state_dict["tickets"]), 2)
        self.assertEqual(state_dict["session"]["total_tickets"], 2)

    def test_clear(self):
        """Test clearing state."""
        self.state.start_session(
            session_id="test-001",
            tickets_path="tickets.md",
            total_tickets=1,
            total_waves=1,
            workers=1
        )
        self.state.add_ticket("001", "Test", "sonnet", [])
        
        self.state.clear()
        
        self.assertEqual(len(self.state.tickets), 0)
        self.assertIsNone(self.state.session)

    def test_persistence(self):
        """Test state persistence."""
        # Create and save state
        self.state.start_session(
            session_id="test-001",
            tickets_path="tickets.md",
            total_tickets=1,
            total_waves=1,
            workers=1
        )
        self.state.add_ticket("001", "Test", "sonnet", [])
        
        # Create new state instance and load
        state2 = DashboardState(state_dir=self.temp_dir)
        
        self.assertIsNotNone(state2.session)
        self.assertEqual(state2.session.session_id, "test-001")
        self.assertEqual(len(state2.tickets), 1)
        self.assertIn("001", state2.tickets)


class TestDashboardServer(unittest.TestCase):
    """Test dashboard server."""

    def test_init(self):
        """Test server initialization."""
        server = DashboardServer(port=8081)
        self.assertEqual(server.port, 8081)
        self.assertEqual(server.host, "localhost")
        self.assertFalse(server.running)
        self.assertIsNotNone(server.dashboard_state)

    def test_start_stop(self):
        """Test starting and stopping server."""
        server = DashboardServer(port=8082)
        
        try:
            # Start server
            server.start()
            self.assertTrue(server.running)
            time.sleep(0.5)  # Give server time to start
            
            # Stop server
            server.stop()
            self.assertFalse(server.running)
        except RuntimeError as e:
            if "can't start new thread" in str(e):
                self.skipTest("Skipping test in CI environment - thread limit reached")
            else:
                raise


if __name__ == "__main__":
    unittest.main()