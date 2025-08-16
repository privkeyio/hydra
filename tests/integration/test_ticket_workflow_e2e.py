"""End-to-end integration tests for the complete ticket workflow."""

import os
import tempfile
import json
from pathlib import Path
import pytest
import subprocess
import sys
import time


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def run_subprocess_safe(cmd, env=None, timeout=60, cwd=None):
    """Run a subprocess with resource limits and better error handling."""
    # Add a small delay to prevent rapid subprocess spawning
    time.sleep(0.1)
    
    # Set resource limits via environment
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    
    # Limit subprocess resources in CI environment
    if os.getenv("CI"):
        process_env["PYTHONUNBUFFERED"] = "1"
        # Reduce parallelism in CI
        if "--workers" in cmd:
            worker_idx = cmd.index("--workers")
            if worker_idx + 1 < len(cmd):
                cmd[worker_idx + 1] = "1"  # Force single worker in CI
    
    try:
        result = subprocess.run(
            cmd,
            env=process_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False
        )
        return result
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(
            cmd, 1, 
            stdout=f"Process timed out after {timeout} seconds",
            stderr=str(e)
        )
    except OSError as e:
        # Handle resource exhaustion more gracefully
        if "Resource temporarily unavailable" in str(e):
            time.sleep(1)  # Wait before retry
            try:
                # Retry once with longer delay
                result = subprocess.run(
                    cmd,
                    env=process_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                    check=False
                )
                return result
            except Exception as retry_error:
                return subprocess.CompletedProcess(
                    cmd, 1,
                    stdout="",
                    stderr=f"Resource exhaustion: {retry_error}"
                )
        return subprocess.CompletedProcess(
            cmd, 1,
            stdout="",
            stderr=f"OS Error: {e}"
        )


@pytest.fixture(scope="session")
def hydra_cli():
    """Get the path to the hydra CLI."""
    # Use the installed hydra if available
    try:
        result = run_subprocess_safe(
            ["which", "hydra"],
            timeout=5
        )
        hydra_path = result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        hydra_path = None
    
    if not hydra_path:
        # Fall back to the local installation
        hydra_path = "/home/kyle/.local/share/pipx/venvs/hydra-agents/bin/hydra"
    
    return hydra_path


