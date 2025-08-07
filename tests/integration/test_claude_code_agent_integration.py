import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hydra.agents.claude_code_agent import ClaudeCodeAgent
from hydra.config import get_config


class TestClaudeCodeAgentIntegration(unittest.TestCase):
    """Integration tests for ClaudeCodeAgent with mock Claude CLI."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.project_root = Path(cls.temp_dir)
        
        # Create realistic project structure
        (cls.project_root / "src").mkdir()
        (cls.project_root / "tests").mkdir()
        (cls.project_root / "docs").mkdir()
        
        # Create sample files
        (cls.project_root / "README.md").write_text("""# Test Project
A sample project for testing ClaudeCodeAgent integration.
""")
        
        (cls.project_root / "src" / "__init__.py").write_text("")
        (cls.project_root / "src" / "main.py").write_text("""
def main():
    print("Hello, World!")
    return 0

if __name__ == "__main__":
    main()
""")
        
        (cls.project_root / "src" / "utils.py").write_text("""
def calculate(a, b):
    return a + b

def format_output(value):
    return f"Result: {value}"
""")
        
        (cls.project_root / "tests" / "test_main.py").write_text("""
import unittest
from src.main import main

class TestMain(unittest.TestCase):
    def test_main_returns_zero(self):
        self.assertEqual(main(), 0)
""")
        
        (cls.project_root / "requirements.txt").write_text("""
pytest>=6.0.0
requests>=2.25.0
""")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(cls.temp_dir)
    
    def setUp(self):
        """Set up each test."""
        self.agent = ClaudeCodeAgent(
            name="integration_test_agent",
            project_root=str(self.project_root),
            max_context_size=100000,
            memory_limit=500
        )
    
    def test_project_structure_analysis(self):
        """Test that agent correctly analyzes project structure."""
        # Should discover all files
        expected_files = {
            "README.md",
            "src/__init__.py", 
            "src/main.py",
            "src/utils.py",
            "tests/test_main.py",
            "requirements.txt"
        }
        
        for expected_file in expected_files:
            self.assertIn(expected_file, self.agent.session.known_files)
        
        # Should ignore hidden/cache directories
        (self.project_root / ".git").mkdir()
        (self.project_root / "__pycache__").mkdir()
        
        new_agent = ClaudeCodeAgent(
            name="structure_test",
            project_root=str(self.project_root)
        )
        
        git_files = [f for f in new_agent.session.known_files if ".git" in f]
        cache_files = [f for f in new_agent.session.known_files if "__pycache__" in f]
        
        self.assertEqual(len(git_files), 0)
        self.assertEqual(len(cache_files), 0)
    
    @patch('hydra.agents.claude_code_agent.CodeAgent')
    def test_end_to_end_code_modification(self, mock_code_agent):
        """Test complete workflow of analyzing and modifying code."""
        
        # Mock the analysis response
        mock_analyzer = Mock()
        mock_analyzer.reason.return_value = {
            "task_type": "code_modification",
            "complexity": "moderate", 
            "required_files": ["src/utils.py"],
            "dependencies": [],
            "estimated_time_minutes": 10,
            "risks": [],
            "approach": "Add new function to utils module"
        }
        
        # Mock the executor response
        mock_executor = Mock()
        mock_executor.complete_task.return_value = {
            "success": True,
            "generated_code": """def multiply(a, b):
    return a * b""",
            "task": "Add multiply function"
        }
        
        mock_code_agent.side_effect = [mock_analyzer, mock_executor]
        
        # Execute the task
        task = "Add a multiply function to the utils module"
        result = self.agent.execute_long_running_task(task)
        
        # Verify analysis was performed
        self.assertTrue(result["success"])
        self.assertIn("analysis", result)
        self.assertEqual(result["analysis"]["task_type"], "code_modification")
        
        # Verify task tracking
        self.assertEqual(len(self.agent.completed_tasks), 1)
        self.assertGreater(result["execution_time"], 0)
        
        # Verify progress was logged
        progress_events = [e for e in self.agent.progress_events if "TASK" in e.event_type]
        self.assertGreater(len(progress_events), 0)
    
    def test_file_operations_with_real_filesystem(self):
        """Test file operations against real filesystem."""
        
        # Test creating a new file
        new_file_content = """def new_feature():
    \"\"\"A new feature for testing.\"\"\"
    return "feature implemented"
