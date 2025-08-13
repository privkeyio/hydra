"""Provider output handling and code extraction utilities.

This module provides enhanced output parsing and code extraction capabilities
for different LLM providers, building on the BaseProvider interface.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from hydra.providers.base_provider import CodeBlock, ParsedResponse


class OutputFormat(Enum):
    """Output format types."""

    TEXT = "text"
    CODE = "code"
    MARKDOWN = "markdown"
    JSON = "json"
    INTERACTIVE = "interactive"
    STREAMED = "streamed"


class CodeLanguage(Enum):
    """Common programming languages for code blocks."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    BASH = "bash"
    SQL = "sql"
    HTML = "html"
    CSS = "css"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    TEXT = "text"


@dataclass
class ExtractedContent:
    """Container for extracted content from responses."""

    code_blocks: List[CodeBlock]
    text_sections: List[str]
    commands: List[str]  # Shell commands to execute
    files: Dict[str, str]  # Filename -> content mapping
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamingBuffer:
    """Buffer for accumulating streaming responses."""

    content: str = ""
    partial_block: Optional[str] = None
    in_code_block: bool = False
    current_language: Optional[str] = None

    def append(self, chunk: str) -> None:
        """Append chunk to buffer."""
        self.content += chunk

    def get_complete_blocks(self) -> List[CodeBlock]:
        """Extract any complete code blocks from buffer."""
        blocks = []
        # Look for complete code blocks
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.finditer(pattern, self.content, re.DOTALL)

        for match in matches:
            language = match.group(1) or "text"
            content = match.group(2).strip()

            blocks.append(CodeBlock(
                language=language,
                content=content,
                line_start=0,
                line_end=0,
                executable=self._is_executable(language)
            ))

        return blocks

    @staticmethod
    def _is_executable(language: str) -> bool:
        """Check if language is executable."""
        executable_langs = {
            "python", "py", "javascript", "js", "bash", "sh",
            "ruby", "go", "rust", "java", "cpp", "c"
        }
        return language.lower() in executable_langs


