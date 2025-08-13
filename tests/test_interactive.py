#!/usr/bin/env python3
"""Tests for interactive ticket refinement functionality."""

import os
import tempfile
import unittest
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.hydra.interactive.ticket_refiner import TicketRefiner, RefinementAction


class TestTicketRefiner(unittest.TestCase):
    """Test cases for the TicketRefiner class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_tickets_content = """# Test Tickets

## Ticket 001: Test ticket with dependencies
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** A test ticket for refinement testing

**Required Input Files:**
- None

**Output Files:**
- src/test/output.py
- tests/test_output.py

**Acceptance Criteria:**
- [ ] Create test functionality
- [ ] Add comprehensive tests
- [ ] Validate output format
- [ ] Implement error handling
- [ ] Add documentation
- [ ] Create integration tests

---

## Ticket 002: Complex ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** A complex ticket requiring refinement

**Required Input Files:**
- src/test/output.py (from Ticket 001)

**Output Files:**
- src/complex/module.py
- src/complex/handler.py
- src/complex/validator.py
- src/complex/processor.py
- tests/test_complex.py

**Acceptance Criteria:**
- [ ] Implement complex processing
- [ ] Create validation logic
- [ ] Add error handling
- [ ] Implement retry mechanism
- [ ] Add comprehensive logging
- [ ] Create performance tests
- [ ] Add integration tests
- [ ] Implement monitoring
- [ ] Add alerts

---
"""
        # Create temporary file for testing
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
        self.temp_file.write(self.test_tickets_content)
        self.temp_file.close()
        
        self.refiner = TicketRefiner(self.temp_file.name)

    def tearDown(self):
        """Clean up test fixtures."""
        os.unlink(self.temp_file.name)

    def test_load_tickets(self):
        """Test that tickets are loaded correctly."""
        self.assertEqual(len(self.refiner.tickets), 2)
        self.assertIn('001', self.refiner.tickets)
        self.assertIn('002', self.refiner.tickets)

    def test_ticket_parsing(self):
        """Test that ticket data is parsed correctly."""
        ticket = self.refiner.tickets['001']
        self.assertEqual(ticket.id, '001')
        self.assertEqual(ticket.title, 'Test ticket with dependencies')
        self.assertEqual(ticket.status, 'TODO')
        self.assertEqual(ticket.model, 'balanced')
        self.assertEqual(len(ticket.acceptance_criteria), 6)
        self.assertEqual(len(ticket.output_files), 2)

    def test_model_adjustment_suggestion(self):
        """Test model adjustment suggestions."""
        suggestions = self.refiner.get_refinement_suggestions('002')
        
        # Should suggest smart model due to high complexity
        model_suggestions = [s for s in suggestions if s.action == RefinementAction.ADJUST_MODEL]
        self.assertTrue(len(model_suggestions) > 0)
        self.assertEqual(model_suggestions[0].suggested_value, 'smart')

    def test_ticket_split_suggestion(self):
        """Test ticket split suggestions."""
        suggestions = self.refiner.get_refinement_suggestions('002')
        
        # Should suggest splitting due to many criteria (9)
        split_suggestions = [s for s in suggestions if s.action == RefinementAction.SPLIT_TICKET]
        self.assertTrue(len(split_suggestions) > 0)

    def test_dependency_suggestions(self):
        """Test dependency suggestions."""
        suggestions = self.refiner.get_refinement_suggestions('002')
        
        # Should not suggest adding dependency 001 since it already exists
        add_dep_suggestions = [s for s in suggestions if s.action == RefinementAction.ADD_DEPENDENCY]
        self.assertEqual(len(add_dep_suggestions), 0)

    def test_adjust_model(self):
        """Test model adjustment functionality."""
        result = self.refiner.adjust_model('001', 'smart')
        self.assertTrue(result)
        self.assertEqual(self.refiner.tickets['001'].model, 'smart')

    def test_add_dependency(self):
        """Test adding dependencies."""
        result = self.refiner.add_dependency('001', '002')
        self.assertTrue(result)
        self.assertIn('002', self.refiner.tickets['001'].dependencies)

    def test_remove_dependency(self):
        """Test removing dependencies."""
        result = self.refiner.remove_dependency('002', '001')
        self.assertTrue(result)
        self.assertNotIn('001', self.refiner.tickets['002'].dependencies)

    def test_validate_file_flows(self):
        """Test file flow validation."""
        result = self.refiner.validate_file_flows('002')
        self.assertIn('valid', result)
        self.assertIn('issues', result)
        self.assertIn('flows', result)

    def test_split_ticket(self):
        """Test ticket splitting functionality."""
        original_criteria_count = len(self.refiner.tickets['002'].acceptance_criteria)
        
        # Split criteria 0, 1, 2 into new ticket
        original_id, new_id = self.refiner.split_ticket('002', [0, 1, 2])
        
        self.assertEqual(original_id, '002')
        self.assertIn(new_id, self.refiner.tickets)
        
        # Check that criteria were split correctly
        original_ticket = self.refiner.tickets['002']
        new_ticket = self.refiner.tickets[new_id]
        
        self.assertEqual(len(original_ticket.acceptance_criteria), original_criteria_count - 3)
        self.assertEqual(len(new_ticket.acceptance_criteria), 3)
        
        # New ticket should depend on original
        self.assertIn('002', new_ticket.dependencies)

    def test_get_ticket_list(self):
        """Test getting ticket list."""
        tickets = self.refiner.get_ticket_list()
        self.assertEqual(len(tickets), 2)
        
        ticket_ids = [t[0] for t in tickets]
        self.assertIn('001', ticket_ids)
        self.assertIn('002', ticket_ids)

    def test_get_ticket_details(self):
        """Test getting ticket details."""
        ticket = self.refiner.get_ticket_details('001')
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.id, '001')
        self.assertEqual(ticket.title, 'Test ticket with dependencies')

    def test_invalid_ticket_operations(self):
        """Test operations on invalid tickets."""
        # Test operations on non-existent ticket
        self.assertFalse(self.refiner.adjust_model('999', 'smart'))
        self.assertFalse(self.refiner.add_dependency('999', '001'))
        self.assertFalse(self.refiner.remove_dependency('999', '001'))
        self.assertIsNone(self.refiner.get_ticket_details('999'))

    def test_invalid_model(self):
        """Test invalid model assignment."""
        result = self.refiner.adjust_model('001', 'invalid_model')
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()