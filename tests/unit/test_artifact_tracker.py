"""Tests for the artifact tracking and context passing system."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hydra.context import ArtifactTracker, TicketArtifact, TicketContext


class TestArtifactTracker:
    """Test the ArtifactTracker class."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / ".hydra").mkdir()
            (project_dir / "tickets.md").write_text(
                """
## Ticket 001: Create audit report
**Status:** DONE
**Dependencies:** None
**Description:** Audit the codebase and create a report

## Ticket 002: Design API based on audit
**Status:** TODO
**Dependencies:** 001
**Description:** Design API endpoints based on audit findings
"""
            )
            yield project_dir

    def test_init(self, temp_project):
        """Test ArtifactTracker initialization."""
        tracker = ArtifactTracker(str(temp_project))
        assert tracker.project_root == temp_project
        assert tracker.context_file == temp_project / ".hydra" / "ticket_context.json"
        assert tracker.ticket_contexts == {}

    def test_record_and_load_context(self, temp_project):
        """Test recording and loading ticket context."""
        tracker = ArtifactTracker(str(temp_project))

        # Create some artifacts
        artifacts = [
            TicketArtifact(
                file_path="claude_audit_report.md",
                operation="created",
                description="Audit report document",
            ),
            TicketArtifact(
                file_path="src/api/design.py",
                operation="created",
                description="API design module",
            ),
        ]

        # Record ticket completion
        tracker.record_ticket_completion(
            ticket_id="001",
            title="Create audit report",
            artifacts=artifacts,
            acceptance_criteria_met=["Audit completed", "Report generated"],
        )

        # Verify context was saved
        assert "001" in tracker.ticket_contexts
        context = tracker.ticket_contexts["001"]
        assert context.ticket_id == "001"
        assert context.title == "Create audit report"
        assert len(context.artifacts) == 2
        assert context.artifacts[0].file_path == "claude_audit_report.md"

        # Load from file
        tracker2 = ArtifactTracker(str(temp_project))
        assert "001" in tracker2.ticket_contexts
        context2 = tracker2.ticket_contexts["001"]
        assert context2.ticket_id == "001"
        assert len(context2.artifacts) == 2

    def test_get_dependency_context(self, temp_project):
        """Test getting context for dependent tickets."""
        tracker = ArtifactTracker(str(temp_project))

        # Record ticket 001 completion
        artifacts = [
            TicketArtifact(
                file_path="claude_audit_report.md",
                operation="created",
                description="Audit report document",
                content_preview="# Claude Code Audit Report\nThis is the audit...",
            )
        ]

        tracker.record_ticket_completion(
            ticket_id="001",
            title="Create audit report",
            artifacts=artifacts,
            acceptance_criteria_met=["Audit completed"],
        )

        # Get context for ticket 002 which depends on 001
        context_str = tracker.get_dependency_context("002", ["001"])

        assert "CONTEXT FROM DEPENDENT TICKETS" in context_str
        assert "Ticket 001: Create audit report" in context_str
        assert "claude_audit_report.md" in context_str
        assert "Audit report document" in context_str
        assert "Acceptance criteria met:" in context_str
        assert "✅ Audit completed" in context_str

    def test_discover_artifacts_with_git(self, temp_project):
        """Test artifact discovery using git status."""
        tracker = ArtifactTracker(str(temp_project))

        # Get initial snapshot
        before = tracker.get_file_snapshot()

        # Create some files
        (temp_project / "new_file.py").write_text("print('hello')")
        (temp_project / "report.md").write_text("# Report")

        # Mock git status output
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "?? new_file.py\n?? report.md\n"
            mock_run.return_value = mock_result

            artifacts = tracker.discover_artifacts("001", before)

        assert len(artifacts) >= 2
        file_paths = [a.file_path for a in artifacts]
        assert "new_file.py" in file_paths
        assert "report.md" in file_paths

    def test_infer_file_description(self, temp_project):
        """Test file description inference."""
        tracker = ArtifactTracker(str(temp_project))

        assert tracker._infer_file_description("test_module.py") == "Test Python module"
        assert tracker._infer_file_description("config.yaml") == "Configuration file"
        assert tracker._infer_file_description("audit_report.md") == "Audit report"
        assert (
            tracker._infer_file_description("__init__.py") == "Package initialization"
        )
        assert tracker._infer_file_description("index.html") == "HTML page"
        assert tracker._infer_file_description("styles.css") == "Stylesheet"

    def test_get_content_preview(self, temp_project):
        """Test getting content preview."""
        tracker = ArtifactTracker(str(temp_project))

        # Create a test file
        test_file = temp_project / "test.py"
        test_file.write_text(
            """def hello():
    return "world"

def foo():
    return "bar"
    
# This is line 7
# Line 8
# Line 9
# Line 10
# Line 11 should be included
# Line 12 should not be included"""
        )

        preview = tracker._get_content_preview("test.py")
        assert preview is not None
        assert "def hello():" in preview
        assert "Line 11" not in preview  # Only first 10 lines

    def test_file_snapshot(self, temp_project):
        """Test getting file snapshot."""
        tracker = ArtifactTracker(str(temp_project))

        # Create some files
        (temp_project / "file1.py").write_text("content")
        (temp_project / "src").mkdir()
        (temp_project / "src" / "file2.js").write_text("content")

        snapshot = tracker.get_file_snapshot()

        assert "tickets.md" in snapshot
        assert "file1.py" in snapshot
        assert "src/file2.js" in snapshot
        # .hydra files should be excluded
        assert not any(".hydra/" in f for f in snapshot)

    def test_clear_context(self, temp_project):
        """Test clearing context."""
        tracker = ArtifactTracker(str(temp_project))

        # Add some contexts
        tracker.ticket_contexts["001"] = TicketContext(
            ticket_id="001", title="Test 1", status="completed"
        )
        tracker.ticket_contexts["002"] = TicketContext(
            ticket_id="002", title="Test 2", status="completed"
        )

        # Clear specific ticket
        tracker.clear_context("001")
        assert "001" not in tracker.ticket_contexts
        assert "002" in tracker.ticket_contexts

        # Clear all
        tracker.clear_context()
        assert len(tracker.ticket_contexts) == 0

    def test_context_with_no_dependencies(self, temp_project):
        """Test getting context when there are no dependencies."""
        tracker = ArtifactTracker(str(temp_project))

        context_str = tracker.get_dependency_context("001", [])
        assert context_str == ""

    def test_context_with_missing_dependencies(self, temp_project):
        """Test getting context when dependencies haven't been recorded."""
        tracker = ArtifactTracker(str(temp_project))

        # Request context for ticket 002 which depends on 001,
        # but 001 hasn't been recorded
        context_str = tracker.get_dependency_context("002", ["001"])

        # Should still have headers but no actual context
        assert "CONTEXT FROM DEPENDENT TICKETS" in context_str
        # But shouldn't have ticket 001 details since it's not recorded
        assert "Ticket 001:" not in context_str or "Status:" not in context_str

    def test_artifact_serialization(self):
        """Test TicketArtifact serialization."""
        artifact = TicketArtifact(
            file_path="test.py",
            operation="created",
            description="Test file",
            content_preview="def test():\n    pass",
        )

        # To dict
        data = artifact.to_dict()
        assert data["file_path"] == "test.py"
        assert data["operation"] == "created"
        assert data["description"] == "Test file"
        assert data["content_preview"] == "def test():\n    pass"

        # From dict
        artifact2 = TicketArtifact.from_dict(data)
        assert artifact2.file_path == artifact.file_path
        assert artifact2.operation == artifact.operation
        assert artifact2.description == artifact.description
        assert artifact2.content_preview == artifact.content_preview

    def test_context_serialization(self):
        """Test TicketContext serialization."""
        context = TicketContext(
            ticket_id="001",
            title="Test ticket",
            status="completed",
            artifacts=[TicketArtifact(file_path="test.py", operation="created")],
            summary="Test summary",
            acceptance_criteria_met=["Criteria 1", "Criteria 2"],
        )

        # To dict
        data = context.to_dict()
        assert data["ticket_id"] == "001"
        assert data["title"] == "Test ticket"
        assert len(data["artifacts"]) == 1
        assert data["summary"] == "Test summary"
        assert len(data["acceptance_criteria_met"]) == 2

        # From dict
        context2 = TicketContext.from_dict(data)
        assert context2.ticket_id == context.ticket_id
        assert context2.title == context.title
        assert len(context2.artifacts) == 1
        assert context2.artifacts[0].file_path == "test.py"