class OutputHandler(ABC):
    """Abstract base class for provider-specific output handlers."""

    def __init__(self, provider_name: str):
        """Initialize output handler.

        Args:
            provider_name: Name of the provider

        """
        self.provider_name = provider_name
        self.streaming_buffer = StreamingBuffer()

    @abstractmethod
    def parse(self, response: str) -> ParsedResponse:
        """Parse provider response into structured format.

        Args:
            response: Raw response from provider

        Returns:
            Parsed response with metadata

        """
        pass

    @abstractmethod
    def extract_content(self, response: str) -> ExtractedContent:
        """Extract all content types from response.

        Args:
            response: Response text

        Returns:
            Extracted content container

        """
        pass

    def extract_code_blocks(self, text: str) -> List[CodeBlock]:
        """Extract code blocks from text.

        Args:
            text: Text containing code blocks

        Returns:
            List of extracted code blocks

        """
        blocks = []

        # Standard markdown code blocks
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.finditer(pattern, text, re.DOTALL)

        for match in matches:
            language = match.group(1) or "text"
            content = match.group(2).strip()

            blocks.append(CodeBlock(
                language=language,
                content=content,
                line_start=text[:match.start()].count('\n') + 1,
                line_end=text[:match.end()].count('\n') + 1,
                executable=self._is_executable_language(language),
                filename=self._extract_filename(content, language)
            ))

        # Also look for inline code if no blocks found
        if not blocks:
            blocks.extend(self._extract_inline_code(text))

        return blocks

    def _extract_inline_code(self, text: str) -> List[CodeBlock]:
        """Extract inline code patterns.

        Args:
            text: Text to search

        Returns:
            List of code blocks

        """
        blocks = []

        # Common code patterns
        patterns = {
            "python": [
                r'(def\s+\w+.*?(?:\n\n|\Z))',
                r'(class\s+\w+.*?(?:\n\n|\Z))',
                r'(import\s+.*?(?:\n|$))',
                r'(from\s+\w+\s+import.*?(?:\n|$))'
            ],
            "javascript": [
                r'(function\s+\w+.*?\})',
                r'(const\s+\w+\s*=.*?(?:;|\n))',
                r'(var\s+\w+\s*=.*?(?:;|\n))',
                r'(let\s+\w+\s*=.*?(?:;|\n))'
            ]
        }

        for language, lang_patterns in patterns.items():
            for pattern in lang_patterns:
                matches = re.finditer(pattern, text, re.MULTILINE | re.DOTALL)
                for match in matches:
                    blocks.append(CodeBlock(
                        language=language,
                        content=match.group(1).strip(),
                        line_start=text[:match.start()].count('\n') + 1,
                        line_end=text[:match.end()].count('\n') + 1,
                        executable=True
                    ))

        return blocks

    def _is_executable_language(self, language: str) -> bool:
        """Check if a language is executable.

        Args:
            language: Language identifier

        Returns:
            True if language is executable

        """
        executable = {
            "python", "py", "python3",
            "javascript", "js", "node",
            "typescript", "ts",
            "bash", "sh", "shell", "zsh",
            "ruby", "rb",
            "go", "golang",
            "rust", "rs",
            "java",
            "c", "cpp", "c++",
            "php",
            "perl",
            "lua"
        }
        return language.lower() in executable

    def _extract_filename(self, content: str, language: str) -> Optional[str]:
        """Try to extract filename from code content or comments.

        Args:
            content: Code content
            language: Programming language

        Returns:
            Filename if found

        """
        # Look for filename in first line comment
        patterns = [
            r'^#\s*(?:filename|file):\s*(.+)$',  # Python/Bash style
            r'^//\s*(?:filename|file):\s*(.+)$',  # C/JS style
            r'^/\*\s*(?:filename|file):\s*(.+)\s*\*/$',  # Block comment
        ]

        first_line = content.split('\n')[0] if content else ""

        for pattern in patterns:
            match = re.match(pattern, first_line.strip())
            if match:
                return match.group(1).strip()

        # Try to infer from content
        if language in ["python", "py"]:
            if "def main(" in content or "__main__" in content:
                return "main.py"
            elif "def test_" in content:
                return "test.py"
        elif language in ["javascript", "js"]:
            if "module.exports" in content:
                return "index.js"
            elif "export default" in content:
                return "module.js"

        return None

    def extract_commands(self, text: str) -> List[str]:
        """Extract shell commands from text.

        Args:
            text: Text containing commands

        Returns:
            List of commands

        """
        commands = []

        # Look for command patterns line by line
        lines = text.split('\n')
        for line in lines:
            # Shell prompt patterns
            if line.strip().startswith('$ '):
                commands.append(line.strip()[2:].strip())
            elif line.strip().startswith('> '):
                commands.append(line.strip()[2:].strip())

        # Also look for bash code blocks
        bash_pattern = r'```(?:bash|sh|shell)\n(.*?)```'
        matches = re.finditer(bash_pattern, text, re.DOTALL)
        for match in matches:
            # Split into individual commands
            block_commands = match.group(1).strip().split('\n')
            commands.extend([
                cmd.strip() for cmd in block_commands
                if cmd.strip() and not cmd.strip().startswith('#')
            ])

        return commands

    def format_code_block(
        self,
        code: str,
        language: str,
        filename: Optional[str] = None
    ) -> str:
        """Format code into a markdown code block.

        Args:
            code: Code content
            language: Programming language
            filename: Optional filename

        Returns:
            Formatted markdown code block

        """
        header = f"```{language}"
        if filename:
            header = f"```{language} # {filename}"

        return f"{header}\n{code}\n```"

    def handle_streaming_chunk(self, chunk: str) -> Optional[ParsedResponse]:
        """Handle a streaming response chunk.

        Args:
            chunk: Streaming chunk

        Returns:
            Parsed response if a complete unit is available

        """
        self.streaming_buffer.append(chunk)

        # Check if we have complete blocks
        blocks = self.streaming_buffer.get_complete_blocks()
        if blocks:
            return ParsedResponse(
                text=self.streaming_buffer.content,
                code_blocks=blocks,
                metadata={"streaming": True, "partial": True}
            )

        return None

    def finalize_streaming(self) -> ParsedResponse:
        """Finalize streaming and return complete response.

        Returns:
            Final parsed response

        """
        response = self.parse(self.streaming_buffer.content)
        response.metadata["streaming"] = True
        response.metadata["complete"] = True

        # Reset buffer
        self.streaming_buffer = StreamingBuffer()

        return response


