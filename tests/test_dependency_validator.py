"""Comprehensive tests for dependency validation system."""

import os
import tempfile
import unittest

from hydra.validation.dependency_validator import (
    DependencyValidator,
    FileFlow,
    ValidationStatus,
)


class TestDependencyValidator(unittest.TestCase):
    """Test cases for dependency validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = DependencyValidator()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_test_tickets_file(self, content: str) -> str:
        """Create a temporary tickets file for testing."""
        tickets_path = os.path.join(self.test_dir, "tickets.md")
        with open(tickets_path, 'w') as f:
            f.write(content)
        return tickets_path

    def test_validate_ticket_dependencies_valid_simple(self):
        """Test validation of simple valid tickets."""
        content = """
## Ticket 001: First ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** First ticket with no dependencies

**Required Input Files:**
- None

**Output Files:**
- src/hydra/validation/validator.py

**Acceptance Criteria:**
- [ ] Create validator module
- [ ] Add validation functions

## Ticket 002: Second ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Second ticket depends on first

**Required Input Files:**
- src/hydra/validation/validator.py (from Ticket 001)

**Output Files:**
- tests/test_validator.py

**Acceptance Criteria:**
- [ ] Create test module
- [ ] Add test cases
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)

        self.assertTrue(result.valid)
        if result.issues:
            print(f"Unexpected issues: {[issue.description for issue in result.issues]}")
        self.assertEqual(len(result.issues), 0)
        self.assertEqual(len(result.file_flows), 1)
        self.assertEqual(result.topological_order, ['001', '002'])

    def test_validate_ticket_dependencies_circular_dependency(self):
        """Test detection of circular dependencies."""
        content = """
## Ticket 001: First ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 002
**Description:** First ticket depends on second

**Required Input Files:**
- None

**Output Files:**
- file1.py

**Acceptance Criteria:**
- [ ] Create file1

## Ticket 002: Second ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Second ticket depends on first

**Required Input Files:**
- None

**Output Files:**
- file2.py

**Acceptance Criteria:**
- [ ] Create file2
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)

        self.assertFalse(result.valid)
        circular_issues = [issue for issue in result.issues
                          if issue.issue_type == "circular_dependency"]
        self.assertEqual(len(circular_issues), 1)
        self.assertIn("001", circular_issues[0].description)
        self.assertIn("002", circular_issues[0].description)

    def test_validate_ticket_dependencies_missing_dependency(self):
        """Test detection of missing dependency tickets."""
        content = """
## Ticket 001: First ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 999
**Description:** First ticket depends on non-existent ticket

**Required Input Files:**
- None

**Output Files:**
- file1.py

**Acceptance Criteria:**
- [ ] Create file1
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)

        self.assertFalse(result.valid)
        missing_issues = [issue for issue in result.issues
                         if issue.issue_type == "missing_dependency"]
        self.assertEqual(len(missing_issues), 1)
        self.assertIn("999", missing_issues[0].description)

    def test_validate_ticket_dependencies_file_flow_mismatch(self):
        """Test detection of file flow mismatches."""
        content = """
## Ticket 001: First ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** First ticket

**Required Input Files:**
- None

**Output Files:**
- src/module1.py

**Acceptance Criteria:**
- [ ] Create module1

## Ticket 002: Second ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Second ticket needs different file

**Required Input Files:**
- src/module2.py (from Ticket 001)

**Output Files:**
- src/module3.py

**Acceptance Criteria:**
- [ ] Create module3
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)

        self.assertTrue(result.valid)  # This is a WARNING, not INVALID
        flow_issues = [issue for issue in result.issues
                      if issue.issue_type == "file_flow_mismatch"]
        self.assertEqual(len(flow_issues), 1)
        self.assertEqual(flow_issues[0].severity, ValidationStatus.WARNING)

    def test_validate_ticket_dependencies_topological_order(self):
        """Test proper topological ordering."""
        content = """
## Ticket 001: First ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Base ticket

**Required Input Files:**
- None

**Output Files:**
- base.py

**Acceptance Criteria:**
- [ ] Create base

## Ticket 002: Second ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Depends on first

**Required Input Files:**
- base.py (from Ticket 001)

**Output Files:**
- module.py

**Acceptance Criteria:**
- [ ] Create module

## Ticket 003: Third ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 001,002
**Description:** Depends on first and second

**Required Input Files:**
- base.py (from Ticket 001)
- module.py (from Ticket 002)

**Output Files:**
- app.py

**Acceptance Criteria:**
- [ ] Create app
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)

        self.assertTrue(result.valid)
        self.assertEqual(result.topological_order, ['001', '002', '003'])

    def test_validate_ticket_dependencies_dependency_order_warning(self):
        """Test warning for backwards dependency order."""
        content = """
## Ticket 002: Second ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 003
**Description:** Later ticket depends on even later ticket

**Required Input Files:**
- None

**Output Files:**
- file2.py

**Acceptance Criteria:**
- [ ] Create file2

## Ticket 003: Third ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Third ticket

**Required Input Files:**
- None

**Output Files:**
- file3.py

**Acceptance Criteria:**
- [ ] Create file3
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)

        self.assertTrue(result.valid)  # Should still be valid, just a warning
        order_issues = [issue for issue in result.issues
                       if issue.issue_type == "dependency_order"]
        self.assertEqual(len(order_issues), 1)
        self.assertEqual(order_issues[0].severity, ValidationStatus.WARNING)

    def test_validate_ticket_dependencies_file_not_found(self):
        """Test handling of non-existent tickets file."""
        non_existent_path = os.path.join(self.test_dir, "nonexistent.md")
        result = self.validator.validate_ticket_dependencies(non_existent_path)

        self.assertFalse(result.valid)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].issue_type, "file_not_found")

    def test_get_parallel_execution_groups_simple(self):
        """Test parallel execution group identification."""
        content = """
