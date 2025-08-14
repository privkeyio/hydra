"""Integration tests with real providers - skip if no API key."""

import os
import pytest
import tempfile
from pathlib import Path

from hydra.ticket_workflow import execute_single_ticket
from hydra.providers.provider_factory import ProviderFactory


# Skip all tests if no provider API keys available
pytestmark = pytest.mark.skipif(
    not any([
        os.getenv("VENICE_API_KEY"),
        os.getenv("ANTHROPIC_API_KEY"),
        os.getenv("OPENAI_API_KEY")
    ]),
    reason="No provider API keys available"
)


class TestRealProviderIntegration:
    """Test with real providers when available."""
    
    @pytest.fixture
    def workspace(self):
        """Create temporary workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
            
    @pytest.mark.skipif(not os.getenv("VENICE_API_KEY"), reason="Venice API key required")
    def test_venice_simple_task(self, workspace):
        """Test Venice provider with deterministic task."""
        content = """# Tickets

## Ticket 001: Hello World Function

**Priority**: 1

**Description**: Write a Python function named hello_world that returns the string "Hello, World!"

**Acceptance Criteria**:
- [ ] Function named hello_world exists
- [ ] Returns exactly "Hello, World!"
- [ ] No parameters required

**Status**: TODO
"""
        tickets_file = Path(workspace) / "tickets.md"
        tickets_file.write_text(content)
        
        # Execute with Venice
        os.environ["LLM_PROVIDER"] = "venice"
        result = execute_single_ticket(str(tickets_file), "001")
        
        assert result is True
        
        # Check if the function was created
        output_file = Path(workspace) / "hello_world.py"
        if output_file.exists():
            content = output_file.read_text()
            assert "def hello_world" in content
            assert "Hello, World!" in content
            
    @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Anthropic API key required")
    def test_claude_deterministic_task(self, workspace):
        """Test Claude provider with deterministic task."""
        content = """# Tickets

## Ticket 001: Fibonacci Function

**Priority**: 1

**Description**: Write a Python function fibonacci(n) that returns the nth Fibonacci number

**Acceptance Criteria**:
- [ ] Function named fibonacci
- [ ] Takes one parameter n
- [ ] Returns correct Fibonacci number
- [ ] fibonacci(0) returns 0
- [ ] fibonacci(1) returns 1
- [ ] fibonacci(5) returns 5

**Status**: TODO
"""
        tickets_file = Path(workspace) / "tickets.md"
        tickets_file.write_text(content)
        
        os.environ["LLM_PROVIDER"] = "anthropic"
        result = execute_single_ticket(str(tickets_file), "001")
        
        assert result is True
        
    def test_provider_fallback(self, workspace):
        """Test provider fallback mechanism."""
        content = """# Tickets

## Ticket 001: Simple Task

**Priority**: 1
**Description**: Create a function that adds two numbers
**Status**: TODO
"""
        tickets_file = Path(workspace) / "tickets.md"
        tickets_file.write_text(content)
        
        # Set invalid primary provider
        os.environ["LLM_PROVIDER"] = "nonexistent"
        os.environ["FALLBACK_PROVIDER"] = "venice" if os.getenv("VENICE_API_KEY") else "mock"
        
        result = execute_single_ticket(str(tickets_file), "001")
        
        # Should fallback and still work
        assert result is True
        
    @pytest.mark.benchmark
    def test_provider_performance(self, workspace):
        """Benchmark provider response times."""
        import time
        
        content = """# Tickets

## Ticket 001: Quick Task

**Priority**: 1
**Description**: Return the number 42
**Status**: TODO
"""
        tickets_file = Path(workspace) / "tickets.md"
        tickets_file.write_text(content)
        
        providers_to_test = []
        if os.getenv("VENICE_API_KEY"):
            providers_to_test.append("venice")
        if os.getenv("ANTHROPIC_API_KEY"):
            providers_to_test.append("anthropic")
            
        timings = {}
        for provider in providers_to_test:
            os.environ["LLM_PROVIDER"] = provider
            
            start = time.time()
            result = execute_single_ticket(str(tickets_file), "001")
            elapsed = time.time() - start
            
            timings[provider] = elapsed
            assert result is True
            
        # Log performance metrics
        for provider, timing in timings.items():
            print(f"{provider}: {timing:.2f}s")
            
    def test_parallel_with_real_provider(self, workspace):
        """Test parallel execution with real provider."""
        content = """# Tickets

## Ticket 001: Task A
**Priority**: 1
**Description**: Create function a() that returns 'A'
**Status**: TODO

## Ticket 002: Task B
**Priority**: 1
**Description**: Create function b() that returns 'B'
**Status**: TODO

## Ticket 003: Task C
**Priority**: 1
**Description**: Create function c() that returns 'C'
**Status**: TODO
"""
        tickets_file = Path(workspace) / "tickets.md"
        tickets_file.write_text(content)
        
        from hydra.ticket_workflow import run_all_tickets
        
        result = run_all_tickets(str(tickets_file), max_parallel=2)
        assert result is True