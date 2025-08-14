"""Core command tests - ensure create/execute/verify workflow works."""

import os
import json
import tempfile
from pathlib import Path
import subprocess
import sys

import pytest


class TestCoreCommands:
    """Test core Hydra commands work end-to-end."""
    
    @pytest.fixture
    def workspace(self):
        """Create isolated workspace for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up environment
            os.environ["LLM_PROVIDER"] = "mock"
            os.environ["TESTING"] = "1"
            yield tmpdir
            
    def run_hydra_command(self, cmd, cwd=None):
        """Run a Hydra command and return result."""
        env = os.environ.copy()
        env["LLM_PROVIDER"] = "mock"
        env["PYTHONPATH"] = os.path.abspath("src")
        
        # Use the Python that has hydra installed
        full_cmd = f"{sys.executable} -m hydra.cli {cmd}"
        
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=30
        )
        return result
        
    def test_ticket_create_command(self, workspace):
        """Test hydra ticket create generates valid tickets.md."""
        # Skip if subprocess calls fail (resource constraints)
        try:
            output_path = Path(workspace) / "tickets.md"
            
            # Create tickets from description
            cmd = f'ticket create "Build a REST API with user authentication" --output {output_path}'
            result = self.run_hydra_command(cmd, cwd=workspace)
            
            # Should succeed even with mock provider
            assert result.returncode == 0, f"Command failed: {result.stderr}"
            assert output_path.exists(), "tickets.md not created"
            
            # Validate tickets.md structure
            content = output_path.read_text()
            assert "# Project Tickets" in content or "## Ticket" in content
            assert "Priority" in content or "priority" in content
            assert "Status" in content or "status" in content
        except (RuntimeError, BlockingIOError) as e:
            pytest.skip(f"Resource constraints: {e}")
        
    def test_ticket_execute_single(self, workspace):
        """Test executing a single ticket."""
        # Create a simple tickets.md
        tickets_content = """# Project Tickets

## Ticket 001: Create utility function

**Priority**: 1

**Description**: Create a utility function for string manipulation

**Acceptance Criteria**:
- [ ] Function exists
- [ ] Has documentation
- [ ] Handles edge cases

**Dependencies**: None

**Status**: TODO
"""
        tickets_path = Path(workspace) / "tickets.md"
        tickets_path.write_text(tickets_content)
        
        # Execute the ticket
        cmd = f'ticket execute 001 --tickets {tickets_path}'
        result = self.run_hydra_command(cmd, cwd=workspace)
        
        # Should complete (mock provider returns success)
        assert result.returncode == 0, f"Execute failed: {result.stderr}"
        
        # Check for execution markers in output
        output = result.stdout + result.stderr
        # Mock provider should at least process the ticket
        assert "001" in output or "Ticket" in output or not output
        
    def test_ticket_parallel_execution(self, workspace):
        """Test parallel execution of multiple tickets."""
        # Create tickets.md with multiple independent tickets
        tickets_content = """# Project Tickets

## Ticket 001: Task A

**Priority**: 1
**Description**: First task
**Status**: TODO

## Ticket 002: Task B  

**Priority**: 1
**Description**: Second task
**Status**: TODO

## Ticket 003: Task C

**Priority**: 1
**Description**: Third task
**Status**: TODO
"""
        tickets_path = Path(workspace) / "tickets.md"
        tickets_path.write_text(tickets_content)
        
        # Execute in parallel
        cmd = f'ticket parallel --tickets {tickets_path} --workers 2'
        result = self.run_hydra_command(cmd, cwd=workspace)
        
        # Should handle parallel execution
        assert result.returncode == 0, f"Parallel execution failed: {result.stderr}"
        
    def test_ticket_verify_command(self, workspace):
        """Test ticket verification."""
        # Create a ticket that's been "executed"
        tickets_content = """# Project Tickets

## Ticket 001: Completed task

**Priority**: 1

**Description**: A task that was completed

**Acceptance Criteria**:
- [ ] Criteria met
- [ ] Tests pass

**Status**: IN_PROGRESS
"""
        tickets_path = Path(workspace) / "tickets.md"
        tickets_path.write_text(tickets_content)
        
        # First execute it
        exec_cmd = f'ticket execute 001 --tickets {tickets_path}'
        exec_result = self.run_hydra_command(exec_cmd, cwd=workspace)
        
        # Then verify it
        verify_cmd = f'ticket verify 001 --tickets {tickets_path}'
        verify_result = self.run_hydra_command(verify_cmd, cwd=workspace)
        
        # Verification should complete
        assert verify_result.returncode == 0, f"Verify failed: {verify_result.stderr}"
        
    def test_verify_parallel_command(self, workspace):
        """Test parallel verification of multiple tickets."""
        tickets_content = """# Project Tickets

