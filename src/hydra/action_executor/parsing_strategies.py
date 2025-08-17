"""Parsing strategies for extracting actions from LLM responses.

This module documents and implements various strategies for parsing
structured actions from different LLM response formats.
"""

import json
import re
from typing import Any, Dict, List, Optional

from .types import Action, ActionType


class ParsingStrategy:
    """Base class for parsing strategies.

    Each strategy handles a specific response format or pattern
    for extracting actions from LLM output.
    """

    def extract_actions(self, response: str) -> List[Action]:
        """Extract actions from the response.

        Args:
            response: The LLM response text

        Returns:
            List of extracted actions

        """
        raise NotImplementedError


class CodeBlockStrategy(ParsingStrategy):
    """Strategy for parsing code blocks with file paths.

    Handles responses like:
    ```python
    # file: src/main.py
    def hello():
        return "world"
    ```

    Or:
    Create file src/main.py:
    ```python
    def hello():
        return "world"
    ```
    """

    # Regex patterns for different code block formats
    PATTERNS = {
        "markdown_with_header": re.compile(
            r"```(?P<lang>\w+)?\n#\s*file:\s*(?P<path>[^\\<>:\"|?*\n]+)\n(?P<content>.*?)```",
            re.DOTALL | re.MULTILINE,
        ),
        "create_file_instruction": re.compile(
            r"(?:Create|Write|Add)\s+(?:file\s+)?(?P<path>[^\\<>:\"|?*\n]+):\s*\n```(?:\w+)?\n(?P<content>.*?)```",
            re.DOTALL | re.MULTILINE | re.IGNORECASE,
        ),
        "modify_file_instruction": re.compile(
            r"(?:Modify|Update|Edit|Change)\s+(?:file\s+)?(?P<path>[^\\<>:\"|?*\n]+):\s*\n```(?:\w+)?\n(?P<content>.*?)```",
            re.DOTALL | re.MULTILINE | re.IGNORECASE,
        ),
        "file_path_comment": re.compile(
            r"```(?P<lang>\w+)?\n\s*(?://|#|--)\s*(?P<path>[^\\<>:\"|?*\n]+)\n(?P<content>.*?)```",
            re.DOTALL | re.MULTILINE,
        ),
        "simple_comment_pattern": re.compile(
            r"```(?P<lang>\w+)?\n\s*#\s*(?P<path>[^\\<>:\"|?*\n]+)\n(?P<content>.*?)```",
            re.DOTALL | re.MULTILINE,
        ),
    }

    def extract_actions(self, response: str) -> List[Action]:
        """Extract file creation/modification actions from code blocks."""
        actions = []

        # Find all individual code blocks by properly matching opening and closing backticks
        all_blocks = self._find_code_blocks(response)

        for lang, content in all_blocks:
            # Look for file path patterns in the first few lines of each block
            lines = content.split("\n")
            if not lines:
                continue

            # Check first line for path comment patterns
            first_line = lines[0].strip()
            path = None

            # Try different comment styles
            path_patterns = [
                r"^(?://|#|--)\s*(.+)$",  # Comment with path
                r"^#\s*file:\s*(.+)$",  # Explicit file: directive
                r"^(?://|#|--)\s*file:\s*(.+)$",  # Comment file: directive
            ]

            for pattern in path_patterns:
                match = re.match(pattern, first_line)
                if match:
                    path = match.group(1).strip()
                    break

            if path and not re.search(r'[\\<>:"|?*]', path):
                # Remove the path line from content
                remaining_content = "\n".join(lines[1:])

                # Determine action type (default to CREATE_FILE)
                action_type = ActionType.CREATE_FILE

                actions.append(
                    Action(
                        type=action_type,
                        target=path,
                        content=remaining_content,
                        metadata={"pattern": "code_block_with_path", "language": lang},
                    )
                )

        # Also try the legacy patterns for backward compatibility
        for pattern_name, pattern in self.PATTERNS.items():
            for match in pattern.finditer(response):
                path = match.group("path").strip()
                content = match.group("content")

                # Skip if we already found this path above
                if any(action.target == path for action in actions):
                    continue

                # Determine action type based on pattern
                if "create" in pattern_name.lower():
                    action_type = ActionType.CREATE_FILE
                elif "modify" in pattern_name.lower():
                    action_type = ActionType.MODIFY_FILE
                else:
                    action_type = ActionType.CREATE_FILE

                actions.append(
                    Action(
                        type=action_type,
                        target=path,
                        content=content,
                        metadata={"pattern": pattern_name},
                    )
                )

        return actions

    def _find_code_blocks(self, response: str) -> List[tuple]:
        """Find all code blocks by properly matching backticks."""
        blocks = []
        lines = response.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Look for opening ```
            if line.startswith("```"):
                # Extract language if present
                lang = line[3:].strip() if len(line) > 3 else ""

                # Find the matching closing ``` using depth counting
                content_lines = []
                j = i + 1
                depth = 1  # We found one opening ```

                while j < len(lines) and depth > 0:
                    current_line = lines[j].strip()

                    if current_line.startswith("```"):
                        if current_line == "```":
                            # This is a closing ```
                            depth -= 1
                        else:
                            # This is an opening ``` (has language or content)
                            depth += 1

                    if depth > 0:
                        content_lines.append(lines[j])
                    j += 1

                if depth == 0:
                    # Found properly matched closing backticks
                    blocks.append((lang, "\n".join(content_lines)))
                    i = j
                else:
                    # No matching closing backticks found, skip this block
                    i += 1
            else:
                i += 1

        return blocks


