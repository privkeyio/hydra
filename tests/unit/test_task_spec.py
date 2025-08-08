import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hydra.specifications.task_spec import (
    TaskSpec, TaskType, ProjectSpec, ExecutionMode,
    TaskSpecValidator, TaskSpecParser, ConditionEvaluator,
    TaskExecutionPlanner, TaskTemplateManager, TaskCondition
)


class TestTaskSpec(unittest.TestCase):
    
    def test_task_spec_creation(self):
        task = TaskSpec(
            id="test_task",
            type=TaskType.CODE_GENERATION,
            name="Test Task",
            description="A test task"
        )
        
        self.assertEqual(task.id, "test_task")
        self.assertEqual(task.type, TaskType.CODE_GENERATION)
        self.assertEqual(task.name, "Test Task")
        self.assertEqual(task.description, "A test task")
    
    def test_task_spec_string_type_conversion(self):
        task = TaskSpec(
            id="test_task", 
            type="code_generation",
            name="Test Task"
        )
        
        self.assertEqual(task.type, TaskType.CODE_GENERATION)


class TestTaskSpecValidator(unittest.TestCase):
    
    def setUp(self):
        self.validator = TaskSpecValidator()
        self.valid_spec = {
            "name": "Test Project",
            "version": "1.0.0",
            "tasks": [
                {
                    "id": "task1",
                    "type": "code_generation",
                    "name": "Generate Code"
                }
            ]
        }
    
    def test_valid_specification(self):
        errors = self.validator.validate_dict(self.valid_spec)
        self.assertEqual(len(errors), 0)
    
    def test_missing_required_fields(self):
        spec = {"name": "Test"}
        errors = self.validator.validate_dict(spec)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("version" in error for error in errors))
        self.assertTrue(any("tasks" in error for error in errors))
    
    def test_invalid_version_format(self):
        spec = self.valid_spec.copy()
        spec["version"] = "1.0"
        errors = self.validator.validate_dict(spec)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("does not match" in error for error in errors))
    
    def test_invalid_task_type(self):
        spec = self.valid_spec.copy()
        spec["tasks"][0]["type"] = "invalid_type"
        errors = self.validator.validate_dict(spec)
        self.assertGreater(len(errors), 0)
    
    def test_dependency_validation(self):
        spec = {
            "name": "Test Project",
            "version": "1.0.0",
            "tasks": [
                {
                    "id": "task1",
                    "type": "code_generation",
                    "name": "Task 1",
                    "dependencies": ["nonexistent_task"]
                }
            ]
        }
        errors = self.validator.validate_dict(spec)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("non-existent task" in error for error in errors))
    
    def test_valid_dependencies(self):
        spec = {
            "name": "Test Project",
            "version": "1.0.0", 
            "tasks": [
                {
                    "id": "task1",
                    "type": "code_generation",
                    "name": "Task 1"
                },
                {
                    "id": "task2",
                    "type": "file_create",
                    "name": "Task 2",
                    "dependencies": ["task1"]
                }
            ]
        }
        errors = self.validator.validate_dict(spec)
        self.assertEqual(len(errors), 0)


class TestTaskSpecParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = TaskSpecParser()
        self.temp_dir = Path(tempfile.mkdtemp())
        
        self.valid_yaml = """
name: "Test Project"
version: "1.0.0"
description: "A test project"
variables:
  project_name: "test_project"
  version: "1.0"
execution_mode: "strict"
max_parallel: 5

tasks:
  - id: "task1"
    type: "code_generation"
    name: "Generate {{ project_name }} v{{ version }}"
    description: "Generate code for the project"
    inputs:
      filename: "{{ project_name }}/main.py"
    outputs:
      result: "generated_file"
"""
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_parse_yaml_file(self):
        yaml_file = self.temp_dir / "test.yaml"
        yaml_file.write_text(self.valid_yaml)
        
        project = self.parser.parse_file(yaml_file)
        
        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.version, "1.0.0")
        self.assertEqual(len(project.tasks), 1)
        self.assertEqual(project.execution_mode, ExecutionMode.STRICT)
        self.assertEqual(project.max_parallel, 5)
    
    def test_variable_substitution(self):
        yaml_file = self.temp_dir / "test.yaml"
        yaml_file.write_text(self.valid_yaml)
        
        project = self.parser.parse_file(yaml_file)
        task = project.tasks[0]
        
        self.assertEqual(task.name, "Generate test_project v1.0")
        self.assertEqual(task.inputs["filename"], "test_project/main.py")
    
    def test_parse_json_file(self):
        json_spec = {
            "name": "JSON Project",
            "version": "1.0.0",
            "tasks": [
                {
                    "id": "json_task",
                    "type": "file_create",
                    "name": "JSON Task"
                }
            ]
        }
        
        json_file = self.temp_dir / "test.json"
        json_file.write_text(json.dumps(json_spec))
        
        project = self.parser.parse_file(json_file)
        
        self.assertEqual(project.name, "JSON Project")
        self.assertEqual(len(project.tasks), 1)
    
    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.parser.parse_file("nonexistent.yaml")
    
    def test_unsupported_format(self):
        txt_file = self.temp_dir / "test.txt"
        txt_file.write_text("not yaml or json")
        
        with self.assertRaises(ValueError):
            self.parser.parse_file(txt_file)
    
    def test_validation_error(self):
        invalid_yaml = """
name: "Invalid Project"
tasks: []
"""
        yaml_file = self.temp_dir / "invalid.yaml"
        yaml_file.write_text(invalid_yaml)
        
        with self.assertRaises(ValueError):
            self.parser.parse_file(yaml_file)


