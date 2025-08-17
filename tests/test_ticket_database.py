"""Tests for ticket database operations."""

import time
from pathlib import Path

import pytest

from hydra.dashboard.database import DatabaseManager, Project, Ticket
from hydra.database.ticket_service import TicketDatabaseService


class TestTicketDatabaseService:
    """Test suite for TicketDatabaseService."""

    @pytest.fixture
    def db_manager(self):
        """Create a test database manager with in-memory SQLite."""
        manager = DatabaseManager("sqlite:///:memory:")
        manager.create_tables()
        return manager

    @pytest.fixture
    def service(self, db_manager):
        """Create a test ticket service."""
        return TicketDatabaseService(db_manager)

    @pytest.fixture
    def sample_markdown(self, tmp_path):
        """Create a sample tickets.md file."""
        tickets_content = """# Project Tickets

## Ticket 001: Setup Database
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Setup database schema
**Progress:** started

**Acceptance Criteria:**
- [ ] Create database models
- [ ] Setup migrations
- [ ] Test database operations

## Ticket 002: Create API
**Status:** TODO
**Model:** smart
**Dependencies:** 001
**Description:** Create REST API endpoints
**Progress:** started

**Acceptance Criteria:**
- [ ] Design API schema
- [ ] Implement endpoints
- [ ] Add authentication

## Ticket 003: Build Frontend
**Status:** IN_PROGRESS
**Model:** coder
**Dependencies:** 002
**Description:** Build user interface
**Progress:** started

**Acceptance Criteria:**
- [ ] Create React components
- [ ] Implement state management
- [ ] Add styling
"""
        tickets_path = tmp_path / "tickets.md"
        tickets_path.write_text(tickets_content)
        return str(tickets_path)

    def test_import_from_markdown(self, service, sample_markdown):
        """Test importing tickets from markdown."""
        # Import tickets
        count = service.import_from_markdown(sample_markdown, "test_project")
        assert count == 3

        # Verify tickets were imported
        tickets = service.get_all_tickets("test_project")
        assert len(tickets) == 3

        # Check ticket details
        ticket_001 = service.get_ticket("test_project", "001")
        assert ticket_001 is not None
        assert ticket_001["title"] == "Setup Database"
        assert ticket_001["status"] == "TODO"
        assert ticket_001["model"] == "balanced"
        assert len(ticket_001["acceptance_criteria"]) == 3
        assert ticket_001["dependencies"] == []

        # Check dependencies
        ticket_002 = service.get_ticket("test_project", "002")
        assert "001" in ticket_002["dependencies"]

    def test_export_to_markdown(self, service, sample_markdown, tmp_path):
        """Test exporting tickets to markdown."""
        # Import tickets first
        service.import_from_markdown(sample_markdown, "test_project")

        # Export to new file
        export_path = tmp_path / "exported_tickets.md"
        result_path = service.export_to_markdown("test_project", str(export_path))

        assert Path(result_path).exists()

        # Read exported content
        with open(result_path) as f:
            content = f.read()

        # Verify content structure
        assert "# Project Tickets - test_project" in content
        assert "## Ticket 001: Setup Database" in content
        assert "## Ticket 002: Create API" in content
        assert "## Ticket 003: Build Frontend" in content
        assert "**Dependencies:** 001" in content

    def test_update_ticket_status(self, service, sample_markdown):
        """Test updating ticket status."""
        # Import tickets
        service.import_from_markdown(sample_markdown, "test_project")

        # Update status
        success = service.update_ticket_status("test_project", "001", "IN_PROGRESS")
        assert success

        # Verify status was updated
        ticket = service.get_ticket("test_project", "001")
        assert ticket["status"] == "IN_PROGRESS"

        # Update to DONE with criteria update
        success = service.update_ticket_status(
            "test_project", "001", "DONE", update_criteria=True
        )
        assert success

        ticket = service.get_ticket("test_project", "001")
        assert ticket["status"] == "DONE"
        assert ticket["completed"]
        # Check that criteria are marked as completed
        for criterion in ticket["acceptance_criteria"]:
            assert criterion.startswith("✅")

    def test_add_ticket_artifact(self, service, sample_markdown):
        """Test adding artifacts to tickets."""
        # Import tickets
        service.import_from_markdown(sample_markdown, "test_project")

        # Add artifact
        success = service.add_ticket_artifact(
            "test_project",
            "001",
            "schema.sql",
            "file",
            path="/db/schema.sql",
            content="CREATE TABLE users...;",
            metadata={"size": 1024},
        )
        assert success

        # Verify artifact was added
        ticket = service.get_ticket("test_project", "001")
        assert "artifacts" in ticket
        assert len(ticket["artifacts"]) == 1
        assert ticket["artifacts"][0]["name"] == "schema.sql"
        assert ticket["artifacts"][0]["type"] == "file"

    def test_dependency_graph(self, service, sample_markdown):
        """Test building dependency graphs."""
        # Import tickets
        service.import_from_markdown(sample_markdown, "test_project")

        # Get dependency graph
        deps, reverse_deps = service.get_dependency_graph("test_project")

        # Check forward dependencies
        assert "001" not in deps  # Ticket 001 has no dependencies
        assert "002" in deps
        assert "001" in deps["002"]  # Ticket 002 depends on 001
        assert "003" in deps
        assert "002" in deps["003"]  # Ticket 003 depends on 002

        # Check reverse dependencies
        assert "001" in reverse_deps
        assert "002" in reverse_deps["001"]  # Ticket 002 depends on 001
        assert "002" in reverse_deps
        assert "003" in reverse_deps["002"]  # Ticket 003 depends on 002

    def test_get_or_create_project(self, service, db_manager):
        """Test project creation and retrieval."""
        with db_manager.get_session() as session:
            # Create new project
            project1 = service.get_or_create_project(
                session, "project1", "/path/to/project1"
            )
            assert project1.name == "project1"
            assert project1.repository_url == "/path/to/project1"

            # Get existing project
            project2 = service.get_or_create_project(session, "project1")
            assert project1.id == project2.id

    def test_performance_large_dataset(self, service, tmp_path):
        """Test performance with large number of tickets."""
        # Create markdown with many tickets
        lines = ["# Project Tickets\n"]
        for i in range(100):
            lines.append(
                f"""
## Ticket {i:03d}: Task {i}
**Status:** TODO
**Model:** balanced
**Dependencies:** {f'{i-1:03d}' if i > 0 else 'None'}
**Description:** Task description {i}
**Progress:** started

**Acceptance Criteria:**
- [ ] Criterion 1
- [ ] Criterion 2
"""
            )

        tickets_path = tmp_path / "large_tickets.md"
        tickets_path.write_text("\n".join(lines))

        # Measure import time
        start = time.time()
        count = service.import_from_markdown(str(tickets_path), "large_project")
        import_time = time.time() - start

        assert count == 100
        assert import_time < 5.0  # Should complete within 5 seconds

        # Measure query time
        start = time.time()
        tickets = service.get_all_tickets("large_project")
        query_time = time.time() - start

        assert len(tickets) == 100
        assert query_time < 1.0  # Should complete within 1 second

        # Measure dependency graph building
        start = time.time()
        deps, reverse_deps = service.get_dependency_graph("large_project")
        graph_time = time.time() - start

        assert len(deps) == 99  # All except first ticket have dependencies
        assert graph_time < 1.0  # Should complete within 1 second

    def test_duplicate_handling(self, service, sample_markdown):
        """Test handling of duplicate imports."""
        # Import tickets twice
        service.import_from_markdown(sample_markdown, "test_project")
        service.import_from_markdown(sample_markdown, "test_project")

        # Second import should update, not duplicate
        tickets = service.get_all_tickets("test_project")
        assert len(tickets) == 3  # Still only 3 tickets

        # Verify no duplicate dependencies
        with service.db_manager.get_session() as session:
            from hydra.dashboard.database import TicketDependency

            dep_count = session.query(TicketDependency).count()
            assert dep_count == 2  # Only 2 dependencies (002->001, 003->002)

    def test_artifact_update(self, service, sample_markdown):
        """Test updating existing artifacts."""
        # Import tickets
        service.import_from_markdown(sample_markdown, "test_project")

        # Add artifact
        service.add_ticket_artifact(
            "test_project", "001", "config.json", "config", content='{"version": 1}'
        )

        # Update same artifact
        service.add_ticket_artifact(
            "test_project", "001", "config.json", "config", content='{"version": 2}'
        )

        # Verify only one artifact exists with updated content
        with service.db_manager.get_session() as session:
            from hydra.dashboard.database import TicketArtifact

            project = session.query(Project).filter_by(name="test_project").first()
            ticket = (
                session.query(Ticket)
                .filter_by(project_id=project.id, ticket_number="001")
                .first()
            )

            artifacts = (
                session.query(TicketArtifact)
                .filter_by(ticket_id=ticket.id, name="config.json")
                .all()
            )

            assert len(artifacts) == 1
            assert artifacts[0].content == '{"version": 2}'


