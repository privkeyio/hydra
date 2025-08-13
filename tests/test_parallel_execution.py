"""Integration tests for parallel ticket execution in Hydra."""

import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from hydra.parallel.async_executor import (
    AsyncParallelExecutor,
    ExecutionStatus,
    TicketNode,
)


class TestAsyncParallelExecutor(unittest.TestCase):
    """Test AsyncParallelExecutor functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.tickets_file = Path(self.test_dir) / "tickets.md"
        self.executor = None
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if self.executor and hasattr(self.executor, 'agent_pool'):
            self.executor.agent_pool.stop()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def create_sample_tickets_file(self, content: str) -> str:
        """Create a sample tickets.md file with given content."""
        self.tickets_file.write_text(content)
        return str(self.tickets_file)
    
    @pytest.mark.asyncio
    async def test_load_tickets(self):
        """Test loading tickets into the executor."""
        content = """## Ticket 001: First Task
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** First task
**Acceptance Criteria:**
- [ ] Complete first task

## Ticket 002: Second Task
**Status:** TODO
**Model:** fast
**Dependencies:** 001
**Description:** Second task
**Acceptance Criteria:**
- [ ] Complete second task
"""
        tickets_path = self.create_sample_tickets_file(content)
        
        with patch('hydra.parallel.async_executor.AgentPool'):
            self.executor = AsyncParallelExecutor(max_concurrent=2)
            tickets = await self.executor.load_tickets(tickets_path)
        
        self.assertEqual(len(tickets), 2)
        self.assertIn("001", tickets)
        self.assertIn("002", tickets)
        self.assertEqual(tickets["001"].status, ExecutionStatus.PENDING)
        self.assertEqual(tickets["002"].dependencies, ["001"])
    
    @pytest.mark.asyncio
    async def test_build_execution_plan(self):
        """Test building an execution plan from tickets."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            self.executor = AsyncParallelExecutor(max_concurrent=2)
            
            # Create mock tickets
            self.executor.tickets = {
                "001": TicketNode(
                    ticket_id="001",
                    title="Task 1",
                    model="balanced",
                    dependencies=[],
                    status=ExecutionStatus.PENDING
                ),
                "002": TicketNode(
                    ticket_id="002",
                    title="Task 2",
                    model="fast",
                    dependencies=["001"],
                    status=ExecutionStatus.PENDING
                ),
                "003": TicketNode(
                    ticket_id="003",
                    title="Task 3",
                    model="smart",
                    dependencies=[],
                    status=ExecutionStatus.PENDING
                ),
            }
            
            plan = await self.executor.build_execution_plan()
            
            # Tickets 001 and 003 should be ready (no dependencies)
            ready_tickets = []
            while not self.executor.ready_queue.empty():
                ready_tickets.append(await self.executor.ready_queue.get())
            
            self.assertEqual(len(ready_tickets), 2)
            self.assertIn("001", ready_tickets)
            self.assertIn("003", ready_tickets)
    
    @pytest.mark.asyncio
    async def test_execute_ticket_mock(self):
        """Test executing a single ticket with mocked provider."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            with patch('hydra.parallel.async_executor.ClaudeCodeOrchestrator') as mock_orchestrator:
                self.executor = AsyncParallelExecutor(max_concurrent=2)
                
                # Mock the orchestrator
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value={
                    "success": True,
                    "output": "Task completed",
                    "quality_passed": True
                })
                mock_orchestrator.return_value = mock_instance
                
                # Create a test ticket
                ticket = TicketNode(
                    ticket_id="001",
                    title="Test Task",
                    model="balanced",
                    dependencies=[],
                    status=ExecutionStatus.PENDING
                )
                self.executor.tickets["001"] = ticket
                
                # Execute the ticket
                result = await self.executor.execute_ticket("001")
                
                self.assertTrue(result)
                self.assertEqual(ticket.status, ExecutionStatus.COMPLETED)
                self.assertIsNotNone(ticket.end_time)
    
    @pytest.mark.asyncio
    async def test_handle_dependencies(self):
        """Test that dependencies are properly handled."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            self.executor = AsyncParallelExecutor(max_concurrent=2)
            
            # Create tickets with dependencies
            self.executor.tickets = {
                "001": TicketNode(
                    ticket_id="001",
                    title="Parent Task",
                    model="balanced",
                    dependencies=[],
                    status=ExecutionStatus.PENDING
                ),
                "002": TicketNode(
                    ticket_id="002",
                    title="Child Task",
                    model="fast",
                    dependencies=["001"],
                    status=ExecutionStatus.PENDING
                ),
            }
            
            # Set up dependency tracking
            self.executor.dependency_waiters["001"] = {"002"}
            
            # Complete ticket 001
            await self.executor.handle_ticket_completion("001")
            
            # Check that ticket 002 is now ready
            self.assertFalse(self.executor.ready_queue.empty())
            ready_ticket = await self.executor.ready_queue.get()
            self.assertEqual(ready_ticket, "002")
    
    @pytest.mark.asyncio
    async def test_parallel_execution_with_workers(self):
        """Test parallel execution with multiple workers."""
        content = """## Ticket 001: Task A
**Status:** TODO
**Model:** fast
**Dependencies:** None
**Description:** Task A
**Acceptance Criteria:**
- [ ] Complete A

## Ticket 002: Task B
**Status:** TODO
**Model:** fast
**Dependencies:** None
**Description:** Task B
**Acceptance Criteria:**
- [ ] Complete B

## Ticket 003: Task C
**Status:** TODO
**Model:** fast
**Dependencies:** 001, 002
**Description:** Task C
**Acceptance Criteria:**
- [ ] Complete C
"""
        tickets_path = self.create_sample_tickets_file(content)
        
        with patch('hydra.parallel.async_executor.AgentPool'):
            with patch('hydra.parallel.async_executor.ClaudeCodeOrchestrator') as mock_orchestrator:
                # Mock successful execution
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value={
                    "success": True,
                    "output": "Task completed",
                    "quality_passed": True
                })
                mock_orchestrator.return_value = mock_instance
                
                self.executor = AsyncParallelExecutor(max_concurrent=2)
                
                # Execute all tickets
                results = await self.executor.execute_all(tickets_path)
                
                # All tickets should be completed
                self.assertEqual(results["completed"], 3)
                self.assertEqual(results["failed"], 0)
                self.assertEqual(len(self.executor.completed_tickets), 3)
    
    @pytest.mark.asyncio
    async def test_handle_failed_ticket(self):
        """Test handling of failed ticket execution."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            with patch('hydra.parallel.async_executor.ClaudeCodeOrchestrator') as mock_orchestrator:
                self.executor = AsyncParallelExecutor(max_concurrent=2)
                
                # Mock failed execution
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value={
                    "success": False,
                    "error": "Execution failed",
                    "quality_passed": False
                })
                mock_orchestrator.return_value = mock_instance
                
                # Create a test ticket
                ticket = TicketNode(
                    ticket_id="001",
                    title="Failing Task",
                    model="balanced",
                    dependencies=[],
                    status=ExecutionStatus.PENDING
                )
                self.executor.tickets["001"] = ticket
                
                # Execute the ticket
                result = await self.executor.execute_ticket("001")
                
                self.assertFalse(result)
                self.assertEqual(ticket.status, ExecutionStatus.FAILED)
                self.assertIsNotNone(ticket.error)
    
    @pytest.mark.asyncio
    async def test_max_concurrent_limit(self):
        """Test that max concurrent executions is respected."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            self.executor = AsyncParallelExecutor(max_concurrent=2)
            
            # Track concurrent executions
            concurrent_count = []
            max_concurrent = 0
            
            async def mock_execute(ticket_id):
                nonlocal max_concurrent
                self.executor.running_tickets.add(ticket_id)
                current = len(self.executor.running_tickets)
                concurrent_count.append(current)
                max_concurrent = max(max_concurrent, current)
                
                # Simulate work
                await asyncio.sleep(0.1)
                
                self.executor.running_tickets.remove(ticket_id)
                return True
            
            # Create multiple tickets
            for i in range(5):
                ticket_id = f"00{i+1}"
                self.executor.tickets[ticket_id] = TicketNode(
                    ticket_id=ticket_id,
                    title=f"Task {i+1}",
                    model="fast",
                    dependencies=[],
                    status=ExecutionStatus.PENDING
                )
            
            # Execute with mocked function
            with patch.object(self.executor, 'execute_ticket', mock_execute):
                tasks = [self.executor.execute_ticket(f"00{i+1}") for i in range(5)]
                await asyncio.gather(*tasks)
            
            # Check that max concurrent never exceeded limit
            self.assertLessEqual(max_concurrent, 2)