class ClaudeOutputHandler(OutputHandler):
    """Output handler for Claude Code interactive responses."""

    def __init__(self):
        """Initialize Claude output handler."""
        super().__init__("claude")

    def parse(self, response: str) -> ParsedResponse:
        """Parse Claude Code response.

        Args:
            response: Raw response from Claude

        Returns:
            Parsed response

        """
        code_blocks = self.extract_code_blocks(response)

        # Extract Claude-specific metadata
        metadata = self._extract_claude_metadata(response)

        return ParsedResponse(
            text=response,
            code_blocks=code_blocks,
            metadata=metadata
        )

    def extract_content(self, response: str) -> ExtractedContent:
        """Extract all content from Claude response.

        Args:
            response: Response text

        Returns:
            Extracted content

        """
        code_blocks = self.extract_code_blocks(response)
        commands = self.extract_commands(response)
        files = self._extract_file_operations(response)
        text_sections = self._extract_text_sections(response)

        return ExtractedContent(
            code_blocks=code_blocks,
            text_sections=text_sections,
            commands=commands,
            files=files,
            metadata=self._extract_claude_metadata(response)
        )

    def _extract_claude_metadata(self, response: str) -> Dict[str, Any]:
        """Extract Claude-specific metadata.

        Args:
            response: Response text

        Returns:
            Metadata dictionary

        """
        metadata = {
            "provider": "claude",
            "interactive": True,
            "has_file_operations": False,
            "has_commands": False
        }

        # Check for file operations
        file_operations = ["Writing", "Creating", "Editing", "Reading"]
        if any(op in response for op in file_operations):
            metadata["has_file_operations"] = True

        # Check for commands
        if "Running" in response or "Executing" in response:
            metadata["has_commands"] = True

        # Extract tool usage
        tools_used = []
        tool_patterns = [
            r'Using (\w+) tool',
            r'(\w+) tool:',
            r'<(\w+)>',  # XML-style tool tags
        ]

        for pattern in tool_patterns:
            matches = re.finditer(pattern, response)
            for match in matches:
                tool = match.group(1)
                if tool not in tools_used:
                    tools_used.append(tool)

        if tools_used:
            metadata["tools_used"] = tools_used

        return metadata

    def _extract_file_operations(self, response: str) -> Dict[str, str]:
        """Extract file operations from Claude response.

        Args:
            response: Response text

        Returns:
            Dictionary of filename -> content

        """
        files = {}

        # More flexible patterns for file creation/writing
        lines = response.split('\n')
        current_file = None
        in_code_block = False
        code_content = []

        for _i, line in enumerate(lines):
            # Check for file operation indicators
            if not in_code_block:
                file_match = re.match(
                    r'(?:Writing|Creating|Editing)\s+(?:file\s+)?([^\s:]+):?\s*$',
                    line.strip(),
                    re.IGNORECASE
                )
                if file_match:
                    current_file = file_match.group(1).strip()
                    # Look for code block on next lines
                    continue

                # Check for start of code block
                if line.strip().startswith('```') and current_file:
                    in_code_block = True
                    code_content = []
                    continue
            else:
                # In code block
                if line.strip().startswith('```'):
                    # End of code block
                    if current_file and code_content:
                        files[current_file] = '\n'.join(code_content)
                    in_code_block = False
                    current_file = None
                    code_content = []
                else:
                    code_content.append(line)

        return files

    def _extract_text_sections(self, response: str) -> List[str]:
        """Extract non-code text sections.

        Args:
            response: Response text

        Returns:
            List of text sections

        """
        # Remove code blocks
        text = re.sub(r'```.*?```', '', response, flags=re.DOTALL)

        # Split into paragraphs
        sections = []
        paragraphs = text.split('\n\n')

        for para in paragraphs:
            para = para.strip()
            if para and len(para) > 20:  # Filter out short fragments
                sections.append(para)

        return sections


