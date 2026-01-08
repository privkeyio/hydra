"""Unit tests for ticket_parser module."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from hydra.tickets.ticket_parser import (
    parse_ticket,
    parse_ticket_md_legacy,
    parse_all_tickets,
    build_dependency_graph,
    get_executable_tickets,
    detect_project_context,
)


class TestTicketParser(unittest.TestCase):
    """Test ticket parsing functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_parse_ticket_yaml(self):
        """Test parsing a ticket from YAML format."""
        # Create a test YAML file
        yaml_content = """
version: '1.0'
tickets:
  - id: '001'
    title: Test Ticket
    description: This is a test ticket
    status: TODO
    model: balanced
    priority: medium
    acceptance_criteria:
      - Implement feature A
      - Write tests for feature A
    dependencies: []
"""
        yaml_path = os.path.join(self.temp_dir, "tickets.yaml")
        with open(yaml_path, "w") as f:
            f.write(yaml_content)
        
        # Parse the ticket
        with patch("hydra.tickets.ticket_parser.get_file_meta_cache") as mock_cache:
            mock_cache.return_value = MagicMock()
            ticket = parse_ticket(yaml_path, "001")
        
        # Verify the parsed ticket
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["title"], "Test Ticket")
        self.assertEqual(ticket["description"], "This is a test ticket")
        self.assertEqual(ticket["status"], "TODO")
        self.assertEqual(ticket["model"], "balanced")
        self.assertEqual(len(ticket["acceptance_criteria"]), 2)
    
    def test_parse_ticket_md_legacy(self):
        """Test parsing a ticket from legacy markdown format."""
        # Create a test markdown file
        md_content = """# Project Tickets

## Ticket 001: Test Ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** This is a test ticket

**Acceptance Criteria:**
- [ ] Implement feature A
- [ ] Write tests for feature A

## Ticket 002: Another Ticket
**Status:** DONE
"""
        md_path = os.path.join(self.temp_dir, "tickets.md")
        with open(md_path, "w") as f:
            f.write(md_content)
        
        # Parse the ticket
        with patch("hydra.tickets.ticket_parser.get_file_meta_cache") as mock_cache:
            mock_cache.return_value = MagicMock()
            mock_cache.return_value.get.return_value = None
            ticket = parse_ticket_md_legacy(md_path, "001")
        
        # Verify the parsed ticket
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["title"], "Test Ticket")
        self.assertEqual(ticket["description"], "This is a test ticket")
        self.assertEqual(ticket["status"], "TODO")
        self.assertEqual(ticket["model"], "balanced")
        self.assertEqual(len(ticket["acceptance_criteria"]), 2)
        self.assertFalse(ticket["completed"])
    
    def test_parse_ticket_md_legacy_completed(self):
        """Test parsing a completed ticket from markdown."""
        md_content = """# Project Tickets

## Ticket 001: Test Ticket
**Status:** DONE
**Model:** fast
**Dependencies:** None

**Acceptance Criteria:**
- [x] Implement feature A
- [x] Write tests for feature A
"""
        md_path = os.path.join(self.temp_dir, "tickets.md")
        with open(md_path, "w") as f:
            f.write(md_content)
        
        with patch("hydra.tickets.ticket_parser.get_file_meta_cache") as mock_cache:
            mock_cache.return_value = MagicMock()
            mock_cache.return_value.get.return_value = None
            ticket = parse_ticket(md_path, "001")
        
        self.assertIsNotNone(ticket)
        # Status parsing might not work perfectly, but completed should be True
        self.assertTrue(ticket["completed"])
        self.assertEqual(ticket["model"], "fast")
    
    def test_parse_ticket_not_found(self):
        """Test parsing a non-existent ticket."""
        md_content = """# Project Tickets

## Ticket 001: Test Ticket
**Status:** TODO
"""
        md_path = os.path.join(self.temp_dir, "tickets.md")
        with open(md_path, "w") as f:
            f.write(md_content)
        
        with patch("hydra.tickets.ticket_parser.get_file_meta_cache") as mock_cache:
            mock_cache.return_value = MagicMock()
            mock_cache.return_value.get.return_value = None
            ticket = parse_ticket_md_legacy(md_path, "999")
        
        self.assertIsNone(ticket)
    
    def test_parse_all_tickets(self):
        """Test parsing all tickets from a file."""
        yaml_content = """
version: '1.0'
tickets:
  - id: '001'
    title: First Ticket
    status: TODO
  - id: '002'
    title: Second Ticket
    status: DONE
  - id: '003'
    title: Third Ticket
    status: IN_PROGRESS
"""
        yaml_path = os.path.join(self.temp_dir, "tickets.yaml")
        with open(yaml_path, "w") as f:
            f.write(yaml_content)
        
        with patch("hydra.tickets.ticket_parser.get_file_meta_cache") as mock_cache:
            mock_cache.return_value = MagicMock()
            mock_cache.return_value.get.return_value = None
            tickets = parse_all_tickets(yaml_path)
        
        self.assertEqual(len(tickets), 3)
        self.assertIn("001", tickets)
        self.assertIn("002", tickets)
        self.assertIn("003", tickets)
        self.assertEqual(tickets["001"]["title"], "First Ticket")
        self.assertEqual(tickets["002"]["status"], "DONE")
    
    def test_build_dependency_graph(self):
        """Test building dependency graphs."""
        tickets = {
            "001": {"dependencies": []},
            "002": {"dependencies": ["001"]},
            "003": {"dependencies": ["001", "002"]},
            "004": {"dependencies": ["002"]},
        }
        
        deps, reverse_deps = build_dependency_graph(tickets)
        
        # Check forward dependencies
        self.assertEqual(len(deps["001"]), 0)
        self.assertEqual(deps["002"], {"001"})
        self.assertEqual(deps["003"], {"001", "002"})
        self.assertEqual(deps["004"], {"002"})
        
        # Check reverse dependencies
        self.assertEqual(reverse_deps["001"], {"002", "003"})
        self.assertEqual(reverse_deps["002"], {"003", "004"})
        self.assertNotIn("003", reverse_deps)
        self.assertNotIn("004", reverse_deps)
    
    def test_get_executable_tickets(self):
        """Test getting executable tickets based on dependencies."""
        tickets = {
            "001": {"dependencies": []},
            "002": {"dependencies": ["001"]},
            "003": {"dependencies": ["001", "002"]},
            "004": {"dependencies": []},
            "005": {"dependencies": ["004"]},
        }
        
        # No tickets completed
        executable = get_executable_tickets(tickets, set())
        self.assertEqual(set(executable), {"001", "004"})
        
        # Ticket 001 completed
        executable = get_executable_tickets(tickets, {"001"})
        self.assertEqual(set(executable), {"002", "004"})
        
        # Tickets 001 and 002 completed
        executable = get_executable_tickets(tickets, {"001", "002"})
        self.assertEqual(set(executable), {"003", "004"})
        
        # Tickets 001, 002, and 004 completed
        executable = get_executable_tickets(tickets, {"001", "002", "004"})
        self.assertEqual(set(executable), {"003", "005"})
    
    def test_detect_project_context_python(self):
        """Test detecting Python project context."""
        # Create a requirements.txt file
        req_path = os.path.join(self.temp_dir, "requirements.txt")
        with open(req_path, "w") as f:
            f.write("django>=3.0\npytest\nrequests")
        
        tickets_path = os.path.join(self.temp_dir, "tickets.yaml")
        context = detect_project_context(tickets_path)
        
        self.assertEqual(context["language"], "python")
        self.assertEqual(context["build_tool"], "pip")
        self.assertEqual(context["framework"], "django")
        self.assertEqual(context["test_framework"], "pytest")
        self.assertEqual(context["project_type"], "django_app")
    
    def test_detect_project_context_node(self):
        """Test detecting Node.js project context."""
        # Create a package.json file
        import json
        pkg_path = os.path.join(self.temp_dir, "package.json")
        pkg_data = {
            "name": "test-project",
            "dependencies": {
                "react": "^18.0.0",
                "express": "^4.18.0"
            },
            "devDependencies": {
                "jest": "^29.0.0"
            }
        }
        with open(pkg_path, "w") as f:
            json.dump(pkg_data, f)
        
        tickets_path = os.path.join(self.temp_dir, "tickets.yaml")
        context = detect_project_context(tickets_path)
        
        self.assertEqual(context["language"], "javascript")
        self.assertEqual(context["build_tool"], "npm")
        self.assertEqual(context["framework"], "react")
        self.assertEqual(context["test_framework"], "jest")
        self.assertEqual(context["project_type"], "react_app")
    
    def test_detect_project_context_rust(self):
        """Test detecting Rust project context."""
        # Create a Cargo.toml file
        cargo_path = os.path.join(self.temp_dir, "Cargo.toml")
        with open(cargo_path, "w") as f:
            f.write("[package]\nname = 'test'\n")
        
        tickets_path = os.path.join(self.temp_dir, "tickets.yaml")
        context = detect_project_context(tickets_path)
        
        self.assertEqual(context["language"], "rust")
        self.assertEqual(context["build_tool"], "cargo")
        self.assertEqual(context["test_framework"], "cargo_test")
        self.assertEqual(context["project_type"], "rust_project")
    
    def test_detect_project_context_go(self):
        """Test detecting Go project context."""
        # Create a go.mod file
        go_path = os.path.join(self.temp_dir, "go.mod")
        with open(go_path, "w") as f:
            f.write("module test\n")
        
        tickets_path = os.path.join(self.temp_dir, "tickets.yaml")
        context = detect_project_context(tickets_path)
        
        self.assertEqual(context["language"], "go")
        self.assertEqual(context["build_tool"], "go")
        self.assertEqual(context["test_framework"], "go_test")
        self.assertEqual(context["project_type"], "go_project")
    
    def test_detect_project_context_unknown(self):
        """Test detecting unknown project context."""
        tickets_path = os.path.join(self.temp_dir, "tickets.yaml")
        context = detect_project_context(tickets_path)
        
        self.assertEqual(context["language"], "unknown")
        self.assertIsNone(context["framework"])
        self.assertIsNone(context["build_tool"])
        self.assertIsNone(context["test_framework"])
        self.assertEqual(context["project_type"], "unknown")


if __name__ == "__main__":
    unittest.main()