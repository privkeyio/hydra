"""Unit tests for the action executor parser module."""

import pytest

from hydra.action_executor.errors import ParseError, ValidationError
from hydra.action_executor.parser import MultiFileParser, ResponseParser
from hydra.action_executor.parsing_strategies import (
    CodeBlockStrategy,
    CommandStrategy,
    CompositeParsingStrategy,
)
from hydra.action_executor.types import Action, ActionType


class TestResponseParser:
    """Test the ResponseParser class."""

    def test_empty_response(self):
        """Test parsing empty responses."""
        parser = ResponseParser()
        
        # Empty string
        assert parser.parse("") == []
        
        # Whitespace only
        assert parser.parse("   \n  \t  ") == []

    def test_parse_code_blocks(self):
        """Test parsing code blocks with file paths."""
        parser = ResponseParser(allow_dangerous=True)
        
        response = """
        Here's the implementation:
        
        ```python
        # main.py
        def hello():
            print("Hello, World!")
        ```
        
        ```javascript
        // app.js
        console.log("Hello from JS");
        ```
        """
        
        actions = parser.parse(response)
        assert len(actions) >= 2
        
        # Check first file
        python_actions = [a for a in actions if "main.py" in a.target]
        assert len(python_actions) > 0
        assert python_actions[0].type in [ActionType.CREATE_FILE, ActionType.MODIFY_FILE]
        assert "def hello():" in python_actions[0].content
        
        # Check second file
        js_actions = [a for a in actions if "app.js" in a.target]
        assert len(js_actions) > 0
        assert "console.log" in js_actions[0].content

    def test_parse_shell_commands(self):
        """Test parsing shell commands."""
        parser = ResponseParser()
        
        response = """
        Run the following commands:
        
        ```bash
        mkdir -p src/tests
        touch src/__init__.py
        pip install pytest
        ```
        """
        
        commands = parser.extract_shell_commands(response)
        assert len(commands) >= 3
        assert any("mkdir" in cmd for cmd in commands)
        assert any("pip install" in cmd for cmd in commands)

    def test_supports_format_detection(self):
        """Test format detection in responses."""
        parser = ResponseParser()
        
        # Code blocks format
        response1 = "```python\ncode here\n```"
        formats1 = parser.supports_format(response1)
        assert formats1["code_blocks"] is True
        
        # JSON format
        response2 = '```json\n{"action": "create"}\n```'
        formats2 = parser.supports_format(response2)
        assert formats2["json"] is True
        
        # Shell commands
        response3 = "Run: npm install\n$ python script.py"
        formats3 = parser.supports_format(response3)
        assert formats3["shell_commands"] is True
        
        # Directives
        response4 = "CREATE FILE: test.py\nMODIFY FILE: main.py"
        formats4 = parser.supports_format(response4)
        assert formats4["directives"] is True

    def test_validation_enabled(self):
        """Test action validation when enabled."""
        parser = ResponseParser(validate_actions=True)
        
        # Invalid action without content
        response = """
        ```python
        # 
        ```
        """
        
        # Should handle validation gracefully
        actions = parser.parse(response)
        assert isinstance(actions, list)

    def test_dangerous_action_filtering(self):
        """Test filtering of dangerous actions."""
        parser = ResponseParser(allow_dangerous=False)
        
        response = """
        ```bash
        rm -rf /
        sudo rm -rf /home
        chmod 777 /etc/passwd
        ```
        """
        
        actions = parser.parse(response)
        # Dangerous commands should be filtered out
        for action in actions:
            if action.type == ActionType.RUN_COMMAND:
                assert "rm -rf" not in action.target
                assert "sudo" not in action.target.lower()
                assert "chmod 777" not in action.target

    def test_max_actions_limit(self):
        """Test max actions limit enforcement."""
        parser = ResponseParser(max_actions=5)
        
        # Create response with many files
        response = ""
        for i in range(20):
            response += f"""
            ```python
            # file{i}.py
            print("{i}")
            ```
            """
        
        actions = parser.parse(response)
        assert len(actions) <= 5

    def test_path_normalization(self):
        """Test file path normalization."""
        parser = ResponseParser()
        
        response = """
        ```python
        # ./src//utils.py
        code
        ```
        
        ```python
        # /absolute/path.py
        code
        ```
        """
        
        actions = parser.parse(response)
        
        # Check normalized paths
        for action in actions:
            if "utils.py" in action.target:
                assert not action.target.startswith("./")
                assert "//" not in action.target

    def test_metadata_addition(self):
        """Test metadata addition to actions."""
        parser = ResponseParser()
        
        response = """
        ```python
        # test_main.py
        import pytest
        def test_function():
            pass
        ```
        
        ```markdown
        # README.md
        Documentation here
        ```
        """
        
        actions = parser.parse(response)
        
        # Check test metadata
        test_actions = [a for a in actions if "test_" in a.target]
        if test_actions:
            assert test_actions[0].metadata.get("is_test") is True
        
        # Check documentation metadata
        doc_actions = [a for a in actions if ".md" in a.target]
        if doc_actions:
            assert doc_actions[0].metadata.get("is_documentation") is True

    def test_parse_error_handling(self):
        """Test parse error handling."""
        parser = ResponseParser()
        
        # Create a strategy that always fails
        class FailingStrategy:
            def extract_actions(self, response):
                raise ValueError("Parsing failed")
        
        parser.strategy = FailingStrategy()
        
        with pytest.raises(ParseError) as exc_info:
            parser.parse("any response")
        
        assert "Failed to parse response" in str(exc_info.value)

    def test_code_block_extraction(self):
        """Test specific code block extraction method."""
        parser = ResponseParser(allow_dangerous=True)
        
        response = """
        ```python
        # utils.py
        def util_func():
            return True
        ```
        
        ```javascript
        // config.js
        export default {};
        ```
        """
        
        blocks = parser.parse_code_blocks(response)
        assert len(blocks) >= 2
        
        # Check extracted tuples
        file_paths = [path for path, _ in blocks]
        contents = [content for _, content in blocks]
        
        assert any("utils.py" in path for path in file_paths)
        assert any("config.js" in path for path in file_paths)
        assert any("def util_func" in content for content in contents)


