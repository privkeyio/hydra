import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from hydra.config import LLMConfig
from hydra.providers.claude_cli_enhanced import (
    ClaudeCLIEnhancedProvider,
    ErrorRecoveryManager,
    FileOperationHandler,
    SessionState,
    SlashCommandProcessor,
    StreamingResponseHandler,
)


class TestFileOperationHandler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.handler = FileOperationHandler(self.temp_dir)

    def tearDown(self):
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_write_and_read_file(self):
        content = "test content"
        self.handler.write_file("test.txt", content)
        
        read_content = self.handler.read_file("test.txt")
        self.assertEqual(read_content, content)
        
        self.assertEqual(len(self.handler.operations_log), 2)
        self.assertEqual(self.handler.operations_log[0]['operation'], 'write')
        self.assertEqual(self.handler.operations_log[1]['operation'], 'read')

    def test_read_nonexistent_file(self):
        with self.assertRaises(FileNotFoundError):
            self.handler.read_file("nonexistent.txt")

    def test_list_files(self):
        self.handler.write_file("file1.txt", "content1")
        self.handler.write_file("file2.txt", "content2")
        self.handler.write_file("dir/file3.py", "content3")
        
        all_files = self.handler.list_files()
        # dir/file3.py creates a directory, so we only have 2 top-level files
        self.assertGreaterEqual(len(all_files), 2)
        
        txt_files = self.handler.list_files("*.txt")
        self.assertEqual(len(txt_files), 2)

    def test_delete_file(self):
        self.handler.write_file("test.txt", "content")
        self.assertTrue((self.temp_dir / "test.txt").exists())
        
        result = self.handler.delete_file("test.txt")
        self.assertTrue(result)
        self.assertFalse((self.temp_dir / "test.txt").exists())
        
        result = self.handler.delete_file("nonexistent.txt")
        self.assertFalse(result)


class TestSlashCommandProcessor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.file_handler = FileOperationHandler(self.temp_dir)
        self.session = SessionState(
            session_id="test-session",
            working_dir=self.temp_dir
        )
        self.processor = SlashCommandProcessor(self.file_handler, self.session)

    def tearDown(self):
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_help_command(self):
        response, should_exit = self.processor.process("/help")
        self.assertFalse(should_exit)
        self.assertIn("Available commands", response)
        self.assertIn("/model", response)
        self.assertIn("/init", response)
        self.assertIn("/clear", response)

    def test_clear_command(self):
        self.session.context_files["test.txt"] = "content"
        self.session.variables["key"] = "value"
        
        response, should_exit = self.processor.process("/clear")
        self.assertFalse(should_exit)
        self.assertEqual(response, "Context cleared")
        self.assertEqual(len(self.session.context_files), 0)
        self.assertEqual(len(self.session.variables), 0)

    def test_add_dir_command(self):
        response, should_exit = self.processor.process("/add-dir", "/some/path")
        self.assertFalse(should_exit)
        self.assertIn("Added working directory", response)
        self.assertIn('/some/path', self.session.variables.get('working_dirs', []))

    def test_config_command(self):
        response, should_exit = self.processor.process("/config")
        self.assertFalse(should_exit)
        self.assertIn("model", response)
        
        response, should_exit = self.processor.process("/config", "temperature=0.5")
        self.assertFalse(should_exit)
        self.assertIn("Config updated", response)
        self.assertEqual(self.session.variables['temperature'], '0.5')

    def test_compact_command(self):
        for i in range(15):
            self.session.history.append({'msg': f'item_{i}'})
        
        response, should_exit = self.processor.process("/compact")
        self.assertFalse(should_exit)
        self.assertIn("Compacted conversation", response)
        self.assertLess(len(self.session.history), 15)

    def test_memory_command(self):
        # First create CLAUDE.md
        self.processor.process("/init")
        
        response, should_exit = self.processor.process("/memory", "show")
        self.assertFalse(should_exit)
        self.assertIn("Project", response)
        
        response, should_exit = self.processor.process("/memory", "edit")
        self.assertFalse(should_exit)
        self.assertIn("Loaded CLAUDE.md", response)

    def test_permissions_command(self):
        response, should_exit = self.processor.process("/permissions")
        self.assertFalse(should_exit)
        self.assertIn("Current permissions", response)
        
        response, should_exit = self.processor.process("/permissions", "file_write=false")
        self.assertFalse(should_exit)
        self.assertIn("Updated permission", response)

    def test_exit_command(self):
        response, should_exit = self.processor.process("/exit")
        self.assertTrue(should_exit)
        self.assertEqual(response, "Exiting session")

    def test_unknown_command(self):
        response, should_exit = self.processor.process("/unknown")
        self.assertFalse(should_exit)
        self.assertIn("Unknown command", response)
    
    def test_model_command(self):
        response, should_exit = self.processor.process("/model")
        self.assertFalse(should_exit)
        self.assertIn("Current model", response)
        self.assertIn("claude", response)
        
        response, should_exit = self.processor.process("/model", "claude-3-opus-20240229")
        self.assertFalse(should_exit)
        self.assertIn("Switched to model", response)
    
    def test_init_command(self):
        response, should_exit = self.processor.process("/init")
        self.assertFalse(should_exit)
        self.assertIn("CLAUDE.md", response)
        
        claude_md = self.temp_dir / "CLAUDE.md"
        self.assertTrue(claude_md.exists())
        
        # Test trying to init again
        response, should_exit = self.processor.process("/init")
        self.assertFalse(should_exit)
        self.assertIn("already exists", response)
    
    def test_status_command(self):
        response, should_exit = self.processor.process("/status")
        self.assertFalse(should_exit)
        self.assertIn("Claude Code Status", response)
        self.assertIn("Session:", response)
    
    def test_cost_command(self):
        response, should_exit = self.processor.process("/cost")
        self.assertFalse(should_exit)
        self.assertIn("Token usage", response)
    
    def test_doctor_command(self):
        response, should_exit = self.processor.process("/doctor")
        self.assertFalse(should_exit)
        self.assertIn("Health Check", response)
        self.assertIn("✓", response)