class TestConditionEvaluator(unittest.TestCase):
    
    def setUp(self):
        self.evaluator = ConditionEvaluator()
        self.temp_file = Path(tempfile.mktemp())
        self.temp_file.write_text("test content")
    
    def tearDown(self):
        if self.temp_file.exists():
            self.temp_file.unlink()
    
    def test_file_exists_condition_true(self):
        condition = TaskCondition(
            type="file_exists",
            expression=str(self.temp_file)
        )
        
        result = self.evaluator.evaluate(condition, {})
        self.assertTrue(result)
    
    def test_file_exists_condition_false(self):
        condition = TaskCondition(
            type="file_exists", 
            expression="nonexistent_file.txt"
        )
        
        result = self.evaluator.evaluate(condition, {})
        self.assertFalse(result)
    
    def test_variable_equals_condition_true(self):
        condition = TaskCondition(
            type="variable_equals",
            expression="status == 'ready'"
        )
        
        context = {"status": "ready"}
        result = self.evaluator.evaluate(condition, context)
        self.assertTrue(result)
    
    def test_variable_equals_condition_false(self):
        condition = TaskCondition(
            type="variable_equals",
            expression="status == 'ready'"
        )
        
        context = {"status": "pending"}
        result = self.evaluator.evaluate(condition, context)
        self.assertFalse(result)
    
    @patch('subprocess.run')
    def test_command_success_condition_true(self, mock_run):
        mock_run.return_value.returncode = 0
        
        condition = TaskCondition(
            type="command_success",
            expression="echo 'test'"
        )
        
        result = self.evaluator.evaluate(condition, {})
        self.assertTrue(result)
    
    @patch('subprocess.run')
    def test_command_success_condition_false(self, mock_run):
        mock_run.return_value.returncode = 1
        
        condition = TaskCondition(
            type="command_success",
            expression="exit 1"
        )
        
        result = self.evaluator.evaluate(condition, {})
        self.assertFalse(result)


class TestTaskExecutionPlanner(unittest.TestCase):
    
    def test_simple_execution_plan(self):
        tasks = [
            TaskSpec(id="task1", type=TaskType.CODE_GENERATION, name="Task 1"),
            TaskSpec(id="task2", type=TaskType.FILE_CREATE, name="Task 2", dependencies=["task1"])
        ]
        
        project = ProjectSpec(name="Test", version="1.0.0", tasks=tasks)
        planner = TaskExecutionPlanner(project)
        
        phases = planner.create_execution_plan()
        
        self.assertEqual(len(phases), 2)
        self.assertEqual(len(phases[0]), 1)
        self.assertEqual(phases[0][0].id, "task1")
        self.assertEqual(len(phases[1]), 1)
        self.assertEqual(phases[1][0].id, "task2")
    
    def test_parallel_execution_plan(self):
        tasks = [
            TaskSpec(id="task1", type=TaskType.CODE_GENERATION, name="Task 1"),
            TaskSpec(id="task2", type=TaskType.FILE_CREATE, name="Task 2"),
            TaskSpec(id="task3", type=TaskType.COMMAND, name="Task 3", dependencies=["task1", "task2"])
        ]
        
        project = ProjectSpec(name="Test", version="1.0.0", tasks=tasks)
        planner = TaskExecutionPlanner(project)
        
        phases = planner.create_execution_plan()
        
        self.assertEqual(len(phases), 2)
        self.assertEqual(len(phases[0]), 2)
        task_ids = {task.id for task in phases[0]}
        self.assertEqual(task_ids, {"task1", "task2"})
        self.assertEqual(len(phases[1]), 1)
        self.assertEqual(phases[1][0].id, "task3")
    
    def test_circular_dependency_error(self):
        tasks = [
            TaskSpec(id="task1", type=TaskType.CODE_GENERATION, name="Task 1", dependencies=["task2"]),
            TaskSpec(id="task2", type=TaskType.FILE_CREATE, name="Task 2", dependencies=["task1"])
        ]
        
        project = ProjectSpec(name="Test", version="1.0.0", tasks=tasks)
        planner = TaskExecutionPlanner(project)
        
        with self.assertRaises(ValueError):
            planner.create_execution_plan()


class TestTaskTemplateManager(unittest.TestCase):
    
    def setUp(self):
        self.template_manager = TaskTemplateManager()
    
    def test_list_templates(self):
        templates = self.template_manager.list_templates()
        self.assertGreater(len(templates), 0)
        self.assertIn("python_script", templates)
        self.assertIn("test_suite", templates)
        self.assertIn("web_api", templates)
    
    def test_get_template(self):
        template = self.template_manager.get_template("python_script")
        self.assertIn("type", template)
        self.assertIn("inputs", template)
        self.assertEqual(template["type"], "code_generation")
    
    def test_get_nonexistent_template(self):
        with self.assertRaises(ValueError):
            self.template_manager.get_template("nonexistent_template")
    
    def test_instantiate_template(self):
        variables = {
            "id": "my_script",
            "name": "My Python Script",
            "filename": "my_script.py",
            "function_name": "main",
            "requirements": "requests"
        }
        
        task = self.template_manager.instantiate_template("python_script", variables)
        
        self.assertEqual(task.id, "my_script")
        self.assertEqual(task.name, "My Python Script")
        self.assertEqual(task.type, TaskType.CODE_GENERATION)
        self.assertIn("filename", task.inputs)
        self.assertEqual(task.inputs["filename"], "my_script.py")


if __name__ == '__main__':
    unittest.main()