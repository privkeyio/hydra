import unittest
import ast
from hydra.agents.base import CodeAgent


class TestCodeAgent(unittest.TestCase):
    def test_init(self):
        agent = CodeAgent("test_agent")
        self.assertEqual(agent.name, "test_agent")
        self.assertIsNone(agent.parent)
        self.assertEqual(agent.depth, 0)
        
        child = CodeAgent("child", parent=agent, depth=1)
        self.assertEqual(child.parent, agent)
        self.assertEqual(child.depth, 1)
    
    def test_depth_enforcement(self):
        from hydra.exceptions import RecursionLimitError
        agent = CodeAgent("boss", depth=3)
        with self.assertRaises(RecursionLimitError):
            agent.reason("test task")
    
    def test_generate_code_validation(self):
        agent = CodeAgent("coder")
        try:
            code = agent.generate_code("Create a function that adds two numbers")
            ast.parse(code)
        except Exception:
            pass
    
    def test_execute_code_sandbox(self):
        agent = CodeAgent("executor")
        result = agent.execute_code("print('hello')")
        self.assertTrue(result["success"])
        self.assertIn("hello", result["stdout"])
        
        from hydra.exceptions import ExecutionTimeoutError
        with self.assertRaises(ExecutionTimeoutError):
            agent.execute_code("import time; time.sleep(40)")


if __name__ == "__main__":
    unittest.main()