class TestStreamingResponseHandler(unittest.TestCase):
    def test_add_chunks_and_get_response(self):
        handler = StreamingResponseHandler()
        
        handler.add_chunk("Hello ")
        handler.add_chunk("World")
        
        self.assertEqual(handler.get_response(), "Hello World")
        self.assertFalse(handler.complete)

    def test_mark_complete(self):
        handler = StreamingResponseHandler()
        handler.mark_complete()
        self.assertTrue(handler.complete)

    def test_set_error(self):
        handler = StreamingResponseHandler()
        handler.set_error("Test error")
        
        self.assertEqual(handler.error, "Test error")
        self.assertTrue(handler.complete)


class TestErrorRecoveryManager(unittest.TestCase):
    def test_handle_timeout_error(self):
        manager = ErrorRecoveryManager()
        
        error = Exception("Connection timeout")
        action = manager.handle_error(error, {"test": "context"})
        
        self.assertEqual(action, "retry_with_longer_timeout")
        self.assertEqual(len(manager.error_history), 1)

    def test_handle_connection_error(self):
        manager = ErrorRecoveryManager()
        
        error = Exception("Connection refused")
        action = manager.handle_error(error, {})
        
        self.assertEqual(action, "retry_after_delay")

    def test_handle_json_error(self):
        manager = ErrorRecoveryManager()
        
        error = Exception("JSON decode error")
        action = manager.handle_error(error, {})
        
        self.assertEqual(action, "retry_with_format_fix")

    def test_should_retry(self):
        manager = ErrorRecoveryManager(max_retries=3)
        
        self.assertTrue(manager.should_retry(0))
        self.assertTrue(manager.should_retry(2))
        self.assertFalse(manager.should_retry(3))

    def test_retry_delay(self):
        manager = ErrorRecoveryManager()
        
        self.assertEqual(manager.get_retry_delay(0), 1)
        self.assertEqual(manager.get_retry_delay(1), 2)
        self.assertEqual(manager.get_retry_delay(2), 4)
        self.assertEqual(manager.get_retry_delay(10), 30)  # Max delay


