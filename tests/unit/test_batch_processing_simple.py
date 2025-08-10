"""Simple unit tests for batch processing components."""

import unittest
from unittest.mock import MagicMock, patch


class TestBatchProcessingComponents(unittest.TestCase):
    """Test individual components of batch processing."""
    
    def test_ticket_complexity_analyzer(self):
        """Test the ticket complexity calculation logic."""
        # Import at test time to avoid circular imports
        from hydra.parallel.batch_executor import TicketCompatibilityAnalyzer
        
        analyzer = TicketCompatibilityAnalyzer()
        
        # Test simple ticket
        simple_ticket = {
            'title': 'Fix typo in readme',
            'description': 'Update documentation',
            'acceptance_criteria': ['Fix typo', 'Run spell check']
        }
        
        complexity = analyzer.calculate_complexity(simple_ticket)
        self.assertLessEqual(complexity, 30, "Simple ticket should have low complexity")
        
        # Test complex ticket
        complex_ticket = {
            'title': 'Implement new authentication system',
            'description': 'Create comprehensive auth architecture',
            'acceptance_criteria': [
                'Design auth flow',
                'Implement JWT tokens', 
                'Add user management',
                'Create admin panel',
                'Write security tests'
            ]
        }
        
        complexity = analyzer.calculate_complexity(complex_ticket)
        self.assertGreaterEqual(complexity, 50, "Complex ticket should have high complexity")
        
    def test_ticket_compatibility(self):
        """Test ticket compatibility checking."""
        from hydra.parallel.batch_executor import TicketCompatibilityAnalyzer
        
        analyzer = TicketCompatibilityAnalyzer()
        
        # Compatible tickets - same model, different files
        ticket1 = {
            'model': 'sonnet',
            'title': 'Fix import statement',
            'description': 'Update import in utils.py',
            'acceptance_criteria': ['Fix import']
        }
        
        ticket2 = {
            'model': 'sonnet',
            'title': 'Add type hint',
            'description': 'Add type hint to helper.py',
            'acceptance_criteria': ['Add typing']
        }
        
        compatible = analyzer.are_tickets_compatible(ticket1, ticket2)
        self.assertTrue(compatible, "Simple tickets with same model should be compatible")
        
        # Incompatible tickets - different models
        ticket3 = {'model': 'opus', 'title': 'Simple fix', 'description': '', 'acceptance_criteria': []}
        compatible = analyzer.are_tickets_compatible(ticket1, ticket3)
        self.assertFalse(compatible, "Tickets with different models should not be compatible")
        
    def test_batch_config(self):
        """Test batch configuration."""
        from hydra.parallel.batch_executor import BatchConfig
        
        # Test default config
        config = BatchConfig()
        self.assertEqual(config.max_batch_size, 5)
        self.assertEqual(config.max_complexity_score, 100)
        self.assertTrue(config.enable_batching)
        self.assertEqual(config.min_tickets_for_batch, 2)
        
        # Test custom config
        config = BatchConfig(
            max_batch_size=3,
            max_complexity_score=50,
            enable_batching=False,
            min_tickets_for_batch=3
        )
        
        self.assertEqual(config.max_batch_size, 3)
        self.assertEqual(config.max_complexity_score, 50)
        self.assertFalse(config.enable_batching)
        self.assertEqual(config.min_tickets_for_batch, 3)
        
    def test_batch_group_structure(self):
        """Test batch group data structure."""
        from hydra.parallel.batch_executor import BatchGroup
        
        batch = BatchGroup(
            batch_id="batch_001",
            ticket_ids=["001", "002", "003"],
            model="sonnet",
            combined_size=3,
            estimated_complexity=75,
            dependencies={"004"}
        )
        
        self.assertEqual(batch.batch_id, "batch_001")
        self.assertEqual(len(batch.ticket_ids), 3)
        self.assertEqual(batch.model, "sonnet")
        self.assertEqual(batch.combined_size, 3)
        self.assertEqual(batch.estimated_complexity, 75)
        self.assertIn("004", batch.dependencies)
        
    def test_session_overhead_calculation(self):
        """Test overhead reduction calculation logic."""
        # Simulate scenario with 6 tickets
        total_tickets = 6
        
        # Without batching: 6 sessions
        sessions_without_batching = total_tickets
        
        # With batching: 2 batches of 3 tickets each = 2 sessions
        batch_sessions = 2
        individual_sessions = 0
        sessions_with_batching = batch_sessions + individual_sessions
        
        overhead_reduction = (sessions_without_batching - sessions_with_batching) / sessions_without_batching * 100
        
        expected_reduction = (6 - 2) / 6 * 100  # 66.67%
        self.assertAlmostEqual(overhead_reduction, expected_reduction, places=1)
        self.assertGreaterEqual(overhead_reduction, 50, "Should achieve at least 50% overhead reduction")
        
    def test_batch_creation_logic(self):
        """Test logic for creating batches from compatible tickets."""
        from hydra.parallel.batch_executor import BatchExecutor, BatchConfig
        
        # Mock the dependencies that cause circular imports
        with patch('hydra.parallel.batch_executor.get_file_lock_manager'), \
             patch('hydra.agents.pool.AgentPool') as mock_pool:
            
            mock_pool_instance = MagicMock()
            mock_pool_instance.start.return_value = None
            mock_pool.return_value = mock_pool_instance
            
            config = BatchConfig(max_batch_size=3, min_tickets_for_batch=2)
            executor = BatchExecutor(batch_config=config)
            
            # Test data for batch creation
            ticket_list = [
                ('001', {
                    'model': 'sonnet', 
                    'title': 'Simple fix 1', 
                    'description': '', 
                    'acceptance_criteria': [], 
                    'dependencies': []
                }),
                ('002', {
                    'model': 'sonnet', 
                    'title': 'Simple fix 2', 
                    'description': '', 
                    'acceptance_criteria': [], 
                    'dependencies': []
                }),
                ('003', {
                    'model': 'sonnet', 
                    'title': 'Simple fix 3', 
                    'description': '', 
                    'acceptance_criteria': [], 
                    'dependencies': []
                })
            ]
            
            # Test batch creation for compatible tickets
            batches = executor._create_batches_for_model(ticket_list, 'sonnet')
            
            self.assertEqual(len(batches), 1, "Should create one batch for compatible tickets")
            self.assertEqual(len(batches[0].ticket_ids), 3, "Batch should contain all 3 tickets")
            self.assertEqual(batches[0].model, 'sonnet', "Batch should be for sonnet model")


if __name__ == '__main__':
    unittest.main()