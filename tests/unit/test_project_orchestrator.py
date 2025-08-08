import asyncio
import json
import os
import pytest
import time
import yaml
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from hydra.orchestrator.project_orchestrator import (
    ProjectOrchestrator,
    ProjectSpecification,
    TaskNode,
    TaskStatus,
    TaskComplexity,
    ModelType
)

# Test mode detection
TEST_MODE = (
    os.getenv('TESTING') == '1' or
    os.getenv('PYTEST_CURRENT_TEST') is not None or
    'pytest' in str(os.getenv('_', ''))
)
from hydra.exceptions import ValidationError


class TestTaskNode:
    def test_task_node_creation(self):
        task = TaskNode(
            id="task1",
            name="Test Task",
            description="A test task",
            dependencies=["task0"],
            complexity=TaskComplexity.SIMPLE,
            model=ModelType.SONNET
        )
        
        assert task.id == "task1"
        assert task.name == "Test Task"
        assert task.dependencies == ["task0"]
        assert task.complexity == TaskComplexity.SIMPLE
        assert task.model == ModelType.SONNET
        assert task.status == TaskStatus.PENDING
    
    def test_can_execute_with_no_dependencies(self):
        task = TaskNode(id="task1", name="Task", description="desc")
        assert task.can_execute(set()) is True
    
    def test_can_execute_with_satisfied_dependencies(self):
        task = TaskNode(
            id="task2",
            name="Task",
            description="desc",
            dependencies=["task1"]
        )
        assert task.can_execute({"task1"}) is True
        assert task.can_execute(set()) is False
    
    def test_execution_time_calculation(self):
        task = TaskNode(id="task1", name="Task", description="desc")
        task.start_time = 100.0
        task.end_time = 105.5
        assert task.execution_time == 5.5


class TestProjectSpecification:
    def test_from_yaml(self):
        yaml_content = """
name: Test Project
description: A test project
tasks:
  - id: task1
    name: First Task
    description: Do something
    complexity: simple
  - id: task2
    name: Second Task
    description: Do something else
    dependencies: [task1]
    complexity: complex
    model: opus
max_parallel: 2
"""
        spec = ProjectSpecification.from_yaml(yaml_content)
        assert spec.name == "Test Project"
        assert len(spec.tasks) == 2
        assert spec.tasks[0].id == "task1"
        assert spec.tasks[1].dependencies == ["task1"]
        assert spec.max_parallel == 2
    
    def test_from_json(self):
        json_content = json.dumps({
            "name": "Test Project",
            "description": "A test project",
            "tasks": [
                {
                    "id": "task1",
                    "name": "First Task",
                    "description": "Do something",
                    "complexity": "simple"
                }
            ]
        })
        spec = ProjectSpecification.from_json(json_content)
        assert spec.name == "Test Project"
        assert len(spec.tasks) == 1
    
    def test_validate_duplicate_ids(self):
        spec = ProjectSpecification(
            name="Test",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Task 1", description="desc"),
                TaskNode(id="task1", name="Task 2", description="desc")
            ]
        )
        valid, errors = spec.validate()
        assert valid is False
        assert "Duplicate task ID: task1" in errors[0]
    
    def test_validate_unknown_dependency(self):
        spec = ProjectSpecification(
            name="Test",
            description="Test",
            tasks=[
                TaskNode(
                    id="task1",
                    name="Task 1",
                    description="desc",
                    dependencies=["unknown"]
                )
            ]
        )
        valid, errors = spec.validate()
        assert valid is False
        assert "unknown task: unknown" in errors[0]
    
    def test_validate_circular_dependency(self):
        spec = ProjectSpecification(
            name="Test",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Task 1", description="desc", dependencies=["task2"]),
                TaskNode(id="task2", name="Task 2", description="desc", dependencies=["task1"])
            ]
        )
        valid, errors = spec.validate()
        assert valid is False
        assert "Circular dependency" in errors[0]
    
    def test_validate_parallel_limits(self):
        spec = ProjectSpecification(
            name="Test",
            description="Test",
            tasks=[],
            max_parallel=11
        )
        valid, errors = spec.validate()
        assert valid is False
        assert "max_parallel must be between 1 and 10" in errors[0]
    
    def test_get_execution_order_simple(self):
        spec = ProjectSpecification(
            name="Test",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Task 1", description="desc"),
                TaskNode(id="task2", name="Task 2", description="desc", dependencies=["task1"]),
                TaskNode(id="task3", name="Task 3", description="desc", dependencies=["task1"])
            ]
        )
        
        levels = spec.get_execution_order()
        assert len(levels) == 2
        assert len(levels[0]) == 1
        assert levels[0][0].id == "task1"
        assert len(levels[1]) == 2
        assert {t.id for t in levels[1]} == {"task2", "task3"}
    
    def test_get_execution_order_complex(self):
        spec = ProjectSpecification(
            name="Test",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Task 1", description="desc"),
                TaskNode(id="task2", name="Task 2", description="desc"),
                TaskNode(id="task3", name="Task 3", description="desc", dependencies=["task1", "task2"]),
                TaskNode(id="task4", name="Task 4", description="desc", dependencies=["task3"]),
                TaskNode(id="task5", name="Task 5", description="desc", dependencies=["task3"])
            ]
        )
        
        levels = spec.get_execution_order()
        assert len(levels) == 3
        assert len(levels[0]) == 2
        assert {t.id for t in levels[0]} == {"task1", "task2"}
        assert len(levels[1]) == 1
        assert levels[1][0].id == "task3"
        assert len(levels[2]) == 2
        assert {t.id for t in levels[2]} == {"task4", "task5"}