## Ticket 001: Independent ticket 1
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Independent ticket

**Required Input Files:**
- None

**Output Files:**
- file1.py

**Acceptance Criteria:**
- [ ] Create file1

## Ticket 002: Independent ticket 2
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Another independent ticket

**Required Input Files:**
- None

**Output Files:**
- file2.py

**Acceptance Criteria:**
- [ ] Create file2

## Ticket 003: Dependent ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Depends on ticket 1

**Required Input Files:**
- file1.py (from Ticket 001)

**Output Files:**
- file3.py

**Acceptance Criteria:**
- [ ] Create file3
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)
        groups = self.validator.get_parallel_execution_groups(result)

        self.assertTrue(result.valid)
        self.assertEqual(len(groups), 2)
        # First group should have tickets 001 and 002 (parallel)
        self.assertEqual(len(groups[0]), 2)
        self.assertIn('001', groups[0])
        self.assertIn('002', groups[0])
        # Second group should have ticket 003 (sequential)
        self.assertEqual(len(groups[1]), 1)
        self.assertIn('003', groups[1])

    def test_generate_dependency_report(self):
        """Test dependency report generation."""
        content = """
## Ticket 001: Test ticket
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Test ticket

**Required Input Files:**
- None

**Output Files:**
- test.py

**Acceptance Criteria:**
- [ ] Create test file
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)
        report = self.validator.generate_dependency_report(result)

        self.assertIn("Dependency Validation Report", report)
        self.assertIn("VALID", report)
        self.assertIn("Execution Order", report)
        self.assertIn("001", report)

    def test_validate_ticket_dependencies_complex_scenario(self):
        """Test complex scenario with multiple dependencies and file flows."""
        content = """
## Ticket 001: Database setup
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Set up database schema

**Required Input Files:**
- None

**Output Files:**
- database/schema.sql
- database/models.py

**Acceptance Criteria:**
- [ ] Create database schema
- [ ] Create database models

## Ticket 002: API layer
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Create API endpoints

**Required Input Files:**
- database/models.py (from Ticket 001)

**Output Files:**
- api/endpoints.py
- api/serializers.py

**Acceptance Criteria:**
- [ ] Create API endpoints
- [ ] Create serializers

## Ticket 003: Frontend components
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Create frontend components

**Required Input Files:**
- None

**Output Files:**
- frontend/components.js
- frontend/styles.css

**Acceptance Criteria:**
- [ ] Create components
- [ ] Create styles

## Ticket 004: Integration layer
**Status:** TODO
**Model:** balanced
**Dependencies:** 002,003
**Description:** Integrate frontend with API

**Required Input Files:**
- api/endpoints.py (from Ticket 002)
- frontend/components.js (from Ticket 003)

**Output Files:**
- integration/client.js
- integration/tests.py

**Acceptance Criteria:**
- [ ] Create integration client
- [ ] Create integration tests
"""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)

        self.assertTrue(result.valid)
        self.assertEqual(len(result.issues), 0)
        self.assertEqual(len(result.file_flows), 3)

        # Verify topological order
        actual_order = result.topological_order
        # 001 must come before 002, 002 and 003 must come before 004
        self.assertLess(actual_order.index('001'), actual_order.index('002'))
        self.assertLess(actual_order.index('002'), actual_order.index('004'))
        self.assertLess(actual_order.index('003'), actual_order.index('004'))

        # Check parallel execution groups
        groups = self.validator.get_parallel_execution_groups(result)
        self.assertTrue(len(groups) >= 3)  # At least 001, (002,003), 004

    def test_validate_ticket_dependencies_empty_file(self):
        """Test handling of empty tickets file."""
        content = ""
        tickets_path = self.create_test_tickets_file(content)
        result = self.validator.validate_ticket_dependencies(tickets_path)

        self.assertTrue(result.valid)  # Empty file is technically valid
        self.assertEqual(len(result.issues), 0)
        self.assertEqual(len(result.topological_order), 0)

    def test_file_flow_conflict_detection(self):
        """Test detection of file flow conflicts in parallel execution."""
        # Set up validator with test data
        self.validator.tickets = {
            '001': {'id': '001', 'output_files': ['shared.py']},
            '002': {'id': '002', 'output_files': ['other.py']}
        }

        file_flows = [
            FileFlow('001', '002', 'shared.py', True)
        ]

        # These tickets have a file flow conflict
        has_conflict = self.validator._has_file_flow_conflict('001', '002', file_flows)
        self.assertTrue(has_conflict)

        # These tickets don't have a file flow conflict
        has_conflict = self.validator._has_file_flow_conflict('001', '003', file_flows)
        self.assertFalse(has_conflict)


if __name__ == '__main__':
    unittest.main()