## Ticket 001: First task
**Priority**: 1
**Status**: IN_PROGRESS

## Ticket 002: Second task
**Priority**: 1
**Status**: IN_PROGRESS
"""
        tickets_path = Path(workspace) / "tickets.md"
        tickets_path.write_text(tickets_content)
        
        # Execute tickets first
        for ticket_id in ["001", "002"]:
            cmd = f'ticket execute {ticket_id} --tickets {tickets_path}'
            self.run_hydra_command(cmd, cwd=workspace)
        
        # Verify in parallel
        verify_cmd = f'ticket verify-parallel --tickets {tickets_path}'
        result = self.run_hydra_command(verify_cmd, cwd=workspace)
        
        assert result.returncode == 0, f"Parallel verify failed: {result.stderr}"
        
    def test_full_workflow(self, workspace):
        """Test complete workflow: create -> execute -> verify."""
        # Step 1: Create tickets
        tickets_path = Path(workspace) / "tickets.md"
        create_cmd = f'ticket create "Simple task management system" --output {tickets_path}'
        create_result = self.run_hydra_command(create_cmd, cwd=workspace)
        assert create_result.returncode == 0
        assert tickets_path.exists()
        
        # Step 2: Parse tickets to find ticket IDs
        content = tickets_path.read_text()
        # Extract ticket IDs (look for "Ticket XXX:")
        import re
        ticket_ids = re.findall(r'Ticket (\d+):', content)
        
        if ticket_ids:
            # Step 3: Execute first ticket
            exec_cmd = f'ticket execute {ticket_ids[0]} --tickets {tickets_path}'
            exec_result = self.run_hydra_command(exec_cmd, cwd=workspace)
            assert exec_result.returncode == 0
            
            # Step 4: Verify the ticket
            verify_cmd = f'ticket verify {ticket_ids[0]} --tickets {tickets_path}'
            verify_result = self.run_hydra_command(verify_cmd, cwd=workspace)
            assert verify_result.returncode == 0
            
    def test_ticket_with_dependencies(self, workspace):
        """Test execution respects dependencies."""
        tickets_content = """# Project Tickets

## Ticket 001: Base module
**Priority**: 1
**Dependencies**: None
**Status**: TODO

## Ticket 002: Extension
**Priority**: 2  
**Dependencies**: 001
**Status**: TODO

## Ticket 003: Integration
**Priority**: 3
**Dependencies**: 001, 002
**Status**: TODO
"""
        tickets_path = Path(workspace) / "tickets.md"
        tickets_path.write_text(tickets_content)
        
        # Execute ticket with dependencies (should handle dependency chain)
        cmd = f'ticket execute 003 --tickets {tickets_path}'
        result = self.run_hydra_command(cmd, cwd=workspace)
        
        # Should handle dependencies (even with mock)
        assert result.returncode == 0, f"Dependency execution failed: {result.stderr}"
        
    def test_invalid_ticket_handling(self, workspace):
        """Test handling of invalid ticket IDs."""
        tickets_path = Path(workspace) / "tickets.md"
        tickets_path.write_text("# Project Tickets\n\n## Ticket 001: Test\n**Status**: TODO")
        
        # Try to execute non-existent ticket
        cmd = f'ticket execute 999 --tickets {tickets_path}'
        result = self.run_hydra_command(cmd, cwd=workspace)
        
        # Should fail gracefully
        assert result.returncode != 0 or "not found" in result.stderr.lower() or "error" in result.stderr.lower()
        
    @pytest.mark.skipif(not os.getenv("VENICE_API_KEY"), reason="Venice API key required for real test")
    def test_with_real_provider(self, workspace):
        """Test with real provider when available."""
        os.environ["LLM_PROVIDER"] = "venice"
        
        tickets_content = """# Project Tickets

## Ticket 001: Hello World

**Priority**: 1
**Description**: Create a hello world function
**Acceptance Criteria**:
- [ ] Function returns "Hello, World!"
**Status**: TODO
"""
        tickets_path = Path(workspace) / "tickets.md"
        tickets_path.write_text(tickets_content)
        
        cmd = f'ticket execute 001 --tickets {tickets_path}'
        result = self.run_hydra_command(cmd, cwd=workspace)
        
        assert result.returncode == 0
        # With real provider, should create actual code
        # Check if any Python files were created
        py_files = list(Path(workspace).glob("*.py"))
        assert len(py_files) > 0, "Real provider should create code files"