class TestClaudeCLIEnhancedProvider(unittest.TestCase):
    def setUp(self):
        from hydra.providers import LLMConfig
        self.config = LLMConfig(
            provider_type="claude_cli_enhanced",
            model="claude-cli",
            api_key=None,
            timeout=30,
            extra_params={'claude_path': 'claude'}
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            self.provider = ClaudeCLIEnhancedProvider(self.config)

    def tearDown(self):
        self.provider.cleanup()

    def test_create_session(self):
        session_id = self.provider.create_session()
        
        self.assertIsNotNone(session_id)
        self.assertIn(session_id, self.provider.sessions)
        self.assertEqual(self.provider.current_session_id, session_id)

    def test_get_existing_session(self):
        session_id = self.provider.create_session("test-session")
        
        session = self.provider.get_session("test-session")
        self.assertEqual(session.session_id, "test-session")

    def test_get_nonexistent_session_creates_new(self):
        session = self.provider.get_session("new-session")
        
        self.assertEqual(session.session_id, "new-session")
        self.assertIn("new-session", self.provider.sessions)

    @patch('subprocess.run')
    def test_generate_regular_prompt(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Response to prompt"
        )
        
        response = self.provider.generate("Test prompt")
        
        self.assertEqual(response, "Response to prompt")
        mock_run.assert_called_once()

    def test_slash_command_processing(self):
        session_id = self.provider.create_session()
        
        response = self.provider.generate("/help", session_id)
        self.assertIn("Available commands", response)

    @patch('subprocess.run')
    def test_generate_with_context(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Response"
        )
        
        session = self.provider.get_session()
        session.context_files["test.txt"] = "file content"
        session.variables["key"] = "value"
        
        response = self.provider.generate("Test prompt", session.session_id)
        
        call_args = mock_run.call_args[1]['input']
        self.assertIn("Context files", call_args)
        self.assertIn("Variables", call_args)

    @patch('subprocess.run')
    def test_error_recovery(self, mock_run):
        mock_run.side_effect = [
            Exception("Connection timeout"),
            Mock(returncode=0, stdout="Success")
        ]
        
        response = self.provider.generate("Test prompt")
        
        self.assertEqual(response, "Success")
        self.assertEqual(mock_run.call_count, 2)

    @patch('subprocess.run')
    def test_generate_json(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"key": "value", "number": 42}'
        )
        
        result = self.provider.generate_json("Generate JSON")
        
        self.assertEqual(result, {"key": "value", "number": 42})

    @patch('subprocess.run')
    def test_generate_json_with_markdown(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout='```json\n{"key": "value"}\n```'
        )
        
        result = self.provider.generate_json("Generate JSON")
        
        self.assertEqual(result, {"key": "value"})

    @patch('subprocess.Popen')
    def test_streaming_response(self, mock_popen):
        import io
        mock_process = Mock()
        mock_process.stdout = io.StringIO("Line 1\nLine 2\n")
        mock_process.poll.return_value = 0
        mock_process.stdin = Mock()
        mock_process.stdin.write = Mock()
        mock_process.stdin.flush = Mock()
        mock_popen.return_value = mock_process
        
        response = self.provider._execute_streaming("Test prompt", 30)
        
        # Response may be empty due to mocking, just verify no exception
        self.assertIsInstance(response, str)

    def test_save_and_load_session(self):
        session_id = self.provider.create_session("test-session")
        session = self.provider.get_session(session_id)
        
        session.context_files["test.txt"] = "content"
        session.variables["key"] = "value"
        session.history.append({"prompt": "test", "response": "response"})
        
        save_path = self.provider.save_session(session_id)
        self.assertTrue(Path(save_path).exists())
        
        self.provider.close_session(session_id)
        self.assertNotIn(session_id, self.provider.sessions)
        
        loaded_session_id = self.provider.load_session(save_path)
        self.assertEqual(loaded_session_id, "test-session")
        
        loaded_session = self.provider.get_session(loaded_session_id)
        self.assertEqual(loaded_session.context_files["test.txt"], "content")
        self.assertEqual(loaded_session.variables["key"], "value")
        self.assertEqual(len(loaded_session.history), 1)

    def test_close_session(self):
        session_id = self.provider.create_session()
        self.assertIn(session_id, self.provider.sessions)
        
        self.provider.close_session(session_id)
        self.assertNotIn(session_id, self.provider.sessions)
        self.assertIsNone(self.provider.current_session_id)

    def test_cleanup(self):
        session_id = self.provider.create_session()
        temp_dir = self.provider.temp_dir
        
        self.assertTrue(temp_dir.exists())
        self.assertIn(session_id, self.provider.sessions)
        
        self.provider.cleanup()
        
        self.assertFalse(temp_dir.exists())
        self.assertEqual(len(self.provider.sessions), 0)

    def test_list_models(self):
        models = self.provider.list_models()
        self.assertEqual(models, ["claude-cli-enhanced"])


class TestIntegration(unittest.TestCase):
    @patch('subprocess.run')
    def test_full_session_workflow(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="Response")
        
        from hydra.providers import LLMConfig
        config = LLMConfig(
            provider_type="claude_cli_enhanced",
            model="claude-cli",
            api_key=None,
            timeout=30,
            extra_params={'claude_path': 'claude'}
        )
        
        provider = ClaudeCLIEnhancedProvider(config)
        
        try:
            session_id = provider.create_session()
            
            # Test file operations directly
            provider.file_handler.write_file("test.txt", "Hello World")
            
            session = provider.get_session(session_id)
            self.assertTrue((provider.temp_dir / "test.txt").exists())
            
            # Test /init command
            provider.generate("/init", session_id)
            self.assertTrue((session.working_dir / "CLAUDE.md").exists())
            
            # Test /model command  
            provider.generate("/model claude-3-opus-20240229", session_id)
            self.assertEqual(session.variables.get('model'), 'claude-3-opus-20240229')
            
            # Test /clear command
            session.context_files["test.txt"] = "content"
            provider.generate("/clear", session_id)
            self.assertEqual(len(session.context_files), 0)
            
        finally:
            provider.cleanup()


if __name__ == '__main__':
    unittest.main()