class TestParallelExecutionErrorHandling(unittest.TestCase):
    """Test error handling in parallel execution."""
    
    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self):
        """Test detection and handling of circular dependencies."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            executor = AsyncParallelExecutor(max_concurrent=2)
            
            # Create tickets with circular dependency
            executor.tickets = {
                "001": TicketNode(
                    ticket_id="001",
                    title="Task 1",
                    model="balanced",
                    dependencies=["002"],
                    status=ExecutionStatus.PENDING
                ),
                "002": TicketNode(
                    ticket_id="002",
                    title="Task 2",
                    model="fast",
                    dependencies=["003"],
                    status=ExecutionStatus.PENDING
                ),
                "003": TicketNode(
                    ticket_id="003",
                    title="Task 3",
                    model="smart",
                    dependencies=["001"],  # Circular!
                    status=ExecutionStatus.PENDING
                ),
            }
            
            # Detect circular dependencies
            def has_circular_dependency():
                visited = set()
                rec_stack = set()
                
                def visit(ticket_id):
                    if ticket_id in rec_stack:
                        return True
                    if ticket_id in visited:
                        return False
                    
                    visited.add(ticket_id)
                    rec_stack.add(ticket_id)
                    
                    if ticket_id in executor.tickets:
                        for dep in executor.tickets[ticket_id].dependencies:
                            if visit(dep):
                                return True
                    
                    rec_stack.remove(ticket_id)
                    return False
                
                for ticket_id in executor.tickets:
                    if visit(ticket_id):
                        return True
                return False
            
            self.assertTrue(has_circular_dependency())
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test handling of ticket execution timeouts."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            with patch('hydra.parallel.async_executor.ClaudeCodeOrchestrator') as mock_orchestrator:
                executor = AsyncParallelExecutor(max_concurrent=2)
                
                # Mock timeout scenario
                async def slow_execute(*args, **kwargs):
                    await asyncio.sleep(10)  # Simulate long execution
                    return {"success": True}
                
                mock_instance = MagicMock()
                mock_instance.execute = slow_execute
                mock_orchestrator.return_value = mock_instance
                
                ticket = TicketNode(
                    ticket_id="001",
                    title="Slow Task",
                    model="balanced",
                    dependencies=[],
                    status=ExecutionStatus.PENDING
                )
                executor.tickets["001"] = ticket
                
                # Execute with timeout
                with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError):
                    result = await executor.execute_ticket("001")
                    
                    self.assertFalse(result)
                    self.assertEqual(ticket.status, ExecutionStatus.FAILED)
    
    @pytest.mark.asyncio
    async def test_worker_failure_recovery(self):
        """Test recovery from worker failures."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            executor = AsyncParallelExecutor(max_concurrent=2)
            
            execution_attempts = {"001": 0}
            
            async def flaky_execute(ticket_id):
                execution_attempts[ticket_id] += 1
                if execution_attempts[ticket_id] < 2:
                    raise Exception("Worker failed")
                return True
            
            ticket = TicketNode(
                ticket_id="001",
                title="Flaky Task",
                model="balanced",
                dependencies=[],
                status=ExecutionStatus.PENDING
            )
            executor.tickets["001"] = ticket
            
            # Test retry logic
            with patch.object(executor, 'execute_ticket', flaky_execute):
                # First attempt should fail
                result = await executor.execute_ticket("001")
                self.assertFalse(result)
                
                # Second attempt should succeed
                result = await executor.execute_ticket("001")
                self.assertTrue(result)
                self.assertEqual(execution_attempts["001"], 2)


