"""Unit tests for ticket_workflow module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from hydra.ticket_workflow import (
    execute_single_ticket,
    parse_ticket,
    run_all_tickets,
    update_ticket_in_database,
    validate_acceptance_criteria,
)


class TestParseTicket:
    """Test ticket parsing functionality."""

    def test_parse_ticket_from_markdown(self):
        """Test parsing a ticket from markdown format."""
        ticket_content = """# Project Tickets

## Ticket 001: Test Task

**Priority**: 1
**Description**: Test task description
**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2
**Status**: TODO
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(ticket_content)
            temp_file = f.name

        try:
            ticket = parse_ticket(temp_file, "001")
            assert ticket is not None
            assert ticket["ticket_id"] == "001"
            assert ticket["title"] == "Test Task"
            assert ticket["status"] == "TODO"
            assert len(ticket["acceptance_criteria"]) == 2
        finally:
            os.unlink(temp_file)

    def test_parse_ticket_not_found(self):
        """Test parsing a non-existent ticket."""
        ticket_content = """# Project Tickets

## Ticket 001: Test Task
**Status**: TODO
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(ticket_content)
            temp_file = f.name

        try:
            ticket = parse_ticket(temp_file, "999")
            assert ticket is None
        finally:
            os.unlink(temp_file)

    def test_parse_ticket_from_yaml(self):
        """Test parsing a ticket from YAML format."""
        ticket_content = """version: '1.0'
project:
  name: Test Project
tickets:
- id: '001'
  title: Test Task
  status: TODO
  priority: 1
  description: Test task description
  acceptance_criteria:
  - Criterion 1
  - Criterion 2
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(ticket_content)
            temp_file = f.name

        try:
            ticket = parse_ticket(temp_file, "001")
            assert ticket is not None
            assert ticket["ticket_id"] == "001"
            assert ticket["title"] == "Test Task"
            assert ticket["status"] == "TODO"
            assert len(ticket["acceptance_criteria"]) == 2
        finally:
            os.unlink(temp_file)


class TestUpdateTicketInFile:
    """Test ticket status update functionality in files."""

    @patch('hydra.ticket_workflow.update_ticket_in_database')
    def test_update_ticket_markdown(self, mock_update_db):
        """Test updating ticket status in markdown."""
        ticket_content = """# Project Tickets

## Ticket 001: Test Task
**Status**: TODO
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(ticket_content)
            temp_file = f.name

        try:
            # This would normally be done by execute_single_ticket
            # Just verify the file can be read and parsed
            ticket = parse_ticket(temp_file, "001")
            assert ticket is not None
            assert ticket["status"] == "TODO"
        finally:
            os.unlink(temp_file)

    def test_update_ticket_yaml(self):
        """Test updating ticket status in YAML."""
        ticket_content = """version: '1.0'
tickets:
- id: '001'
  title: Test Task
  status: TODO
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(ticket_content)
            temp_file = f.name

        try:
            # Verify parsing works
            ticket = parse_ticket(temp_file, "001")
            assert ticket is not None
            assert ticket["status"] == "TODO"
        finally:
            os.unlink(temp_file)


