"""Unit tests for ticket creation functionality in Hydra."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from hydra.ticket_workflow import (
    SharedWorkspace,
    parse_all_tickets,
    parse_ticket,
)


class TestTicketParsing(unittest.TestCase):
    """Test ticket parsing functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.tickets_file = Path(self.test_dir) / "tickets.md"
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def create_sample_tickets_file(self, content: str) -> str:
        """Create a sample tickets.md file with given content."""
        self.tickets_file.write_text(content)
        return str(self.tickets_file)
    
    def test_parse_single_ticket(self):
        """Test parsing a single ticket from tickets.md."""
        content = """## Ticket 001: Test Ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** This is a test ticket
**Acceptance Criteria:**
- [ ] First criterion
- [ ] Second criterion
"""
        tickets_path = self.create_sample_tickets_file(content)
        ticket = parse_ticket(tickets_path, "001")
        
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["number"], "001")
        self.assertEqual(ticket["title"], "Test Ticket")
        self.assertEqual(ticket["status"], "TODO")
        self.assertEqual(ticket["model"], "balanced")
        self.assertEqual(ticket["dependencies"], [])
        self.assertIn("First criterion", ticket["acceptance_criteria"][0])
        self.assertIn("Second criterion", ticket["acceptance_criteria"][1])
    
    def test_parse_ticket_with_dependencies(self):
        """Test parsing a ticket with dependencies."""
        content = """## Ticket 002: Dependent Ticket
**Status:** TODO
**Model:** smart
**Dependencies:** 001
**Description:** This ticket depends on 001
**Acceptance Criteria:**
- [ ] Complete after 001
"""
        tickets_path = self.create_sample_tickets_file(content)
        ticket = parse_ticket(tickets_path, "002")
        
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["dependencies"], ["001"])
    
    def test_parse_ticket_with_multiple_dependencies(self):
        """Test parsing a ticket with multiple dependencies."""
        content = """## Ticket 003: Multi-Dependent Ticket
**Status:** TODO
**Model:** fast
**Dependencies:** 001, 002
**Description:** This ticket depends on 001 and 002
**Acceptance Criteria:**
- [ ] Complete after both dependencies
"""
        tickets_path = self.create_sample_tickets_file(content)
        ticket = parse_ticket(tickets_path, "003")
        
        self.assertIsNotNone(ticket)
        self.assertEqual(sorted(ticket["dependencies"]), ["001", "002"])
    
    def test_parse_all_tickets(self):
        """Test parsing all tickets from a file."""
        content = """## Ticket 001: First Ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** First ticket
**Acceptance Criteria:**
- [ ] First ticket criterion

## Ticket 002: Second Ticket
**Status:** IN_PROGRESS
**Model:** smart
**Dependencies:** 001
**Description:** Second ticket
**Acceptance Criteria:**
- [ ] Second ticket criterion
"""
        tickets_path = self.create_sample_tickets_file(content)
        tickets = parse_all_tickets(tickets_path)
        
        self.assertEqual(len(tickets), 2)
        self.assertIn("001", tickets)
        self.assertIn("002", tickets)
        self.assertEqual(tickets["001"]["title"], "First Ticket")
        self.assertEqual(tickets["002"]["status"], "IN_PROGRESS")
    
    def test_parse_ticket_with_completed_criteria(self):
        """Test parsing ticket with some completed acceptance criteria."""
        content = """## Ticket 004: Partially Complete
**Status:** IN_PROGRESS
**Model:** coder
**Dependencies:** None
**Description:** Partially completed ticket
**Acceptance Criteria:**
- [x] Completed criterion
- [ ] Pending criterion
- [x] Another completed criterion
"""
        tickets_path = self.create_sample_tickets_file(content)
        ticket = parse_ticket(tickets_path, "004")
        
        self.assertIsNotNone(ticket)
        criteria = ticket["acceptance_criteria"]
        self.assertEqual(len(criteria), 3)
        # Check that we have both completed and pending criteria
        self.assertTrue(any("✅" in c for c in criteria))
        self.assertTrue(any(not c.startswith("✅") for c in criteria))
    
    def test_parse_nonexistent_ticket(self):
        """Test parsing a ticket that doesn't exist."""
        content = """## Ticket 001: Test Ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** This is a test ticket
"""
        tickets_path = self.create_sample_tickets_file(content)
        ticket = parse_ticket(tickets_path, "999")
        
        self.assertIsNone(ticket)
    
    def test_parse_malformed_ticket(self):
        """Test parsing a malformed ticket."""
        content = """## Ticket 005: Malformed Ticket
This ticket is missing required fields
"""
        tickets_path = self.create_sample_tickets_file(content)
        ticket = parse_ticket(tickets_path, "005")
        
        # Should still parse but with missing fields
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["number"], "005")
        self.assertEqual(ticket.get("status", "TODO"), "TODO")
    
    def test_parse_ticket_with_special_characters(self):
        """Test parsing ticket with special characters in title."""
        content = """## Ticket 006: Test & Development (Phase 1)
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Test with special chars: @#$%^&*()
**Acceptance Criteria:**
- [ ] Handle special chars properly
"""
        tickets_path = self.create_sample_tickets_file(content)
        ticket = parse_ticket(tickets_path, "006")
        
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["title"], "Test & Development (Phase 1)")
        self.assertIn("@#$%^&*()", ticket["description"])


