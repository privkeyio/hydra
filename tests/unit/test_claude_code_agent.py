import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hydra.agents.claude_code_agent import ClaudeCodeAgent, TaskType, ProgressEvent
from hydra.exceptions import ValidationError


class TestClaudeCodeAgent(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        
        # Create test project structure
        (self.project_root / "src").mkdir()
        (self.project_root / "tests").mkdir()
        (self.project_root / "src" / "main.py").write_text("print('hello')")
        (self.project_root / "README.md").write_text("# Test Project")
        
        self.agent = ClaudeCodeAgent(
            name="test_agent",
            project_root=str(self.project_root)
        )
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_initialization(self):
        """Test agent initialization."""
        self.assertTrue(self.agent.agent_id.startswith("test_agent_"))
        self.assertEqual(self.agent.project_root, self.project_root)
        self.assertGreater(len(self.agent.session.known_files), 0)
        self.assertIn("src/main.py", self.agent.session.known_files)
        self.assertIn("README.md", self.agent.session.known_files)
    
    def test_file_operations(self):
        """Test file read/write operations."""
        # Test reading existing file
        success, content = self.agent.read_file("README.md")
        self.assertTrue(success)
        self.assertEqual(content, "# Test Project")
        
        # Test writing new file
        test_content = "def test_function():\n    return 42"
        success, message = self.agent.write_file("src/test.py", test_content)
        self.assertTrue(success)
        
        # Verify file was written
        success, read_content = self.agent.read_file("src/test.py")
        self.assertTrue(success)
        self.assertEqual(read_content, test_content)
        
        # Test editing file
        old_content = "def test_function():"
        new_content = "def updated_function():"
        success, message = self.agent.edit_file("src/test.py", old_content, new_content)
        self.assertTrue(success)
        
        # Verify edit
        success, updated_content = self.agent.read_file("src/test.py")
        self.assertTrue(success)
        self.assertIn("def updated_function():", updated_content)
        
        # Test reading non-existent file
        success, error = self.agent.read_file("nonexistent.py")
        self.assertFalse(success)
        self.assertIn("File not found", error)
    
    def test_command_execution(self):
        """Test shell command execution."""
        # Test successful command
        result = self.agent.execute_command("echo 'hello world'")
        self.assertTrue(result["success"])
        self.assertIn("hello world", result["stdout"])
        
        # Test command with error
        result = self.agent.execute_command("nonexistent_command")
        self.assertFalse(result["success"])
        self.assertGreater(len(result["stderr"]), 0)
        
        # Test command timeout
        result = self.agent.execute_command("sleep 2", timeout=1)
        self.assertFalse(result["success"])
        self.assertIn("timed out", result["stderr"])
    
    def test_progress_tracking(self):
        """Test progress event tracking."""
        initial_count = len(self.agent.progress_events)
        
        self.agent._log_progress("TEST", "Test message", task_id="task123")
        
        self.assertEqual(len(self.agent.progress_events), initial_count + 1)
        
        latest_event = self.agent.progress_events[-1]
        self.assertEqual(latest_event.event_type, "TEST")
        self.assertEqual(latest_event.message, "Test message")
        self.assertEqual(latest_event.task_id, "task123")
    
    def test_memory_tracking(self):
        """Test file operation and decision memory."""
        # Test file operation recording
        self.agent.read_file("README.md")
        
        self.assertGreater(len(self.agent.file_operations), 0)
        latest_op = self.agent.file_operations[-1]
        self.assertEqual(latest_op.action, "read")
        self.assertEqual(latest_op.path, "README.md")
        self.assertTrue(latest_op.success)
        
        # Test decision recording
        self.agent._record_decision(
            context="Test context",
            decision="Test decision",
            reasoning="Test reasoning",
            confidence=0.9
        )
        
        self.assertGreater(len(self.agent.decisions), 0)
        latest_decision = self.agent.decisions[-1]
        self.assertEqual(latest_decision.decision, "Test decision")
        self.assertEqual(latest_decision.confidence, 0.9)
    
    def test_context_building(self):
        """Test context prompt building."""
        # Add some operations and decisions
        self.agent.read_file("README.md")
        self.agent._record_decision("ctx", "dec", "reason", 0.8)
        
        context = self.agent._build_context_prompt()
        
        self.assertIn(str(self.project_root), context)
        self.assertIn("Recent file operations:", context)
        self.assertIn("Recent decisions:", context)
        self.assertGreater(len(context), 0)
    
    @patch('hydra.agents.claude_code_agent.CodeAgent')
    def test_task_analysis(self, mock_code_agent):
        """Test task analysis functionality."""
        mock_agent_instance = Mock()
        mock_agent_instance.reason.return_value = {
            "task_type": "code_generation",
            "complexity": "moderate",
            "required_files": ["src/new_module.py"],
            "dependencies": ["existing_module"],
            "estimated_time_minutes": 15,
            "risks": [],
            "approach": "Create new module with required functionality"
        }
        mock_code_agent.return_value = mock_agent_instance
        
        result = self.agent.analyze_task("Create a new Python module")
        
        self.assertEqual(result["task_type"], "code_generation")
        self.assertEqual(result["complexity"], "moderate")
        self.assertIn("src/new_module.py", result["required_files"])
        
        # Verify decision was recorded
        self.assertGreater(len(self.agent.decisions), 0)
    
    @patch('hydra.agents.claude_code_agent.CodeAgent')
    def test_long_running_task_execution(self, mock_code_agent):
        """Test long-running task execution with progress tracking."""
        mock_agent_instance = Mock()
        mock_agent_instance.reason.return_value = {
            "task_type": "code_generation",
            "complexity": "simple",
            "approach": "Generate simple function"
        }
        mock_agent_instance.complete_task.return_value = {
            "success": True,
            "generated_code": "def hello(): return 'world'"
        }
        mock_code_agent.return_value = mock_agent_instance
        
        result = self.agent.execute_long_running_task("Create hello function")
        
        self.assertTrue(result["success"])
        self.assertIn("task_id", result)
        self.assertIn("analysis", result)
        self.assertIn("result", result)
        self.assertGreater(result["execution_time"], 0)
        
        # Verify task tracking
        task_id = result["task_id"]
        self.assertIn(task_id, self.agent.active_tasks)
        self.assertIn(task_id, self.agent.completed_tasks)
    
    def test_progress_report(self):
        """Test progress report generation."""
        # Perform some operations
        self.agent.read_file("README.md")
        self.agent.write_file("test.txt", "test content")
        
        report = self.agent.get_progress_report()
        
        self.assertIn("agent_id", report)
        self.assertIn("runtime_seconds", report)
        self.assertIn("total_operations", report)
        self.assertIn("successful_operations", report)
        self.assertIn("success_rate", report)
        self.assertIn("recent_events", report)
        
        self.assertGreater(report["total_operations"], 0)
        self.assertGreaterEqual(report["success_rate"], 0.0)
        self.assertLessEqual(report["success_rate"], 1.0)
    
    def test_context_maintenance(self):
        """Test context maintenance across interactions."""
        interaction1 = "First interaction"
        context1 = self.agent.maintain_context_across_interactions(interaction1)
        
        interaction2 = "Second interaction"
        context2 = self.agent.maintain_context_across_interactions(interaction2)
        
        self.assertEqual(len(self.agent.conversation_history), 2)
        self.assertIn(interaction1, str(self.agent.conversation_history))
        self.assertIn(interaction2, str(self.agent.conversation_history))
    
    def test_memory_stats(self):
        """Test memory statistics."""
        # Add some data to memory systems
        self.agent.read_file("README.md")
        self.agent._record_decision("ctx", "dec", "reason", 0.8)
        
        stats = self.agent.get_memory_stats()
        
        expected_keys = [
            "file_operations", "decisions", "progress_events",
            "conversation_history", "cached_files", "known_files", "active_tasks"
        ]
        
        for key in expected_keys:
            self.assertIn(key, stats)
        
        self.assertGreater(stats["file_operations"], 0)
        self.assertGreater(stats["decisions"], 0)
        self.assertGreater(stats["known_files"], 0)
    
    def test_context_cleanup(self):
        """Test context cleanup functionality."""
        # Fill cache with many files to trigger cleanup
        for i in range(60):
            self.agent.session.file_contents_cache[f"file_{i}.py"] = f"content_{i}" * 1000
        
        original_count = len(self.agent.session.file_contents_cache)
        
        self.agent._cleanup_old_context()
        
        # Should have cleaned up some files
        self.assertLess(len(self.agent.session.file_contents_cache), original_count)
    
    def test_file_ignore_patterns(self):
        """Test file ignore patterns."""
        # Create files that should be ignored
        (self.project_root / ".git").mkdir()
        (self.project_root / "__pycache__").mkdir()
        (self.project_root / ".git" / "config").write_text("git config")
        (self.project_root / "__pycache__" / "module.pyc").write_text("compiled")
        
        # Re-scan after creating ignored files
        agent = ClaudeCodeAgent(name="test_ignore", project_root=str(self.project_root))
        
        # Should not include ignored files
        self.assertNotIn(".git/config", agent.session.known_files)
        self.assertNotIn("__pycache__/module.pyc", agent.session.known_files)
    
    def test_error_handling(self):
        """Test error handling in various scenarios."""
        # Test file operation error handling
        success, error = self.agent.write_file("/invalid/path/file.txt", "content")
        self.assertFalse(success)
        self.assertIn("Failed to write", error)
        
        # Test edit operation with non-existent content
        success, error = self.agent.edit_file("README.md", "non-existent", "replacement")
        self.assertFalse(success)
        self.assertIn("Old content not found", error)
        
        # Verify error tracking in operations log
        failed_ops = [op for op in self.agent.file_operations if not op.success]
        self.assertGreater(len(failed_ops), 0)


if __name__ == '__main__':
    unittest.main()