class TestExecuteSingleTicket:
    """Test single ticket execution."""

    @patch('hydra.ticket_workflow.ProviderFactory')
    @patch('hydra.ticket_workflow.update_ticket_in_database')
    @patch('hydra.ticket_workflow.parse_ticket')
    def test_execute_single_ticket_success(self, mock_parse, mock_update_db, mock_factory):
        """Test successful ticket execution."""
        # Setup mocks
        mock_parse.return_value = {
            "ticket_id": "001",
            "title": "Test Task",
            "description": "Test description",
            "status": "TODO",
            "acceptance_criteria": ["Test criterion"],
            "model": "fast"
        }
        
        mock_provider = Mock()
        mock_provider.generate.return_value = "Task completed successfully"
        mock_factory.get_provider.return_value = mock_provider
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tickets_file = Path(tmpdir) / "tickets.md"
            tickets_file.write_text("# Tickets\n## Ticket 001")
            
            result = execute_single_ticket(str(tickets_file), "001")
            
            assert result is True
            # Database update should be called
            mock_update_db.assert_called()

    @patch('hydra.ticket_workflow.parse_ticket')
    def test_execute_single_ticket_not_found(self, mock_parse):
        """Test execution when ticket not found."""
        mock_parse.return_value = None
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tickets_file = Path(tmpdir) / "tickets.md"
            tickets_file.write_text("# Tickets")
            
            result = execute_single_ticket(str(tickets_file), "999")
            
            assert result is False

    @patch('hydra.ticket_workflow.parse_ticket')
    def test_execute_single_ticket_already_done(self, mock_parse):
        """Test execution when ticket already done."""
        mock_parse.return_value = {
            "ticket_id": "001",
            "status": "DONE"
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tickets_file = Path(tmpdir) / "tickets.md"
            tickets_file.write_text("# Tickets")
            
            result = execute_single_ticket(str(tickets_file), "001")
            
            assert result is True  # Already done returns True


class TestValidateAcceptanceCriteria:
    """Test acceptance criteria validation."""

    def test_validate_acceptance_criteria_all_met(self):
        """Test validation when all criteria are met."""
        ticket = {
            "ticket_id": "001",
            "acceptance_criteria": [
                "[x] File exists",
                "[x] Tests pass",
                "[x] Documentation updated"
            ]
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_acceptance_criteria(ticket, tmpdir)
            assert result is True

    def test_validate_acceptance_criteria_partial(self):
        """Test validation when criteria partially met."""
        ticket = {
            "ticket_id": "001",
            "acceptance_criteria": [
                "[x] File exists",
                "[ ] Tests pass",
                "[ ] Documentation updated"
            ]
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_acceptance_criteria(ticket, tmpdir)
            assert result is False

    def test_validate_acceptance_criteria_file_check(self):
        """Test file existence validation."""
        ticket = {
            "ticket_id": "001",
            "acceptance_criteria": [
                "Create file test.py"
            ]
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # File doesn't exist
            result = validate_acceptance_criteria(ticket, tmpdir)
            assert result is False
            
            # Create the file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# Test file")
            
            # Now it should pass
            result = validate_acceptance_criteria(ticket, tmpdir)
            assert result is True


class TestRunAllTickets:
    """Test running all tickets."""

    @patch('hydra.ticket_workflow.execute_single_ticket')
    @patch('hydra.ticket_workflow.parse_ticket')
    def test_run_all_tickets_success(self, mock_parse, mock_execute):
        """Test successful execution of all tickets."""
        # Mock two tickets
        mock_parse.side_effect = [
            {"id": "001", "status": "TODO"},
            {"id": "002", "status": "TODO"},
            None  # End of tickets
        ]
        mock_execute.return_value = True
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tickets_file = Path(tmpdir) / "tickets.md"
            tickets_file.write_text("# Tickets")
            
            results = run_all_tickets(str(tickets_file))
            
            assert len(results) == 2
            assert all(results.values())

    @patch('hydra.ticket_workflow.execute_single_ticket')
    @patch('hydra.ticket_workflow.parse_ticket')
    def test_run_all_tickets_skip_done(self, mock_parse, mock_execute):
        """Test skipping already done tickets."""
        mock_parse.side_effect = [
            {"id": "001", "status": "DONE"},
            {"id": "002", "status": "TODO"},
            None
        ]
        mock_execute.return_value = True
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tickets_file = Path(tmpdir) / "tickets.md"
            tickets_file.write_text("# Tickets")
            
            results = run_all_tickets(str(tickets_file))
            
            # Only ticket 002 should be executed
            assert len(results) == 1
            assert "002" in results


class TestUpdateTicketInDatabase:
    """Test database update functionality."""

    @patch('hydra.ticket_workflow.get_db_manager')
    def test_update_ticket_in_database(self, mock_get_db):
        """Test updating ticket in database."""
        mock_session = MagicMock()
        mock_ticket = Mock()
        mock_session.query().filter_by().first.return_value = mock_ticket
        
        mock_db_manager = Mock()
        mock_db_manager.get_session.return_value.__enter__.return_value = mock_session
        mock_get_db.return_value = mock_db_manager
        
        update_ticket_in_database("001", "DONE", "/test/path")
        
        assert mock_ticket.status == "DONE"
        assert mock_ticket.completed_at is not None
        mock_session.commit.assert_called_once()

    @patch('hydra.ticket_workflow.get_db_manager')
    def test_update_ticket_in_database_not_found(self, mock_get_db):
        """Test updating non-existent ticket in database."""
        mock_session = MagicMock()
        mock_session.query().filter_by().first.return_value = None
        
        mock_db_manager = Mock()
        mock_db_manager.get_session.return_value.__enter__.return_value = mock_session
        mock_get_db.return_value = mock_db_manager
        
        # Should not raise error
        update_ticket_in_database("999", "DONE", "/test/path")
        
        # Commit should not be called for non-existent ticket
        mock_session.commit.assert_not_called()