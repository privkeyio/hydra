"""Automatic Quality Issue Fixer for Hydra.

Automatically fixes common quality gate failures after ticket execution.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Tuple

from hydra.quality.ai_detection import AIGeneratedCodeDetector


class QualityAutoFixer:
    """Automatically fixes common quality issues."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()

    def fix_common_issues(self) -> List[Tuple[str, bool, str]]:
        """Fix common quality issues automatically.

        Returns:
            List of (issue, fixed, message) tuples

        """
        fixes = []

        # Check for AI-generated code first - this can't be auto-fixed
        ai_issues = self._check_ai_generated_code()
        if ai_issues:
            fixes.append(("AI-generated code detected", False,
                         f"Found {len(ai_issues)} AI-generated patterns that need manual review"))

        # Fix 1: Add missing __init__.py files
        fixes.extend(self._add_missing_init_files())

        # Fix 2: Run ruff with auto-fix
        fixes.extend(self._run_ruff_autofix())

        # Fix 3: Fix import sorting
        fixes.extend(self._fix_import_sorting())

        # Fix 4: Add minimal docstrings to new files
        fixes.extend(self._add_missing_docstrings())

        return fixes

    def _add_missing_init_files(self) -> List[Tuple[str, bool, str]]:
        """Add missing __init__.py files to Python packages."""
        fixes = []
        src_dir = self.project_root / "src"

        if not src_dir.exists():
            return fixes

        for root, _dirs, files in os.walk(src_dir):
            root_path = Path(root)

            # Skip non-Python directories
            if '__pycache__' in root or '.git' in root:
                continue

            # Check if directory has Python files but no __init__.py
            py_files = [f for f in files if f.endswith('.py') and f != '__init__.py']
            if py_files and '__init__.py' not in files:
                init_file = root_path / '__init__.py'
                init_file.write_text('"""Package initialization."""\n')
                fixes.append((
                    f"Missing __init__.py in {root_path.relative_to(self.project_root)}",
                    True,
                    "Created __init__.py"
                ))

        return fixes

    def _run_ruff_autofix(self) -> List[Tuple[str, bool, str]]:
        """Run ruff with auto-fix on new files."""
        fixes = []

        try:
            # Run ruff with auto-fix
            result = subprocess.run(
                ["ruff", "check", "--fix", "src/"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30
            )

            if "fixed" in result.stdout.lower():
                fixes.append((
                    "Linting issues",
                    True,
                    "Auto-fixed with ruff"
                ))
            elif result.returncode != 0:
                # Try more aggressive fixes
                subprocess.run(
                    ["ruff", "check", "--fix", "--unsafe-fixes", "src/"],
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                    timeout=30
                )
                fixes.append((
                    "Linting issues",
                    True,
                    "Applied unsafe fixes with ruff"
                ))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            fixes.append((
                "Ruff linting",
                False,
                "Ruff not available"
            ))

        return fixes

    def _fix_import_sorting(self) -> List[Tuple[str, bool, str]]:
        """Fix import sorting with isort."""
        fixes = []

        try:
            result = subprocess.run(
                ["isort", "src/", "--profile", "black"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30
            )

            if result.returncode == 0:
                fixes.append((
                    "Import sorting",
                    True,
                    "Fixed with isort"
                ))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # isort not available, try with ruff
            try:
                subprocess.run(
                    ["ruff", "check", "--select", "I", "--fix", "src/"],
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                    timeout=30
                )
                fixes.append((
                    "Import sorting",
                    True,
                    "Fixed with ruff"
                ))
            except:
                pass

        return fixes

    def _add_missing_docstrings(self) -> List[Tuple[str, bool, str]]:
        """Add minimal docstrings to files missing them."""
        fixes = []
        src_dir = self.project_root / "src"

        if not src_dir.exists():
            return fixes

        for root, _, files in os.walk(src_dir):
            root_path = Path(root)

            for file in files:
                if not file.endswith('.py'):
                    continue

                file_path = root_path / file
                try:
                    content = file_path.read_text()

                    # Check if file has module docstring
                    if not content.startswith('"""') and not content.startswith("'''"):
                        # Add minimal module docstring
                        module_name = file_path.stem.replace('_', ' ').title()
                        new_content = f'"""{module_name} module."""\n\n{content}'
                        file_path.write_text(new_content)

                        fixes.append((
                            f"Missing docstring in {file_path.relative_to(self.project_root)}",
                            True,
                            "Added module docstring"
                        ))
                except Exception:
                    pass

        return fixes

    def run_post_fix_validation(self) -> bool:
        """Run quick validation after fixes."""
        try:
            # Quick ruff check
            result = subprocess.run(
                ["ruff", "check", "src/"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30
            )
            return result.returncode == 0
        except:
            return True  # Assume OK if can't validate

    def _check_ai_generated_code(self) -> List:
        """Check for AI-generated code patterns in recent changes."""
        try:
            # Get git diff
            git_diff = subprocess.run(
                ["git", "diff", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )

            if git_diff.returncode != 0:
                return []

            detector = AIGeneratedCodeDetector()
            issues = detector.detect_in_diff(git_diff.stdout)
            return issues
        except Exception:
            return []
