"""Unit tests for ticket_executor module."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, call

from hydra.tickets.ticket_executor import (
    SharedWorkspace,
    get_shared_workspace,
    execute_single_ticket,
    execute_ticket_worker,
    get_quality_summary,
    _build_claude_prompt,
    _check_created_files,
    _validate_code_changes,
)


class TestSharedWorkspace(unittest.TestCase):
    """Test SharedWorkspace functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.workspace = SharedWorkspace("test-session")
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.workspace.workspace_path):
            shutil.rmtree(self.workspace.workspace_path, ignore_errors=True)
    
    def test_workspace_initialization(self):
        """Test workspace is properly initialized."""
        self.assertTrue(os.path.exists(self.workspace.workspace_path))
        self.assertTrue(os.path.exists(os.path.join(self.workspace.workspace_path, "docs")))
        self.assertTrue(os.path.exists(os.path.join(self.workspace.workspace_path, "configs")))
        self.assertTrue(os.path.exists(os.path.join(self.workspace.workspace_path, "shared_data")))
        self.assertTrue(os.path.exists(os.path.join(self.workspace.workspace_path, "artifacts")))
        self.assertTrue(os.path.exists(os.path.join(self.workspace.workspace_path, "manifests")))
        self.assertEqual(self.workspace.session_id, "test-session")
    
    def test_save_artifact(self):
        """Test saving an artifact."""
        content = "Test artifact content"
        artifact_path = self.workspace.save_artifact("001", "test.txt", content)
        
        self.assertTrue(os.path.exists(artifact_path))
        with open(artifact_path, "r") as f:
            saved_content = f.read()
        self.assertEqual(saved_content, content)
    
    def test_create_manifest(self):
        """Test creating a manifest."""
        files = ["file1.py", "file2.js", "file3.md"]
        manifest_path = self.workspace.create_manifest("001", files)
        
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, "r") as f:
            content = f.read()
        
        for file in files:
            self.assertIn(file, content)
    
    def test_get_dependency_artifacts(self):
        """Test getting dependency artifacts."""
        # Create some artifacts for dependencies
        self.workspace.save_artifact("001", "dep1.txt", "content1")
        self.workspace.save_artifact("002", "dep2.txt", "content2")
        
        # Get artifacts for dependencies
        artifacts = self.workspace.get_dependency_artifacts(["001", "002"])
        
        self.assertEqual(len(artifacts), 2)
        self.assertIn("001", artifacts)
        self.assertIn("002", artifacts)
        self.assertEqual(len(artifacts["001"]), 1)
        self.assertEqual(len(artifacts["002"]), 1)
    
    def test_get_dependency_artifacts_with_numeric_ids(self):
        """Test getting dependency artifacts with numeric IDs."""
        # Create artifacts with numeric IDs
        self.workspace.save_artifact("1", "dep1.txt", "content1")
        self.workspace.save_artifact("2", "dep2.txt", "content2")
        
        # Get artifacts using numeric dependencies
        artifacts = self.workspace.get_dependency_artifacts(["1", "2"])
        
        self.assertEqual(len(artifacts), 2)


