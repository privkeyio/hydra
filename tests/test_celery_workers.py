"""Tests for Celery worker implementation."""

import pytest
from unittest.mock import patch, MagicMock
from celery import states

from hydra.workers.tasks import generate_code, generate_code_priority, execute_workflow, execute_workflow_priority, dead_letter_handler
from hydra.workers.celery_app import app as celery_app


@pytest.fixture
def celery_worker():
    celery_app.conf.update(task_always_eager=True)
    yield
    celery_app.conf.update(task_always_eager=False)


def test_generate_code_success(celery_worker):
    with patch('hydra.workers.tasks.get_config') as mock_config, \
         patch('hydra.workers.tasks.CodeAgent') as mock_agent, \
         patch('hydra.workers.tasks.send_progress_update'):
        
        mock_agent_instance = MagicMock()
        mock_agent_instance.generate_code.return_value = "def hello(): pass"
        mock_agent.return_value = mock_agent_instance
        
        result = generate_code.apply(args=["Generate hello function", "python", 100])
        
        assert result.state == states.SUCCESS
        assert result.result["code"] == "def hello(): pass"
        assert "task_id" in result.result
        assert "completed_at" in result.result


def test_generate_code_failure(celery_worker):
    with patch('hydra.workers.tasks.get_config') as mock_config, \
         patch('hydra.workers.tasks.CodeAgent') as mock_agent, \
         patch('hydra.workers.tasks.send_progress_update'):
        
        mock_agent.side_effect = Exception("Agent initialization failed")
        
        result = generate_code.apply(args=["Generate hello function", "python", 100])
        
        assert result.state == states.FAILURE


def test_execute_workflow_success(celery_worker):
    with patch('hydra.workers.tasks.get_config') as mock_config, \
         patch('hydra.workers.tasks.run_workflow') as mock_workflow, \
         patch('hydra.workers.tasks.send_progress_update'):
        
        mock_workflow.return_value = {"agents": 3, "result": "Task completed"}
        
        result = execute_workflow.apply(args=["Build REST API", 3, 10])
        
        assert result.state == states.SUCCESS
        assert result.result["result"]["agents"] == 3
        assert "task_id" in result.result
        assert "completed_at" in result.result


def test_priority_queue_routing():
    task = generate_code.s("test", "python", 100)
    assert task.options.get('queue', 'default') == 'default'
    
    priority_task = generate_code_priority.s("test", "python", 100)
    assert celery_app.conf.task_routes['hydra.workers.tasks.generate_code_priority']['queue'] == 'high_priority'


def test_dead_letter_handler():
    with patch('logging.getLogger') as mock_logger:
        logger_instance = MagicMock()
        mock_logger.return_value = logger_instance
        
        dead_letter_handler("task-123", "Task failed", ["arg1"], {"key": "value"})
        
        logger_instance.error.assert_called_once()
        call_args = logger_instance.error.call_args
        assert "Task task-123 failed permanently" in call_args[0][0]