class TestTicketCompatibility:
    """Test backward compatibility layer."""

    @pytest.fixture
    def sample_markdown(self, tmp_path):
        """Create a sample tickets.md file."""
        tickets_content = """# Project Tickets

## Ticket 001: Test Task
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Test task
**Progress:** started

**Acceptance Criteria:**
- [ ] Test criterion
"""
        tickets_path = tmp_path / "test_project" / "tickets.md"
        tickets_path.parent.mkdir(parents=True)
        tickets_path.write_text(tickets_content)
        return str(tickets_path)

    def test_parse_ticket_compat_markdown_fallback(self, sample_markdown, monkeypatch):
        """Test parse_ticket_compat falls back to markdown."""
        # Force markdown mode
        monkeypatch.setenv("HYDRA_USE_DATABASE", "false")

        from hydra.database.ticket_compatibility import parse_ticket_compat

        ticket = parse_ticket_compat(sample_markdown, "001")
        assert ticket is not None
        assert ticket["title"] == "Test Task"
        assert ticket["status"] == "TODO"

    def test_sync_operations(self, sample_markdown, monkeypatch):
        """Test sync between markdown and database."""
        # Force database mode
        monkeypatch.setenv("HYDRA_USE_DATABASE", "true")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

        from hydra.database.ticket_compatibility import (
            sync_database_to_markdown,
            sync_markdown_to_database,
        )

        # Sync from markdown to database
        count = sync_markdown_to_database(sample_markdown)
        assert count > 0

        # Export back to markdown
        project_name = Path(sample_markdown).parent.name
        export_path = Path(sample_markdown).parent / "export.md"
        result = sync_database_to_markdown(project_name, str(export_path))
        assert Path(result).exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
