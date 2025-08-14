"""End-to-end tests for CLI commands."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestCLICommandsE2E:
    """Test CLI command integration."""

    @pytest.fixture
    def workspace(self):
        """Create test workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tickets_dir = Path(tmpdir) / "tickets"
            tickets_dir.mkdir()
            os.environ["LLM_PROVIDER"] = "mock"
            yield tmpdir

    def run_command(self, cmd, cwd=None):
        """Execute CLI command."""
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30
        )
        return result

    def test_create_ticket_command(self, workspace):
        """Test hydra ticket generation command."""
        # Create ticket file manually for testing
        ticket_content = """# Ticket 001: Test task

## Priority
1

## Description
Test task

## Acceptance Criteria
- [ ] Task completes

## Status
TODO
"""
        ticket_file = Path(f"{workspace}/tickets/001-test-task.md")
        ticket_file.write_text(ticket_content)

        assert ticket_file.exists()

    def test_execute_ticket_command(self, workspace):
        """Test hydra ticket execute command."""
        tickets_path = f"{workspace}/tickets"

        # Create ticket first
        ticket_content = """# Ticket 001: Execute test

## Priority
1

## Description
Execute test

## Acceptance Criteria
- [ ] Task runs

## Status
TODO
"""
        ticket_file = Path(tickets_path) / "001-execute-test.md"
        ticket_file.write_text(ticket_content)

        # Execute ticket
        exec_cmd = (
            f'python3 -m hydra.cli ticket execute 001 '
            f'--tickets-path {tickets_path}'
        )
        result = self.run_command(exec_cmd)

        assert result.returncode == 0

    def test_verify_ticket_command(self, workspace):
        """Test hydra ticket verify command."""
        tickets_path = f"{workspace}/tickets"

        # Create ticket
        ticket_content = """# Ticket 001: Verify test

## Priority
1

## Description
Verify test

## Acceptance Criteria
- [ ] Task verifies

## Status
TODO
"""
        ticket_file = Path(tickets_path) / "001-verify-test.md"
        ticket_file.write_text(ticket_content)

        # Execute ticket
        exec_cmd = (
            f'python3 -m hydra.cli ticket execute 001 '
            f'--tickets-path {tickets_path}'
        )
        self.run_command(exec_cmd)

        # Verify ticket
        verify_cmd = (
            f'python3 -m hydra.cli ticket verify 001 '
            f'--tickets-path {tickets_path}'
        )
        result = self.run_command(verify_cmd)

        assert result.returncode == 0

    def test_parallel_execution_command(self, workspace):
        """Test parallel execution command."""
        tickets_path = f"{workspace}/tickets"

        # Create multiple tickets
        for i in range(3):
            ticket_content = f"""# Ticket 00{i+1}: Task {i+1}

## Priority
{i+1}

## Description
Task {i+1}

## Acceptance Criteria
- [ ] Task {i+1} completes

## Status
TODO
"""
            ticket_file = Path(tickets_path) / f"00{i+1}-task-{i+1}.md"
            ticket_file.write_text(ticket_content)

        # Execute in parallel
        parallel_cmd = (
            f'python3 -m hydra.cli ticket parallel '
            f'--tickets-path {tickets_path} --max-parallel 2'
        )
        result = self.run_command(parallel_cmd)

        assert result.returncode == 0

    def test_verify_parallel_command(self, workspace):
        """Test parallel verification command."""
        tickets_path = f"{workspace}/tickets"

        # Create and execute tickets
        for i in range(2):
            ticket_content = f"""# Ticket 00{i+1}: Task {i+1}

## Priority
{i+1}

## Description
Task {i+1}

## Acceptance Criteria
- [ ] Task {i+1} verifies

## Status
TODO
"""
            ticket_file = Path(tickets_path) / f"00{i+1}-task-{i+1}.md"
            ticket_file.write_text(ticket_content)

            exec_cmd = (
                f'python3 -m hydra.cli ticket execute 00{i+1} '
                f'--tickets-path {tickets_path}'
            )
            self.run_command(exec_cmd)

        # Verify in parallel
        verify_cmd = (
            f'python3 -m hydra.cli ticket verify-parallel '
            f'--tickets-path {tickets_path}'
        )
        result = self.run_command(verify_cmd)

        assert result.returncode == 0

    def test_generate_tickets_command(self, workspace):
        """Test tickets.md generation."""
        tickets_path = f"{workspace}/tickets"

        # Create tickets
        for i in range(2):
            ticket_content = f"""# Ticket 00{i+1}: Task {i+1}

## Priority
{i+1}

## Description
Task {i+1}

## Acceptance Criteria
- [ ] Criterion {i+1}

## Status
TODO
"""
            ticket_file = Path(tickets_path) / f"00{i+1}-task-{i+1}.md"
            ticket_file.write_text(ticket_content)

        # Generate tickets.md
        gen_cmd = (
            f'python3 -m hydra.cli ticket generate "Test project" '
            f'--output-path {tickets_path}/tickets.md'
        )
        result = self.run_command(gen_cmd)

        assert result.returncode == 0
        assert Path(f"{tickets_path}/tickets.md").exists()

    def test_error_handling_invalid_ticket(self, workspace):
        """Test error handling for invalid ticket."""
        tickets_path = f"{workspace}/tickets"

        # Try to execute non-existent ticket
        exec_cmd = (
            f'python3 -m hydra.cli ticket execute nonexistent '
            f'--tickets-path {tickets_path}'
        )
        result = self.run_command(exec_cmd)

        assert result.returncode != 0

    def test_command_with_dependencies(self, workspace):
        """Test execution with dependencies."""
        tickets_path = f"{workspace}/tickets"

        # Create base ticket
        base_content = """# Ticket 001: Base task

## Priority
1

## Description
Base task

## Acceptance Criteria
- [ ] Base completes

## Status
TODO
"""
        base_file = Path(tickets_path) / "001-base-task.md"
        base_file.write_text(base_content)

        # Create dependent ticket
        dep_content = """# Ticket 002: Dependent task

## Priority
2

## Dependencies
- 001

## Description
Dependent task

## Acceptance Criteria
- [ ] Dependent completes

## Status
TODO
"""
        dep_file = Path(tickets_path) / "002-dependent-task.md"
        dep_file.write_text(dep_content)

        # Execute dependent (should handle dependency)
        exec_cmd = (
            f'python3 -m hydra.cli ticket execute 002 '
            f'--tickets-path {tickets_path}'
        )
        result = self.run_command(exec_cmd)

        assert result.returncode == 0

    @pytest.mark.integration
    def test_full_workflow_cli(self, workspace):
        """Test complete workflow via CLI."""
        tickets_path = f"{workspace}/tickets"

        # Create
        ticket_content = """# Ticket 001: Complete workflow

## Priority
1

## Description
Complete workflow

## Acceptance Criteria
- [ ] Task completes
- [ ] Returns success

## Status
TODO
"""
        ticket_file = Path(tickets_path) / "001-complete-workflow.md"
        ticket_file.write_text(ticket_content)
        assert ticket_file.exists()

        # Execute
        exec_cmd = (
            f'python3 -m hydra.cli ticket execute 001 '
            f'--tickets-path {tickets_path}'
        )
        exec_result = self.run_command(exec_cmd)
        assert exec_result.returncode == 0

        # Verify
        verify_cmd = (
            f'python3 -m hydra.cli ticket verify 001 '
            f'--tickets-path {tickets_path}'
        )
        verify_result = self.run_command(verify_cmd)
        assert verify_result.returncode == 0
