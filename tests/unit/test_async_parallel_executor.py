"""Tests for AsyncParallelExecutor."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import pytest

from hydra.parallel.async_executor import (
    AsyncParallelExecutor, 
    ExecutionStatus, 
    TicketNode,
    ExecutionPlan
)


class TestAsyncParallelExecutor(unittest.TestCase):
    """Test suite for AsyncParallelExecutor."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.executor = AsyncParallelExecutor(
            max_concurrent=2,
            project_root=self.temp_dir,
            dashboard_state=None
        )

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self.executor, 'agent_pool'):
            self.executor.agent_pool.stop()

    def test_init(self):
        """Test AsyncParallelExecutor initialization."""
        self.assertEqual(self.executor.max_concurrent, 2)
        self.assertEqual(str(self.executor.project_root), self.temp_dir)
        self.assertIsInstance(self.executor.tickets, dict)
        self.assertIsInstance(self.executor.completed_tickets, set)
        self.assertIsInstance(self.executor.failed_tickets, set)
        self.assertIsInstance(self.executor.running_tickets, set)

    @pytest.mark.asyncio
    async def test_load_tickets_async(self):
        """Test async ticket loading."""
        # Create a mock tickets.md file
        tickets_content = """# Test Tickets

## Ticket 001: Test Task
**Status:** TODO
**Model:** Sonnet 4
**Dependencies:** None

Simple test task.

**Acceptance Criteria:**
- [ ] Task is completed

## Ticket 002: Dependent Task
**Status:** TODO  
**Model:** Opus 4
**Dependencies:** 001

Task that depends on 001.

**Acceptance Criteria:**
- [ ] Dependency satisfied
- [ ] Task completed
"""
        tickets_path = Path(self.temp_dir) / "tickets.md"
        with open(tickets_path, 'w') as f:
            f.write(tickets_content)

        # Load tickets
        tickets = await self.executor.load_tickets(str(tickets_path))
        
        # Verify tickets loaded
        self.assertEqual(len(tickets), 2)
        self.assertIn('001', tickets)
        self.assertIn('002', tickets)
        
        # Verify ticket properties
        ticket1 = tickets['001']
        self.assertEqual(ticket1.title, 'Test Task')
        self.assertEqual(ticket1.model, 'Sonnet 4')
        self.assertEqual(ticket1.dependencies, [])
        self.assertEqual(ticket1.status, ExecutionStatus.PENDING)
        
        ticket2 = tickets['002']
        self.assertEqual(ticket2.title, 'Dependent Task')
        self.assertEqual(ticket2.model, 'Opus 4')
        self.assertEqual(ticket2.dependencies, ['001'])

    def test_build_dynamic_execution_plan(self):
        """Test dynamic execution plan building."""
        # Set up test tickets
        self.executor.tickets = {
            '001': TicketNode('001', 'Task 1', 'sonnet', [], ExecutionStatus.PENDING),
            '002': TicketNode('002', 'Task 2', 'opus', ['001'], ExecutionStatus.PENDING),
            '003': TicketNode('003', 'Task 3', 'sonnet', [], ExecutionStatus.PENDING),
        }
        
        # Build execution plan
        plan = self.executor.build_dynamic_execution_plan()
        
        # Verify plan structure
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.total_tickets, 3)
        self.assertEqual(plan.max_concurrent, 2)
        
        # Verify ready queue has tickets with no dependencies
        self.assertEqual(plan.ready_queue.qsize(), 2)  # 001 and 003

    @pytest.mark.asyncio 
    async def test_trigger_dependents(self):
        """Test dependency triggering mechanism."""
        # Set up tickets with dependencies
        self.executor.tickets = {
            '001': TicketNode('001', 'Base Task', 'sonnet', [], ExecutionStatus.COMPLETED),
            '002': TicketNode('002', 'Dependent Task', 'opus', ['001'], ExecutionStatus.PENDING),
        }
        self.executor.completed_tickets.add('001')
        self.executor.dependency_waiters = {'001': {'002'}}
        self.executor.ready_queue = asyncio.Queue()
        
        # Trigger dependents for completed ticket
        await self.executor._trigger_dependents('001')
        
        # Verify dependent was added to ready queue
        self.assertEqual(self.executor.ready_queue.qsize(), 1)
        ready_ticket = await self.executor.ready_queue.get()
        self.assertEqual(ready_ticket, '002')
        
        # Verify cleanup
        self.assertNotIn('001', self.executor.dependency_waiters)

    @pytest.mark.asyncio
    async def test_execute_ticket_success(self):
        """Test successful ticket execution."""
        tickets_path = Path(self.temp_dir) / "tickets.md"
        tickets_content = """# Test Tickets

## Ticket 001: Simple Task
**Status:** TODO
**Model:** Sonnet 4
**Dependencies:** None

Simple test task.

**Acceptance Criteria:**
- [ ] Task completed successfully
"""
        with open(tickets_path, 'w') as f:
            f.write(tickets_content)

        # Set up test ticket
        self.executor.tickets = {
            '001': TicketNode('001', 'Simple Task', 'sonnet', [], ExecutionStatus.PENDING)
        }
        
        # Mock the orchestrator and related components
        with patch('hydra.parallel.async_executor.ClaudeCodeOrchestrator') as mock_orchestrator_class:
            mock_orchestrator = Mock()
            mock_orchestrator_class.return_value = mock_orchestrator
            
            # Mock successful task result
            mock_result = Mock()
            mock_result.status.value = "completed"
            mock_orchestrator.execute_task.return_value = mock_result
            
            # Mock validation functions
            with patch('hydra.ticket_workflow.parse_ticket') as mock_parse:
                mock_parse.return_value = {
                    'title': 'Simple Task',
                    'model': 'sonnet',
                    'status': 'TODO'
                }
                
                with patch('hydra.ticket_workflow.validate_acceptance_criteria') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('hydra.quality.auto_fixer.QualityAutoFixer') as mock_fixer_class:
                        mock_fixer = Mock()
                        mock_fixer_class.return_value = mock_fixer
                        mock_fixer.fix_common_issues.return_value = []
                        
                        with patch('hydra.quality.QualityGateRunner') as mock_gate_class:
                            mock_gate_runner = Mock()
                            mock_gate_class.return_value = mock_gate_runner
                            
                            mock_report = Mock()
                            mock_report.overall_status.value = "passed"
                            mock_report.results = []
                            mock_gate_runner.run_quality_gates.return_value = mock_report
                            
                            with patch('hydra.ticket_workflow.mark_ticket_in_progress'):
                                with patch('hydra.ticket_workflow.mark_ticket_completed'):
                                    # Execute ticket
                                    result = await self.executor.execute_ticket('001', str(tickets_path))
                                    
                                    # Verify success
                                    self.assertTrue(result)
                                    self.assertIn('001', self.executor.completed_tickets)
                                    
                                    # Verify ticket status updated
                                    ticket = self.executor.tickets['001']
                                    self.assertEqual(ticket.status, ExecutionStatus.COMPLETED)
                                    self.assertTrue(ticket.quality_passed)
                                    self.assertIsNotNone(ticket.start_time)
                                    self.assertIsNotNone(ticket.end_time)

    @pytest.mark.asyncio
    async def test_execute_ticket_failure(self):
        """Test ticket execution failure handling."""
        tickets_path = Path(self.temp_dir) / "tickets.md"
        
        # Set up test ticket
        self.executor.tickets = {
            '001': TicketNode('001', 'Failing Task', 'sonnet', [], ExecutionStatus.PENDING)
        }
        
        # Mock orchestrator to raise exception
        with patch('hydra.parallel.async_executor.ClaudeCodeOrchestrator') as mock_orchestrator_class:
            mock_orchestrator = Mock()
            mock_orchestrator_class.return_value = mock_orchestrator
            mock_orchestrator.execute_task.side_effect = Exception("Task failed")
            
            with patch('hydra.ticket_workflow.parse_ticket') as mock_parse:
                mock_parse.return_value = {
                    'title': 'Failing Task',
                    'model': 'sonnet',
                    'status': 'TODO'
                }
                
                with patch('hydra.ticket_workflow.mark_ticket_in_progress'):
                    # Execute ticket
                    result = await self.executor.execute_ticket('001', str(tickets_path))
                    
                    # Verify failure
                    self.assertFalse(result)
                    self.assertIn('001', self.executor.failed_tickets)
                    
                    # Verify ticket status updated
                    ticket = self.executor.tickets['001']
                    self.assertEqual(ticket.status, ExecutionStatus.FAILED)
                    self.assertIsNotNone(ticket.error)

    def test_generate_report(self):
        """Test report generation."""
        # Set up test data
        self.executor.tickets = {
            '001': TicketNode('001', 'Completed Task', 'sonnet', [], ExecutionStatus.COMPLETED),
            '002': TicketNode('002', 'Failed Task', 'opus', [], ExecutionStatus.FAILED),
        }
        
        # Set up ticket timing
        self.executor.tickets['001'].start_time = 1000.0
        self.executor.tickets['001'].end_time = 1010.0
        self.executor.tickets['001'].quality_passed = True
        
        self.executor.tickets['002'].start_time = 1005.0
        self.executor.tickets['002'].end_time = 1015.0
        self.executor.tickets['002'].error = "Test error"
        
        self.executor.completed_tickets.add('001')
        self.executor.failed_tickets.add('002')
        
        summary = {
            'total_tickets': 2,
            'completed': 1,
            'failed': 1,
            'blocked': 0,
            'duration': 20.0,
            'success_rate': 50.0,
            'results': {'001': True, '002': False}
        }
        
        # Generate report
        report = self.executor.generate_report(summary)
        
        # Verify report content
        self.assertIn("Async Parallel Execution Report", report)
        self.assertIn("Total tickets: 2", report)
        self.assertIn("✅ Completed (Quality Passed): 1", report)
        self.assertIn("❌ Failed/Quality Issues: 1", report)
        self.assertIn("Success rate: 50.0%", report)
        self.assertIn("001: Completed Task", report)
        self.assertIn("002: Failed Task", report)
        self.assertIn("Test error", report)

    @pytest.mark.asyncio
    async def test_save_execution_log(self):
        """Test async execution log saving."""
        # Set up test data
        self.executor.tickets = {
            '001': TicketNode('001', 'Test Task', 'sonnet', [], ExecutionStatus.COMPLETED)
        }
        
        summary = {
            'total_tickets': 1,
            'completed': 1,
            'failed': 0,
            'blocked': 0,
            'duration': 10.0,
            'success_rate': 100.0,
            'results': {'001': True}
        }
        
        # Save log
        log_path = await self.executor.save_execution_log(summary)
        
        # Verify log file exists
        self.assertTrue(Path(log_path).exists())
        self.assertTrue(log_path.endswith('.json'))
        
        # Verify log content
        import json
        with open(log_path, 'r') as f:
            log_data = json.load(f)
        
        self.assertEqual(log_data['execution_mode'], 'async')
        self.assertEqual(log_data['summary']['total_tickets'], 1)
        self.assertIn('001', log_data['tickets'])

    def test_shutdown(self):
        """Test executor shutdown."""
        # Mock agent pool
        mock_pool = Mock()
        self.executor.agent_pool = mock_pool
        
        # Call shutdown
        self.executor.shutdown()
        
        # Verify agent pool was stopped
        mock_pool.stop.assert_called_once()


