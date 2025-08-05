import unittest
from unittest.mock import patch
from hydra.workflows.engine import create_workflow, execute_workflow, WorkflowState
from hydra.agents.base import CodeAgent


class TestWorkflowEngine(unittest.TestCase):
    
    def test_workflow_compilation(self):
        workflow = create_workflow()
        self.assertIsNotNone(workflow)
        
    def test_state_schema(self):
        state = WorkflowState(
            task="Test task",
            depth=0,
            results={},
            agents=["test_agent"],
            current_agent="test_agent",
            subtasks=[],
            plan=""
        )
        self.assertEqual(state["task"], "Test task")
        self.assertEqual(state["depth"], 0)
        
    @patch.object(CodeAgent, 'reason')
    def test_plan_node_with_subtasks(self, mock_reason):
        mock_reason.return_value = {
            "plan": "Test plan",
            "subtasks": ["subtask1", "subtask2"]
        }
        
        from workflow_engine import plan_node
        
        state = WorkflowState(
            task="Complex task",
            depth=0,
            results={},
            agents=["boss"],
            current_agent="boss",
            subtasks=[],
            plan=""
        )
        
        result = plan_node(state)
        
        self.assertEqual(result["plan"], "Test plan")
        self.assertEqual(len(result["subtasks"]), 2)
        self.assertEqual(result["subtasks"][0], "subtask1")
        
    def test_depth_enforcement(self):
        from workflow_engine import plan_node
        
        state = WorkflowState(
            task="Deep task",
            depth=3,
            results={},
            agents=["deep_agent"],
            current_agent="deep_agent",
            subtasks=[],
            plan=""
        )
        
        result = plan_node(state)
        
        self.assertEqual(len(result["subtasks"]), 0)
        self.assertIn("Depth limit", result["plan"])
        
    @patch.object(CodeAgent, 'reason')
    @patch.object(CodeAgent, 'execute_code')
    def test_mock_subtask_flow(self, mock_execute, mock_reason):
        mock_reason.return_value = {
            "plan": "Decompose into parallel tasks",
            "subtasks": ["Calculate sum", "Calculate product"]
        }
        
        mock_execute.side_effect = [
            {
                "success": True,
                "stdout": str({
                    "agent": "boss_employee_0",
                    "task": "Calculate sum",
                    "plan": "Add numbers",
                    "subtasks": []
                }),
                "stderr": "",
                "returncode": 0
            },
            {
                "success": True,
                "stdout": str({
                    "agent": "boss_employee_1",
                    "task": "Calculate product",
                    "plan": "Multiply numbers",
                    "subtasks": []
                }),
                "stderr": "",
                "returncode": 0
            }
        ]
        
        result = execute_workflow("Process numbers", "boss", 0)
        
        self.assertIn("boss_employee_0", result["results"])
        self.assertIn("boss_employee_1", result["results"])
        self.assertEqual(result["results"]["summary"]["total_agents"], 3)
        self.assertEqual(result["results"]["summary"]["successful"], 2)
        
    def test_conditional_edges(self):
        from workflow_engine import should_spawn
        
        state_with_subtasks = WorkflowState(
            task="",
            depth=0,
            results={},
            agents=[],
            current_agent="",
            subtasks=["task1", "task2"],
            plan=""
        )
        self.assertEqual(should_spawn(state_with_subtasks), "spawn")
        
        state_no_subtasks = WorkflowState(
            task="",
            depth=0,
            results={},
            agents=[],
            current_agent="",
            subtasks=[],
            plan=""
        )
        self.assertEqual(should_spawn(state_no_subtasks), "aggregate")
        
        state_max_depth = WorkflowState(
            task="",
            depth=2,
            results={},
            agents=[],
            current_agent="",
            subtasks=["task1"],
            plan=""
        )
        self.assertEqual(should_spawn(state_max_depth), "aggregate")


if __name__ == "__main__":
    unittest.main()