class VeniceOutputHandler(OutputHandler):
    """Output handler for Venice AI text responses."""

    def __init__(self):
        """Initialize Venice output handler."""
        super().__init__("venice")

    def parse(self, response: str) -> ParsedResponse:
        """Parse Venice response.

        Args:
            response: Raw response from Venice

        Returns:
            Parsed response

        """
        # Venice responses need more aggressive code extraction
        code_blocks = self._extract_venice_code(response)

        return ParsedResponse(
            text=response,
            code_blocks=code_blocks,
            metadata={
                "provider": "venice",
                "requires_code_extraction": True
            }
        )

    def extract_content(self, response: str) -> ExtractedContent:
        """Extract all content from Venice response.

        Args:
            response: Response text

        Returns:
            Extracted content

        """
        code_blocks = self._extract_venice_code(response)
        commands = self.extract_commands(response)
        files = self._extract_implied_files(response, code_blocks)
        text_sections = self._extract_explanations(response)

        return ExtractedContent(
            code_blocks=code_blocks,
            text_sections=text_sections,
            commands=commands,
            files=files,
            metadata={"provider": "venice", "model": "varies"}
        )

    def _extract_venice_code(self, response: str) -> List[CodeBlock]:
        """Extract code from Venice response with enhanced detection.

        Args:
            response: Response text

        Returns:
            List of code blocks

        """
        blocks = self.extract_code_blocks(response)

        # If no explicit blocks, try to detect code patterns
        if not blocks:
            blocks = self._detect_implicit_code(response)

        return blocks

    def _detect_implicit_code(self, text: str) -> List[CodeBlock]:
        """Detect code that isn't in explicit blocks.

        Args:
            text: Text to analyze

        Returns:
            List of detected code blocks

        """
        blocks = []
        lines = text.split('\n')

        # Track code sections
        in_code = False
        code_lines = []
        code_language = "text"

        for line in lines:
            # Detect code start patterns
            if not in_code:
                if self._is_code_line(line):
                    in_code = True
                    code_language = self._detect_language(line)
                    code_lines = [line]
            else:
                # Check if we're still in code
                if line.strip() == "" and code_lines:
                    # Empty line might be part of code
                    code_lines.append(line)
                elif self._is_code_line(line) or self._is_continuation(line):
                    code_lines.append(line)
                else:
                    # End of code section
                    if code_lines:
                        blocks.append(CodeBlock(
                            language=code_language,
                            content='\n'.join(code_lines),
                            line_start=0,
                            line_end=0,
                            executable=self._is_executable_language(code_language)
                        ))
                    in_code = False
                    code_lines = []

        # Handle remaining code
        if code_lines:
            blocks.append(CodeBlock(
                language=code_language,
                content='\n'.join(code_lines),
                line_start=0,
                line_end=0,
                executable=self._is_executable_language(code_language)
            ))

        return blocks

    def _is_code_line(self, line: str) -> bool:
        """Check if a line looks like code.

        Args:
            line: Line to check

        Returns:
            True if line appears to be code

        """
        indicators = [
            r'^\s*def\s+\w+',  # Python function
            r'^\s*class\s+\w+',  # Python/Java class
            r'^\s*import\s+',  # Import statement
            r'^\s*from\s+\w+\s+import',  # Python import
            r'^\s*function\s+\w+',  # JavaScript function
            r'^\s*const\s+\w+\s*=',  # JS const
            r'^\s*var\s+\w+\s*=',  # JS var
            r'^\s*let\s+\w+\s*=',  # JS let
            r'^\s*if\s*\(',  # If statement
            r'^\s*for\s*\(',  # For loop
            r'^\s*while\s*\(',  # While loop
            r'^\s*return\s+',  # Return statement
        ]

        return any(re.match(pattern, line) for pattern in indicators)

    def _is_continuation(self, line: str) -> bool:
        """Check if line is continuation of code.

        Args:
            line: Line to check

        Returns:
            True if line continues code

        """
        # Indented lines are usually continuations
        if line.startswith('    ') or line.startswith('\t'):
            return True

        # Lines starting with operators
        if line.strip().startswith(('.', '+', '-', '*', '/', '|', '&')):
            return True

        return False

    def _detect_language(self, line: str) -> str:
        """Detect programming language from line.

        Args:
            line: Code line

        Returns:
            Detected language

        """
        # Python patterns
        if re.search(r'\bdef\s+\w+', line) or re.search(r'\bimport\s+', line) or re.search(r'\bfrom\s+\w+\s+import', line):
            return "python"
        # JavaScript patterns
        elif re.search(r'\bfunction\s+\w+', line) or re.search(r'\bconst\s+\w+\s*=', line) or re.search(r'\bvar\s+\w+\s*=', line) or re.search(r'\blet\s+\w+\s*=', line):
            return "javascript"
        # Java patterns
        elif re.search(r'\bclass\s+\w+.*\{', line):
            return "java"
        # C/C++ patterns
        elif '#include' in line or 'int main' in line:
            return "c"

        return "text"

    def _extract_implied_files(
        self,
        response: str,
        code_blocks: List[CodeBlock]
    ) -> Dict[str, str]:
        """Extract implied file contents from response.

        Args:
            response: Response text
            code_blocks: Extracted code blocks

        Returns:
            Dictionary of filename -> content

        """
        files = {}

        # Look for file references
        file_pattern = r'(?:create|write|save|in)\s+(?:file\s+)?`?([^\s`]+\.\w+)`?'
        matches = re.finditer(file_pattern, response, re.IGNORECASE)

        filenames = []
        for match in matches:
            filename = match.group(1)
            if '/' not in filename:  # Simple filename
                filenames.append(filename)

        # Try to match filenames with code blocks
        for i, block in enumerate(code_blocks):
            if block.filename:
                files[block.filename] = block.content
            elif i < len(filenames):
                files[filenames[i]] = block.content
            elif len(code_blocks) == 1 and filenames:
                # Single block, multiple files mentioned - use first
                files[filenames[0]] = block.content

        return files

    def _extract_explanations(self, response: str) -> List[str]:
        """Extract explanation text from response.

        Args:
            response: Response text

        Returns:
            List of explanation sections

        """
        # Remove code blocks
        text = re.sub(r'```.*?```', '', response, flags=re.DOTALL)

        # Remove inline code
        text = re.sub(r'`[^`]+`', '', text)

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Group into sections
        sections = []
        current_section = []

        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                current_section.append(sentence)
                # Start new section after certain markers
                if any(marker in sentence for marker in [':', 'following', 'below']):
                    if current_section:
                        sections.append(' '.join(current_section))
                        current_section = []

        if current_section:
            sections.append(' '.join(current_section))

        return sections