class TestTicketExecution(unittest.TestCase):
    """Test ticket execution functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tickets_path = os.path.join(self.temp_dir, "tickets.yaml")
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch("hydra.tickets.ticket_parser.parse_ticket")
    @patch("hydra.tickets.ticket_executor.update_ticket_in_database")
    @patch("hydra.tickets.ticket_executor.mark_ticket_in_progress")
    @patch("hydra.providers.provider_factory.ProviderFactory")
    def test_execute_single_ticket_already_completed(
        self, mock_provider_factory, mock_mark_progress, mock_update_db, mock_parse
    ):
        """Test executing a ticket that's already completed."""
        # Mock a completed ticket
        mock_parse.return_value = {
            "title": "Test Ticket",
            "description": "Test description",
            "status": "DONE",
            "completed": True,
            "model": "balanced",
            "acceptance_criteria": [],
            "dependencies": [],
        }
        
        result = execute_single_ticket(self.tickets_path, "001", skip_preflight=True)
        
        self.assertTrue(result)
        mock_mark_progress.assert_not_called()
        mock_provider_factory.assert_not_called()
    
    @patch("hydra.tickets.ticket_parser.parse_ticket")
    def test_execute_single_ticket_not_found(self, mock_parse):
        """Test executing a ticket that doesn't exist."""
        mock_parse.return_value = None
        
        result = execute_single_ticket(self.tickets_path, "999", skip_preflight=True)
        
        self.assertFalse(result)
    
    @patch("hydra.preflight.preflight_checker.PreflightChecker")
    @patch("hydra.tickets.ticket_parser.parse_ticket")
    def test_execute_single_ticket_preflight_failure(self, mock_parse, mock_preflight):
        """Test ticket execution with preflight failures."""
        # Mock a valid ticket
        mock_parse.return_value = {
            "title": "Test Ticket",
            "status": "TODO",
            "completed": False,
        }
        
        # Mock preflight failure
        mock_checker = MagicMock()
        mock_report = MagicMock()
        mock_report.has_critical_issues.return_value = True
        mock_report.get_critical_issues.return_value = [
            MagicMock(description="Critical issue", message="Test failure", details=[])
        ]
        mock_checker.run_preflight_checks.return_value = mock_report
        mock_preflight.return_value = mock_checker
        
        result = execute_single_ticket(self.tickets_path, "001", skip_preflight=False)
        
        self.assertFalse(result)
        mock_checker.run_preflight_checks.assert_called_once()
    
    def test_build_claude_prompt(self):
        """Test building Claude tmux prompt."""
        prompt = _build_claude_prompt(
            "001",
            "tickets.yaml",
            "Find ticket 001",
            "Update status",
            "/project/dir",
            "Workspace info",
            "Dependency context",
            {"language": "python"}
        )
        
        self.assertIn("Execute ONLY Ticket 001", prompt)
        self.assertIn("tickets.yaml", prompt)
        self.assertIn("Find ticket 001", prompt)
        self.assertIn("Update status", prompt)
        self.assertIn("/project/dir", prompt)
        self.assertIn("Workspace info", prompt)
        self.assertIn("Dependency context", prompt)
    
    @patch("subprocess.run")
    def test_check_created_files(self, mock_run):
        """Test checking created files."""
        # Mock git status output
        mock_run.return_value = MagicMock(
            stdout="A  file1.py\nM  file2.js\n?? file3.md",
            returncode=0
        )
        
        files = _check_created_files("/project/dir")
        
        self.assertEqual(len(files), 3)
        self.assertIn("file1.py", files)
        self.assertIn("file2.js", files)
        self.assertIn("file3.md", files)
    
    @patch("subprocess.run")
    def test_check_created_files_no_changes(self, mock_run):
        """Test checking created files when no changes."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        
        files = _check_created_files("/project/dir")
        
        self.assertEqual(len(files), 0)
    
    def test_execute_ticket_worker(self):
        """Test ticket worker function."""
        ticket_data = {
            "title": "Test Ticket",
            "raw_id": "001",
            "dependencies": [],
        }
        
        with patch("hydra.tickets.ticket_executor.execute_single_ticket") as mock_execute:
            mock_execute.return_value = True
            
            result = execute_ticket_worker(
                ("001", ticket_data, self.tickets_path, None, False)
            )
            
            ticket_id, success, error = result
            self.assertEqual(ticket_id, "001")
            self.assertTrue(success)
            self.assertIsNone(error)
    
    def test_execute_ticket_worker_failure(self):
        """Test ticket worker function with failure."""
        ticket_data = {
            "title": "Test Ticket",
            "raw_id": "001",
            "dependencies": [],
        }
        
        with patch("hydra.tickets.ticket_executor.execute_single_ticket") as mock_execute:
            mock_execute.return_value = False
            
            result = execute_ticket_worker(
                ("001", ticket_data, self.tickets_path, None, False)
            )
            
            ticket_id, success, error = result
            self.assertEqual(ticket_id, "001")
            self.assertFalse(success)
            self.assertIsNotNone(error)
    
    def test_execute_ticket_worker_exception(self):
        """Test ticket worker function with exception."""
        ticket_data = {
            "title": "Test Ticket",
            "raw_id": "001",
            "dependencies": [],
        }
        
        with patch("hydra.tickets.ticket_executor.execute_single_ticket") as mock_execute:
            mock_execute.side_effect = Exception("Test error")
            
            result = execute_ticket_worker(
                ("001", ticket_data, self.tickets_path, None, False)
            )
            
            ticket_id, success, error = result
            self.assertEqual(ticket_id, "001")
            self.assertFalse(success)
            self.assertIn("Test error", error)
    
    @patch("hydra.tickets.ticket_executor.parse_all_tickets")
    def test_get_quality_summary(self, mock_parse):
        """Test getting quality summary."""
        mock_parse.return_value = {
            "001": {"status": "DONE", "completed": True},
            "002": {"status": "TODO", "completed": False},
            "003": {"status": "IN_PROGRESS", "completed": False},
            "004": {"status": "QUALITY_FAILED", "completed": False},
            "005": {"status": "DONE", "completed": True},
        }
        
        summary = get_quality_summary(self.tickets_path)
        
        self.assertEqual(summary["total"], 5)
        self.assertEqual(summary["completed"], 2)
        self.assertEqual(summary["quality_failed"], 1)
        self.assertEqual(summary["in_progress"], 1)
        self.assertEqual(summary["todo"], 1)
        self.assertEqual(summary["unknown"], 0)
    
    @patch("hydra.tickets.ticket_executor.validate_code_changes")
    def test_validate_code_changes_success(self, mock_validate):
        """Test successful code validation."""
        mock_validate.return_value = (True, [])
        
        result = _validate_code_changes("/project/dir")
        
        self.assertTrue(result)
        mock_validate.assert_called_once_with("/project/dir")
    
    @patch("hydra.tickets.ticket_executor.validate_code_changes")
    def test_validate_code_changes_failure(self, mock_validate):
        """Test failed code validation."""
        mock_validate.return_value = (False, [
            {
                "file": "test.py",
                "pattern": "eval() usage",
                "matches": ["eval(user_input)"]
            }
        ])
        
        result = _validate_code_changes("/project/dir")
        
        self.assertFalse(result)


class TestGetSharedWorkspace(unittest.TestCase):
    """Test get_shared_workspace function."""
    
    def test_get_shared_workspace_no_session(self):
        """Test getting workspace without session ID."""
        workspace = get_shared_workspace()
        self.assertIsNotNone(workspace)
        self.assertIsNotNone(workspace.session_id)
        
        # Clean up
        import shutil
        if os.path.exists(workspace.workspace_path):
            shutil.rmtree(workspace.workspace_path, ignore_errors=True)
    
    def test_get_shared_workspace_with_session(self):
        """Test getting workspace with session ID."""
        workspace = get_shared_workspace("test-session-123")
        self.assertIsNotNone(workspace)
        self.assertEqual(workspace.session_id, "test-session-123")
        
        # Clean up
        import shutil
        if os.path.exists(workspace.workspace_path):
            shutil.rmtree(workspace.workspace_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()