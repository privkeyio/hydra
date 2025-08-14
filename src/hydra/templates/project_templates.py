"""Project-specific ticket templates module."""

from enum import Enum
from pathlib import Path
from typing import Dict, List


class ProjectType(str, Enum):
    """Supported project types."""

    MIGRATION = "migration"
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"


class ProjectTemplateManager:
    """Manages project-specific ticket templates."""

    def __init__(self, templates_dir: Path = None):
        """Initialize the template manager."""
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent.parent.parent / "templates"
        self.templates_dir = Path(templates_dir)

    def get_template_path(self, project_type: ProjectType) -> Path:
        """Get the template file path for a project type."""
        template_files = {
            ProjectType.MIGRATION: "migration_template.md",
            ProjectType.FEATURE: "feature_template.md",
            ProjectType.BUGFIX: "bugfix_template.md",
            ProjectType.REFACTOR: "refactor_template.md",
        }
        return self.templates_dir / template_files[project_type]

    def load_template(self, project_type: ProjectType) -> str:
        """Load template content for a project type."""
        template_path = self.get_template_path(project_type)
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        return template_path.read_text(encoding="utf-8")

    def get_available_types(self) -> List[str]:
        """Get list of available project types."""
        return [pt.value for pt in ProjectType]

    def get_template_structure(self, project_type: ProjectType) -> Dict[str, List[str]]:
        """Get the typical structure/phases for a project type."""
        structures = {
            ProjectType.MIGRATION: [
                "Analysis",
                "Design",
                "Implementation",
                "Testing",
                "Validation"
            ],
            ProjectType.FEATURE: [
                "Requirements",
                "Design",
                "Backend",
                "Frontend",
                "Integration"
            ],
            ProjectType.BUGFIX: [
                "Reproduce",
                "Analyze",
                "Fix",
                "Test",
                "Verify"
            ],
            ProjectType.REFACTOR: [
                "Analysis",
                "Plan",
                "Refactor",
                "Test",
                "Cleanup"
            ]
        }

        return {
            "phases": structures[project_type],
            "project_type": project_type.value
        }

    def validate_project_type(self, project_type: str) -> bool:
        """Validate if a project type is supported."""
        try:
            ProjectType(project_type)
            return True
        except ValueError:
            return False
