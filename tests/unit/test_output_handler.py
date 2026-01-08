"""Unit tests for provider output handlers."""

import pytest

from hydra.providers.output_handler import (
    ClaudeOutputHandler,
    ExtractedContent,
    OutputHandler,
    OutputHandlerFactory,
    ParsedResponse,
    StreamingBuffer,
    VeniceOutputHandler,
    extract_executable_code,
    format_code_for_execution,
    merge_streaming_responses,
)


class TestOutputHandler:
    """Test base OutputHandler functionality."""

    def test_extract_code_blocks_markdown(self):
        """Test extraction of markdown code blocks."""
        handler = ClaudeOutputHandler()

        text = """
        Here's a Python function:
        
        ```python
        def hello_world():
            print("Hello, World!")
        ```
        
        And here's some JavaScript:
        
        ```javascript
        function greet(name) {
            console.log(`Hello, ${name}!`);
        }
        ```
        """

        blocks = handler.extract_code_blocks(text)

        assert len(blocks) == 2
        assert blocks[0].language == "python"
        assert "def hello_world" in blocks[0].content
        assert blocks[0].executable is True

        assert blocks[1].language == "javascript"
        assert "function greet" in blocks[1].content
        assert blocks[1].executable is True

    def test_extract_code_blocks_no_language(self):
        """Test extraction when language is not specified."""
        handler = VeniceOutputHandler()

        text = """
        ```
        some code here
        without language
        ```
        """

        blocks = handler.extract_code_blocks(text)

        assert len(blocks) == 1
        assert blocks[0].language == "text"
        assert blocks[0].executable is False

    def test_extract_commands(self):
        """Test extraction of shell commands."""
        handler = ClaudeOutputHandler()

        text = """
        First, install the package:
        $ pip install numpy
        
        Then run the script:
        > python main.py
        
        Or use bash:
        ```bash
        cd /project
        python script.py --arg value
        ```
        """

        commands = handler.extract_commands(text)

        assert "pip install numpy" in commands
        assert "python main.py" in commands
        assert "cd /project" in commands
        assert "python script.py --arg value" in commands

    def test_format_code_block(self):
        """Test code block formatting."""
        handler = VeniceOutputHandler()

        code = "print('Hello')"
        formatted = handler.format_code_block(code, "python", "hello.py")

        assert "```python # hello.py" in formatted
        assert "print('Hello')" in formatted
        assert "```" in formatted


class TestClaudeOutputHandler:
    """Test Claude-specific output handling."""

    def test_parse_claude_response(self):
        """Test parsing Claude Code response."""
        handler = ClaudeOutputHandler()

        response = """
        I'll help you create a function.
        
        Writing main.py:
        ```python
        def calculate(x, y):
            return x + y
        ```
        
        Running tests...
        """

        parsed = handler.parse(response)

        assert isinstance(parsed, ParsedResponse)
        assert len(parsed.code_blocks) == 1
        assert parsed.code_blocks[0].language == "python"
        assert "calculate" in parsed.code_blocks[0].content
        assert parsed.metadata["provider"] == "claude"
        assert parsed.metadata["interactive"] is True

    def test_extract_file_operations(self):
        """Test extraction of file operations from Claude output."""
        handler = ClaudeOutputHandler()

        response = """
        Creating config.json:
        ```json
        {
            "name": "test",
            "version": "1.0"
        }
        ```
        
        Writing src/main.py:
        ```python
        def main():
            pass
        ```
        """

        content = handler.extract_content(response)

        assert "config.json" in content.files
        assert "src/main.py" in content.files
        assert '"name": "test"' in content.files["config.json"]
        assert "def main" in content.files["src/main.py"]

    def test_extract_claude_metadata(self):
        """Test extraction of Claude-specific metadata."""
        handler = ClaudeOutputHandler()

        response = """
        Using Read tool to examine the file.
        Reading: config.json
        
        Now Writing updated configuration:
        ```json
        {"updated": true}
        ```
        
        Running npm install
        """

        content = handler.extract_content(response)

        assert content.metadata["has_file_operations"] is True
        assert content.metadata["has_commands"] is True