"""
        
        success, message = self.agent.write_file("src/new_feature.py", new_file_content)
        self.assertTrue(success)
        
        # Verify file was actually created
        new_file_path = self.project_root / "src" / "new_feature.py"
        self.assertTrue(new_file_path.exists())
        self.assertEqual(new_file_path.read_text(), new_file_content)
        
        # Test reading the file back
        success, content = self.agent.read_file("src/new_feature.py")
        self.assertTrue(success)
        self.assertEqual(content, new_file_content)
        
        # Test editing the file
        old_text = 'return "feature implemented"'
        new_text = 'return "enhanced feature implemented"'
        success, message = self.agent.edit_file("src/new_feature.py", old_text, new_text)
        self.assertTrue(success)
        
        # Verify edit was applied
        success, updated_content = self.agent.read_file("src/new_feature.py")
        self.assertTrue(success)
        self.assertIn("enhanced feature implemented", updated_content)
        self.assertNotIn("feature implemented", updated_content.replace("enhanced feature implemented", ""))
        
        # Verify file operation tracking
        file_ops = list(self.agent.file_operations)
        write_ops = [op for op in file_ops if op.action == "write"]
        read_ops = [op for op in file_ops if op.action == "read"]
        edit_ops = [op for op in file_ops if op.action == "edit"]
        
        self.assertGreater(len(write_ops), 0)
        self.assertGreater(len(read_ops), 0)
        self.assertGreater(len(edit_ops), 0)
    
    def test_command_execution_integration(self):
        """Test command execution in real environment."""
        
        # Test Python execution
        python_code = "print('Hello from Python!')"
        result = self.agent.execute_command(f'python3 -c "{python_code}"')
        
        if result["success"]:  # Only test if Python is available
            self.assertIn("Hello from Python!", result["stdout"])
        
        # Test directory listing
        result = self.agent.execute_command("ls -la", working_dir=str(self.project_root))
        self.assertTrue(result["success"])
        self.assertIn("README.md", result["stdout"])
        self.assertIn("src", result["stdout"])
        
        # Test command with error
        result = self.agent.execute_command("this_command_does_not_exist")
        self.assertFalse(result["success"])
        self.assertGreater(len(result["stderr"]), 0)
    
    def test_memory_persistence_across_operations(self):
        """Test that memory is maintained across multiple operations."""
        
        # Perform several operations
        self.agent.read_file("README.md")
        self.agent.read_file("src/main.py")
        self.agent.write_file("temp.txt", "temporary content")
        
        # Record decisions
        self.agent._record_decision("context1", "decision1", "reasoning1", 0.8)
        self.agent._record_decision("context2", "decision2", "reasoning2", 0.9)
        
        # Check memory persistence
        self.assertGreater(len(self.agent.file_operations), 0)
        self.assertGreater(len(self.agent.decisions), 0)
        
        # Verify context building includes history
        context = self.agent._build_context_prompt()
        self.assertIn("Recent file operations:", context)
        self.assertIn("Recent decisions:", context)
        self.assertIn("README.md", context)
        self.assertIn("decision1", context)
    
    @patch('hydra.agents.claude_code_agent.CodeAgent')
    def test_context_aware_task_execution(self, mock_code_agent):
        """Test that context is properly used in task execution."""
        
        # Set up some context
        self.agent.read_file("src/utils.py")
        self.agent._record_decision(
            "Previous analysis",
            "Use existing utils module",
            "Module already has calculation functions",
            0.9
        )
        
        # Mock agent responses
        mock_analyzer = Mock()
        mock_analyzer.reason.return_value = {
            "task_type": "enhancement",
            "complexity": "simple",
            "approach": "Extend existing functionality"
        }
        
        mock_executor = Mock()
        mock_executor.complete_task.return_value = {
            "success": True,
            "result": "Enhanced utils module"
        }
        
        mock_code_agent.side_effect = [mock_analyzer, mock_executor]
        
        # Execute task
        task = "Improve the utils module with better error handling"
        result = self.agent.execute_long_running_task(task)
        
        # Verify context was used
        self.assertTrue(result["success"])
        
        # Check that the prompts included context
        call_args = mock_analyzer.reason.call_args
        prompt = call_args[0][0]  # First positional argument
        
        self.assertIn("Context:", prompt)
        self.assertIn("src/utils.py", prompt)
        self.assertIn("Recent decisions:", prompt)
        self.assertIn("Use existing utils module", prompt)
    
    def test_progress_tracking_integration(self):
        """Test comprehensive progress tracking."""
        
        initial_event_count = len(self.agent.progress_events)
        
        # Perform various operations
        self.agent.read_file("README.md")
        self.agent.write_file("progress_test.txt", "test content")
        self.agent.execute_command("echo 'progress test'")
        
        # Check progress events were recorded
        final_event_count = len(self.agent.progress_events)
        self.assertGreater(final_event_count, initial_event_count)
        
        # Get progress report
        report = self.agent.get_progress_report()
        
        # Verify report completeness
        required_fields = [
            "agent_id", "runtime_seconds", "total_operations",
            "successful_operations", "success_rate", "recent_events"
        ]
        
        for field in required_fields:
            self.assertIn(field, report)
        
        self.assertGreater(report["total_operations"], 0)
        self.assertGreater(len(report["recent_events"]), 0)
        
        # Verify recent events include our operations
        event_types = [event["type"] for event in report["recent_events"]]
        self.assertIn("FILE_READ", event_types)
        self.assertIn("FILE_WRITE", event_types)
    
    def test_memory_limits_and_cleanup(self):
        """Test memory management and cleanup functionality."""
        
        # Create agent with very low memory limits
        limited_agent = ClaudeCodeAgent(
            name="memory_test_agent",
            project_root=str(self.project_root),
            memory_limit=10
        )
        
        # Fill up memory beyond limit
        for i in range(20):
            limited_agent._record_decision(f"context_{i}", f"decision_{i}", f"reason_{i}", 0.5)
            limited_agent._log_progress("TEST", f"Event {i}")
        
        # Check that memory limits are respected
        self.assertLessEqual(len(limited_agent.decisions), 10)
        self.assertLessEqual(len(limited_agent.progress_events), 10)
        
        # Test context cleanup
        for i in range(60):
            limited_agent.session.file_contents_cache[f"file_{i}.py"] = "x" * 1000
        
        original_cache_size = len(limited_agent.session.file_contents_cache)
        limited_agent._cleanup_old_context()
        new_cache_size = len(limited_agent.session.file_contents_cache)
        
        self.assertLess(new_cache_size, original_cache_size)
    
    def test_error_recovery_and_tracking(self):
        """Test error handling and recovery mechanisms."""
        
        # Test file operation errors
        success, error = self.agent.write_file("/invalid/readonly/path.txt", "content")
        self.assertFalse(success)
        
        # Test command execution errors
        result = self.agent.execute_command("exit 1")  # Command that fails
        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], 1)
        
        # Verify errors are tracked
        failed_ops = [op for op in self.agent.file_operations if not op.success]
        self.assertGreater(len(failed_ops), 0)
        
        # Verify progress report shows failures
        report = self.agent.get_progress_report()
        self.assertLess(report["success_rate"], 1.0)
    
    def test_concurrent_task_handling(self):
        """Test handling of multiple concurrent task scenarios."""
        
        # Start multiple tasks (simulated)
        task_ids = []
        
        with patch('hydra.agents.claude_code_agent.CodeAgent') as mock_code_agent:
            mock_analyzer = Mock()
            mock_analyzer.reason.return_value = {"task_type": "test", "complexity": "simple", "approach": "test"}
            
            mock_executor = Mock() 
            mock_executor.complete_task.return_value = {"success": True, "result": "completed"}
            
            mock_code_agent.side_effect = lambda *args, **kwargs: mock_analyzer if "analyzer" in args[0] else mock_executor
            
            # Execute multiple tasks
            for i in range(3):
                result = self.agent.execute_long_running_task(f"Task {i}")
                self.assertTrue(result["success"])
                task_ids.append(result["task_id"])
        
        # Verify all tasks were tracked
        self.assertEqual(len(task_ids), 3)
        self.assertEqual(len(self.agent.completed_tasks), 3)
        
        # Verify task isolation
        for task_id in task_ids:
            self.assertIn(task_id, self.agent.active_tasks)
            self.assertIn(task_id, self.agent.completed_tasks)


if __name__ == '__main__':
    unittest.main()