"""Unit tests for BatchExecutor functionality."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra.parallel.batch_executor import (
    BatchConfig,
    BatchExecutor,
    BatchGroup,
    TicketCompatibilityAnalyzer
)


class TestTicketCompatibilityAnalyzer(unittest.TestCase):
    """Test the ticket compatibility analysis."""
    
    def setUp(self):
        self.analyzer = TicketCompatibilityAnalyzer()
        
    def test_calculate_complexity_simple_ticket(self):
        """Test complexity calculation for simple tickets."""
        simple_ticket = {
            'title': 'Fix typo in readme',
            'description': 'Update documentation',
            'acceptance_criteria': ['Fix typo', 'Run spell check']
        }
        
        complexity = self.analyzer.calculate_complexity(simple_ticket)
        self.assertLessEqual(complexity, 30, "Simple ticket should have low complexity")
        
    def test_calculate_complexity_complex_ticket(self):
        """Test complexity calculation for complex tickets."""
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
        
        complexity = self.analyzer.calculate_complexity(complex_ticket)
        self.assertGreaterEqual(complexity, 50, "Complex ticket should have high complexity")
        
    def test_are_tickets_compatible_same_model(self):
        """Test compatibility check for tickets with same model."""
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
        
        compatible = self.analyzer.are_tickets_compatible(ticket1, ticket2)
        self.assertTrue(compatible, "Simple tickets with same model should be compatible")
        
    def test_are_tickets_compatible_different_models(self):
        """Test compatibility check fails for different models."""
        ticket1 = {'model': 'sonnet', 'title': 'Simple fix', 'description': '', 'acceptance_criteria': []}
        ticket2 = {'model': 'opus', 'title': 'Simple fix', 'description': '', 'acceptance_criteria': []}
        
        compatible = self.analyzer.are_tickets_compatible(ticket1, ticket2)
        self.assertFalse(compatible, "Tickets with different models should not be compatible")
        
    def test_file_conflict_detection(self):
        """Test file conflict detection."""
        ticket1 = {
            'model': 'sonnet',
            'title': 'Update config.py settings',
            'description': 'Modify config.py',
            'acceptance_criteria': []
        }
        
        ticket2 = {
            'model': 'sonnet', 
            'title': 'Fix bug in config.py',
            'description': 'Fix config.py error',
            'acceptance_criteria': []
        }
        
        compatible = self.analyzer.are_tickets_compatible(ticket1, ticket2)
        self.assertFalse(compatible, "Tickets modifying same file should not be compatible")


class TestBatchConfig(unittest.TestCase):
    """Test batch configuration."""
    
    def test_default_config(self):
        """Test default batch configuration values."""
        config = BatchConfig()
        
        self.assertEqual(config.max_batch_size, 5)
        self.assertEqual(config.max_complexity_score, 100)
        self.assertTrue(config.enable_batching)
        self.assertEqual(config.min_tickets_for_batch, 2)
        
    def test_custom_config(self):
        """Test custom batch configuration."""
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


@pytest.mark.asyncio
class TestBatchExecutor:
    """Test the BatchExecutor functionality."""
    
    async def test_batch_executor_initialization(self):
        """Test BatchExecutor initializes correctly."""
        config = BatchConfig(max_batch_size=3)
        
        with patch('hydra.parallel.async_executor.get_file_lock_manager'), \
             patch('hydra.agents.pool.AgentPool') as mock_pool:
            
            mock_pool_instance = MagicMock()
            mock_pool_instance.start.return_value = None
            mock_pool.return_value = mock_pool_instance
            
            executor = BatchExecutor(batch_config=config, max_concurrent=2)
            
            assert executor.batch_config.max_batch_size == 3
            assert executor.max_concurrent == 2
            assert len(executor.batches) == 0
            
    @pytest.mark.stress
    async def test_overhead_calculation(self):
        """Test that batch processing reduces session overhead."""
        # Create a temporary tickets file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("""# Test Tickets

## Ticket 001: Fix typo
**Status:** TODO  
**Model:** Sonnet 4
**Dependencies:** None
**Description:** Fix typo in readme

**Acceptance Criteria:**
- [ ] Fix spelling error
- [ ] Run spell check

## Ticket 002: Add comment
**Status:** TODO
**Model:** Sonnet 4  
**Dependencies:** None
**Description:** Add documentation comment

**Acceptance Criteria:**
- [ ] Add docstring
- [ ] Verify format

## Ticket 003: Update import
**Status:** TODO
**Model:** Sonnet 4
**Dependencies:** None  
**Description:** Fix import statement

**Acceptance Criteria:**
- [ ] Fix import
- [ ] Test import

## Ticket 004: Rename variable
**Status:** TODO
**Model:** Sonnet 4
**Dependencies:** None
**Description:** Rename variable for clarity

