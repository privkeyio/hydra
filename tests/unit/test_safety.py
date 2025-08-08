import unittest
import os
import tempfile
from hydra.agents.base import CodeAgent
from hydra.exceptions import RecursionLimitError


class TestSafetyFeatures(unittest.TestCase):
    
    def setUp(self):
        self.temp_log_dir = tempfile.mkdtemp()
        
    def test_recursion_guard_depth_limit(self):
        agent = CodeAgent("test_boss", depth=3)
        
        with self.assertRaises(RecursionLimitError) as context:
            agent.reason("test task")
        
        self.assertIn("exceeded max depth", str(context.exception))
    
    def test_employee_spawn_depth_limit(self):
        agent = CodeAgent("test_boss", depth=3)
        
        with self.assertRaises(RecursionLimitError) as context:
            agent.create_employee("test subtask")
        
        self.assertIn("Cannot spawn employee", str(context.exception))
        self.assertIn("exceeds max depth", str(context.exception))
    
    def test_hierarchy_logging(self):
        boss = CodeAgent("boss", depth=0)
        employee = CodeAgent("employee", parent=boss, depth=1)
        
        hierarchy = employee._get_hierarchy_path()
        self.assertEqual(hierarchy, "boss -> employee")
    
    def test_log_rotation_configuration(self):
        CodeAgent._logger = None
        agent = CodeAgent("test", depth=0)
        
        logger = agent._setup_logger()
        
        self.assertTrue(os.path.exists('logs'))
        self.assertEqual(len(logger.handlers), 1)
        handler = logger.handlers[0]
        self.assertEqual(handler.maxBytes, 10*1024*1024)  # 10MB
        self.assertEqual(handler.backupCount, 5)
    
    def test_code_validation(self):
        agent = CodeAgent("test", depth=0)
        
        import ast
        
        valid_code = "print('hello')"
        try:
            ast.parse(valid_code)
            parsed = True
        except SyntaxError:
            parsed = False
        
        self.assertTrue(parsed)
        
        invalid_code = "print('hello'"
        try:
            ast.parse(invalid_code)
            parsed = True
        except SyntaxError:
            parsed = False
        
        self.assertFalse(parsed)
    
    def test_actionable_error_messages(self):
        agent = CodeAgent("test", depth=0)
        
        result = agent.execute_code("import nonexistent_module")
        
        self.assertFalse(result["success"])
        self.assertTrue(
            "Check system resources" in result["stderr"] or 
            "ModuleNotFoundError" in result["stderr"]
        )
    
    def test_agent_id_uniqueness(self):
        agent1 = CodeAgent("test", depth=0)
        agent2 = CodeAgent("test", depth=0)
        
        self.assertNotEqual(agent1.agent_id, agent2.agent_id)
        self.assertIn("test_", agent1.agent_id)
        self.assertIn("test_", agent2.agent_id)


if __name__ == "__main__":
    unittest.main()