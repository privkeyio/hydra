"""Response parser for extracting actions from LLM responses.

This module implements the main parser that extracts structured actions
from various LLM response formats including markdown, JSON, and directives.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .errors import ParseError, ValidationError
from .parsing_strategies import (
    CodeBlockStrategy,
    CommandStrategy,
    CompositeParsingStrategy,
    ParsingStrategy,
)
from .types import Action, ActionType

logger = logging.getLogger(__name__)


class ResponseParser:
    """Main parser for extracting actions from LLM responses.

    This parser supports multiple formats including:
    - Code blocks with file paths
    - Shell commands
    - JSON-structured actions
    - Directive-style instructions
    - Mixed-format responses

    Attributes:
        strategy: The parsing strategy to use
        validate_actions: Whether to validate parsed actions
        allow_dangerous: Whether to allow potentially dangerous actions
        max_actions: Maximum number of actions to extract per response

    """

    def __init__(
        self,
        strategy: Optional[ParsingStrategy] = None,
        validate_actions: bool = True,
        allow_dangerous: bool = False,
        max_actions: int = 100,
    ) -> None:
        """Initialize the response parser.

        Args:
            strategy: Custom parsing strategy to use
            validate_actions: Whether to validate parsed actions
            allow_dangerous: Whether to allow potentially dangerous actions
            max_actions: Maximum number of actions to extract

        """
        self.strategy = strategy or CompositeParsingStrategy()
        self.validate_actions = validate_actions
        self.allow_dangerous = allow_dangerous
        self.max_actions = max_actions

    def parse(self, response: str) -> List[Action]:
        """Parse a response and extract actions.

        Args:
            response: The LLM response text to parse

        Returns:
            List of extracted and validated actions

        Raises:
            ParseError: If parsing fails
            ValidationError: If validation fails

        """
        if not response or not response.strip():
            return []

        try:
            # Extract actions using the configured strategy
            actions = self.strategy.extract_actions(response)

            # Limit number of actions
            if len(actions) > self.max_actions:
                logger.warning(
                    f"Response contained {len(actions)} actions, limiting to {self.max_actions}"
                )
                actions = actions[: self.max_actions]

            # Validate actions if enabled
            if self.validate_actions:
                actions = self._validate_actions(actions)

            # Check for dangerous actions if not allowed
            if not self.allow_dangerous:
                actions = self._filter_dangerous_actions(actions)

            # Post-process actions
            actions = self._post_process_actions(actions)

            logger.info(f"Parsed {len(actions)} actions from response")
            return actions

        except Exception as e:
            raise ParseError(f"Failed to parse response: {e}", response=response) from e

    def parse_code_blocks(self, response: str) -> List[Tuple[str, str]]:
        """Parse code blocks with file paths from response.

        Args:
            response: The response containing code blocks

        Returns:
            List of (file_path, content) tuples

        """
        strategy = CodeBlockStrategy()
        actions = strategy.extract_actions(response)

        result = []
        for action in actions:
            if action.type in [ActionType.CREATE_FILE, ActionType.MODIFY_FILE]:
                result.append((action.target, action.content or ""))

        return result

    def extract_shell_commands(self, response: str) -> List[str]:
        """Extract shell commands from response.

        Args:
            response: The response containing shell commands

        Returns:
            List of shell command strings

        """
        strategy = CommandStrategy()
        actions = strategy.extract_actions(response)

        commands = []
        for action in actions:
            if action.type in [ActionType.RUN_COMMAND, ActionType.INSTALL_PACKAGE]:
                commands.append(action.target)

        return commands

    def supports_format(self, response: str) -> Dict[str, bool]:
        """Check which formats are present in the response.

        Args:
            response: The response to analyze

        Returns:
            Dictionary mapping format names to presence booleans

        """
        formats = {
            "code_blocks": bool(re.search(r"```[\w]*\n.*?```", response, re.DOTALL)),
            "json": bool(re.search(r"```json\n.*?```", response, re.DOTALL))
            or self._is_json_response(response),
            "shell_commands": bool(
                re.search(r"(?:Run|Execute|Exec):\s*", response, re.IGNORECASE)
                or re.search(r"^\$\s+", response, re.MULTILINE)
                or re.search(r"```(?:bash|sh|shell)\n", response)
            ),
            "directives": bool(
                re.search(
                    r"^(?:CREATE|MODIFY|DELETE|MOVE|COPY)\s+(?:FILE)?:",
                    response,
                    re.MULTILINE | re.IGNORECASE,
                )
            ),
        }

        return formats

    def _validate_actions(self, actions: List[Action]) -> List[Action]:
        """Validate a list of actions.

        Args:
            actions: Actions to validate

        Returns:
            List of valid actions

        Raises:
            ValidationError: If validation fails

        """
        validated = []

        for action in actions:
            try:
                # Validate required fields
                if not action.target:
                    raise ValidationError(f"Action {action.type.name} missing target")

                # Validate content for file operations
                if action.type in [
                    ActionType.CREATE_FILE,
                    ActionType.MODIFY_FILE,
                    ActionType.APPEND_FILE,
                    ActionType.REPLACE_IN_FILE,
                ] and action.content is None:
                    raise ValidationError(
                        f"Action {action.type.name} requires content for {action.target}"
                    )

                # Validate paths
                if action.type in [
                    ActionType.CREATE_FILE,
                    ActionType.MODIFY_FILE,
                    ActionType.DELETE_FILE,
                    ActionType.READ_FILE,
                ]:
                    self._validate_path(action.target)

                # Validate move/copy operations
                if action.type in [ActionType.MOVE_FILE, ActionType.COPY_FILE]:
                    if "source" not in action.options:
                        raise ValidationError(
                            f"Action {action.type.name} missing source in options"
                        )
                    self._validate_path(action.options["source"])
                    self._validate_path(action.target)

                validated.append(action)

            except ValidationError as e:
                logger.warning(f"Validation failed for action: {e}")
                if self.validate_actions:
                    raise

        return validated

    def _validate_path(self, path: str) -> None:
        """Validate a file path.

        Args:
            path: Path to validate

        Raises:
            ValidationError: If path is invalid

        """
        if not path:
            raise ValidationError("Empty path")

        # Check for dangerous path patterns
        dangerous_patterns = [
            r"^\.\.",  # Parent directory access
            r"^/etc",  # System configuration
            r"^/sys",  # System internals
            r"^/proc",  # Process information
            r"^~/\.",  # Hidden home files
            r"^\$",  # Environment variables
        ]

        for pattern in dangerous_patterns:
            if re.match(pattern, path):
                raise ValidationError(f"Potentially dangerous path: {path}")

        # Check for valid characters
        if not re.match(r"^[\w\-./~]+$", path):
            raise ValidationError(f"Invalid characters in path: {path}")

    def _filter_dangerous_actions(self, actions: List[Action]) -> List[Action]:
        """Filter out potentially dangerous actions.

        Args:
            actions: Actions to filter

        Returns:
            List of safe actions

        """
        safe_actions = []
        dangerous_types = {
            ActionType.DELETE_FILE,
            ActionType.DELETE_DIRECTORY,
            ActionType.GIT_PUSH,
            ActionType.GIT_MERGE,
        }

        dangerous_commands = [
            "rm -rf",
            "sudo",
            "chmod 777",
            "eval",
            "exec",
            "> /dev/",
        ]

        for action in actions:
            # Check for dangerous action types
            if action.type in dangerous_types and not self.allow_dangerous:
                logger.warning(
                    f"Filtering dangerous action: {action.type.name} on {action.target}"
                )
                continue

            # Check for dangerous commands
            if action.type == ActionType.RUN_COMMAND:
                command_lower = action.target.lower()
                if any(danger in command_lower for danger in dangerous_commands):
                    logger.warning(f"Filtering dangerous command: {action.target}")
                    continue

            safe_actions.append(action)

        return safe_actions

    def _post_process_actions(self, actions: List[Action]) -> List[Action]:
        """Post-process actions to normalize and enhance them.

        Args:
            actions: Actions to post-process

        Returns:
            List of processed actions

        """
        processed = []

        for action in actions:
            # Normalize file paths
            if action.type in [
                ActionType.CREATE_FILE,
                ActionType.MODIFY_FILE,
                ActionType.DELETE_FILE,
                ActionType.READ_FILE,
            ]:
                action.target = self._normalize_path(action.target)

            # Add default metadata
            if "source" not in action.metadata:
                action.metadata["source"] = "parser"

            # Detect and mark test-related actions
            if self._is_test_action(action):
                action.metadata["is_test"] = True

            # Detect and mark documentation actions
            if self._is_documentation_action(action):
                action.metadata["is_documentation"] = True

            processed.append(action)

        return processed

    def _normalize_path(self, path: str) -> str:
        """Normalize a file path.

        Args:
            path: Path to normalize

        Returns:
            Normalized path string

        """
        # Remove leading/trailing whitespace
        path = path.strip()

        # Remove leading ./ if present
        if path.startswith("./"):
            path = path[2:]

        # Normalize slashes
        path = re.sub(r"//+", "/", path)

        # Remove trailing slash for files
        if path.endswith("/") and "." in path.split("/")[-1]:
            path = path[:-1]

        return path

    def _is_json_response(self, response: str) -> bool:
        """Check if the response is valid JSON.

        Args:
            response: Response to check

        Returns:
            True if response is valid JSON

        """
        import json

        try:
            json.loads(response.strip())
            return True
        except (json.JSONDecodeError, ValueError):
            return False

    def _is_test_action(self, action: Action) -> bool:
        """Check if an action is test-related.

        Args:
            action: Action to check

        Returns:
            True if action is test-related

        """
        test_indicators = ["test", "spec", "pytest", "unittest", "jest", "mocha"]

        target_lower = action.target.lower()
        if any(indicator in target_lower for indicator in test_indicators):
            return True

        if action.type in [ActionType.RUN_TEST, ActionType.RUN_LINT]:
            return True

        return False

    def _is_documentation_action(self, action: Action) -> bool:
        """Check if an action is documentation-related.

        Args:
            action: Action to check

        Returns:
            True if action is documentation-related

        """
        doc_extensions = [".md", ".rst", ".txt", ".adoc"]
        doc_dirs = ["docs", "documentation", "doc"]

        target_lower = action.target.lower()

        # Check file extension
        if any(target_lower.endswith(ext) for ext in doc_extensions):
            return True

        # Check if in documentation directory
        if any(f"/{dir}/" in target_lower for dir in doc_dirs):
            return True

        # Check for README files
        if "readme" in target_lower:
            return True

        return False


class MultiFileParser:
    """Parser specifically for handling responses with multiple files.

    This parser can handle responses that create or modify multiple files
    in a single response, maintaining proper separation and context.
    """

    def __init__(self, parser: Optional[ResponseParser] = None) -> None:
        """Initialize the multi-file parser.

        Args:
            parser: Base parser to use for extraction

        """
        self.parser = parser or ResponseParser()

    def parse_files(self, response: str) -> Dict[str, Dict[str, Any]]:
        """Parse multiple files from a response.

        Args:
            response: Response containing multiple files

        Returns:
            Dictionary mapping file paths to file info

        """
        actions = self.parser.parse(response)
        files = {}

        for action in actions:
            if action.type in [ActionType.CREATE_FILE, ActionType.MODIFY_FILE]:
                files[action.target] = {
                    "content": action.content or "",
                    "action": action.type.name,
                    "metadata": action.metadata,
                }

        return files

    def group_by_directory(
        self, response: str
    ) -> Dict[str, List[Tuple[str, str]]]:
        """Group parsed files by directory.

        Args:
            response: Response containing files

        Returns:
            Dictionary mapping directories to list of (filename, content) tuples

        """
        import os

        files = self.parse_files(response)
        grouped = {}

        for filepath, info in files.items():
            directory = os.path.dirname(filepath) or "."
            filename = os.path.basename(filepath)

            if directory not in grouped:
                grouped[directory] = []

            grouped[directory].append((filename, info["content"]))

        return grouped