class TestMultiFileParser:
    """Test the MultiFileParser class."""

    def test_parse_multiple_files(self):
        """Test parsing multiple files from response."""
        parser = MultiFileParser(ResponseParser(allow_dangerous=True))
        
        response = """
        ```python
        # src/main.py
        import sys
        
        def main():
            print("Main")
        ```
        
        ```python
        # src/utils.py
        def helper():
            return "help"
        ```
        
        ```python
        # tests/test_main.py
        import pytest
        from src.main import main
        
        def test_main():
            main()
        ```
        """
        
        files = parser.parse_files(response)
        
        assert len(files) >= 3
        assert "src/main.py" in files
        assert "src/utils.py" in files
        assert "tests/test_main.py" in files
        
        # Check content
        assert "import sys" in files["src/main.py"]["content"]
        assert "def helper" in files["src/utils.py"]["content"]
        assert "import pytest" in files["tests/test_main.py"]["content"]

    def test_group_by_directory(self):
        """Test grouping files by directory."""
        parser = MultiFileParser(ResponseParser(allow_dangerous=True))
        
        response = """
        ```python
        # src/main.py
        main_code
        ```
        
        ```python
        # src/utils.py
        utils_code
        ```
        
        ```python
        # tests/test_main.py
        test_code
        ```
        
        ```python
        # config.py
        config_code
        ```
        """
        
        grouped = parser.group_by_directory(response)
        
        assert "src" in grouped
        assert "tests" in grouped
        assert "." in grouped  # Root directory
        
        # Check grouped files
        src_files = grouped["src"]
        assert len(src_files) == 2
        filenames = [name for name, _ in src_files]
        assert "main.py" in filenames
        assert "utils.py" in filenames

    def test_empty_response_handling(self):
        """Test handling of empty responses."""
        parser = MultiFileParser()
        
        files = parser.parse_files("")
        assert files == {}
        
        grouped = parser.group_by_directory("")
        assert grouped == {}

    def test_custom_base_parser(self):
        """Test using custom base parser."""
        base_parser = ResponseParser(validate_actions=False, max_actions=2)
        multi_parser = MultiFileParser(parser=base_parser)
        
        response = """
        ```python
        # file1.py
        code1
        ```
        
        ```python
        # file2.py
        code2
        ```
        
        ```python
        # file3.py
        code3
        ```
        """
        
        files = multi_parser.parse_files(response)
        # Should respect max_actions from base parser
        assert len(files) <= 2


