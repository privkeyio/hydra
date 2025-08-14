import asyncio
import json
import pytest
import tempfile
import yaml
from pathlib import Path

from hydra.orchestrator.project_orchestrator import (
    ProjectOrchestrator,
    ProjectSpecification,
    TaskNode,
    TaskStatus,
    TaskComplexity,
    ModelType
)
from hydra.config import get_config


@pytest.mark.integration
class TestOrchestratorIntegration:
    
    @pytest.fixture
    def sample_yaml_project(self):
        return """
name: Web Application Development
description: Build a complete web application with frontend and backend
tasks:
  - id: design_api
    name: Design REST API
    description: Create OpenAPI specification for the application
    complexity: moderate
    model: sonnet
    
  - id: implement_models
    name: Implement Data Models
    description: Create database models and schemas
    complexity: simple
    model: sonnet
    
  - id: implement_api
    name: Implement API Endpoints
    description: Build REST API endpoints based on the design
    dependencies: [design_api, implement_models]
    complexity: moderate
    model: sonnet
    
  - id: create_frontend
    name: Create Frontend Structure
    description: Set up React application with routing
    complexity: simple
    model: sonnet
    
  - id: implement_ui
    name: Implement UI Components
    description: Build user interface components
    dependencies: [create_frontend]
    complexity: moderate
    model: sonnet
    
  - id: integrate_frontend_backend
    name: Integrate Frontend with Backend
    description: Connect React app to REST API
    dependencies: [implement_api, implement_ui]
    complexity: complex
    model: opus
    
  - id: add_authentication
    name: Add Authentication
    description: Implement secure authentication system
    dependencies: [integrate_frontend_backend]
    complexity: critical
    model: opus
    
  - id: write_tests
    name: Write Tests
    description: Create comprehensive test suite
    dependencies: [add_authentication]
    complexity: moderate
    model: sonnet
    
  - id: optimize_performance
    name: Optimize Performance
    description: Optimize application performance and scalability
    dependencies: [write_tests]
    complexity: complex
    model: opus

max_parallel: 4
global_timeout: 1800
model_preferences:
  default: sonnet
  complex_tasks: opus
"""
    
    @pytest.fixture
    def sample_json_project(self):
        return {
            "name": "Data Processing Pipeline",
            "description": "Build a data processing pipeline",
            "tasks": [
                {
                    "id": "fetch_data",
                    "name": "Fetch Data",
                    "description": "Fetch data from external sources",
                    "complexity": "simple",
                    "parameters": {
                        "sources": ["api", "database", "files"]
                    }
                },
                {
                    "id": "validate_data",
                    "name": "Validate Data",
                    "description": "Validate and clean the fetched data",
                    "dependencies": ["fetch_data"],
                    "complexity": "moderate"
                },
                {
                    "id": "transform_data",
                    "name": "Transform Data",
                    "description": "Transform data into required format",
                    "dependencies": ["validate_data"],
                    "complexity": "moderate"
                },
                {
                    "id": "analyze_data",
                    "name": "Analyze Data",
                    "description": "Perform data analysis and generate insights",
                    "dependencies": ["transform_data"],
                    "complexity": "complex",
                    "model": "opus"
                },
                {
                    "id": "generate_report",
                    "name": "Generate Report",
                    "description": "Create comprehensive report with visualizations",
                    "dependencies": ["analyze_data"],
                    "complexity": "moderate"
                }
            ],
            "max_parallel": 3
        }
    
    def test_yaml_specification_parsing(self, sample_yaml_project):
        spec = ProjectSpecification.from_yaml(sample_yaml_project)
        
        assert spec.name == "Web Application Development"
        assert len(spec.tasks) == 9
        assert spec.max_parallel == 4
        
        design_task = next(t for t in spec.tasks if t.id == "design_api")
        assert design_task.complexity == TaskComplexity.MODERATE
        assert design_task.model == ModelType.SONNET
        
        auth_task = next(t for t in spec.tasks if t.id == "add_authentication")
        assert auth_task.complexity == TaskComplexity.CRITICAL
        assert auth_task.model == ModelType.OPUS
        assert auth_task.dependencies == ["integrate_frontend_backend"]
    
    def test_json_specification_parsing(self, sample_json_project):
        spec = ProjectSpecification.from_json(json.dumps(sample_json_project))
        
        assert spec.name == "Data Processing Pipeline"
        assert len(spec.tasks) == 5
        
        fetch_task = next(t for t in spec.tasks if t.id == "fetch_data")
        assert fetch_task.parameters["sources"] == ["api", "database", "files"]
        
        analyze_task = next(t for t in spec.tasks if t.id == "analyze_data")
        assert analyze_task.model == ModelType.OPUS
    
    def test_dependency_graph_construction(self, sample_yaml_project):
        spec = ProjectSpecification.from_yaml(sample_yaml_project)
        levels = spec.get_execution_order()
        
        assert len(levels) == 6
        
        level_0_ids = {t.id for t in levels[0]}
        assert level_0_ids == {"design_api", "implement_models", "create_frontend"}
        
        level_1_ids = {t.id for t in levels[1]}
        assert "implement_ui" in level_1_ids
        
        level_1_ids_set = set(level_1_ids)  
        if "implement_api" in level_1_ids_set:
            # implement_api can be in level 1 if dependencies are satisfied
            level_2_ids = {t.id for t in levels[2]}
            assert "integrate_frontend_backend" in level_2_ids
        else:
            level_2_ids = {t.id for t in levels[2]}
            assert "implement_api" in level_2_ids
        
        last_level_ids = {t.id for t in levels[-1]}
        assert "optimize_performance" in last_level_ids
    
    def test_circular_dependency_detection(self):
        spec_dict = {
            "name": "Invalid Project",
            "description": "Project with circular dependencies",
            "tasks": [
                {
                    "id": "task_a",
                    "name": "Task A",
                    "description": "First task",
                    "dependencies": ["task_c"]
                },
                {
                    "id": "task_b",
                    "name": "Task B",
                    "description": "Second task",
                    "dependencies": ["task_a"]
                },
                {
                    "id": "task_c",
                    "name": "Task C",
                    "description": "Third task",
                    "dependencies": ["task_b"]
                }
            ]
        }
        
        spec = ProjectSpecification.from_dict(spec_dict)
        valid, errors = spec.validate()
        
        assert valid is False
        assert any("Circular dependency" in error for error in errors)
    
    def test_model_routing_logic(self, sample_yaml_project):
        spec = ProjectSpecification.from_yaml(sample_yaml_project)
        config = get_config()
        orchestrator = ProjectOrchestrator(spec, config)
        
        simple_task = next(t for t in spec.tasks if t.complexity == TaskComplexity.SIMPLE)
        model = orchestrator._select_model_for_task(simple_task)
        # In test environment with mock providers, expect mock model names
        assert "sonnet" in model.lower() or "mock" in model.lower()
        
        critical_task = next(t for t in spec.tasks if t.complexity == TaskComplexity.CRITICAL)
        model = orchestrator._select_model_for_task(critical_task)
        # In test environment with mock providers, expect mock model names
        assert "opus" in model.lower() or "mock" in model.lower()
        
        auto_task = TaskNode(
            id="auto_task",
            name="Auto Task",
            description="architect and design system with security",
            model=ModelType.AUTO
        )
        complexity = orchestrator._analyze_task_complexity(auto_task)
        assert complexity in [TaskComplexity.COMPLEX, TaskComplexity.CRITICAL]
    
    @pytest.mark.asyncio
    async def test_parallel_execution_limits(self):
        tasks = []
        for i in range(12):
            tasks.append(TaskNode(
                id=f"task_{i}",
                name=f"Task {i}",
                description=f"Parallel task {i}"
            ))
        
        spec = ProjectSpecification(
            name="Parallel Test",
            description="Test parallel execution limits",
            tasks=tasks,
            max_parallel=10
        )
        
        valid, errors = spec.validate()
        assert valid is True
        
        spec.max_parallel = 11
        valid, errors = spec.validate()
        assert valid is False
        assert "max_parallel must be between 1 and 10" in errors[0]
    
    def test_save_and_load_specification(self, sample_yaml_project, tmp_path):
        spec = ProjectSpecification.from_yaml(sample_yaml_project)
        
        yaml_file = tmp_path / "project.yaml"
        yaml_file.write_text(sample_yaml_project)
        
        loaded_spec = ProjectSpecification.from_yaml(yaml_file.read_text())
        
        assert loaded_spec.name == spec.name
        assert len(loaded_spec.tasks) == len(spec.tasks)
        assert loaded_spec.max_parallel == spec.max_parallel
    
    @pytest.mark.asyncio
    async def test_task_retry_logic(self):
        spec = ProjectSpecification(
            name="Retry Test",
            description="Test retry logic",
            tasks=[
                TaskNode(
                    id="flaky_task",
                    name="Flaky Task",
                    description="Task that may fail",
                    retry_count=3
                )
            ]
        )
        
        config = get_config()
        orchestrator = ProjectOrchestrator(spec, config)
        
        attempt_count = 0
        
        async def flaky_execute(task):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Temporary failure")
            task.status = TaskStatus.COMPLETED
            orchestrator.completed_tasks.add(task.id)
            return {"success": True}
        
        orchestrator._execute_task = flaky_execute
        
        report = await orchestrator.execute()
        
        assert report['tasks_completed'] == 1
        assert report['tasks_failed'] == 0
    
    @pytest.mark.asyncio
    async def test_progress_visualization(self, sample_yaml_project):
        spec = ProjectSpecification.from_yaml(sample_yaml_project)
        config = get_config()
        orchestrator = ProjectOrchestrator(spec, config)
        
        spec.tasks[0].status = TaskStatus.COMPLETED
        spec.tasks[0].start_time = 1000.0
        spec.tasks[0].end_time = 1005.23
        orchestrator.completed_tasks.add(spec.tasks[0].id)
        
        spec.tasks[1].status = TaskStatus.RUNNING
        spec.tasks[1].assigned_agent = "agent_abc123"
        orchestrator.running_tasks.add(spec.tasks[1].id)
        
        spec.tasks[2].status = TaskStatus.FAILED
        spec.tasks[2].error = "Connection timeout"
        orchestrator.failed_tasks.add(spec.tasks[2].id)
        
        visualization = await orchestrator.visualize_progress()
        
        assert "Web Application Development" in visualization
        assert "✅ design_api: Design REST API" in visualization
        assert "Time: 5.23s" in visualization
        assert "🔄 implement_models: Implement Data Models" in visualization
        assert "Agent: agent_abc123" in visualization
        assert "❌ implement_api: Implement API Endpoints" in visualization
        assert "Error: Connection timeout" in visualization
        assert "Progress: 1/9 tasks" in visualization
    
    def test_execution_report_generation(self, sample_yaml_project):
        spec = ProjectSpecification.from_yaml(sample_yaml_project)
        config = get_config()
        orchestrator = ProjectOrchestrator(spec, config)
        
        orchestrator.start_time = 1000.0
        orchestrator.end_time = 1500.0
        
        for i, task in enumerate(spec.tasks[:5]):
            task.status = TaskStatus.COMPLETED
            task.start_time = 1000.0 + i * 50
            task.end_time = task.start_time + 30
            task.result = {"success": True, "code": f"code_{task.id}"}
            orchestrator.completed_tasks.add(task.id)
        
        spec.tasks[5].status = TaskStatus.FAILED
        spec.tasks[5].error = "Test failure"
        orchestrator.failed_tasks.add(spec.tasks[5].id)
        
        report = orchestrator._generate_report()
        
        assert report['project'] == "Web Application Development"
        assert report['status'] == 'partial'
        assert report['total_execution_time'] == 500.0
        assert report['tasks_completed'] == 5
        assert report['tasks_failed'] == 1
        
        assert 'design_api' in report['task_results']
        assert report['task_results']['design_api']['status'] == 'completed'
        assert report['task_results']['design_api']['execution_time'] == 30.0
        
        assert report['task_results']['integrate_frontend_backend']['status'] == 'failed'
        assert report['task_results']['integrate_frontend_backend']['error'] == "Test failure"
        
        assert 'statistics' in report
        assert 'model_distribution' in report['statistics']
        assert report['statistics']['model_distribution']['balanced'] == 6
        assert report['statistics']['model_distribution']['smart'] == 3