class TestSharedWorkspace(unittest.TestCase):
    """Test SharedWorkspace functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.workspace = SharedWorkspace(session_id="test_session")
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.workspace.workspace_path):
            shutil.rmtree(self.workspace.workspace_path)
    
    def test_workspace_creation(self):
        """Test that workspace is created with proper structure."""
        self.assertTrue(os.path.exists(self.workspace.workspace_path))
        
        # Check subdirectories
        for subdir in ["artifacts", "docs", "configs", "shared_data"]:
            path = os.path.join(self.workspace.workspace_path, subdir)
            self.assertTrue(os.path.exists(path))
        
        # Check session info file
        info_file = os.path.join(self.workspace.workspace_path, "session_info.txt")
        self.assertTrue(os.path.exists(info_file))
    
    def test_artifact_path_generation(self):
        """Test artifact path generation."""
        path = self.workspace.get_artifact_path("001", "output.txt")
        expected = os.path.join(
            self.workspace.workspace_path,
            "artifacts",
            "ticket_001",
            "output.txt"
        )
        self.assertEqual(path, expected)
        
        # Check that directory is created
        self.assertTrue(os.path.exists(os.path.dirname(path)))
    
    def test_save_artifact(self):
        """Test saving an artifact."""
        content = "Test artifact content"
        path = self.workspace.save_artifact("002", "test.txt", content)
        
        self.assertTrue(os.path.exists(path))
        with open(path, 'r') as f:
            saved_content = f.read()
        self.assertEqual(saved_content, content)
    
    def test_list_ticket_artifacts(self):
        """Test listing artifacts for a ticket."""
        # Save multiple artifacts
        self.workspace.save_artifact("003", "file1.txt", "content1")
        self.workspace.save_artifact("003", "file2.txt", "content2")
        self.workspace.save_artifact("003", "file3.txt", "content3")
        
        artifacts = self.workspace.list_ticket_artifacts("003")
        self.assertEqual(len(artifacts), 3)
        self.assertIn("file1.txt", artifacts)
        self.assertIn("file2.txt", artifacts)
        self.assertIn("file3.txt", artifacts)
    
    def test_list_artifacts_empty_ticket(self):
        """Test listing artifacts for a ticket with no artifacts."""
        artifacts = self.workspace.list_ticket_artifacts("999")
        self.assertEqual(len(artifacts), 0)
    
    def test_ticket_id_normalization(self):
        """Test that ticket IDs are properly normalized."""
        path1 = self.workspace.get_artifact_path("1", "test.txt")
        path2 = self.workspace.get_artifact_path("001", "test.txt")
        self.assertEqual(path1, path2)


class TestTicketCreationHelpers(unittest.TestCase):
    """Test helper functions for ticket creation."""
    
    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies in tickets."""
        tickets = {
            "001": {"dependencies": ["002"], "title": "Ticket 1"},
            "002": {"dependencies": ["003"], "title": "Ticket 2"},
            "003": {"dependencies": ["001"], "title": "Ticket 3"},  # Circular!
        }
        
        # Helper function to detect circular dependencies
        def has_circular_dependency(tickets):
            visited = set()
            rec_stack = set()
            
            def visit(ticket_id):
                if ticket_id in rec_stack:
                    return True
                if ticket_id in visited:
                    return False
                
                visited.add(ticket_id)
                rec_stack.add(ticket_id)
                
                if ticket_id in tickets:
                    for dep in tickets[ticket_id].get("dependencies", []):
                        if visit(dep):
                            return True
                
                rec_stack.remove(ticket_id)
                return False
            
            for ticket_id in tickets:
                if visit(ticket_id):
                    return True
            return False
        
        self.assertTrue(has_circular_dependency(tickets))
        
        # Test non-circular dependencies
        tickets["003"]["dependencies"] = []
        self.assertFalse(has_circular_dependency(tickets))


if __name__ == "__main__":
    unittest.main()