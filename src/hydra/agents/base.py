import ast
import subprocess
import json
import logging
import os
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
from hydra.config import USE_VENICE, USE_CLAUDE_CLI, anthropic_client, generate_code_with_claude_cli


class CodeAgent:
    _logger = None

    @classmethod
    def _setup_logger(cls):
        if cls._logger is None:
            cls._logger = logging.getLogger('hydra_agent')
            cls._logger.setLevel(logging.INFO)

            if not cls._logger.handlers:
                os.makedirs('logs', exist_ok=True)
                handler = RotatingFileHandler(
                    'logs/agent_activity.log',
                    maxBytes=10*1024*1024,
                    backupCount=5
                )
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                handler.setFormatter(formatter)
                cls._logger.addHandler(handler)
        return cls._logger

    def __init__(self, name: str, parent: Optional['CodeAgent'] = None,
                 depth: int = 0):
        self.name = name
        self.parent = parent
        self.depth = depth
        self.max_depth = 2
        self.employees = []
        self.agent_id = f"{name}_{id(self)}"
        self.logger = self._setup_logger()

        hierarchy = self._get_hierarchy_path()
        self.logger.info(
            f"Agent created: {self.agent_id} at depth {depth}, "
            f"hierarchy: {hierarchy}"
        )

    def _get_hierarchy_path(self) -> str:
        if self.parent is None:
            return self.name
        return f"{self.parent._get_hierarchy_path()} -> {self.name}"
    
    def reason(self, task: str) -> Dict[str, Any]:
        if self.depth > self.max_depth:
            error_msg = (
                f"RecursionError: Agent {self.agent_id} exceeded "
                f"max depth {self.max_depth} (current: {self.depth})"
            )
            self.logger.error(error_msg)
            raise RecursionError(error_msg)

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

        if USE_CLAUDE_CLI:
            response = generate_code_with_claude_cli(prompt)
        elif USE_VENICE:
            from hydra.utils.venice import venice_call
            response = venice_call(prompt)
        else:
            response = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            response = response.content[0].text

        try:
            result = json.loads(response)
            subtask_count = len(result.get('subtasks', []))
            self.logger.info(
                f"Agent {self.agent_id} generated plan with "
                f"{subtask_count} subtasks"
            )
            return result
        except json.JSONDecodeError as e:
            self.logger.warning(
                f"Agent {self.agent_id} failed to parse JSON response: {e}"
            )
            return {"plan": response, "subtasks": []}

    def generate_code(self, prompt: str, retry_count: int = 0) -> str:
        max_retries = 2
        self.logger.info(
            f"Agent {self.agent_id} generating code "
            f"(attempt {retry_count + 1}/{max_retries})"
        )
        code_prompt = f"""Generate Python code for this task:
{prompt}

Return ONLY executable Python code. No explanations or markdown."""

        if USE_CLAUDE_CLI:
            code = generate_code_with_claude_cli(code_prompt)
        elif USE_VENICE:
            from hydra.utils.venice import venice_call
            code = venice_call(code_prompt)
        else:
            response = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{"role": "user", "content": code_prompt}]
            )
            code = response.content[0].text

        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        try:
            ast.parse(code)
            self.logger.info(
                f"Agent {self.agent_id} generated valid code "
                f"({len(code)} chars)"
            )
        except SyntaxError as e:
            error_msg = f"Generated invalid Python code: {e}"
            self.logger.error(
                f"Agent {self.agent_id} syntax error: {error_msg}"
            )

            if retry_count < max_retries - 1:
                self.logger.info(
                    f"Agent {self.agent_id} retrying code generation"
                )
                return self.generate_code(prompt, retry_count + 1)

            raise ValueError(error_msg)

        return code

    def execute_code(self, code_str: str, retry_count: int = 0) -> Dict[str, Any]:
        max_retries = 2
        self.logger.info(
            f"Agent {self.agent_id} executing code "
            f"(attempt {retry_count + 1}/{max_retries})"
        )

        try:
            result = subprocess.run(
                ["python", "-c", code_str],
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            execution_result = {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }

            if execution_result["success"]:
                self.logger.info(
                    f"Agent {self.agent_id} code execution successful"
                )
            else:
                error_msg = (
                    f"Code execution failed with return code "
                    f"{result.returncode}: {result.stderr}"
                )
                self.logger.error(f"Agent {self.agent_id} {error_msg}")

                if retry_count < max_retries - 1:
                    self.logger.info(
                        f"Agent {self.agent_id} retrying code execution"
                    )
                    return self.execute_code(code_str, retry_count + 1)

            return execution_result

        except subprocess.TimeoutExpired:
            error_msg = (
                "Execution timeout (30s exceeded) - Code may contain "
                "infinite loops or blocking operations"
            )
            self.logger.error(f"Agent {self.agent_id} {error_msg}")
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
                "returncode": -1
            }
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
                "returncode": -1
            }

    def create_employee(self, subtask: str) -> Dict[str, Any]:
        if self.depth > self.max_depth:
            error_msg = (
                f"Cannot spawn employee: Agent {self.agent_id} at depth "
                f"{self.depth} exceeds max depth {self.max_depth}"
            )
            self.logger.error(error_msg)
            raise RecursionError(error_msg)

        hierarchy = self._get_hierarchy_path()
        self.logger.info(
            f"Agent {self.agent_id} spawning employee for subtask: "
            f"{subtask[:100]}... (parent hierarchy: {hierarchy})"
        )

        employee_name = f"{self.name}_employee_{len(self.employees) + 1}"
        employee = CodeAgent(
            employee_name, parent=self, depth=self.depth + 1)
        self.employees.append(employee)

        self.logger.info(
            f"Agent {self.agent_id} created employee {employee.agent_id}"
        )

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
                        "spawn_code": spawn_code
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
                        "spawn_code": spawn_code
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
                    "spawn_code": spawn_code
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
                "spawn_code": None
            }
        finally:
            hierarchy = self._get_hierarchy_path()
            self.logger.info(
                f"Agent {self.agent_id} completed employee spawn attempt "
                f"(hierarchy: {hierarchy})"
            )
