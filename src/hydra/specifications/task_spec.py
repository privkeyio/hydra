"""Task Spec module."""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import jsonschema
import yaml


class TaskType(Enum):
    FILE_CREATE = "file_create"
    FILE_EDIT = "file_edit"
    COMMAND = "command"
    CODE_GENERATION = "code_generation"
    ANALYSIS = "analysis"
    TEST = "test"
    LOOP = "loop"
    CONDITION = "condition"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


class ExecutionMode(Enum):
    STRICT = "strict"
    BEST_EFFORT = "best_effort"
    FAIL_FAST = "fail_fast"


@dataclass
class TaskCondition:
    type: str
    expression: str
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskSpec:
    id: str
    type: TaskType
    name: str
    description: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, str] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    conditions: List[TaskCondition] = field(default_factory=list)
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    timeout: Optional[int] = None
    model_preference: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = TaskType(self.type)


@dataclass
class LoopSpec:
    variable: str
    iterable: Union[List[Any], str]
    tasks: List[TaskSpec]
    max_iterations: Optional[int] = None


@dataclass
class ProjectSpec:
    name: str
    version: str
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    tasks: List[TaskSpec] = field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.STRICT
    max_parallel: int = 10
    timeout: Optional[int] = None


class TaskSpecValidator:

    TASK_SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "description": {"type": "string"},
            "metadata": {"type": "object"},
            "variables": {"type": "object"},
            "execution_mode": {"enum": ["strict", "best_effort", "fail_fast"]},
            "max_parallel": {"type": "integer", "minimum": 1, "maximum": 50},
            "timeout": {"type": "integer", "minimum": 1},
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "pattern": r"^[a-zA-Z0-9_-]+$"},
                        "type": {"enum": [t.value for t in TaskType]},
                        "name": {"type": "string", "minLength": 1},
                        "description": {"type": "string"},
                        "inputs": {"type": "object"},
                        "outputs": {"type": "object"},
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "conditions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "expression": {"type": "string"},
                                    "variables": {"type": "object"}
                                },
                                "required": ["type", "expression"]
                            }
                        },
                        "retry_policy": {
                            "type": "object",
                            "properties": {
                                "max_attempts": {"type": "integer", "minimum": 1},
                                "backoff_factor": {"type": "number", "minimum": 0},
                                "retry_on": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                }
                            }
                        },
                        "timeout": {"type": "integer", "minimum": 1},
                        "model_preference": {"type": "string"}
                    },
                    "required": ["id", "type", "name"]
                }
            }
        },
        "required": ["name", "version", "tasks"]
    }

    def __init__(self):
        self.validator = jsonschema.Draft7Validator(self.TASK_SCHEMA)

    def validate_dict(self, spec_dict: Dict[str, Any]) -> List[str]:
        errors = []

        for error in self.validator.iter_errors(spec_dict):
            path = ".".join(str(p) for p in error.path) if error.path else "root"
            errors.append(f"At {path}: {error.message}")

        errors.extend(self._validate_dependencies(spec_dict))
        errors.extend(self._validate_loops(spec_dict))

        return errors

    def _validate_dependencies(self, spec_dict: Dict[str, Any]) -> List[str]:
        errors = []
        tasks = spec_dict.get("tasks", [])
        task_ids = {task.get("id") for task in tasks}

        for task in tasks:
            for dep in task.get("dependencies", []):
                if dep not in task_ids:
                    errors.append(
                        f"Task {task.get('id')} depends on non-existent task: {dep}"
                    )

        return errors

    def _validate_loops(self, spec_dict: Dict[str, Any]) -> List[str]:
        errors = []
        tasks = spec_dict.get("tasks", [])

        for task in tasks:
            if task.get("type") == "loop":
                loop_inputs = task.get("inputs", {})
                if "variable" not in loop_inputs or "iterable" not in loop_inputs:
                    errors.append(f"Loop task {task.get('id')} missing required inputs")

        return errors