class OutputHandlerFactory:
    """Factory for creating provider-specific output handlers."""

    _handlers = {
        "claude": ClaudeOutputHandler,
        "claude_tmux": ClaudeOutputHandler,
        "venice": VeniceOutputHandler,
    }

    @classmethod
    def create(cls, provider_name: str) -> OutputHandler:
        """Create output handler for provider.

        Args:
            provider_name: Name of the provider

        Returns:
            Output handler instance

        Raises:
            ValueError: If provider not supported

        """
        handler_class = cls._handlers.get(provider_name)

        if not handler_class:
            # Default to base handler
            class DefaultHandler(OutputHandler):
                def __init__(self):
                    super().__init__(provider_name)

                def parse(self, response: str) -> ParsedResponse:
                    return ParsedResponse(
                        text=response,
                        code_blocks=self.extract_code_blocks(response),
                        metadata={"provider": provider_name}
                    )

                def extract_content(self, response: str) -> ExtractedContent:
                    return ExtractedContent(
                        code_blocks=self.extract_code_blocks(response),
                        text_sections=[response],
                        commands=self.extract_commands(response),
                        files={},
                        metadata={"provider": provider_name}
                    )

            return DefaultHandler()

        return handler_class(provider_name)

    @classmethod
    def register(cls, provider_name: str, handler_class: type) -> None:
        """Register a new handler class.

        Args:
            provider_name: Provider name
            handler_class: Handler class

        """
        cls._handlers[provider_name] = handler_class


# Utility functions for common operations
def extract_executable_code(response: str, provider: str = "unknown") -> List[str]:
    """Extract only executable code from response.

    Args:
        response: Response text
        provider: Provider name

    Returns:
        List of executable code strings

    """
    handler = OutputHandlerFactory.create(provider)
    content = handler.extract_content(response)

    executable = []
    for block in content.code_blocks:
        if block.executable:
            executable.append(block.content)

    return executable


def format_code_for_execution(
    code: str,
    language: str,
    add_main: bool = True
) -> str:
    """Format code for execution.

    Args:
        code: Code to format
        language: Programming language
        add_main: Whether to add main block if missing

    Returns:
        Formatted executable code

    """
    if language in ["python", "py"]:
        if add_main and "if __name__" not in code:
            # Add main block
            lines = code.split('\n')
            # Find where to add main
            for _i, line in enumerate(lines):
                if line.strip() and not line.startswith(('import', 'from', '#')):
                    break

            # Check if we have function definitions
            has_functions = any('def ' in line for line in lines)

            if has_functions:
                # Add main block that calls the first function
                func_match = re.search(r'def\s+(\w+)\s*\(', code)
                if func_match:
                    func_name = func_match.group(1)
                    lines.append("")
                    lines.append("if __name__ == '__main__':")
                    lines.append(f"    {func_name}()")
                    code = '\n'.join(lines)

    return code


def merge_streaming_responses(chunks: List[str]) -> ParsedResponse:
    """Merge streaming chunks into final response.

    Args:
        chunks: List of streaming chunks

    Returns:
        Merged parsed response

    """
    full_text = ''.join(chunks)

    # Use a simple implementation for merging
    # Extract code blocks from merged text
    code_blocks = []
    pattern = r'```(\w+)?\n(.*?)```'
    matches = re.finditer(pattern, full_text, re.DOTALL)

    for match in matches:
        language = match.group(1) or "text"
        content = match.group(2).strip()

        code_blocks.append(CodeBlock(
            language=language,
            content=content,
            line_start=full_text[:match.start()].count('\n') + 1,
            line_end=full_text[:match.end()].count('\n') + 1,
            executable=language.lower() in {
                "python", "py", "javascript", "js", "bash", "sh",
                "ruby", "go", "rust", "java", "cpp", "c"
            }
        ))

    return ParsedResponse(
        text=full_text,
        code_blocks=code_blocks,
        metadata={"merged_from_stream": True}
    )