class TestPathValidation:
    """Test path validation functionality."""

    def test_dangerous_path_detection(self):
        """Test detection of dangerous paths."""
        parser = ResponseParser(validate_actions=True)
        
        dangerous_paths = [
            "/etc/passwd",
            "/sys/kernel",
            "/proc/1/mem",
            "~/.ssh/id_rsa",
            "../../../etc/passwd",
        ]
        
        for path in dangerous_paths:
            response = f"""
            ```python
            # {path}
            malicious code
            ```
            """
            
            # Should filter or raise validation error
            actions = parser.parse(response)
            if actions:
                assert not any(path in action.target for action in actions)

    def test_valid_path_patterns(self):
        """Test valid path patterns are accepted."""
        parser = ResponseParser(allow_dangerous=True)
        
        valid_paths = [
            "src/main.py",
            "tests/unit/test_module.py",
            "config/settings.json",
            "README.md",
            ".gitignore",
        ]
        
        for path in valid_paths:
            response = f"""
            ```python
            # {path}
            valid code
            ```
            """
            
            actions = parser.parse(response)
            assert len(actions) > 0
            assert any(path in action.target for action in actions)


class TestActionTypeDetection:
    """Test detection of different action types."""

    def test_file_operation_detection(self):
        """Test detection of file operations."""
        parser = ResponseParser(allow_dangerous=True)
        
        response = """
        Creating new file:
        ```python
        # new_file.py
        print("new")
        ```
        
        Modifying existing:
        ```python
        # existing_file.py
        print("modified")
        ```
        """
        
        actions = parser.parse(response)
        
        # Should detect appropriate action types
        file_types = {ActionType.CREATE_FILE, ActionType.MODIFY_FILE}
        action_types = {action.type for action in actions}
        assert len(action_types & file_types) > 0

    def test_command_detection(self):
        """Test detection of command actions."""
        parser = ResponseParser()
        
        response = """
        ```bash
        npm install express
        npm run build
        ```
        
        ```shell
        python -m pytest
        ```
        """
        
        actions = parser.parse(response)
        
        command_actions = [a for a in actions if a.type in [
            ActionType.RUN_COMMAND,
            ActionType.INSTALL_PACKAGE,
            ActionType.RUN_TEST
        ]]
        assert len(command_actions) > 0


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_malformed_code_blocks(self):
        """Test handling of malformed code blocks."""
        parser = ResponseParser()
        
        malformed = [
            "```python\nno closing",
            "``python\nmissing backtick\n```",
            "```\nno language\n```",
        ]
        
        for response in malformed:
            # Should not crash
            actions = parser.parse(response)
            assert isinstance(actions, list)

    def test_unicode_content(self):
        """Test handling of Unicode content."""
        parser = ResponseParser(allow_dangerous=True)
        
        response = """
        ```python
        # unicode_file.py
        # -*- coding: utf-8 -*-
        print("Hello 世界 🌍")
        emoji = "😀"
        ```
        """
        
        actions = parser.parse(response)
        assert len(actions) > 0
        assert "世界" in actions[0].content
        assert "😀" in actions[0].content

    def test_very_long_content(self):
        """Test handling of very long content."""
        parser = ResponseParser(allow_dangerous=True)
        
        # Create very long content
        long_content = "x" * 100000
        response = f"""
        ```python
        # long_file.py
        data = "{long_content}"
        ```
        """
        
        actions = parser.parse(response)
        assert len(actions) > 0
        assert len(actions[0].content) > 50000

    def test_nested_code_blocks(self):
        """Test handling of nested code blocks."""
        parser = ResponseParser(allow_dangerous=True)
        
        response = """
        ```python
        # doc_file.py
        '''
        Example:
        ```python
        print("nested")
        ```
        '''
        def main():
            pass
        ```
        """
        
        actions = parser.parse(response)
        assert len(actions) > 0
        # Should handle the outer block correctly
        assert "def main():" in actions[0].content