class TestVeniceOutputHandler:
    """Test Venice-specific output handling."""

    def test_parse_venice_response(self):
        """Test parsing Venice response."""
        handler = VeniceOutputHandler()

        response = """
        Here's a Python function to calculate factorial:
        
        ```python
        def factorial(n):
            if n <= 1:
                return 1
            return n * factorial(n - 1)
        ```
        
        This uses recursion to calculate the factorial.
        """

        parsed = handler.parse(response)

        assert len(parsed.code_blocks) == 1
        assert parsed.code_blocks[0].language == "python"
        assert "factorial" in parsed.code_blocks[0].content
        assert parsed.metadata["provider"] == "venice"

    def test_detect_implicit_code(self):
        """Test detection of code without markdown blocks."""
        handler = VeniceOutputHandler()

        response = """
        Here's the function you requested:
        
        def greet(name):
            message = f"Hello, {name}!"
            print(message)
            return message
        
        You can call it like: greet("Alice")
        """

        parsed = handler.parse(response)

        # Should detect the Python function even without markdown
        assert len(parsed.code_blocks) > 0
        found_function = False
        for block in parsed.code_blocks:
            if "def greet" in block.content:
                found_function = True
                # The language detection might vary, but it should be executable
                assert block.executable is True

        assert found_function

    def test_extract_implied_files(self):
        """Test extraction of implied file structure."""
        handler = VeniceOutputHandler()

        response = """
        Create a file called app.py with this code:
        
        ```python
        from flask import Flask
        app = Flask(__name__)
        ```
        
        Then create config.yaml:
        
        ```yaml
        database:
          host: localhost
        ```
        """

        content = handler.extract_content(response)

        # Should match files with code blocks
        assert "app.py" in content.files or len(content.files) > 0
        assert any("Flask" in code for code in content.files.values())


class TestStreamingBuffer:
    """Test streaming buffer functionality."""

    def test_append_and_get_blocks(self):
        """Test appending chunks and extracting complete blocks."""
        buffer = StreamingBuffer()

        # Simulate streaming
        buffer.append("Here's code:\n```python\n")
        assert len(buffer.get_complete_blocks()) == 0  # Not complete yet

        buffer.append("def test():\n    pass\n")
        assert len(buffer.get_complete_blocks()) == 0  # Still not complete

        buffer.append("```\nDone.")
        blocks = buffer.get_complete_blocks()

        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert "def test" in blocks[0].content


class TestOutputHandlerFactory:
    """Test output handler factory."""

    def test_create_known_handlers(self):
        """Test creation of known handler types."""
        claude_handler = OutputHandlerFactory.create("claude")
        assert isinstance(claude_handler, ClaudeOutputHandler)

        venice_handler = OutputHandlerFactory.create("venice")
        assert isinstance(venice_handler, VeniceOutputHandler)

    def test_create_default_handler(self):
        """Test creation of default handler for unknown provider."""
        handler = OutputHandlerFactory.create("unknown_provider")
        assert isinstance(handler, OutputHandler)
        assert handler.provider_name == "unknown_provider"

    def test_register_custom_handler(self):
        """Test registering custom handler."""

        class CustomHandler(OutputHandler):
            def __init__(self, provider_name: str):
                super().__init__(provider_name)

            def parse(self, response: str) -> ParsedResponse:
                return ParsedResponse(
                    text=response, code_blocks=[], metadata={"custom": True}
                )

            def extract_content(self, response: str) -> ExtractedContent:
                return ExtractedContent(
                    code_blocks=[],
                    text_sections=[response],
                    commands=[],
                    files={},
                    metadata={"custom": True},
                )

        OutputHandlerFactory.register("custom", CustomHandler)
        handler = OutputHandlerFactory.create("custom")

        assert isinstance(handler, CustomHandler)
        parsed = handler.parse("test")
        assert parsed.metadata["custom"] is True


class TestUtilityFunctions:
    """Test utility functions."""

    def test_extract_executable_code(self):
        """Test extraction of only executable code."""
        response = """
        ```python
        def main():
            print("Hello")
        ```
        
        ```text
        This is not executable
        ```
        
        ```bash
        echo "This is executable"
        ```
        """

        executable = extract_executable_code(response, "claude")

        assert len(executable) == 2
        assert any("def main" in code for code in executable)
        assert any("echo" in code for code in executable)
        assert not any("not executable" in code for code in executable)

    def test_format_code_for_execution_python(self):
        """Test formatting Python code for execution."""
        code = """
def greet(name):
    print(f"Hello, {name}!")

def main():
    greet("World")
"""

        formatted = format_code_for_execution(code, "python", add_main=True)

        assert "if __name__ == '__main__':" in formatted
        assert "main()" in formatted

    def test_format_code_for_execution_no_functions(self):
        """Test formatting code without functions."""
        code = "print('Hello, World!')"

        formatted = format_code_for_execution(code, "python", add_main=True)

        # Should not add main for simple scripts
        assert code == formatted

    def test_merge_streaming_responses(self):
        """Test merging streaming chunks."""
        chunks = ["Here's the ", "code:\n```python\n", "print('Hello')\n", "```\nDone."]

        merged = merge_streaming_responses(chunks)

        assert merged.text == "Here's the code:\n```python\nprint('Hello')\n```\nDone."
        # Note: The base OutputHandler doesn't have parse method implemented
        # so we'd need to use a specific handler for full functionality


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
