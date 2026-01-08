"""Tests for YAML ticket system."""

import os
import tempfile

import pytest
import yaml

from hydra.tickets.compatibility import TicketFormatHandler
from hydra.tickets.generator import TicketGenerator
from hydra.tickets.yaml_handler import TicketYAMLHandler


class TestYAMLHandler:
    """Test YAML ticket handler."""

    def test_save_and_load_tickets(self):
        """Test saving and loading tickets."""
        handler = TicketYAMLHandler()

        data = {
            "version": "1.0",
            "tickets": [
                {
                    "id": "001",
                    "title": "First task",
                    "status": "TODO",
                    "priority": 1,
                    "model": "fast",
                    "description": "Test description",
                    "acceptance_criteria": ["Do thing 1", "Do thing 2"],
                    "dependencies": [],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            temp_path = f.name

        try:
            handler.save_tickets(data, temp_path)
            loaded = handler.load_tickets(temp_path)

            assert loaded["version"] == "1.0"
            assert len(loaded["tickets"]) == 1
            assert loaded["tickets"][0]["id"] == "001"
            assert loaded["tickets"][0]["title"] == "First task"

        finally:
            os.unlink(temp_path)

    def test_parse_single_ticket(self):
        """Test parsing single ticket."""
        handler = TicketYAMLHandler()

        data = {
            "tickets": [
                {"id": "001", "title": "Task 1", "status": "TODO"},
                {"id": "002", "title": "Task 2", "status": "DONE"},
            ]
        }

        ticket = handler.parse_single_ticket(data, "002")
        assert ticket is not None
        assert ticket["number"] == "002"
        assert ticket["title"] == "Task 2"
        assert ticket["completed"] is True

        ticket = handler.parse_single_ticket(data, "999")
        assert ticket is None

    def test_update_ticket_status(self):
        """Test updating ticket status."""
        handler = TicketYAMLHandler()

        data = {"tickets": [{"id": "001", "title": "Task", "status": "TODO"}]}

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            temp_path = f.name

        try:
            handler.save_tickets(data, temp_path)
            handler.update_ticket_status(temp_path, "001", "DONE")

            loaded = handler.load_tickets(temp_path)
            assert loaded["tickets"][0]["status"] == "DONE"
            assert "completed_at" in loaded["tickets"][0]

        finally:
            os.unlink(temp_path)

    def test_validation(self):
        """Test structure validation."""
        handler = TicketYAMLHandler(strict_mode=True)

        # Missing tickets field
        with pytest.raises(ValueError, match="Missing 'tickets' field"):
            handler._validate_structure({})

        # Tickets not a list
        with pytest.raises(ValueError, match="'tickets' must be a list"):
            handler._validate_structure({"tickets": "not a list"})

        # Missing required field
        with pytest.raises(ValueError, match="missing required field"):
            handler._validate_structure({"tickets": [{"title": "Test"}]})


class TestCompatibility:
    """Test format compatibility layer."""

    def test_detect_yaml_format(self):
        """Test YAML format detection."""
        handler = TicketFormatHandler()

        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("version: 1.0\ntickets:\n  - id: 001\n")
            temp_path = f.name

        try:
            assert handler.detect_format(temp_path) == "yaml"
        finally:
            os.unlink(temp_path)

    def test_detect_md_format(self):
        """Test MD format detection."""
        handler = TicketFormatHandler()

        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("# Project Tickets\n\n## Ticket 001\n")
            temp_path = f.name

        try:
            assert handler.detect_format(temp_path) == "md"
        finally:
            os.unlink(temp_path)

    def test_parse_from_yaml(self):
        """Test parsing ticket from YAML."""
        handler = TicketFormatHandler()

        data = {
            "tickets": [
                {
                    "id": "001",
                    "title": "Test task",
                    "status": "TODO",
                    "description": "A test",
                    "dependencies": ["002", "003"],
                }
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            temp_path = f.name

        try:
            ticket = handler.parse_ticket(temp_path, "001")
            assert ticket is not None
            assert ticket["number"] == "001"
            assert ticket["title"] == "Test task"
            assert ticket["dependencies"] == ["002", "003"]

        finally:
            os.unlink(temp_path)

    def test_get_all_tickets(self):
        """Test getting all tickets."""
        handler = TicketFormatHandler()

        data = {
            "tickets": [
                {"id": "001", "title": "Task 1", "status": "TODO"},
                {"id": "002", "title": "Task 2", "status": "DONE"},
                {"id": "003", "title": "Task 3", "status": "IN_PROGRESS"},
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            temp_path = f.name

        try:
            tickets = handler.get_all_tickets(temp_path)
            assert len(tickets) == 3
            assert "001" in tickets
            assert "002" in tickets
            assert "003" in tickets
            assert tickets["002"]["completed"] is True

        finally:
            os.unlink(temp_path)


class TestGenerator:
    """Test ticket generator."""

    def test_parse_response(self):
        """Test parsing LLM response."""
        generator = TicketGenerator()

        # Direct YAML content (without Claude's prompts)
        yaml_content = """
- id: "001"
  title: Setup project
  status: TODO
  priority: 1
  model: fast
  description: Initialize project structure
  acceptance_criteria:
    - Create directories
    - Add config files
  dependencies: []
  
- id: "002"
  title: Implement core
  status: TODO
  priority: 2
  model: balanced
  description: Build core functionality
  acceptance_criteria:
    - Write main module
    - Add tests
  dependencies: ["001"]
"""

        # For direct YAML, it should parse successfully
        result = generator._parse_response(yaml_content)
        # The parser now returns either a list of tickets or None for empty input
        assert result is not None
        # Handle both list and dict responses
        if isinstance(result, list):
            tickets = result
        else:
            tickets = result.get("tickets", [])
        assert len(tickets) == 2
        assert tickets[0]["id"] == "001"
        assert tickets[0]["title"] == "Setup project"
        assert tickets[1]["dependencies"] == ["001"]

    def test_fallback_parse(self):
        """Test fallback parser."""
        generator = TicketGenerator()

        # YAML-like content that triggers fallback parser
        text_content = """- id: "001"
  title: First task
  status: TODO
  priority: 1
  model: fast
  description: Do the first thing
  acceptance_criteria:
    - Create directories
    - Add config
  dependencies: []

- id: "002"
  title: Second task
  status: TODO
  priority: 2
  model: balanced
  description: Do the second thing
  acceptance_criteria:
    - Create file
    - Run tests
  dependencies: ["001"]
"""

        tickets = generator._fallback_parse(text_content)
        assert len(tickets) == 2
        assert tickets[0]["id"] == "001"
        assert tickets[0]["title"] == "First task"
        assert tickets[1]["acceptance_criteria"] == ["Create file", "Run tests"]
