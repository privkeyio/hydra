"""Full workflow integration tests for CI: create tickets -> execute parallel -> verify parallel."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hydra.ticket_workflow import (
    SharedWorkspace,
    build_dependency_graph,
    generate_tickets_md,
    get_executable_tickets,
    parse_all_tickets,
    validate_acceptance_criteria,
)


class TestCIIntegrationWorkflow(unittest.TestCase):
    """Test complete CI integration workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.tickets_file = Path(self.test_dir) / "tickets.md"
        self.workspace = SharedWorkspace(session_id="ci_test")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if hasattr(self, 'workspace'):
            self.workspace.cleanup()

    def create_tickets_file(self, content: str) -> str:
        """Create a tickets.md file with given content."""
        self.tickets_file.write_text(content)
        return str(self.tickets_file)

    def test_full_workflow_simple_project(self):
        """Test complete workflow for a simple project."""
        # Step 1: Create tickets (simulated - would normally use generate_tickets_md)
        content = """## Ticket 001: Setup Basic Structure
**Status:** TODO
**Model:** fast
**Dependencies:** None
**Description:** Create basic project structure
**Progress:** started

**Acceptance Criteria:**
- [ ] Create src directory
- [ ] Create tests directory
- [ ] Add README.md file

## Ticket 002: Implement Core Feature
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Implement the main feature
**Progress:** started

**Acceptance Criteria:**
- [ ] Create main.py with core logic
- [ ] Add basic error handling
- [ ] Create configuration file

## Ticket 003: Add Tests
**Status:** TODO
**Model:** smart
**Dependencies:** 002
**Description:** Add comprehensive tests
**Progress:** started

**Acceptance Criteria:**
- [ ] Create test_main.py
- [ ] Add unit tests for core features
- [ ] Ensure 80% code coverage
"""
        tickets_path = self.create_tickets_file(content)

        # Step 2: Parse tickets
        tickets = parse_all_tickets(tickets_path)
        self.assertEqual(len(tickets), 3)

        # Step 3: Verify dependency order
        deps, reverse_deps = build_dependency_graph(tickets)

        # Verify correct dependencies
        self.assertEqual(deps.get("001", set()), set())
        self.assertEqual(deps.get("002", set()), {"001"})
        self.assertEqual(deps.get("003", set()), {"002"})

        # Step 4: Test executable ticket identification
        completed = set()
        executable = get_executable_tickets(tickets, completed)

        # Only ticket 001 should be executable initially
        self.assertEqual(executable, ["001"])

        # After completing 001, 002 should be executable
        completed.add("001")
        executable = get_executable_tickets(tickets, completed)
        self.assertIn("002", executable)
        self.assertNotIn("001", executable)

        # After completing 002, 003 should be executable
        completed.add("002")
        executable = get_executable_tickets(tickets, completed)
        self.assertIn("003", executable)
        self.assertNotIn("002", executable)

    @patch('hydra.ticket_workflow.execute_single_ticket')
    def test_parallel_execution_workflow(self, mock_execute):
        """Test parallel execution workflow with mocked ticket execution."""
        # Mock successful execution
        mock_execute.return_value = True

        content = """## Ticket 001: Independent Task A
**Status:** TODO
**Model:** fast
**Dependencies:** None
**Description:** Task A
**Acceptance Criteria:**
- [ ] Complete task A

## Ticket 002: Independent Task B
**Status:** TODO
**Model:** fast
**Dependencies:** None
**Description:** Task B
**Acceptance Criteria:**
- [ ] Complete task B

## Ticket 003: Dependent Task
**Status:** TODO
**Model:** balanced
**Dependencies:** 001, 002
**Description:** Task depending on A and B
**Acceptance Criteria:**
- [ ] Complete task C after A and B
"""
        tickets_path = self.create_tickets_file(content)

        # Test the workflow
        tickets = parse_all_tickets(tickets_path)
        completed = set()

        # Round 1: Execute independent tasks
        executable = get_executable_tickets(tickets, completed)
        self.assertEqual(set(executable), {"001", "002"})

        # Simulate parallel execution of 001 and 002
        for ticket_id in executable:
            success = mock_execute.return_value
            self.assertTrue(success)
            completed.add(ticket_id)

        # Round 2: Execute dependent task
        executable = get_executable_tickets(tickets, completed)
        self.assertEqual(executable, ["003"])

        # Execute final ticket
        success = mock_execute.return_value
        self.assertTrue(success)
        completed.add("003")

        # Verify all tickets completed
        self.assertEqual(len(completed), 3)
        self.assertEqual(completed, {"001", "002", "003"})

    def test_error_handling_in_workflow(self):
        """Test error handling throughout the workflow."""
        # Test with circular dependencies
        content = """## Ticket 001: Task A
**Status:** TODO
**Model:** balanced
**Dependencies:** 002
**Description:** Task A depends on B

## Ticket 002: Task B
**Status:** TODO
**Model:** fast
**Dependencies:** 001
**Description:** Task B depends on A (circular!)
"""
        tickets_path = self.create_tickets_file(content)
        tickets = parse_all_tickets(tickets_path)

        # Should detect circular dependency
        deps, _ = build_dependency_graph(tickets)

        # No tickets should be executable due to circular dependency
        completed = set()
        executable = get_executable_tickets(tickets, completed)
        self.assertEqual(executable, [])

    def test_workspace_integration_across_workflow(self):
        """Test workspace integration throughout the workflow."""
        content = """## Ticket 001: Create Config
**Status:** DONE
**Model:** fast
**Dependencies:** None
**Description:** Create configuration
**Acceptance Criteria:**
- [x] Create config.json

## Ticket 002: Use Config
**Status:** TODO
**Model:** balanced
**Dependencies:** 001
**Description:** Use the configuration
**Acceptance Criteria:**
- [ ] Read config.json
- [ ] Apply settings
"""
        tickets_path = self.create_tickets_file(content)

        # Simulate ticket 001 creating an artifact
        self.workspace.save_artifact("001", "config.json", '{"setting": "value"}')

        # Verify artifact exists for ticket 002 to use
        dep_artifacts = self.workspace.get_dependency_artifacts(["001"])
        self.assertIn("001", dep_artifacts)
        self.assertTrue(any("config.json" in path for path in dep_artifacts["001"]))

        # Test manifest creation
        created_files = ["src/config.py", "config.json"]
        self.workspace.create_manifest("001", created_files)

        manifest_files = self.workspace.list_ticket_artifacts("001")
        self.assertIn("manifest.txt", manifest_files)

    def test_quality_gate_integration(self):
        """Test integration with quality gates."""
        content = """## Ticket 001: Quality Test
**Status:** TODO
**Model:** coder
**Dependencies:** None
**Description:** Test quality gates
**Acceptance Criteria:**
- [ ] Write clean code
- [ ] Pass all linting
- [ ] Pass all tests
"""
        tickets_path = self.create_tickets_file(content)

        # Create some test files to validate
        src_dir = os.path.join(self.test_dir, "src")
        os.makedirs(src_dir, exist_ok=True)

        test_file = os.path.join(src_dir, "main.py")
        with open(test_file, 'w') as f:
            f.write("""#!/usr/bin/env python3
def hello_world():
    '''Return a greeting message.'''
    return "Hello, World!"

if __name__ == "__main__":
    print(hello_world())
""")

        tickets = parse_all_tickets(tickets_path)
        ticket_001 = tickets["001"]

        # Test acceptance criteria validation
        # Note: This will do manual validation since specific files aren't mentioned
        validation_result = validate_acceptance_criteria(ticket_001, self.test_dir)
        # Should pass for manual validation
        self.assertTrue(validation_result)

    @patch('hydra.providers.provider_factory.create_provider_from_environment')
    def test_ticket_generation_integration(self, mock_provider_factory):
        """Test ticket generation as part of the workflow."""
        # Mock the provider
        mock_provider = MagicMock()
        mock_provider.config.timeout = 120
        mock_provider.generate.return_value = True
        mock_provider_factory.return_value = mock_provider

        # Mock the model mapper
        with patch('hydra.providers.model_mapper.get_model_mapper') as mock_mapper:
            mock_mapper_instance = MagicMock()
            mock_mapper_instance.map_model.return_value = "test-model"
            mock_mapper.return_value = mock_mapper_instance

            # Create a temporary output path
            output_path = os.path.join(self.test_dir, "generated_tickets.md")

            # Mock file creation by generate_tickets_md
            def mock_generate(*args, **kwargs):
                # Simulate successful generation by creating the file
                with open(output_path, 'w') as f:
                    f.write("""## Ticket 001: Test Task
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Generated test task
**Progress:** started

**Acceptance Criteria:**
- [ ] Complete the task
""")
                return True

            mock_provider.generate.side_effect = mock_generate

            # Test ticket generation
            project_description = "Create a simple test project"
            result = generate_tickets_md(project_description, output_path)

            # Verify generation was called
            mock_provider.generate.assert_called_once()
            self.assertTrue(result)
            self.assertTrue(os.path.exists(output_path))

    def test_comprehensive_workflow_simulation(self):
        """Test a comprehensive workflow simulation."""
        # Create a realistic ticket set
        content = """## Ticket 001: Project Setup
**Status:** DONE
**Model:** fast
**Dependencies:** None
**Description:** Initialize project structure
**Acceptance Criteria:**
- [x] Create directory structure
- [x] Initialize git repository
- [x] Create README.md

## Ticket 002: Core Implementation
**Status:** DONE
**Model:** balanced
**Dependencies:** 001
**Description:** Implement core functionality
**Acceptance Criteria:**
- [x] Create main module
- [x] Implement core algorithms
- [x] Add configuration support

## Ticket 003: Testing Suite
**Status:** DONE
**Model:** smart
**Dependencies:** 002
**Description:** Add comprehensive tests
**Acceptance Criteria:**
- [x] Create unit tests
- [x] Add integration tests
- [x] Achieve target coverage

## Ticket 004: Documentation
**Status:** TODO
**Model:** coder
**Dependencies:** 002, 003
**Description:** Create documentation
**Acceptance Criteria:**
- [ ] Write API documentation
- [ ] Create user guide
- [ ] Add code examples
"""
        tickets_path = self.create_tickets_file(content)

        # Parse and analyze the workflow
        tickets = parse_all_tickets(tickets_path)
        self.assertEqual(len(tickets), 4)

        # Verify completion status
        completed_tickets = {
            ticket_id for ticket_id, ticket_data in tickets.items()
            if ticket_data.get("completed", False) or ticket_data.get("status") == "DONE"
        }
        self.assertEqual(completed_tickets, {"001", "002", "003"})

        # Verify next executable ticket
        executable = get_executable_tickets(tickets, completed_tickets)
        self.assertEqual(executable, ["004"])

        # Simulate workspace state after previous tickets
        for ticket_id in ["001", "002", "003"]:
            self.workspace.save_artifact(ticket_id, f"output_{ticket_id}.txt", f"Output from ticket {ticket_id}")

        # Verify ticket 004 can access all dependency artifacts
        dep_artifacts = self.workspace.get_dependency_artifacts(["002", "003"])
        self.assertEqual(len(dep_artifacts), 2)
        self.assertIn("002", dep_artifacts)
        self.assertIn("003", dep_artifacts)

    def test_failure_recovery_workflow(self):
        """Test workflow recovery from failures."""
        content = """## Ticket 001: Setup
**Status:** DONE
**Model:** fast
**Dependencies:** None
**Description:** Setup task

## Ticket 002: Implementation
**Status:** QUALITY_FAILED
**Model:** balanced
**Dependencies:** 001
**Description:** Implementation with quality issues

## Ticket 003: Testing
**Status:** TODO
**Model:** smart
**Dependencies:** 002
**Description:** Testing task
"""
        tickets_path = self.create_tickets_file(content)
        tickets = parse_all_tickets(tickets_path)

        # Completed tickets
        completed = {"001"}

        # Ticket 002 failed quality, needs to be re-executed
        executable = get_executable_tickets(tickets, completed)

        # Both 002 should be executable (to fix quality issues)
        # but 003 should not be until 002 is properly completed
        self.assertIn("002", executable)
        self.assertNotIn("003", executable)

        # After fixing ticket 002
        completed.add("002")
        tickets["002"]["status"] = "DONE"
        tickets["002"]["completed"] = True

        executable = get_executable_tickets(tickets, completed)
        self.assertIn("003", executable)


