"""Tests for ticket validation module."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from hydra.tickets.ticket_validation import (
    _validate_provider_consolidation,
    _validate_provider_documentation,
    _validate_provider_interface,
    validate_acceptance_criteria,
)


def test_validate_provider_interface_with_base_provider():
    """Test validation when base_provider.py exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create base_provider.py with proper interface
        os.makedirs(os.path.join(tmpdir, "src/hydra/providers"), exist_ok=True)
        base_provider_path = os.path.join(tmpdir, "src/hydra/providers/base_provider.py")
        
        with open(base_provider_path, "w") as f:
            f.write("""
from abc import abstractmethod

class LLMProvider:
    @abstractmethod
    def execute(self):
        pass
""")
        
        failed_criteria = []
        result = _validate_provider_interface(
            1, "Create clear provider interface in base_provider.py", tmpdir, failed_criteria
        )
        
        assert result is True
        assert len(failed_criteria) == 0


def test_validate_provider_interface_missing_file():
    """Test validation when base_provider.py is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        failed_criteria = []
        result = _validate_provider_interface(
            1, "Create clear provider interface in base_provider.py", tmpdir, failed_criteria
        )
        
        assert result is False
        assert len(failed_criteria) == 1


def test_validate_provider_consolidation_with_unified_files():
    """Test validation when unified provider files exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create unified provider files
        os.makedirs(os.path.join(tmpdir, "src/hydra/providers"), exist_ok=True)
        unified_path = os.path.join(tmpdir, "src/hydra/providers/claude_unified.py")
        
        with open(unified_path, "w") as f:
            f.write("# Unified provider implementation")
        
        failed_criteria = []
        result = _validate_provider_consolidation(
            2, "Consolidate Claude providers into single implementation", tmpdir, failed_criteria
        )
        
        assert result is True
        assert len(failed_criteria) == 0


def test_validate_provider_documentation_exists():
    """Test validation when provider documentation exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create documentation
        os.makedirs(os.path.join(tmpdir, "docs/architecture"), exist_ok=True)
        doc_path = os.path.join(tmpdir, "docs/architecture/providers.md")
        
        with open(doc_path, "w") as f:
            f.write("# Provider Architecture")
        
        failed_criteria = []
        result = _validate_provider_documentation(
            4, "Document provider architecture in docs/architecture/providers.md", tmpdir, failed_criteria
        )
        
        assert result is True
        assert len(failed_criteria) == 0


def test_validate_acceptance_criteria_with_system_mods_allowed():
    """Test validation with system modifications allowed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ticket = {
            "id": "001",
            "title": "Test Ticket",
            "acceptance_criteria": [
                "Create test file",
                "Document changes"
            ]
        }
        
        # Mock git status to show system file modifications
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "M src/hydra/test.py\n"
            mock_run.return_value = mock_result
            
            # Should pass with allow_system_modifications=True
            result = validate_acceptance_criteria(ticket, tmpdir, allow_system_modifications=True)
            
            # The validation should pass even with system modifications
            assert result is True


def test_validate_acceptance_criteria_blocks_system_mods():
    """Test validation blocks system modifications by default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ticket = {
            "id": "001", 
            "title": "Test Ticket",
            "acceptance_criteria": [
                "Create test file",
                "Document changes"
            ]
        }
        
        # Mock git status to show system file modifications
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "M src/hydra/test.py\n"
            mock_run.return_value = mock_result
            
            # Should fail without allow_system_modifications
            result = validate_acceptance_criteria(ticket, tmpdir, allow_system_modifications=False)
            
            # The validation should fail due to system modifications
            assert result is False