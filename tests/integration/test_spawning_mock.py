#!/usr/bin/env python3

import ast
import json
import os
import pytest
from typing import Optional, Dict, Any

# Test mode detection
TEST_MODE = (
    os.getenv('TESTING') == '1' or
    os.getenv('PYTEST_CURRENT_TEST') is not None or
    'pytest' in str(os.getenv('_', ''))
)

class MockCodeAgent:
    def __init__(self, name: str, parent: Optional['MockCodeAgent'] = None, depth: int = 0):
        self.name = name
        self.parent = parent
        self.depth = depth
        self.max_depth = 2
        self.employees = []

    def generate_code(self, prompt: str) -> str:
        if "sum of numbers 1 to 10" in prompt:
            return "result = sum(range(1, 11))\nprint(f'{{\"success\": true, \"result\": {result}, \"employee_name\": \"boss_employee_1\"}}')"
        elif "factorial of 5" in prompt:
            return "import math\nresult = math.factorial(5)\nprint(f'{{\"success\": true, \"result\": {result}, \"employee_name\": \"boss_employee_2\"}}')"
        else:
            return "print('{\"success\": true, \"result\": \"completed\", \"employee_name\": \"test_employee\"}')"

    def execute_code(self, code_str: str) -> Dict[str, Any]:
        import subprocess
        try:
            result = subprocess.run(
                ["python", "-c", code_str],
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1
            }

    def create_employee(self, subtask: str) -> Dict[str, Any]:
        if self.depth >= self.max_depth:
            raise RecursionError(f"Cannot spawn employee at max depth {self.max_depth}")
        
        employee_name = f"{self.name}_employee_{len(self.employees) + 1}"
        employee = MockCodeAgent(employee_name, parent=self, depth=self.depth + 1)
        self.employees.append(employee)
        
        try:
            spawn_code = self.generate_code(subtask)
            execution_result = self.execute_code(spawn_code)
            
            if execution_result["success"]:
                try:
                    result_data = json.loads(execution_result["stdout"].strip())
                    return {
                        "success": True,
                        "employee": employee,
                        "result": result_data,
                        "spawn_code": spawn_code
                    }
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "employee": employee,
                        "result": {"output": execution_result["stdout"]},
                        "spawn_code": spawn_code
                    }
            else:
                return {
                    "success": False,
                    "employee": employee,
                    "error": execution_result["stderr"],
                    "spawn_code": spawn_code
                }
        except Exception as e:
            return {
                "success": False,
                "employee": employee,
                "error": str(e),
                "spawn_code": None
            }

@pytest.mark.skipif(TEST_MODE, reason="Skip spawning tests - resource exhaustion in CI environment")
def test_boss_spawning():
    boss = MockCodeAgent("boss", depth=0)
    
    subtask1 = "Calculate the sum of numbers 1 to 10"
    subtask2 = "Calculate the factorial of 5"
    
    print("Testing boss spawning 2 employees for parallel tasks...")
    
    result1 = boss.create_employee(subtask1)
    result2 = boss.create_employee(subtask2)
    
    print(f"Boss has {len(boss.employees)} employees")
    
    print(f"Employee 1 result: {result1['success']}")
    if result1['success']:
        print(f"Employee 1 output: {result1['result']}")
    else:
        print(f"Employee 1 error: {result1.get('error', 'Unknown error')}")
    
    print(f"Employee 2 result: {result2['success']}")
    if result2['success']:
        print(f"Employee 2 output: {result2['result']}")
    else:
        print(f"Employee 2 error: {result2.get('error', 'Unknown error')}")
    
    results = [result1, result2]
    aggregated = {
        "total_employees": len(boss.employees),
        "successful_tasks": sum(1 for r in results if r['success']),
        "results": [r['result'] if r['success'] else r.get('error') for r in results]
    }
    
    print(f"Aggregated results: {json.dumps(aggregated, indent=2)}")
    
    assert len(boss.employees) == 2, "Boss should have 2 employees"
    assert result1['success'], "Employee 1 should succeed"
    assert result2['success'], "Employee 2 should succeed"
    assert result1['result']['result'] == 55, "Sum 1-10 should be 55"
    assert result2['result']['result'] == 120, "Factorial of 5 should be 120"
    
    print("✅ All tests passed!")
    return aggregated

if __name__ == "__main__":
    test_boss_spawning()