"""Generic prompt and response handlers for AI providers."""
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol


class PromptTemplate(Protocol):
    """Protocol for prompt templates."""

    def format(self, **kwargs) -> str:
        """Format the template with given parameters."""
        ...


class SimplePromptTemplate:
    """Simple string-based prompt template."""

    def __init__(self, template: str):
        self.template = template

    def format(self, **kwargs) -> str:
        """Format template using string formatting."""
        return self.template.format(**kwargs)


class ResponseParser(ABC):
    """Abstract base class for response parsers."""

    @abstractmethod
    def parse(self, response: str) -> Dict[str, Any]:
        """Parse a response string into structured data."""
        pass


class JSONResponseParser(ResponseParser):
    """Parser for JSON responses."""

    def parse(self, response: str) -> Dict[str, Any]:
        """Parse JSON from response."""
        import json

        # Try to find JSON in the response
        json_pattern = r'\{.*\}'
        match = re.search(json_pattern, response, re.DOTALL)

        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return response as is
        return {"response": response}


class CodeBlockResponseParser(ResponseParser):
    """Parser for responses containing code blocks."""

    def parse(self, response: str) -> Dict[str, Any]:
        """Extract code blocks from response."""
        code_pattern = r'```(\w+)?\n(.*?)\n```'
        matches = re.findall(code_pattern, response, re.DOTALL)

        code_blocks = []
        for language, code in matches:
            code_blocks.append({
                "language": language or "text",
                "code": code.strip()
            })

        return {
            "response": response,
            "code_blocks": code_blocks
        }


class GenericPromptHandler:
    """Generic handler for prompts across different AI providers."""

    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {}
        self.response_parsers: Dict[str, ResponseParser] = {}

    def register_template(self, name: str, template: PromptTemplate):
        """Register a prompt template."""
        self.templates[name] = template

    def register_response_parser(self, name: str, parser: ResponseParser):
        """Register a response parser."""
        self.response_parsers[name] = parser

    def format_prompt(self, template_name: str, **kwargs) -> str:
        """Format a prompt using a registered template."""
        if template_name not in self.templates:
            raise ValueError(f"Unknown template: {template_name}")

        return self.templates[template_name].format(**kwargs)

    def parse_response(self, parser_name: str, response: str) -> Dict[str, Any]:
        """Parse a response using a registered parser."""
        if parser_name not in self.response_parsers:
            raise ValueError(f"Unknown parser: {parser_name}")

        return self.response_parsers[parser_name].parse(response)


class UniversalPromptDetector:
    """Universal prompt detection system for various AI tools."""

    def __init__(self):
        self.patterns: Dict[str, List[str]] = {}
        self.response_strategies: Dict[str, str] = {}

    def add_pattern(self, tool_name: str, patterns: List[str], strategy: str = "prompt_user"):
        """Add patterns for a specific AI tool."""
        self.patterns[tool_name] = patterns
        self.response_strategies[tool_name] = strategy

    def detect_prompt(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text contains a recognizable AI tool prompt."""
        for tool_name, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return {
                        "tool": tool_name,
                        "pattern": pattern,
                        "strategy": self.response_strategies[tool_name],
                        "text": text
                    }
        return None

    def get_response_strategy(self, detection: Dict[str, Any]) -> str:
        """Get the response strategy for a detected prompt."""
        return detection.get("strategy", "prompt_user")


# Pre-configured handlers
def create_default_prompt_handler() -> GenericPromptHandler:
    """Create a prompt handler with default templates and parsers."""
    handler = GenericPromptHandler()

    # Register common templates
    handler.register_template(
        "code_generation",
        SimplePromptTemplate("""
Create {language} code for the following task:
{task}

Requirements:
{requirements}

Please provide only the code without additional explanations.
""".strip())
    )

    handler.register_template(
        "file_operation",
        SimplePromptTemplate("""
Perform the following file operation:
Action: {action}
File: {file_path}
Content: {content}

Use appropriate tools to complete this task.
""".strip())
    )

    # Register response parsers
    handler.register_response_parser("json", JSONResponseParser())
    handler.register_response_parser("code", CodeBlockResponseParser())

    return handler


def create_default_prompt_detector() -> UniversalPromptDetector:
    """Create a prompt detector with common AI tool patterns."""
    detector = UniversalPromptDetector()

    # Claude Code patterns
    claude_patterns = [
        r"Welcome to Claude",
        r"Claude Code",
        r"Assistant:",
        r"don't ask again",
        r"Yes, looks good",
        r"tell Claude what to do"
    ]
    detector.add_pattern("claude_code", claude_patterns, "auto_approve_safe")

    # Git operation patterns (safety-critical)
    git_patterns = [
        r"git commit",
        r"git push",
        r"git merge",
        r"git rebase",
        r"git reset",
        r"force push"
    ]
    detector.add_pattern("git", git_patterns, "deny_unsafe")

    # Generic confirmation patterns
    confirmation_patterns = [
        r"\(y/n\)",
        r"\(yes/no\)",
        r"Continue\?",
        r"Proceed\?",
        r"overwrite"
    ]
    detector.add_pattern("confirmation", confirmation_patterns, "prompt_user")

    return detector