class TestExecutionPlan(unittest.TestCase):
    """Test ExecutionPlan data class."""

    def test_execution_plan_creation(self):
        """Test ExecutionPlan creation."""
        ready_queue = asyncio.Queue()
        dependency_graph = {'001': [], '002': ['001']}
        
        plan = ExecutionPlan(
            ready_queue=ready_queue,
            dependency_graph=dependency_graph,
            total_tickets=2,
            max_concurrent=3
        )
        
        self.assertEqual(plan.total_tickets, 2)
        self.assertEqual(plan.max_concurrent, 3)
        self.assertEqual(plan.dependency_graph, dependency_graph)
        self.assertIs(plan.ready_queue, ready_queue)


class TestTicketNodeAsync(unittest.TestCase):
    """Test TicketNode for async scenarios."""

    def test_ticket_node_creation(self):
        """Test TicketNode creation."""
        node = TicketNode(
            ticket_id='001',
            title='Test Task',
            model='sonnet',
            dependencies=['000'],
            status=ExecutionStatus.PENDING
        )
        
        self.assertEqual(node.ticket_id, '001')
        self.assertEqual(node.title, 'Test Task')
        self.assertEqual(node.model, 'sonnet')
        self.assertEqual(node.dependencies, ['000'])
        self.assertEqual(node.status, ExecutionStatus.PENDING)
        self.assertIsNone(node.start_time)
        self.assertIsNone(node.end_time)
        self.assertIsNone(node.error)
        self.assertIsNone(node.quality_passed)


# Async test runner
def run_async_tests():
    """Run async tests using pytest."""
    # This allows running async tests with pytest
    pytest.main([__file__, '-v'])


if __name__ == '__main__':
    # Run standard unit tests
    unittest.main()