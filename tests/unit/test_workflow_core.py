import tempfile
import os
from pathlib import Path

from hydra.ticket_workflow import parse_ticket, update_ticket_in_database


def test_parse_ticket_yaml():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""tickets:
- id: '001'
  title: Test Task
  status: TODO
  description: Simple test
  acceptance_criteria:
  - Task works
""")
        f.flush()
        
        ticket = parse_ticket(f.name, '001')
        
        assert ticket['title'] == 'Test Task'
        assert ticket['status'] == 'TODO'
        assert ticket['description'] == 'Simple test'
        assert 'Task works' in ticket['acceptance_criteria']
        
        os.unlink(f.name)


def test_parse_ticket_missing():
    ticket = parse_ticket('/nonexistent/file.yaml', '001')
    assert ticket is None


def test_parse_ticket_wrong_id():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""tickets:
- id: '001'
  title: Test Task
""")
        f.flush()
        
        ticket = parse_ticket(f.name, '999')
        assert ticket is None
        
        os.unlink(f.name)


def test_update_ticket_database():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup database environment
        db_dir = Path(tmpdir) / '.hydra' / 'dashboard'
        db_dir.mkdir(parents=True)
        
        # Create a project file so database path is set correctly
        tickets_file = Path(tmpdir) / 'tickets.yaml'
        tickets_file.write_text("""tickets:
- id: '001'
  title: Test
""")
        
        # Initialize database
        from hydra.dashboard.database import get_db_manager
        original_db = os.environ.get('DATABASE_URL')
        try:
            update_ticket_in_database('001', 'IN_PROGRESS', tmpdir, {
                'title': 'Test Ticket',
                'description': 'Test description'
            })
            
            # Verify database was created and populated
            db_path = db_dir / 'hydra.db'
            assert db_path.exists()
            
        finally:
            if original_db:
                os.environ['DATABASE_URL'] = original_db
            elif 'DATABASE_URL' in os.environ:
                del os.environ['DATABASE_URL']


def test_execute_single_ticket_basic():
    from hydra.ticket_workflow import execute_single_ticket
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""tickets:
- id: '001'
  title: Simple Task
  status: TODO
  description: Basic test task
  acceptance_criteria:
  - Task completes
""")
        f.flush()
        
        # Test with skip_preflight to avoid complex dependencies
        result = execute_single_ticket(f.name, '001', skip_preflight=True)
        
        # Should return True for mock provider success
        assert result is True
        
        os.unlink(f.name)


def test_execute_single_ticket_missing_file():
    from hydra.ticket_workflow import execute_single_ticket
    
    # Should handle missing file gracefully
    result = execute_single_ticket('/nonexistent/file.yaml', '001', skip_preflight=True)
    assert result is not True


def test_execute_single_ticket_missing_ticket():
    from hydra.ticket_workflow import execute_single_ticket
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""tickets:
- id: '001'
  title: Only ticket
""")
        f.flush()
        
        # Test with non-existent ticket ID
        result = execute_single_ticket(f.name, '999', skip_preflight=True)
        assert result is not True
        
        os.unlink(f.name)


def test_parse_all_tickets():
    from hydra.ticket_workflow import parse_all_tickets
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""tickets:
- id: '001'
  title: First Task
  status: TODO
- id: '002'
  title: Second Task
  status: DONE
""")
        f.flush()
        
        tickets = parse_all_tickets(f.name)
        assert len(tickets) == 2
        assert '001' in tickets
        assert '002' in tickets
        assert tickets['001']['title'] == 'First Task'
        assert tickets['002']['status'] == 'DONE'
        
        os.unlink(f.name)


def test_mark_ticket_completed():
    from hydra.ticket_workflow import mark_ticket_completed
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""tickets:
- id: '001'
  title: Test Task
  status: TODO
""")
        f.flush()
        
        # Mark ticket as completed
        mark_ticket_completed(f.name, '001')
        
        # Verify it was marked as completed
        from hydra.ticket_workflow import parse_ticket
        ticket = parse_ticket(f.name, '001')
        assert ticket['status'] == 'DONE'
        
        os.unlink(f.name)


def test_mark_ticket_in_progress():
    from hydra.ticket_workflow import mark_ticket_in_progress
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""tickets:
- id: '001'
  title: Test Task
  status: TODO
""")
        f.flush()
        
        # Mark ticket as in progress
        mark_ticket_in_progress(f.name, '001')
        
        # Verify it was marked correctly
        from hydra.ticket_workflow import parse_ticket
        ticket = parse_ticket(f.name, '001')
        assert ticket['status'] == 'IN_PROGRESS'
        
        os.unlink(f.name)


def test_run_all_tickets_basic():
    from hydra.ticket_workflow import run_all_tickets
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""tickets:
- id: '001'
  title: Simple Task
  status: TODO
  description: Test task
  acceptance_criteria:
  - Task works
""")
        f.flush()
        
        # Test with skip_preflight to avoid complex dependencies
        result = run_all_tickets(f.name, max_parallel=1, skip_preflight=True)
        
        # Should complete without errors
        assert result is not None
        
        os.unlink(f.name)


def test_validate_acceptance_criteria():
    from hydra.ticket_workflow import validate_acceptance_criteria
    
    ticket = {
        'acceptance_criteria': ['Task works', 'Tests pass'],
        'title': 'Test Task'
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = validate_acceptance_criteria(ticket, tmpdir)
        assert isinstance(result, bool)


def test_generate_tickets_md():
    from hydra.ticket_workflow import generate_tickets_md
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tickets_path = os.path.join(tmpdir, 'tickets.yaml')
        
        # Test ticket generation
        generate_tickets_md(
            "Create a simple function",
            tickets_path
        )
        
        # Verify file was created
        assert os.path.exists(tickets_path)