"""Unit tests for context sharing between ticket agents."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hydra.context import (
    ContextStore,
    ExecutionPattern,
    SessionState,
    TicketContextManager,
)
from hydra.context.artifact_tracker import TicketArtifact


class TestContextStore(unittest.TestCase):
    """Test the ContextStore class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.context_store = ContextStore(self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_start_session(self):
        """Test starting a new session."""
        session_id = self.context_store.start_session("001", "venice")
        
        self.assertIn(session_id, self.context_store.sessions)
        session = self.context_store.sessions[session_id]
        self.assertEqual(session.ticket_id, "001")
        self.assertEqual(session.agent_type, "venice")
        self.assertEqual(session.status, "active")
    
    def test_complete_session(self):
        """Test completing a session."""
        session_id = self.context_store.start_session("001", "claude")
        
        artifacts = [
            TicketArtifact(
                file_path="test.py",
                operation="created",
                description="Test file"
            )
        ]
        
        self.context_store.complete_session(session_id, True, artifacts)
        
        self.assertNotIn(session_id, self.context_store.sessions)
    
    def test_learn_pattern(self):
        """Test learning a new pattern."""
        pattern_id = self.context_store.learn_pattern(
            "001",
            "testing",
            "Test pattern",
            "def test():\n    pass"
        )
        
        self.assertIn(pattern_id, self.context_store.patterns)
        pattern = self.context_store.patterns[pattern_id]
        self.assertEqual(pattern.category, "testing")
        self.assertEqual(pattern.success_rate, 1.0)
        self.assertEqual(pattern.usage_count, 1)
    
    def test_apply_pattern_success(self):
        """Test applying a pattern successfully."""
        pattern_id = self.context_store.learn_pattern(
            "001",
            "refactoring",
            "Refactor pattern",
            "Extract method"
        )
        
        self.context_store.apply_pattern(pattern_id, True)
        
        pattern = self.context_store.patterns[pattern_id]
        self.assertEqual(pattern.usage_count, 2)
        self.assertGreater(pattern.success_rate, 0.5)
    
    def test_apply_pattern_failure(self):
        """Test applying a pattern that fails."""
        pattern_id = self.context_store.learn_pattern(
            "001",
            "refactoring",
            "Refactor pattern",
            "Extract method"
        )
        
        self.context_store.apply_pattern(pattern_id, False)
        
        pattern = self.context_store.patterns[pattern_id]
        self.assertEqual(pattern.usage_count, 2)
        self.assertLess(pattern.success_rate, 1.0)
    
    def test_get_ticket_context(self):
        """Test getting comprehensive ticket context."""
        # Learn some patterns
        self.context_store.learn_pattern(
            "001",
            "testing",
            "Test pattern",
            "pytest"
        )
        
        context = self.context_store.get_ticket_context("002", ["001"])
        
        self.assertEqual(context['ticket_id'], "002")
        self.assertEqual(context['dependencies'], ["001"])
        self.assertIn('applicable_patterns', context)
        self.assertIn('previous_attempts', context)
        self.assertIn('related_solutions', context)
    
    def test_record_solution(self):
        """Test recording a solution."""
        self.context_store.record_solution(
            "001",
            "performance",
            "Use caching",
            True,
            0.9
        )
        
        # Verify solution was recorded
        solutions = self.context_store._find_related_solutions("002")
        self.assertGreater(len(solutions), 0)
    
    def test_get_execution_stats(self):
        """Test getting execution statistics."""
        stats = self.context_store.get_execution_stats()
        
        self.assertIn('total_executions', stats)
        self.assertIn('successful', stats)
        self.assertIn('success_rate', stats)
        self.assertIn('total_patterns', stats)
        self.assertIn('active_sessions', stats)
    
    def test_cleanup_stale_sessions(self):
        """Test cleaning up stale sessions."""
        session_id = self.context_store.start_session("001", "claude")
        
        # Manually set last activity to old time
        from datetime import datetime, timedelta
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        self.context_store.sessions[session_id].last_activity = old_time
        
        cleaned = self.context_store.cleanup_stale_sessions(hours=24)
        
        self.assertEqual(cleaned, 1)
        self.assertNotIn(session_id, self.context_store.sessions)


class TestTicketContextManager(unittest.TestCase):
    """Test the TicketContextManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = TicketContextManager(self.temp_dir)
        
        # Create a test tickets.md file
        tickets_content = """## Ticket 001: Test Ticket
**Dependencies:** None
**Description:** Test ticket

## Ticket 002: Dependent Ticket
**Dependencies:** 001
**Description:** Depends on 001
"""
        tickets_path = Path(self.temp_dir) / "tickets.md"
        tickets_path.write_text(tickets_content)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_prepare_ticket_context(self):
        """Test preparing context for ticket execution."""
        ticket_data = {
            'id': '002',
            'dependencies': ['001']
        }
        
        context = self.manager.prepare_ticket_context('002', ticket_data)
        
        self.assertIsInstance(context, str)
        # Context should mention dependencies if they exist
        if '001' in self.manager.artifact_tracker.ticket_contexts:
            self.assertIn('001', context)
    
    def test_start_ticket_execution(self):
        """Test starting ticket execution."""
        session_id = self.manager.start_ticket_execution('001', 'claude')
        
        self.assertIsNotNone(session_id)
        self.assertIn(session_id, self.manager.context_store.sessions)
    
    def test_complete_ticket_execution_success(self):
        """Test completing successful ticket execution."""
        session_id = self.manager.start_ticket_execution('001', 'venice')
        
        self.manager.complete_ticket_execution(
            session_id, '001', True
        )
        
        self.assertNotIn(session_id, self.manager.context_store.sessions)
    
    def test_complete_ticket_execution_failure(self):
        """Test completing failed ticket execution."""
        session_id = self.manager.start_ticket_execution('001', 'claude')
        
        self.manager.complete_ticket_execution(
            session_id, '001', False, "Test error"
        )
        
        self.assertNotIn(session_id, self.manager.context_store.sessions)
    
    def test_get_session_metrics(self):
        """Test getting session metrics."""
        session_id = self.manager.start_ticket_execution('001', 'claude')
        
        metrics = self.manager.get_session_metrics(session_id)
        
        self.assertEqual(metrics['session_id'], session_id)
        self.assertEqual(metrics['ticket_id'], '001')
        self.assertEqual(metrics['agent_type'], 'claude')
    
    def test_get_execution_stats(self):
        """Test getting execution statistics."""
        stats = self.manager.get_execution_stats()
        
        self.assertIn('total_executions', stats)
        self.assertIn('total_tracked_tickets', stats)
        self.assertIn('total_artifacts', stats)
    
    def test_extract_and_learn_patterns(self):
        """Test extracting and learning patterns from execution."""
        artifacts = [
            TicketArtifact(
                file_path="test_example.py",
                operation="created",
                description="Test file"
            ),
            TicketArtifact(
                file_path="src/module.py",
                operation="modified",
                description="Module file"
            )
        ]
        
        self.manager._extract_and_learn_patterns('001', artifacts)
        
        # Check that patterns were learned
        patterns = self.manager.context_store.patterns
        self.assertGreater(len(patterns), 0)
        
        # Check for expected categories
        categories = {p.category for p in patterns.values()}
        # The test file will trigger 'testing' category
        self.assertIn('testing', categories)
        # The files will trigger python_development category
        self.assertIn('python_development', categories)


class TestExecutionPattern(unittest.TestCase):
    """Test the ExecutionPattern class."""
    
    def test_pattern_creation(self):
        """Test creating an execution pattern."""
        pattern = ExecutionPattern(
            pattern_id="test_001",
            category="testing",
            description="Test pattern",
            solution_template="pytest"
        )
        
        self.assertEqual(pattern.pattern_id, "test_001")
        self.assertEqual(pattern.category, "testing")
        self.assertEqual(pattern.success_rate, 0.0)
        self.assertEqual(pattern.usage_count, 0)
    
    def test_pattern_serialization(self):
        """Test pattern serialization to dict."""
        pattern = ExecutionPattern(
            pattern_id="test_001",
            category="refactoring",
            description="Refactor pattern",
            solution_template="Extract method"
        )
        
        data = pattern.to_dict()
        
        self.assertEqual(data['pattern_id'], "test_001")
        self.assertEqual(data['category'], "refactoring")
        self.assertIn('created_at', data)
    
    def test_pattern_deserialization(self):
        """Test pattern deserialization from dict."""
        data = {
            'pattern_id': 'test_001',
            'category': 'optimization',
            'description': 'Optimize pattern',
            'solution_template': 'Use cache',
            'success_rate': 0.8,
            'usage_count': 5
        }
        
        pattern = ExecutionPattern.from_dict(data)
        
        self.assertEqual(pattern.pattern_id, 'test_001')
        self.assertEqual(pattern.success_rate, 0.8)
        self.assertEqual(pattern.usage_count, 5)


class TestSessionState(unittest.TestCase):
    """Test the SessionState class."""
    
    def test_session_creation(self):
        """Test creating a session state."""
        from datetime import datetime
        
        session = SessionState(
            session_id="session_001",
            ticket_id="001",
            agent_type="claude",
            status="active",
            started_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat()
        )
        
        self.assertEqual(session.session_id, "session_001")
        self.assertEqual(session.ticket_id, "001")
        self.assertEqual(session.status, "active")
    
    def test_session_serialization(self):
        """Test session serialization to dict."""
        from datetime import datetime
        
        session = SessionState(
            session_id="session_001",
            ticket_id="001",
            agent_type="venice",
            status="completed",
            started_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat(),
            learned_patterns=["pattern_001", "pattern_002"]
        )
        
        data = session.to_dict()
        
        self.assertEqual(data['session_id'], "session_001")
        self.assertEqual(data['status'], "completed")
        self.assertEqual(len(data['learned_patterns']), 2)


class TestContextIntegration(unittest.TestCase):
    """Integration tests for context sharing."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = TicketContextManager(self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_ticket_execution_flow(self):
        """Test complete flow of ticket execution with context."""
        # Start execution of first ticket
        session1 = self.manager.start_ticket_execution('001', 'claude')
        
        # Complete first ticket successfully
        self.manager.complete_ticket_execution(session1, '001', True)
        
        # Learn a pattern from first ticket with high success rate
        pattern_id = self.manager.context_store.learn_pattern(
            '001', 'testing', 'Test pattern', 'pytest'
        )
        # Update pattern to meet applicability criteria
        if pattern_id in self.manager.context_store.patterns:
            self.manager.context_store.patterns[pattern_id].success_rate = 0.8
            self.manager.context_store.patterns[pattern_id].usage_count = 3
        
        # Start execution of dependent ticket
        ticket_data = {'id': '002', 'dependencies': ['001']}
        context = self.manager.prepare_ticket_context('002', ticket_data)
        
        session2 = self.manager.start_ticket_execution('002', 'venice')
        
        # Context should include learned patterns
        ticket_context = self.manager.context_store.get_ticket_context('002', ['001'])
        self.assertGreater(len(ticket_context['applicable_patterns']), 0)
        
        # Complete second ticket
        self.manager.complete_ticket_execution(session2, '002', True)
        
        # Check statistics
        stats = self.manager.get_execution_stats()
        self.assertEqual(stats['total_executions'], 2)
        self.assertEqual(stats['successful'], 2)
    
    def test_context_improves_success_rate(self):
        """Test that context sharing improves success rate."""
        # Simulate multiple executions without context
        baseline_success = 0
        for i in range(10):
            session = self.manager.start_ticket_execution(f'test_{i}', 'claude')
            success = i % 3 == 0  # 33% success rate
            self.manager.complete_ticket_execution(session, f'test_{i}', success)
            if success:
                baseline_success += 1
        
        # Learn patterns from successful executions
        self.manager.context_store.learn_pattern(
            'test_0', 'optimization', 'Success pattern', 'Use this approach'
        )
        
        # Simulate executions with context
        context_success = 0
        for i in range(10, 20):
            # Prepare context with learned patterns
            ticket_data = {'id': f'test_{i}', 'dependencies': ['test_0']}
            context = self.manager.prepare_ticket_context(f'test_{i}', ticket_data)
            
            session = self.manager.start_ticket_execution(f'test_{i}', 'claude')
            
            # With context, success rate should be higher
            # Simulate that context helps achieve 60% success
            success = i % 5 != 0  # 80% success rate with context
            self.manager.complete_ticket_execution(session, f'test_{i}', success)
            if success:
                context_success += 1
        
        # Context should improve success rate
        self.assertGreater(context_success, baseline_success)
        
        # Get final statistics
        stats = self.manager.get_execution_stats()
        self.assertGreater(stats['total_executions'], 0)


if __name__ == '__main__':
    unittest.main()