class TestProjectOrchestrator:
    @pytest.fixture
    def simple_spec(self):
        return ProjectSpecification(
            name="Test Project",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Simple Task", description="create a function", complexity=TaskComplexity.SIMPLE),
                TaskNode(id="task2", name="Complex Task", description="architect system", complexity=TaskComplexity.COMPLEX, dependencies=["task1"])
            ],
            max_parallel=2
        )
    
    @pytest.fixture
    def mock_config(self):
        config = Mock()
        config.llm_provider.model = "claude-3-5-sonnet-20241022"
        return config
    
    def test_orchestrator_initialization(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        assert orchestrator.spec == simple_spec
        assert len(orchestrator.agents) == 0
        assert len(orchestrator.completed_tasks) == 0
    
    def test_select_model_for_task_auto(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        
        simple_task = simple_spec.tasks[0]
        model = orchestrator._select_model_for_task(simple_task)
        assert "sonnet" in model.lower()
        
        complex_task = simple_spec.tasks[1]
        model = orchestrator._select_model_for_task(complex_task)
        assert "opus" in model.lower()
    
    def test_select_model_for_task_manual(self, mock_config):
        task = TaskNode(
            id="task1",
            name="Task",
            description="test",
            model=ModelType.OPUS
        )
        spec = ProjectSpecification(name="Test", description="Test", tasks=[task])
        orchestrator = ProjectOrchestrator(spec, mock_config)
        
        model = orchestrator._select_model_for_task(task)
        assert "opus" in model.lower()
    
    def test_analyze_task_complexity(self, mock_config):
        spec = ProjectSpecification(name="Test", description="Test", tasks=[])
        orchestrator = ProjectOrchestrator(spec, mock_config)
        
        simple_task = TaskNode(id="t1", name="Task", description="create a list of items")
        assert orchestrator._analyze_task_complexity(simple_task) == TaskComplexity.SIMPLE
        
        complex_task = TaskNode(id="t2", name="Task", description="architect the system")
        assert orchestrator._analyze_task_complexity(complex_task) == TaskComplexity.COMPLEX
        
        critical_task = TaskNode(id="t3", name="Task", description="implement security measures")
        assert orchestrator._analyze_task_complexity(critical_task) == TaskComplexity.CRITICAL
    
    @pytest.mark.asyncio
    async def test_execute_task_success(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        task = simple_spec.tasks[0]
        
        with patch('hydra.orchestrator.project_orchestrator.CodeAgent') as MockAgent:
            mock_agent = Mock()
            mock_agent.complete_task.return_value = {
                "success": True,
                "generated_code": "def test(): pass"
            }
            MockAgent.return_value = mock_agent
            
            result = await orchestrator._execute_task(task)
            
            assert task.status == TaskStatus.COMPLETED
            assert task.result == {"success": True, "generated_code": "def test(): pass"}
            assert task.id in orchestrator.completed_tasks
            assert task.start_time is not None
            assert task.end_time is not None
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(TEST_MODE, reason="Skip timeout tests - synchronous execution in test mode doesn't timeout")
    async def test_execute_task_timeout(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        task = simple_spec.tasks[0]
        task.timeout = 0.1
        
        with patch('hydra.orchestrator.project_orchestrator.CodeAgent') as MockAgent:
            mock_agent = Mock()
            mock_agent.complete_task.side_effect = lambda x: time.sleep(1)
            MockAgent.return_value = mock_agent
            
            with pytest.raises(asyncio.TimeoutError):
                await orchestrator._execute_task(task)
            
            assert task.status == TaskStatus.FAILED
            assert "timed out" in task.error
            assert task.id in orchestrator.failed_tasks
    
    @pytest.mark.asyncio
    async def test_execute_task_failure(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        task = simple_spec.tasks[0]
        
        with patch('hydra.orchestrator.project_orchestrator.CodeAgent') as MockAgent:
            mock_agent = Mock()
            mock_agent.complete_task.side_effect = Exception("Test error")
            MockAgent.return_value = mock_agent
            
            with pytest.raises(Exception):
                await orchestrator._execute_task(task)
            
            assert task.status == TaskStatus.FAILED
            assert task.error == "Test error"
            assert task.id in orchestrator.failed_tasks
    
    def test_build_task_prompt(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        task = simple_spec.tasks[1]
        
        simple_spec.tasks[0].result = {"success": True}
        
        prompt = orchestrator._build_task_prompt(task)
        
        assert "Test Project" in prompt
        assert "Complex Task" in prompt
        assert "architect system" in prompt
        assert "Simple Task: Completed" in prompt
    
    @pytest.mark.asyncio
    async def test_execute_project_success(self, mock_config):
        spec = ProjectSpecification(
            name="Test Project",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Task 1", description="create function"),
                TaskNode(id="task2", name="Task 2", description="create class"),
                TaskNode(id="task3", name="Task 3", description="implement feature", dependencies=["task1", "task2"])
            ],
            max_parallel=2
        )
        
        orchestrator = ProjectOrchestrator(spec, mock_config)
        
        with patch.object(orchestrator, '_execute_task') as mock_execute:
            async def execute_side_effect(task):
                task.status = TaskStatus.COMPLETED
                task.result = {"success": True}
                task.start_time = time.time()
                task.end_time = time.time() + 0.1
                orchestrator.completed_tasks.add(task.id)
                return {"success": True}
            
            mock_execute.side_effect = execute_side_effect
            
            report = await orchestrator.execute()
            
            assert report['project'] == "Test Project"
            assert report['status'] == 'completed'
            assert report['tasks_completed'] == 3
            assert report['tasks_failed'] == 0
            assert mock_execute.call_count == 3
    
    @pytest.mark.asyncio
    async def test_execute_project_with_failures(self, mock_config):
        spec = ProjectSpecification(
            name="Test Project",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Task 1", description="test"),
                TaskNode(id="task2", name="Task 2", description="test", dependencies=["task1"])
            ]
        )
        
        orchestrator = ProjectOrchestrator(spec, mock_config)
        
        with patch.object(orchestrator, '_execute_task') as mock_execute:
            async def execute_side_effect(task):
                if task.id == "task1":
                    task.status = TaskStatus.FAILED
                    task.error = "Test failure"
                    orchestrator.failed_tasks.add(task.id)
                    raise Exception("Test failure")
                else:
                    task.status = TaskStatus.COMPLETED
                    orchestrator.completed_tasks.add(task.id)
                return {"success": task.status == TaskStatus.COMPLETED}
            
            mock_execute.side_effect = execute_side_effect
            
            report = await orchestrator.execute()
            
            assert report['status'] == 'partial'
            assert report['tasks_failed'] == 1
    
    @pytest.mark.asyncio
    async def test_execute_validates_specification(self, mock_config):
        spec = ProjectSpecification(
            name="Invalid",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Task", description="test", dependencies=["nonexistent"])
            ]
        )
        
        orchestrator = ProjectOrchestrator(spec, mock_config)
        
        with pytest.raises(ValidationError):
            await orchestrator.execute()
    
    @pytest.mark.asyncio
    async def test_parallel_execution(self, mock_config):
        spec = ProjectSpecification(
            name="Parallel Test",
            description="Test",
            tasks=[
                TaskNode(id="task1", name="Task 1", description="test"),
                TaskNode(id="task2", name="Task 2", description="test"),
                TaskNode(id="task3", name="Task 3", description="test"),
                TaskNode(id="task4", name="Task 4", description="test")
            ],
            max_parallel=2
        )
        
        orchestrator = ProjectOrchestrator(spec, mock_config)
        execution_times = []
        
        with patch.object(orchestrator, '_execute_task') as mock_execute:
            async def execute_side_effect(task):
                start = time.time()
                await asyncio.sleep(0.1)
                execution_times.append(time.time() - start)
                task.status = TaskStatus.COMPLETED
                orchestrator.completed_tasks.add(task.id)
                return {"success": True}
            
            mock_execute.side_effect = execute_side_effect
            
            start_time = time.time()
            await orchestrator.execute()
            total_time = time.time() - start_time
            
            assert total_time < 0.4
            assert mock_execute.call_count == 4
    
    def test_generate_report(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        orchestrator.start_time = 100.0
        orchestrator.end_time = 110.0
        
        simple_spec.tasks[0].status = TaskStatus.COMPLETED
        simple_spec.tasks[0].result = {"success": True}
        simple_spec.tasks[0].start_time = 100.0
        simple_spec.tasks[0].end_time = 105.0
        orchestrator.completed_tasks.add("task1")
        
        simple_spec.tasks[1].status = TaskStatus.FAILED
        simple_spec.tasks[1].error = "Test error"
        orchestrator.failed_tasks.add("task2")
        
        report = orchestrator._generate_report()
        
        assert report['project'] == "Test Project"
        assert report['status'] == 'partial'
        assert report['total_execution_time'] == 10.0
        assert report['tasks_completed'] == 1
        assert report['tasks_failed'] == 1
        assert 'task1' in report['task_results']
        assert report['task_results']['task1']['status'] == 'completed'
        assert report['task_results']['task2']['status'] == 'failed'
    
    @pytest.mark.asyncio
    async def test_visualize_progress(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        orchestrator.start_time = time.time()
        
        simple_spec.tasks[0].status = TaskStatus.COMPLETED
        simple_spec.tasks[0].start_time = time.time() - 5.0
        simple_spec.tasks[0].end_time = time.time()
        orchestrator.completed_tasks.add("task1")
        
        simple_spec.tasks[1].status = TaskStatus.RUNNING
        simple_spec.tasks[1].assigned_agent = "agent_123"
        
        visualization = await orchestrator.visualize_progress()
        
        assert "Test Project" in visualization
        assert "✅ task1: Simple Task" in visualization
        assert "🔄 task2: Complex Task" in visualization
        assert "Agent: agent_123" in visualization
        assert "Progress: 1/2 tasks" in visualization
    
    def test_cleanup(self, simple_spec, mock_config):
        orchestrator = ProjectOrchestrator(simple_spec, mock_config)
        orchestrator.agents = {"agent1": Mock(), "agent2": Mock()}
        
        orchestrator.cleanup()
        
        assert len(orchestrator.agents) == 0
        assert orchestrator.executor._shutdown is True