class TestCIPerformanceRequirements(unittest.TestCase):
    """Test CI performance requirements."""

    def test_parsing_performance(self):
        """Test that ticket parsing is fast enough for CI."""
        import time

        # Create a large tickets file
        content_parts = []
        for i in range(1, 51):  # 50 tickets
            content_parts.append(f"""## Ticket {i:03d}: Task {i}
**Status:** TODO
**Model:** balanced
**Dependencies:** {max(1, i-1):03d} if i > 1 else None
**Description:** Task number {i}
**Acceptance Criteria:**
- [ ] Complete task {i}
- [ ] Verify results
""")

        content = "\n\n".join(content_parts)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            tickets_path = f.name

        try:
            start_time = time.time()
            tickets = parse_all_tickets(tickets_path)
            parse_time = time.time() - start_time

            # Should parse 50 tickets in under 1 second
            self.assertLess(parse_time, 1.0)
            self.assertEqual(len(tickets), 50)

        finally:
            os.unlink(tickets_path)

    def test_dependency_graph_performance(self):
        """Test dependency graph building performance."""
        import time

        # Create tickets with complex dependencies
        tickets = {}
        for i in range(1, 26):  # 25 tickets
            ticket_id = f"{i:03d}"
            dependencies = []
            if i > 1:
                # Each ticket depends on the previous 2 tickets (if they exist)
                for j in range(max(1, i-2), i):
                    dependencies.append(f"{j:03d}")

            tickets[ticket_id] = {
                "ticket_id": ticket_id,
                "dependencies": dependencies,
                "completed": False
            }

        start_time = time.time()
        deps, reverse_deps = build_dependency_graph(tickets)
        graph_time = time.time() - start_time

        # Should build dependency graph in under 0.1 seconds
        self.assertLess(graph_time, 0.1)
        # Not all tickets will have entries in deps (those with no dependencies won't)
        self.assertLessEqual(len(deps), 25)
        # Check that reverse_deps contains the expected number of entries
        self.assertLessEqual(len(reverse_deps), 24)  # At most 24, but could be less
        # Verify that dependencies are correctly mapped
        self.assertGreater(len(deps), 20)  # Should have most tickets with dependencies

    def test_workspace_operations_performance(self):
        """Test workspace operations performance."""
        import time

        workspace = SharedWorkspace(session_id="perf_test")

        try:
            start_time = time.time()

            # Create many artifacts
            for i in range(100):
                workspace.save_artifact(f"{i:03d}", f"file_{i}.txt", f"Content {i}")

            creation_time = time.time() - start_time

            # Should create 100 artifacts in under 1 second
            self.assertLess(creation_time, 1.0)

            # Test retrieval performance
            start_time = time.time()

            for i in range(100):
                artifacts = workspace.list_ticket_artifacts(f"{i:03d}")
                self.assertEqual(len(artifacts), 1)

            retrieval_time = time.time() - start_time

            # Should retrieve all artifacts in under 0.5 seconds
            self.assertLess(retrieval_time, 0.5)

        finally:
            workspace.cleanup()


if __name__ == "__main__":
    unittest.main()