class TaskSpecParser:

    def __init__(self):
        self.validator = TaskSpecValidator()
        self.variables = {}

    def parse_file(self, file_path: Union[str, Path]) -> ProjectSpec:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Specification file not found: {path}")

        content = path.read_text(encoding="utf-8")

        if path.suffix.lower() in [".yaml", ".yml"]:
            spec_dict = yaml.safe_load(content)
        elif path.suffix.lower() == ".json":
            spec_dict = json.loads(content)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

        return self.parse_dict(spec_dict)

    def parse_dict(self, spec_dict: Dict[str, Any]) -> ProjectSpec:
        errors = self.validator.validate_dict(spec_dict)
        if errors:
            raise ValueError(f"Validation errors: {', '.join(errors)}")

        self.variables = spec_dict.get("variables", {})

        tasks = []
        for task_dict in spec_dict.get("tasks", []):
            task = self._parse_task(task_dict)
            tasks.append(task)

        return ProjectSpec(
            name=spec_dict["name"],
            version=spec_dict["version"],
            description=spec_dict.get("description", ""),
            metadata=spec_dict.get("metadata", {}),
            variables=self.variables,
            tasks=tasks,
            execution_mode=ExecutionMode(spec_dict.get("execution_mode", "strict")),
            max_parallel=spec_dict.get("max_parallel", 10),
            timeout=spec_dict.get("timeout")
        )

    def _parse_task(self, task_dict: Dict[str, Any]) -> TaskSpec:
        conditions = []
        for cond_dict in task_dict.get("conditions", []):
            conditions.append(TaskCondition(
                type=cond_dict["type"],
                expression=cond_dict["expression"],
                variables=cond_dict.get("variables", {})
            ))

        inputs = self._resolve_variables(task_dict.get("inputs", {}))
        name = self._substitute_variables(task_dict["name"])
        description = self._substitute_variables(task_dict.get("description", ""))

        return TaskSpec(
            id=task_dict["id"],
            type=TaskType(task_dict["type"]),
            name=name,
            description=description,
            inputs=inputs,
            outputs=task_dict.get("outputs", {}),
            dependencies=task_dict.get("dependencies", []),
            conditions=conditions,
            retry_policy=task_dict.get("retry_policy", {}),
            timeout=task_dict.get("timeout"),
            model_preference=task_dict.get("model_preference")
        )

    def _resolve_variables(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self._substitute_variables(obj)
        elif isinstance(obj, dict):
            return {k: self._resolve_variables(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_variables(item) for item in obj]
        else:
            return obj

    def _substitute_variables(self, text: str) -> str:
        pattern = r'\{\{\s*(\w+)\s*\}\}'

        def replace_var(match):
            var_name = match.group(1)
            return str(self.variables.get(var_name, match.group(0)))

        return re.sub(pattern, replace_var, text)


class ConditionEvaluator:

    def evaluate(self, condition: TaskCondition, context: Dict[str, Any]) -> bool:
        variables = {**context, **condition.variables}

        if condition.type == "file_exists":
            return Path(condition.expression).exists()
        elif condition.type == "variable_equals":
            parts = condition.expression.split("==")
            if len(parts) != 2:
                return False
            var_name, expected = parts[0].strip(), parts[1].strip().strip('"\'')
            return str(variables.get(var_name, "")) == expected
        elif condition.type == "command_success":
            import subprocess
            try:
                result = subprocess.run(
                    condition.expression,
                    shell=True,
                    capture_output=True,
                    timeout=30
                )
                return result.returncode == 0
            except Exception:
                return False
        else:
            return True


class TaskExecutionPlanner:

    def __init__(self, project_spec: ProjectSpec):
        self.project = project_spec
        self.condition_evaluator = ConditionEvaluator()

    def create_execution_plan(
        self, context: Dict[str, Any] = None
    ) -> List[List[TaskSpec]]:
        context = context or {}

        eligible_tasks = []
        for task in self.project.tasks:
            if self._task_conditions_met(task, context):
                eligible_tasks.append(task)

        return self._build_execution_phases(eligible_tasks)

    def _task_conditions_met(self, task: TaskSpec, context: Dict[str, Any]) -> bool:
        for condition in task.conditions:
            if not self.condition_evaluator.evaluate(condition, context):
                return False
        return True

    def _build_execution_phases(self, tasks: List[TaskSpec]) -> List[List[TaskSpec]]:
        phases = []
        remaining = tasks.copy()
        completed = set()

        while remaining:
            ready_tasks = []

            for task in remaining:
                if all(dep in completed for dep in task.dependencies):
                    ready_tasks.append(task)

            if not ready_tasks:
                raise ValueError("Circular dependency or unresolvable dependencies")

            phases.append(ready_tasks)
            for task in ready_tasks:
                remaining.remove(task)
                completed.add(task.id)

        return phases


class TaskTemplateManager:

    TEMPLATES = {
        "python_script": {
            "type": "code_generation",
            "inputs": {
                "filename": "{{ filename }}",
                "function_name": "{{ function_name }}",
                "requirements": "{{ requirements }}"
            },
            "description": "Generate a Python script with specified function"
        },
        "test_suite": {
            "type": "test",
            "inputs": {
                "test_framework": "pytest",
                "target_files": "{{ target_files }}",
                "coverage_threshold": 80
            },
            "description": "Create comprehensive test suite"
        },
        "web_api": {
            "type": "sequential",
            "inputs": {
                "framework": "{{ framework | default('fastapi') }}",
                "endpoints": "{{ endpoints }}",
                "database": "{{ database | default('sqlite') }}"
            },
            "description": "Generate web API with specified endpoints"
        },
        "docker_setup": {
            "type": "file_create",
            "inputs": {
                "base_image": "{{ base_image }}",
                "port": "{{ port | default(8000) }}",
                "dependencies": "{{ dependencies }}"
            },
            "description": "Create Docker configuration files"
        },
        "ci_pipeline": {
            "type": "file_create",
            "inputs": {
                "platform": "{{ platform | default('github') }}",
                "languages": "{{ languages }}",
                "test_commands": "{{ test_commands }}"
            },
            "description": "Generate CI/CD pipeline configuration"
        }
    }

    def get_template(self, name: str) -> Dict[str, Any]:
        if name not in self.TEMPLATES:
            raise ValueError(f"Unknown template: {name}")
        return self.TEMPLATES[name].copy()

    def list_templates(self) -> List[str]:
        return list(self.TEMPLATES.keys())

    def instantiate_template(self, name: str, variables: Dict[str, Any]) -> TaskSpec:
        template = self.get_template(name)

        def substitute_template_vars(obj):
            if isinstance(obj, str):
                result = obj
                for var, value in variables.items():
                    pattern = f"{{{{ {var} }}}}"
                    result = result.replace(pattern, str(value))
                return result
            elif isinstance(obj, dict):
                return {k: substitute_template_vars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [substitute_template_vars(item) for item in obj]
            else:
                return obj

        template_dict = substitute_template_vars(template)

        return TaskSpec(
            id=variables.get("id", f"{name}_task"),
            type=TaskType(template_dict["type"]),
            name=variables.get("name", f"{name.replace('_', ' ').title()} Task"),
            description=template_dict.get("description", ""),
            inputs=template_dict.get("inputs", {}),
            outputs=template_dict.get("outputs", {}),
            dependencies=template_dict.get("dependencies", [])
        )