class CommandStrategy(ParsingStrategy):
    """Strategy for parsing shell commands.

    Handles responses like:
    - Run: npm install
    - Execute: pytest tests/
    - $ git add .
    - ```bash
      npm test
      ```
    """

    PATTERNS = {
        "run_instruction": re.compile(
            r"(?:Run|Execute|Exec):\s*(?P<cmd>.*?)(?:\n|$)", re.IGNORECASE
        ),
        "shell_prompt": re.compile(r"^\$\s+(?P<cmd>.+)$", re.MULTILINE),
        "bash_block": re.compile(r"```(?:bash|sh|shell)\n(?P<cmd>.*?)```", re.DOTALL),
        "install_instruction": re.compile(
            r"(?:Install|Add):\s*(?P<cmd>(?:npm|pip|yarn|cargo|gem|apt|brew).*?)(?:\n|$)",
            re.IGNORECASE,
        ),
    }

    def extract_actions(self, response: str) -> List[Action]:
        """Extract command execution actions."""
        actions = []

        for pattern_name, pattern in self.PATTERNS.items():
            for match in pattern.finditer(response):
                cmd = match.group("cmd").strip()

                # Split multi-line bash blocks into separate commands
                if pattern_name == "bash_block" and "\n" in cmd:
                    commands = [
                        line.strip()
                        for line in cmd.split("\n")
                        if line.strip() and not line.strip().startswith("#")
                    ]
                else:
                    commands = [cmd]

                for command in commands:
                    if "install" in pattern_name.lower():
                        action_type = ActionType.INSTALL_PACKAGE
                    else:
                        action_type = ActionType.RUN_COMMAND

                    actions.append(
                        Action(
                            type=action_type,
                            target=command,
                            metadata={"pattern": pattern_name},
                        )
                    )

        return actions


class JSONStrategy(ParsingStrategy):
    """Strategy for parsing JSON-formatted action lists.

    Handles responses that include structured JSON like:
    ```json
    {
        "actions": [
            {
                "type": "create_file",
                "path": "src/main.py",
                "content": "def hello(): pass"
            }
        ]
    }
    ```
    """

    def extract_actions(self, response: str) -> List[Action]:
        """Extract actions from JSON blocks."""
        actions = []

        # Find JSON blocks
        json_pattern = re.compile(r"```json\n(.*?)```", re.DOTALL)
        for match in json_pattern.finditer(response):
            try:
                data = json.loads(match.group(1))
                actions.extend(self._parse_json_actions(data))
            except json.JSONDecodeError:
                continue

        # Also try to parse the entire response as JSON
        try:
            data = json.loads(response)
            actions.extend(self._parse_json_actions(data))
        except (json.JSONDecodeError, ValueError):
            pass

        return actions

    def _parse_json_actions(self, data: Dict[str, Any]) -> List[Action]:
        """Parse actions from JSON data structure."""
        actions = []

        # Handle different JSON structures
        if isinstance(data, dict):
            if "actions" in data:
                action_list = data["actions"]
            elif "steps" in data:
                action_list = data["steps"]
            else:
                action_list = [data]
        elif isinstance(data, list):
            action_list = data
        else:
            return actions

        for item in action_list:
            if not isinstance(item, dict):
                continue

            # Map JSON fields to Action attributes
            action_type_str = item.get("type", "").upper().replace(" ", "_")
            try:
                action_type = ActionType[action_type_str]
            except KeyError:
                continue

            actions.append(
                Action(
                    type=action_type,
                    target=item.get("path", item.get("target", item.get("file", ""))),
                    content=item.get("content", item.get("code", None)),
                    options=item.get("options", {}),
                    metadata={"source": "json"},
                )
            )

        return actions


