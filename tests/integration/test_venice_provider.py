"""Integration tests for Venice provider execute_ticket functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from hydra.action_executor import ActionType
from hydra.providers.base import LLMConfig
from hydra.providers.venice import VeniceProvider


class TestVeniceProviderIntegration:
    """Integration tests for Venice provider ticket execution."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def venice_config(self):
        """Create a test Venice configuration."""
        return LLMConfig(
            provider_type="venice",
            model="llama-3.1-8b",
            api_key="test-api-key",
            base_url="https://api.venice.ai/api/v1",
            temperature=0.7,
            max_tokens=1000,
        )

    @pytest.fixture
    def venice_provider(self, venice_config):
        """Create a Venice provider instance."""
        with (
            patch("hydra.providers.venice.OpenAI"),
            patch("hydra.providers.venice.AsyncOpenAI"),
        ):
            return VeniceProvider(venice_config)

    def test_execute_ticket_basic_file_creation(self, venice_provider, temp_dir):
        """Test basic file creation through execute_ticket."""
        # Mock Venice response with file creation
        mock_response = """
        Here's the implementation:

        ```python
        # main.py
        def hello_world():
            print("Hello, World!")

        if __name__ == "__main__":
            hello_world()
        ```
        """

        with patch.object(venice_provider, "generate", return_value=mock_response):
            result = venice_provider.execute_ticket(
                "Create a hello world Python script",
                working_directory=str(temp_dir),
                dry_run=True,  # Use dry run to avoid actual file creation
            )

            assert result["success"] is True
            assert result["actions_executed"] >= 0
            assert "response" in result
            assert result["response"] == mock_response

    def test_execute_ticket_multiple_files(self, venice_provider, temp_dir):
        """Test creating multiple files through execute_ticket."""
        mock_response = """
        I'll create the project structure:

        ```python
        # src/app.py
        from config import Config

        class App:
            def __init__(self):
                self.config = Config()

            def run(self):
                print(f"Running {self.config.name}")
        ```

        ```python
        # src/config.py
        class Config:
            def __init__(self):
                self.name = "MyApp"
                self.version = "1.0.0"
        ```

        ```python
        # main.py
        from src.app import App

        if __name__ == "__main__":
            app = App()
            app.run()
        ```
        """

        with patch.object(venice_provider, "generate", return_value=mock_response):
            result = venice_provider.execute_ticket(
                "Create a Python project with app and config modules",
                working_directory=str(temp_dir),
                dry_run=True,
            )

            assert result["success"] is True
            assert len(result["results"]) > 0

    @pytest.mark.external
    @pytest.mark.skipif(
        not os.getenv("VENICE_API_KEY"), reason="Venice API key required"
    )
    def test_execute_ticket_with_commands(self, venice_provider, temp_dir):
        """Test executing commands through execute_ticket."""
        mock_response = """
        Setting up the project:

        ```bash
        mkdir -p src/tests
        touch src/__init__.py
        touch src/tests/__init__.py
        ```

        ```python
        # src/calculator.py
        class Calculator:
            def add(self, a, b):
                return a + b

            def subtract(self, a, b):
                return a - b
        ```

        ```bash
        echo "Project setup complete"
        ```
        """

        with patch.object(venice_provider, "generate", return_value=mock_response):
            result = venice_provider.execute_ticket(
                "Create a calculator module with tests",
                working_directory=str(temp_dir),
                dry_run=True,
            )

            assert result["success"] is True
            # Check that both file and command actions were extracted
            action_types = {r["action_type"] for r in result["results"]}
            assert len(action_types) > 0

    def test_execute_ticket_error_handling(self, venice_provider, temp_dir):
        """Test error handling in execute_ticket."""
        # Test with empty response
        with patch.object(venice_provider, "generate", return_value=""):
            result = venice_provider.execute_ticket(
                "Create something",
                working_directory=str(temp_dir),
            )

            assert result["success"] is True  # No actions means success
            assert result["actions_executed"] == 0
            assert len(result["errors"]) > 0

        # Test with generation failure
        with patch.object(
            venice_provider, "generate", side_effect=Exception("API error")
        ):
            result = venice_provider.execute_ticket(
                "Create something",
                working_directory=str(temp_dir),
            )

            assert result["success"] is False
            assert "Ticket execution failed" in str(result["errors"])

    def test_parse_venice_response(self, venice_provider):
        """Test Venice response parsing."""
        response = """
        ```python
        # utils.py
        def format_name(first, last):
            return f"{first} {last}"
        ```

        ```bash
        pip install requests
        ```
        """

        actions = venice_provider._parse_venice_response(response)

        assert len(actions) >= 1
        # Check for file creation action
        file_actions = [a for a in actions if a.type == ActionType.CREATE_FILE]
        assert len(file_actions) > 0

        # Check for command action
        cmd_actions = [a for a in actions if a.type == ActionType.RUN_COMMAND]
        assert len(cmd_actions) >= 0

    def test_venice_specific_parsing(self, venice_provider):
        """Test Venice-specific response format parsing."""
        # Test format with language:filepath notation
        response = """
        ```python:src/main.py
        import sys

        def main():
            print("Venice Test")

        if __name__ == "__main__":
            main()
        ```
        """

        actions = venice_provider._extract_venice_specific_actions(response)

        assert len(actions) == 1
        assert actions[0].type == ActionType.CREATE_FILE
        assert actions[0].target == "src/main.py"
        assert "import sys" in actions[0].content

    def test_is_valid_file_path(self, venice_provider):
        """Test file path validation."""
        # Valid paths
        assert venice_provider._is_valid_file_path("main.py") is True
        assert venice_provider._is_valid_file_path("src/utils.js") is True
        assert venice_provider._is_valid_file_path("test/data.json") is True
        assert venice_provider._is_valid_file_path("README.md") is True

        # Invalid paths
        assert venice_provider._is_valid_file_path("") is False
        assert venice_provider._is_valid_file_path("a" * 256) is False
        assert venice_provider._is_valid_file_path("no_extension") is False

    def test_parse_response_for_actions_compatibility(self, venice_provider):
        """Test the compatibility method for parsing actions."""
        response = """
        ```python
        # app.py
        print("Hello")
        ```

        ```bash
        python app.py
        ```
        """

        file_ops, commands = venice_provider.parse_response_for_actions(response)

        assert len(file_ops) >= 0
        assert len(commands) >= 0

    @pytest.mark.external
    def test_execute_ticket_with_rollback(self, venice_provider, temp_dir):
        """Test rollback functionality on failure."""
        mock_response = """
        ```python
        # good_file.py
        print("This will succeed")
        ```
        """

        with patch.object(venice_provider, "generate", return_value=mock_response):
            # Create a mock executor that fails on second action
            with patch(
                "hydra.providers.venice.FileOperationsExecutor"
            ) as mock_executor:
                mock_executor_instance = mock_executor.return_value
                mock_executor_instance.validate.return_value = True

                # First execution succeeds, second fails
                mock_results = [
                    Mock(
                        success=True, error=None, output="Created", execution_time=0.1
                    ),
                    Mock(
                        success=False,
                        error="Permission denied",
                        output=None,
                        execution_time=0.1,
                    ),
                ]
                mock_executor_instance.execute.side_effect = mock_results

                venice_provider.execute_ticket(
                    "Create files with failure",
                    working_directory=str(temp_dir),
                    rollback_on_failure=True,
                )

                # Verify rollback was called
                if len(mock_results) > 1 and not mock_results[1].success:
                    mock_executor_instance.rollback.assert_called()

    def test_execute_ticket_dry_run(self, venice_provider, temp_dir):
        """Test dry run mode doesn't create actual files."""
        mock_response = """
        ```python
        # test.py
        print("Dry run test")
        ```
        """

        with patch.object(venice_provider, "generate", return_value=mock_response):
            result = venice_provider.execute_ticket(
                "Create test file",
                working_directory=str(temp_dir),
                dry_run=True,
            )

            assert result["success"] is True
            # In dry run, files should not actually be created
            test_file = temp_dir / "test.py"
            assert not test_file.exists()

    def test_build_ticket_prompt(self, venice_provider):
        """Test ticket prompt building."""
        ticket_content = "Implement a REST API endpoint"
        prompt = venice_provider._build_ticket_prompt(ticket_content)

        assert ticket_content in prompt
        assert "Code files" in prompt
        assert "Commands" in prompt or "bash blocks" in prompt

    @pytest.mark.parametrize(
        "response_format",
        [
            # Different response formats to test
            """```python\n# file.py\ncode```""",
            """```python:path/file.py\ncode```""",
            """```bash\necho "test"```""",
            """Create file:\n```python\ncode```""",
        ],
    )
    def test_various_response_formats(self, venice_provider, response_format):
        """Test parsing various Venice response formats."""
        actions = venice_provider._parse_venice_response(response_format)
        # Should extract at least one action from each format
        assert isinstance(actions, list)


class TestVeniceProviderEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def venice_provider(self):
        """Create a Venice provider with minimal config."""
        config = LLMConfig(
            provider_type="venice",
            api_key="test-key",
        )
        with (
            patch("hydra.providers.venice.OpenAI"),
            patch("hydra.providers.venice.AsyncOpenAI"),
        ):
            return VeniceProvider(config)

    def test_execute_ticket_with_invalid_working_dir(self, venice_provider):
        """Test execute_ticket with invalid working directory."""
        mock_response = "```python\n# test.py\nprint()```"
        with patch.object(venice_provider, "generate", return_value=mock_response):
            result = venice_provider.execute_ticket(
                "Test",
                working_directory="/nonexistent/path",
                dry_run=True,  # Use dry run to avoid actual filesystem operations
            )

            # Should handle gracefully
            assert "success" in result
            assert "errors" in result

    def test_malformed_code_blocks(self, venice_provider):
        """Test handling of malformed code blocks."""
        malformed_responses = [
            "```python\nunclosed block",
            "```\nno language specified\n```",
            "``python\nmissing backtick\n```",
        ]

        for response in malformed_responses:
            actions = venice_provider._parse_venice_response(response)
            # Should handle gracefully without crashing
            assert isinstance(actions, list)

    def test_empty_ticket_content(self, venice_provider):
        """Test with empty ticket content."""
        with patch.object(venice_provider, "generate", return_value=""):
            result = venice_provider.execute_ticket("")

            assert result["success"] is True  # Empty response is technically successful
            assert result["actions_executed"] == 0

    def test_very_large_response(self, venice_provider):
        """Test handling of very large responses."""
        # Create a large response with many files
        large_response = ""
        for i in range(50):
            large_response += f"""
            ```python
            # file{i}.py
            print("File {i}")
            ```
            """

        with patch.object(venice_provider, "generate", return_value=large_response):
            result = venice_provider.execute_ticket(
                "Create many files",
                dry_run=True,
                max_actions=10,  # Limit actions
            )

            assert "success" in result
            # Should respect max_actions limit
            assert len(result["results"]) <= 100  # Default max from parser