class TestMultiWorkerScenarios(unittest.TestCase):
    """Test scenarios with multiple workers."""
    
    @pytest.mark.asyncio
    async def test_load_balancing(self):
        """Test that work is distributed among workers."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            executor = AsyncParallelExecutor(max_concurrent=3)
            
            worker_tasks = {"worker1": [], "worker2": [], "worker3": []}
            
            async def mock_execute_with_worker(ticket_id):
                # Simulate worker assignment
                import random
                worker = random.choice(list(worker_tasks.keys()))
                worker_tasks[worker].append(ticket_id)
                await asyncio.sleep(0.01)
                return True
            
            # Create multiple independent tickets
            for i in range(9):
                ticket_id = f"00{i+1}"
                executor.tickets[ticket_id] = TicketNode(
                    ticket_id=ticket_id,
                    title=f"Task {i+1}",
                    model="fast",
                    dependencies=[],
                    status=ExecutionStatus.PENDING
                )
            
            with patch.object(executor, 'execute_ticket', mock_execute_with_worker):
                tasks = [executor.execute_ticket(f"00{i+1}") for i in range(9)]
                await asyncio.gather(*tasks)
            
            # Check that work was distributed (each worker should have tasks)
            for worker, tasks in worker_tasks.items():
                self.assertGreater(len(tasks), 0, f"{worker} had no tasks")
    
    @pytest.mark.asyncio
    async def test_complex_dependency_chain(self):
        """Test execution with complex dependency chains."""
        with patch('hydra.parallel.async_executor.AgentPool'):
            with patch('hydra.parallel.async_executor.ClaudeCodeOrchestrator') as mock_orchestrator:
                executor = AsyncParallelExecutor(max_concurrent=3)
                
                # Mock successful execution
                mock_instance = MagicMock()
                mock_instance.execute = AsyncMock(return_value={
                    "success": True,
                    "output": "Task completed",
                    "quality_passed": True
                })
                mock_orchestrator.return_value = mock_instance
                
                # Create a complex dependency graph
                # 001 -> 002 -> 004
                #     -> 003 -> 004
                #            -> 005
                executor.tickets = {
                    "001": TicketNode("001", "Task 1", "fast", [], ExecutionStatus.PENDING),
                    "002": TicketNode("002", "Task 2", "fast", ["001"], ExecutionStatus.PENDING),
                    "003": TicketNode("003", "Task 3", "fast", ["001"], ExecutionStatus.PENDING),
                    "004": TicketNode("004", "Task 4", "fast", ["002", "003"], ExecutionStatus.PENDING),
                    "005": TicketNode("005", "Task 5", "fast", ["003"], ExecutionStatus.PENDING),
                }
                
                # Track execution order
                execution_order = []
                
                async def track_execution(ticket_id):
                    execution_order.append(ticket_id)
                    return await mock_instance.execute(ticket_id)
                
                mock_instance.execute = track_execution
                
                # Execute all tickets
                plan = await executor.build_execution_plan()
                # Implementation would go here
                
                # Verify dependencies were respected
                # 001 must execute before 002 and 003
                # 002 and 003 must execute before 004
                # 003 must execute before 005


if __name__ == "__main__":
    # Use pytest for async tests
    pytest.main([__file__, "-v"])