class DirectiveStrategy(ParsingStrategy):
    """Strategy for parsing directive-style instructions.

    Handles responses with clear action directives like:
    - CREATE FILE: src/main.py
    - DELETE: old_file.txt
    - MOVE: src/old.py -> src/new.py
    """

    DIRECTIVE_PATTERNS = [
        (
            re.compile(
                r"^(?P<action>CREATE|ADD|WRITE)\s+FILE:\s*(?P<target>[^\\<>:\"|?*\n]+)",
                re.MULTILINE | re.IGNORECASE,
            ),
            ActionType.CREATE_FILE,
        ),
        (
            re.compile(
                r"^(?P<action>MODIFY|UPDATE|EDIT)\s+FILE:\s*(?P<target>[^\\<>:\"|?*\n]+)",
                re.MULTILINE | re.IGNORECASE,
            ),
            ActionType.MODIFY_FILE,
        ),
        (
            re.compile(
                r"^(?P<action>DELETE|REMOVE)\s+(?:FILE:\s*)?(?P<target>[^\\<>:\"|?*\n]+)",
                re.MULTILINE | re.IGNORECASE,
            ),
            ActionType.DELETE_FILE,
        ),
        (
            re.compile(
                r"^(?P<action>MOVE|RENAME):\s*(?P<source>[^\\<>:\"|?*\n]+)\s*->\s*(?P<target>[^\\<>:\"|?*\n]+)",
                re.MULTILINE | re.IGNORECASE,
            ),
            ActionType.MOVE_FILE,
        ),
        (
            re.compile(
                r"^(?P<action>COPY):\s*(?P<source>[^\\<>:\"|?*\n]+)\s*->\s*(?P<target>[^\\<>:\"|?*\n]+)",
                re.MULTILINE | re.IGNORECASE,
            ),
            ActionType.COPY_FILE,
        ),
    ]

    def extract_actions(self, response: str) -> List[Action]:
        """Extract actions from directive instructions."""
        actions = []

        for pattern, action_type in self.DIRECTIVE_PATTERNS:
            for match in pattern.finditer(response):
                target = match.group("target")
                options = {}

                # Handle move/copy operations
                if "source" in match.groupdict():
                    options["source"] = match.group("source")

                # Look for content after the directive
                content = self._extract_content_after_directive(response, match.end())

                actions.append(
                    Action(
                        type=action_type,
                        target=target,
                        content=content,
                        options=options,
                        metadata={"directive": match.group("action")},
                    )
                )

        return actions

    def _extract_content_after_directive(
        self, response: str, start_pos: int
    ) -> Optional[str]:
        """Extract content that follows a directive."""
        # Look for code block or indented content after directive
        remaining = response[start_pos:]

        # Check for code block
        code_match = re.match(r"\s*```\w*\n(.*?)```", remaining, re.DOTALL)
        if code_match:
            return code_match.group(1)

        # Check for indented content
        lines = remaining.split("\n")
        content_lines = []
        for line in lines:
            if line.startswith("    ") or line.startswith("\t"):
                content_lines.append(line[4:] if line.startswith("    ") else line[1:])
            elif line.strip() == "":
                content_lines.append("")
            else:
                break

        if content_lines:
            return "\n".join(content_lines).strip()

        return None


class CompositeParsingStrategy(ParsingStrategy):
    """Composite strategy that combines multiple parsing strategies.

    This allows parsing responses that may contain multiple formats
    or mixed content types.
    """

    def __init__(self, strategies: Optional[List[ParsingStrategy]] = None) -> None:
        """Initialize with a list of strategies to use.

        Args:
            strategies: List of parsing strategies to apply

        """
        self.strategies = strategies or [
            CodeBlockStrategy(),
            CommandStrategy(),
            JSONStrategy(),
            DirectiveStrategy(),
        ]

    def extract_actions(self, response: str) -> List[Action]:
        """Extract actions using all registered strategies.

        Actions are deduplicated based on type and target.
        """
        all_actions = []
        seen = set()

        for strategy in self.strategies:
            actions = strategy.extract_actions(response)
            for action in actions:
                # Create a simple key for deduplication
                key = (action.type, action.target)
                if key not in seen:
                    seen.add(key)
                    all_actions.append(action)

        return all_actions