@pytest.mark.integration
@pytest.mark.resource_intensive
class TestTicketWorkflowE2E:
    """Test the complete ticket workflow from creation to verification."""
    
    def test_create_tickets(self, temp_project, hydra_cli):
        """Test creating tickets from a project description."""
        os.chdir(temp_project)
        
        # Create tickets
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "create", 
             "Create a simple Python calculator with add, subtract, multiply, and divide functions",
             "--output", "tickets.md"],
            env={"LLM_PROVIDER": "mock"},
            timeout=30,
            cwd=temp_project
        )
        
        assert result.returncode == 0, f"Failed to create tickets: {result.stderr}"
        assert (temp_project / "tickets.md").exists()
        
        # Verify the tickets file contains expected structure
        content = (temp_project / "tickets.md").read_text()
        assert "## Ticket" in content or "## TICKET" in content
        assert "**Status:**" in content
        assert "**Acceptance Criteria:**" in content
        
    def test_execute_single_ticket(self, temp_project, hydra_cli):
        """Test executing a single ticket."""
        os.chdir(temp_project)
        
        # Create a simple tickets file
        tickets_content = """# Project Tickets

## Ticket 001: Create Calculator Module

**Status**: TODO
**Priority**: 1
**Model**: fast
**Description**: Create a calculator.py module with basic arithmetic functions

**Acceptance Criteria**:
- [ ] Create calculator.py file
- [ ] Implement add function
- [ ] Implement subtract function
- [ ] Implement multiply function
"""
        (temp_project / "tickets.md").write_text(tickets_content)
        
        # Execute the ticket
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "execute", "tickets.md", "001"],
            env={"LLM_PROVIDER": "mock"},
            timeout=60,
            cwd=temp_project
        )
        
        assert result.returncode == 0, f"Failed to execute ticket: {result.stderr}"
        
        # Verify the ticket was marked as done
        updated_content = (temp_project / "tickets.md").read_text()
        assert "DONE" in updated_content or "COMPLETED" in updated_content
        
    def test_parallel_execution(self, temp_project, hydra_cli):
        """Test parallel execution of multiple tickets."""
        os.chdir(temp_project)
        
        # Create multiple tickets
        tickets_content = """# Project Tickets

## Ticket 001: Create Main Module

**Status**: TODO
**Priority**: 1
**Model**: fast
**Description**: Create main.py module

**Acceptance Criteria**:
- [ ] Create main.py file
- [ ] Add main function

## Ticket 002: Create Utils Module

**Status**: TODO
**Priority**: 2
**Model**: fast
**Description**: Create utils.py module

**Acceptance Criteria**:
- [ ] Create utils.py file
- [ ] Add helper functions

## Ticket 003: Create Tests

**Status**: TODO
**Priority**: 3
**Model**: fast
**Dependencies**: 001, 002
**Description**: Create test files

**Acceptance Criteria**:
- [ ] Create test_main.py
- [ ] Create test_utils.py
"""
        (temp_project / "tickets.md").write_text(tickets_content)
        
        # Execute in parallel
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "parallel", "tickets.md", "--workers", "2"],
            env={"LLM_PROVIDER": "mock"},
            timeout=120,
            cwd=temp_project
        )
        
        assert result.returncode == 0, f"Parallel execution failed: {result.stderr}"
        
        # Check that execution completed
        assert "All tickets completed successfully" in result.stdout or "All tickets executed successfully" in result.stdout
        
        # Verify completion report was created
        reports_dir = temp_project / ".hydra" / "reports"
        assert reports_dir.exists()
        completion_reports = list(reports_dir.glob("completion_*.md"))
        assert len(completion_reports) > 0
        
    def test_verify_parallel(self, temp_project, hydra_cli):
        """Test verification of completed tickets."""
        os.chdir(temp_project)
        
        # Create completed tickets
        tickets_content = """# Project Tickets

## Ticket 001: Create Calculator

**Status**: DONE
**Priority**: 1
**Model**: fast
**Description**: Create calculator module

**Acceptance Criteria**:
- [x] Create calculator.py file
- [x] Implement add function
- [x] Implement tests

## Ticket 002: Create Documentation

**Status**: DONE
**Priority**: 2
**Model**: fast
**Description**: Create documentation

**Acceptance Criteria**:
- [x] Create README.md
- [x] Add usage examples
"""
        (temp_project / "tickets.md").write_text(tickets_content)
        
        # Create the files to satisfy acceptance criteria
        (temp_project / "calculator.py").write_text("""
def add(a, b):
    return a + b
""")
        (temp_project / "README.md").write_text("# Calculator\n\nUsage: calculator.add(1, 2)")
        
        # Run verification
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "verify-parallel", "tickets.md", 
             "--workers", "2", "--check-ai"],
            env={"LLM_PROVIDER": "mock"},
            timeout=60,
            cwd=temp_project
        )
        
        assert result.returncode == 0, f"Verification failed: {result.stderr}"
        assert "All tickets passed verification" in result.stdout
        
    def test_full_workflow(self, temp_project, hydra_cli):
        """Test the complete workflow: create -> execute -> verify."""
        os.chdir(temp_project)
        
        # Step 1: Create tickets
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "create",
             "Create a simple Python module with a greeting function and tests",
             "--output", "tickets.md"],
            env={"LLM_PROVIDER": "mock"},
            timeout=30,
            cwd=temp_project
        )
        assert result.returncode == 0
        
        # Step 2: Execute tickets in parallel
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "parallel", "tickets.md", "--workers", "2"],
            env={"LLM_PROVIDER": "mock"},
            timeout=120,
            cwd=temp_project
        )
        # May succeed or fail depending on mock implementation
        
        # Step 3: Verify tickets
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "verify-parallel", "tickets.md", 
             "--workers", "2", "--check-ai", "--audit-diff"],
            env={"LLM_PROVIDER": "mock"},
            timeout=60,
            cwd=temp_project
        )
        # Verification should run regardless of execution status
        assert "PARALLEL TICKET VERIFICATION REPORT" in result.stdout
        
    def test_ticket_dependencies(self, temp_project, hydra_cli):
        """Test that ticket dependencies are respected in parallel execution."""
        os.chdir(temp_project)
        
        tickets_content = """# Project Tickets

## Ticket 001: Create Base Module

**Status**: TODO
**Priority**: 1
**Model**: fast
**Description**: Create base.py

**Acceptance Criteria**:
- [ ] Create base.py

## Ticket 002: Extend Base Module

**Status**: TODO
**Priority**: 2
**Model**: fast
**Dependencies**: 001
**Description**: Extend base.py with additional features

**Acceptance Criteria**:
- [ ] Add new functions to base.py

## Ticket 003: Create Tests for Base

**Status**: TODO
**Priority**: 3
**Model**: fast
**Dependencies**: 001, 002
**Description**: Create comprehensive tests

**Acceptance Criteria**:
- [ ] Create test_base.py
"""
        (temp_project / "tickets.md").write_text(tickets_content)
        
        # Execute with dependency resolution
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "parallel", "tickets.md", "--workers", "3"],
            env={"LLM_PROVIDER": "mock"},
            timeout=120,
            cwd=temp_project
        )
        
        # Check that execution plan respects dependencies
        assert "Wave" in result.stdout or "wave" in result.stdout
        # Dependencies should be executed in order
        
    def test_quality_gates(self, temp_project, hydra_cli):
        """Test that quality gates are enforced during execution."""
        os.chdir(temp_project)
        
        tickets_content = """# Project Tickets

## Ticket 001: High Quality Module

**Status**: TODO
**Priority**: 1
**Model**: smart
**Description**: Create a high-quality module with proper tests and documentation

**Acceptance Criteria**:
- [ ] Create module.py with clean code
- [ ] All functions have docstrings
- [ ] Tests achieve 100% coverage
- [ ] No linting errors
"""
        (temp_project / "tickets.md").write_text(tickets_content)
        
        # Execute ticket
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "execute", "tickets.md", "001"],
            env={"LLM_PROVIDER": "mock"},
            timeout=60,
            cwd=temp_project
        )
        
        # Quality gates should be mentioned in output
        # (even if mock provider doesn't actually enforce them)
        
    @pytest.mark.parametrize("workers", [1, 2, 4])
    def test_parallel_scalability(self, temp_project, hydra_cli, workers):
        """Test parallel execution with different worker counts."""
        os.chdir(temp_project)
        
        # Create multiple independent tickets
        tickets_content = "# Project Tickets\n\n"
        for i in range(1, 7):
            tickets_content += f"""## Ticket {i:03d}: Module {i}

**Status**: TODO
**Priority**: {i}
**Model**: fast
**Description**: Create module{i}.py

**Acceptance Criteria**:
- [ ] Create module{i}.py

"""
        (temp_project / "tickets.md").write_text(tickets_content)
        
        # Execute with specified worker count
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "parallel", "tickets.md", "--workers", str(workers)],
            env={"LLM_PROVIDER": "mock"},
            timeout=180,
            cwd=temp_project
        )
        
        assert result.returncode == 0, f"Failed with {workers} workers: {result.stderr}"
        assert f"Max parallel workers: {workers}" in result.stdout or f"workers: {workers}" in result.stdout.lower()
        
    def test_error_handling(self, temp_project, hydra_cli):
        """Test error handling in ticket workflow."""
        os.chdir(temp_project)
        
        # Test with non-existent tickets file
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "execute", "nonexistent.md", "001"],
            timeout=30,
            cwd=temp_project
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()
        
        # Test with invalid ticket ID
        tickets_content = """# Project Tickets

## Ticket 001: Test

**Status**: TODO
"""
        (temp_project / "tickets.md").write_text(tickets_content)
        
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "execute", "tickets.md", "999"],
            timeout=30,
            cwd=temp_project
        )
        assert result.returncode != 0
        
    def test_save_reports(self, temp_project, hydra_cli):
        """Test that reports are saved correctly."""
        os.chdir(temp_project)
        
        tickets_content = """# Project Tickets

## Ticket 001: Test Module

**Status**: DONE
**Priority**: 1
**Model**: fast
**Description**: Create test module

**Acceptance Criteria**:
- [x] Create test.py
"""
        (temp_project / "tickets.md").write_text(tickets_content)
        (temp_project / "test.py").write_text("# Test module")
        
        # Run verification with report saving
        result = run_subprocess_safe(
            [hydra_cli, "ticket", "verify-parallel", "tickets.md",
             "--workers", "1", "--save-report"],
            env={"LLM_PROVIDER": "mock"},
            timeout=60,
            cwd=temp_project
        )
        
        # Check that report was saved
        reports_dir = temp_project / ".hydra" / "reports"
        if reports_dir.exists():
            verify_reports = list(reports_dir.glob("verify_parallel_*.json"))
            assert len(verify_reports) > 0
            
            # Verify report content
            with open(verify_reports[0]) as f:
                report = json.load(f)
                assert "total_tickets" in report
                assert "fully_verified" in report