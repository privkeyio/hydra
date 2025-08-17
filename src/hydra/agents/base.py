"""Base module."""

import ast
import json
import logging
import os
import subprocess
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from hydra.config import get_config
from hydra.exceptions import (
    CodeGenerationError,
    ExecutionTimeoutError,
    RecursionLimitError,
    ValidationError,
)
from hydra.validators import CodeValidator, InputSanitizer, TaskValidator


class CodeAgent:
    _logger = None

    @classmethod
    def _setup_logger(cls):
        if cls._logger is None:
            cls._logger = logging.getLogger("hydra_agent")
            cls._logger.setLevel(logging.INFO)

            if not cls._logger.handlers:
                os.makedirs("logs", exist_ok=True)
                handler = RotatingFileHandler(
                    "logs/agent_activity.log", maxBytes=10 * 1024 * 1024, backupCount=5
                )
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                handler.setFormatter(formatter)
                cls._logger.addHandler(handler)
        return cls._logger

    def __init__(
        self,
        name: str,
        parent: Optional["CodeAgent"] = None,
        depth: int = 0,
        safe_mode: bool = True,
    ):
        # Sanitize and validate inputs
        self.name = InputSanitizer.sanitize_agent_name(name)
        if not self.name:
            raise ValidationError("Invalid agent name")

        self.parent = parent
        self.depth = depth
        self.safe_mode = safe_mode
        self.config = get_config()
        self.agent_config = self.config.get_agent_config()
        self.max_depth = self.agent_config["max_depth"]
        self.max_retries = self.agent_config["retry_attempts"]
        self.employees = []
        self.agent_id = f"{self.name}_{id(self)}"
        self.logger = self._setup_logger()
        self.llm_provider = self.config.llm_provider
        self.start_time = time.time()
        self.total_tokens_used = 0
        self.code_generations = 0

        hierarchy = self._get_hierarchy_path()
        self.logger.info(
            f"Agent created: {self.agent_id} at depth {depth}, "
            f"hierarchy: {hierarchy}, provider: {self.llm_provider.name}"
        )

    def _get_hierarchy_path(self) -> str:
        if self.parent is None:
            return self.name
        return f"{self.parent._get_hierarchy_path()} -> {self.name}"

    def reason(self, task: str) -> Dict[str, Any]:
        if self.depth > self.max_depth:
            error_msg = (
                f"Agent {self.agent_id} exceeded "
                f"max depth {self.max_depth} (current: {self.depth})"
            )
            self.logger.error(error_msg)
            raise RecursionLimitError(error_msg)

        # Validate task input
        validation_result = TaskValidator.validate_task(task)
        if not validation_result["valid"]:
            raise ValidationError(f"Invalid task: {validation_result['errors']}")

        if validation_result["warnings"]:
            for warning in validation_result["warnings"]:
                self.logger.warning(f"Agent {self.agent_id}: {warning}")

        task = validation_result["sanitized_task"]
        hierarchy = self._get_hierarchy_path()
        self.logger.info(
            f"Agent {self.agent_id} reasoning task: {task[:100]}... "
            f"(hierarchy: {hierarchy})"
        )

        prompt = f"""Analyze this task and create a plan:
Task: {task}

You MUST respond with ONLY valid JSON in this exact format:
{{"plan": "your strategy here", "subtasks": ["subtask1", "subtask2"]}}

If the task is simple and doesn't need subtasks, use an empty array:
{{"plan": "your strategy here", "subtasks": []}}

Important: Return ONLY the JSON object, no other text or formatting.
"""

        try:
            result = self.llm_provider.generate_json(prompt)
            subtask_count = len(result.get("subtasks", []))
            self.logger.info(
                f"Agent {self.agent_id} generated plan with "
                f"{subtask_count} subtasks"
            )
            return result
        except Exception as e:
            self.logger.warning(
                f"Agent {self.agent_id} failed to parse JSON response: {e}"
            )
            # Try regular generation and parse
            try:
                response = self.llm_provider.generate(prompt)
                result = json.loads(response)
                return result
            except Exception:
                # Fallback response
                return {"plan": str(e), "subtasks": []}

    def _clean_code_format(self, code: str) -> str:
        """Clean up code formatting."""
        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        return code.strip()

    def _validate_generated_code(self, code: str) -> None:
        """Validate generated code for security and syntax."""
        # Security validation if in safe mode
        if self.safe_mode:
            validation = CodeValidator.validate_code(code, allow_imports=False)
            if not validation["valid"]:
                raise ValidationError(f"Code validation failed: {validation['errors']}")

            if validation["dangerous_patterns"]:
                self.logger.warning(
                    f"Agent {self.agent_id} generated code with warnings: "
                    f"{validation['dangerous_patterns']}"
                )

        # Validate syntax
        ast.parse(code)

    def generate_code(self, prompt: str, retry_count: int = 0) -> str:
        self.logger.info(
            f"Agent {self.agent_id} generating code "
            f"(attempt {retry_count + 1}/{self.max_retries})"
        )

        # Validate prompt
        validation_result = TaskValidator.validate_task(prompt)
        if not validation_result["valid"]:
            raise ValidationError(f"Invalid prompt: {validation_result['errors']}")

        code_prompt = f"""Generate Python code for this task:
{validation_result['sanitized_task']}

Return ONLY executable Python code. No explanations or markdown.

IMPORTANT: Do not include any imports of os, subprocess, sys, or other system modules.
Only use safe built-in functions and standard library modules like math, datetime, json.
"""

        try:
            self.code_generations += 1
            code = self.llm_provider.generate(code_prompt)
            code = self._clean_code_format(code)
            self._validate_generated_code(code)

            self.logger.info(
                f"Agent {self.agent_id} generated valid code "
                f"({len(code)} chars, generation #{self.code_generations})"
            )
            return code

        except (SyntaxError, ValidationError) as e:
            if retry_count < self.max_retries - 1:
                self.logger.info(f"Agent {self.agent_id} retrying code generation")
                return self.generate_code(prompt, retry_count + 1)
            raise CodeGenerationError(f"Generated invalid Python code: {e}") from e
        except Exception as e:
            if retry_count < self.max_retries - 1:
                return self.generate_code(prompt, retry_count + 1)
            raise CodeGenerationError(f"Code generation failed: {str(e)}") from e

    def execute_code(self, code_str: str, retry_count: int = 0) -> Dict[str, Any]:
        self.logger.info(
            f"Agent {self.agent_id} executing code "
            f"(attempt {retry_count + 1}/{self.max_retries})"
        )

        try:
            # Set up environment with proper Python path
            env = os.environ.copy()
            # Add the src directory to Python path
            src_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            if "PYTHONPATH" in env:
                env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
            else:
                env["PYTHONPATH"] = src_path

            result = subprocess.run(
                ["python", "-c", code_str],
                capture_output=True,
                text=True,
                timeout=self.agent_config["timeout"],
                check=False,
                env=env,
            )

            execution_result = {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

            if execution_result["success"]:
                self.logger.info(f"Agent {self.agent_id} code execution successful")
            else:
                error_msg = (
                    f"Code execution failed with return code "
                    f"{result.returncode}: {result.stderr}"
                )
                self.logger.error(f"Agent {self.agent_id} {error_msg}")

                if retry_count < self.max_retries - 1:
                    self.logger.info(f"Agent {self.agent_id} retrying code execution")
                    return self.execute_code(code_str, retry_count + 1)

            return execution_result

        except subprocess.TimeoutExpired:
            error_msg = (
                f"Execution timeout ({self.agent_config['timeout']}s exceeded) - "
                "Code may contain infinite loops or blocking operations"
            )
            self.logger.error(f"Agent {self.agent_id} {error_msg}")
            raise ExecutionTimeoutError(error_msg) from None
        except Exception as e:
            error_msg = (
                f"Unexpected execution error: {str(e)} - Check system "
                "resources and permissions"
            )
            self.logger.error(f"Agent {self.agent_id} {error_msg}")
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
                "returncode": -1,
            }

    def create_employee(self, subtask: str) -> Dict[str, Any]:
        if self.depth > self.max_depth:
            error_msg = (
                f"Cannot spawn employee: Agent {self.agent_id} at depth "
                f"{self.depth} exceeds max depth {self.max_depth}"
            )
            self.logger.error(error_msg)
            raise RecursionLimitError(error_msg)

        hierarchy = self._get_hierarchy_path()
        self.logger.info(
            f"Agent {self.agent_id} spawning employee for subtask: "
            f"{subtask[:100]}... (parent hierarchy: {hierarchy})"
        )

        employee_name = f"{self.name}_employee_{len(self.employees) + 1}"
        employee = CodeAgent(
            employee_name, parent=self, depth=self.depth + 1, safe_mode=self.safe_mode
        )
        self.employees.append(employee)

        self.logger.info(f"Agent {self.agent_id} created employee {employee.agent_id}")

        spawn_prompt = f"""Create a complete Python script for this subtask:
Subtask: {subtask}

The script should:
1. Import necessary classes
2. Create CodeAgent employee '{employee_name}' depth {self.depth + 1}
3. Execute subtask using employee methods
4. Return JSON with 'success', 'result', 'employee_name' keys

Return ONLY executable Python code."""

        try:
            spawn_code = self.generate_code(spawn_prompt)
            execution_result = self.execute_code(spawn_code)

            if execution_result["success"]:
                try:
                    result_data = json.loads(execution_result["stdout"])
                    self.logger.info(
                        f"Agent {self.agent_id} employee {employee.agent_id} "
                        "completed successfully"
                    )
                    return {
                        "success": True,
                        "employee": employee,
                        "result": result_data,
                        "spawn_code": spawn_code,
                    }
                except json.JSONDecodeError:
                    self.logger.warning(
                        f"Agent {self.agent_id} employee {employee.agent_id} "
                        "returned non-JSON output"
                    )
                    return {
                        "success": True,
                        "employee": employee,
                        "result": {"output": execution_result["stdout"]},
                        "spawn_code": spawn_code,
                    }
            else:
                error_msg = (
                    f"Employee execution failed: {execution_result['stderr']} - "
                    "Check employee task complexity and system state"
                )
                self.logger.error(
                    f"Agent {self.agent_id} employee {employee.agent_id} "
                    f"failed: {error_msg}"
                )
                return {
                    "success": False,
                    "employee": employee,
                    "error": error_msg,
                    "spawn_code": spawn_code,
                }
        except Exception as e:
            error_msg = (
                f"Employee creation failed: {str(e)} - Verify system "
                "resources and agent configuration"
            )
            self.logger.error(
                f"Agent {self.agent_id} employee creation error: {error_msg}"
            )
            return {
                "success": False,
                "employee": employee,
                "error": error_msg,
                "spawn_code": None,
            }
        finally:
            hierarchy = self._get_hierarchy_path()
            self.logger.info(
                f"Agent {self.agent_id} completed employee spawn attempt "
                f"(hierarchy: {hierarchy})"
            )

    def explain_code(self, code: str) -> str:
        """Explain what the given code does."""
        self.logger.info(f"Agent {self.agent_id} explaining code")

        explain_prompt = f"""Explain what this code does in clear, simple terms:

```python
{code}
```

Provide a concise explanation of:
1. What the code does
2. How it works
3. Key algorithms or techniques used

Return ONLY the explanation text, no markdown formatting."""

        try:
            explanation = self.llm_provider.generate(explain_prompt)
            self.logger.info(f"Agent {self.agent_id} generated code explanation")
            return explanation.strip()
        except Exception as e:
            error_msg = f"Failed to explain code: {str(e)}"
            self.logger.error(f"Agent {self.agent_id} {error_msg}")
            return error_msg

    def complete_task(self, task: str) -> Dict[str, Any]:
        """Complete a task by generating and optionally executing code."""
        self.logger.info(f"Agent {self.agent_id} completing task: {task[:100]}...")

        # Check depth limits
        if self.depth > self.max_depth:
            error_msg = f"{self.depth} exceeds max depth {self.max_depth}"
            self.logger.error(f"Agent {self.agent_id} {error_msg}")
            raise RecursionLimitError(error_msg)

        try:
            # Generate code for the task
            code = self.generate_code(task)

            result = {
                "success": True,
                "task": task,
                "generated_code": code,
                "agent": self.agent_id,
                "hierarchy": self._get_hierarchy_path(),
            }

            # Try to execute if it's a simple task
            if len(code.split("\n")) < 50:  # Only execute smaller code blocks
                try:
                    execution = self.execute_code(code)
                    result["execution"] = execution
                    if execution["success"] and execution["stdout"]:
                        result["output"] = execution["stdout"]
                except Exception as exec_e:
                    self.logger.warning(
                        f"Agent {self.agent_id} execution failed: {exec_e}"
                    )
                    result["execution_error"] = str(exec_e)

            self.logger.info(f"Agent {self.agent_id} task completed successfully")
            return result

        except Exception as e:
            error_msg = f"Task completion failed: {str(e)}"
            self.logger.error(f"Agent {self.agent_id} {error_msg}")
            return {
                "success": False,
                "task": task,
                "error": error_msg,
                "agent": self.agent_id,
                "hierarchy": self._get_hierarchy_path(),
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get agent performance statistics."""
        runtime = time.time() - self.start_time
        return {
            "agent_id": self.agent_id,
            "hierarchy": self._get_hierarchy_path(),
            "depth": self.depth,
            "runtime_seconds": round(runtime, 2),
            "code_generations": self.code_generations,
            "total_employees": len(self.employees),
            "provider": self.llm_provider.name,
            "safe_mode": self.safe_mode,
        }