**Acceptance Criteria:**
- [ ] Rename variable
- [ ] Update references
""")
            tickets_path = f.name
        
        try:
            config = BatchConfig(
                max_batch_size=4,
                min_tickets_for_batch=2,
                enable_batching=True
            )
            
            with patch('hydra.parallel.async_executor.get_file_lock_manager'), \
                 patch('hydra.agents.pool.AgentPool') as mock_pool, \
                 patch('hydra.parallel.batch_executor.parse_ticket') as mock_parse:
                
                # Setup mocks
                mock_pool_instance = MagicMock()
                mock_pool_instance.start.return_value = None
                mock_pool_instance.spawn_agent.return_value = "agent_1"
                mock_pool_instance.release_agent.return_value = None
                mock_pool.return_value = mock_pool_instance
                
                # Mock ticket parsing
                def mock_parse_side_effect(path, ticket_id):
                    tickets_data = {
                        '001': {
                            'title': 'Fix typo',
                            'model': 'sonnet',
                            'dependencies': [],
                            'status': 'TODO',
                            'acceptance_criteria': ['Fix spelling error'],
                            'completed': False
                        },
                        '002': {
                            'title': 'Add comment', 
                            'model': 'sonnet',
                            'dependencies': [],
                            'status': 'TODO',
                            'acceptance_criteria': ['Add docstring'],
                            'completed': False
                        },
                        '003': {
                            'title': 'Update import',
                            'model': 'sonnet', 
                            'dependencies': [],
                            'status': 'TODO',
                            'acceptance_criteria': ['Fix import'],
                            'completed': False
                        },
                        '004': {
                            'title': 'Rename variable',
                            'model': 'sonnet',
                            'dependencies': [],
                            'status': 'TODO', 
                            'acceptance_criteria': ['Rename variable'],
                            'completed': False
                        }
                    }
                    return tickets_data.get(ticket_id)
                
                mock_parse.side_effect = mock_parse_side_effect
                
                executor = BatchExecutor(batch_config=config, max_concurrent=2)
                
                # Load tickets and analyze for batching
                await executor.load_tickets(tickets_path)
                
                # Verify tickets were loaded
                assert len(executor.tickets) == 4
                
                # Verify batches were created
                assert len(executor.batches) > 0, "Should create at least one batch"
                
                # Calculate theoretical overhead reduction
                total_tickets = len(executor.tickets)
                batch_count = len(executor.batches)
                single_tickets = total_tickets - sum(len(batch.ticket_ids) for batch in executor.batches.values())
                
                sessions_without_batching = total_tickets
                sessions_with_batching = batch_count + single_tickets
                overhead_reduction = (sessions_without_batching - sessions_with_batching) / sessions_without_batching * 100
                
                # Verify we achieve meaningful overhead reduction
                assert overhead_reduction > 0, f"Should reduce overhead, got {overhead_reduction}%"
                
                # For this test with 4 simple compatible tickets, we should be able to batch them
                # which should give us significant reduction
                print(f"Overhead reduction achieved: {overhead_reduction:.1f}%")
                
        finally:
            # Clean up
            os.unlink(tickets_path)
            
    async def test_batch_group_creation(self):
        """Test that compatible tickets are grouped correctly."""
        config = BatchConfig(max_batch_size=3, min_tickets_for_batch=2)
        
        with patch('hydra.parallel.async_executor.get_file_lock_manager'), \
             patch('hydra.agents.pool.AgentPool') as mock_pool:
            
            mock_pool_instance = MagicMock()
            mock_pool_instance.start.return_value = None
            mock_pool.return_value = mock_pool_instance
            
            executor = BatchExecutor(batch_config=config)
            
            # Test data for batch creation
            ticket_list = [
                ('001', {'model': 'sonnet', 'title': 'Simple fix 1', 'description': '', 'acceptance_criteria': [], 'dependencies': []}),
                ('002', {'model': 'sonnet', 'title': 'Simple fix 2', 'description': '', 'acceptance_criteria': [], 'dependencies': []}),
                ('003', {'model': 'opus', 'title': 'Complex task', 'description': '', 'acceptance_criteria': [], 'dependencies': []}),
                ('004', {'model': 'sonnet', 'title': 'Simple fix 3', 'description': '', 'acceptance_criteria': [], 'dependencies': []})
            ]
            
            # Test batch creation for sonnet model
            sonnet_tickets = [(tid, data) for tid, data in ticket_list if data['model'] == 'sonnet']
            batches = executor._create_batches_for_model(sonnet_tickets, 'sonnet')
            
            assert len(batches) == 1, "Should create one batch for sonnet tickets"
            assert len(batches[0].ticket_ids) == 3, "Batch should contain 3 tickets"
            assert batches[0].model == 'sonnet', "Batch should be for sonnet model"


if __name__ == '__main__':
    # Run the tests
    unittest.main()