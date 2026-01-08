"""Universal prompt detection system for interactive AI tools.

This module provides a configurable prompt detection engine that can identify
and respond to various AI tool prompts using pattern matching and response strategies.
"""

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Set

import yaml

# from ..config_system.config_manager import ConfigManager
# ConfigManager was removed - using direct config loading instead


class ResponseStrategy(Enum):
    """Enumeration of response strategies for detected prompts."""

    AUTO_APPROVE = "auto_approve"
    DENY = "deny"
    PROMPT_USER = "prompt_user"
    CUSTOM_RESPONSE = "custom_response"
    LEARN = "learn"


class MatchType(Enum):
    """Enumeration of pattern matching types."""

    REGEX = "regex"
    LITERAL = "literal"
    SUBSTRING = "substring"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"


@dataclass
class PromptPattern:
    """Configuration for a prompt pattern."""

    name: str
    pattern: str
    match_type: MatchType
    response_strategy: ResponseStrategy
    response_text: Optional[str] = None
    confidence_threshold: float = 0.8
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    safety_override: bool = False

    def __post_init__(self):
        if isinstance(self.match_type, str):
            self.match_type = MatchType(self.match_type)
        if isinstance(self.response_strategy, str):
            self.response_strategy = ResponseStrategy(self.response_strategy)
        if isinstance(self.tags, list):
            self.tags = set(self.tags)


@dataclass
class DetectionResult:
    """Result of prompt detection."""

    matched: bool
    pattern: Optional[PromptPattern] = None
    confidence: float = 0.0
    match_groups: List[str] = field(default_factory=list)
    suggested_response: Optional[str] = None
    requires_user_input: bool = False
    safety_blocked: bool = False


class PromptDetector:
    """Universal prompt detection engine with configurable patterns."""

    def __init__(
        self,
        config_manager: Optional[Any] = None,  # ConfigManager removed from system
        patterns_dir: Optional[Path] = None,
        enable_learning: bool = True,
    ):
        """Initialize the prompt detector.

        Args:
            config_manager: Configuration manager instance (deprecated)
            patterns_dir: Directory containing pattern configuration files
            enable_learning: Whether to enable learning mode for new patterns

        """
        self.config_manager = None  # ConfigManager no longer used
        self.patterns_dir = patterns_dir or Path.cwd() / ".hydra" / "patterns"
        self.enable_learning = enable_learning

        # Pattern storage
        self._patterns: Dict[str, PromptPattern] = {}
        self._compiled_patterns: Dict[str, Pattern] = {}

        # Learning mode data
        self._learning_buffer: List[Dict[str, Any]] = []
        self._unknown_prompts: Set[str] = set()

        # Statistics
        self._stats = {
            "total_detections": 0,
            "successful_matches": 0,
            "learning_captures": 0,
            "safety_blocks": 0,
        }

        # Load patterns
        self._load_all_patterns()

    def _load_all_patterns(self):
        """Load all pattern configurations from files."""
        self.patterns_dir.mkdir(parents=True, exist_ok=True)

        # Load built-in patterns
        self._load_builtin_patterns()

        # Load custom patterns from configuration files
        for pattern_file in self.patterns_dir.glob("*.yaml"):
            self._load_pattern_file(pattern_file)

        for pattern_file in self.patterns_dir.glob("*.yml"):
            self._load_pattern_file(pattern_file)

        for pattern_file in self.patterns_dir.glob("*.json"):
            self._load_pattern_file(pattern_file)

    def _load_builtin_patterns(self):
        """Load built-in patterns for common AI tools."""
        builtin_patterns = {
            "claude_permission_request": {
                "name": "claude_permission_request",
                "pattern": (
                    r"Do you want me to proceed\?|Should I continue.*\?|"
                    r"Would you like me to.*\?|May I proceed"
                ),
                "match_type": "regex",
                "response_strategy": "prompt_user",
                "tags": ["claude", "permission", "interactive"],
                "metadata": {"tool": "claude", "category": "permission"},
            },
            "claude_file_creation": {
                "name": "claude_file_creation",
                "pattern": r"I need to create.*file|Should I create.*file",
                "match_type": "regex",
                "response_strategy": "auto_approve",
                "response_text": "yes",
                "tags": ["claude", "file_operation"],
                "metadata": {"tool": "claude", "category": "file_ops"},
            },
            "git_confirmation": {
                "name": "git_confirmation",
                "pattern": r"git.*commit|git.*push|git.*merge",
                "match_type": "regex",
                "response_strategy": "deny",
                "safety_override": True,
                "tags": ["git", "dangerous"],
                "metadata": {
                    "tool": "git",
                    "category": "version_control",
                    "danger_level": "high",
                },
            },
            "tmux_session_prompt": {
                "name": "tmux_session_prompt",
                "pattern": "[tmux]",
                "match_type": "substring",
                "response_strategy": "auto_approve",
                "response_text": "y",
                "tags": ["tmux", "session"],
                "metadata": {"tool": "tmux", "category": "session_management"},
            },
            "generic_yes_no": {
                "name": "generic_yes_no",
                "pattern": r"\(y/n\)|\[y/N\]|\[Y/n\]",
                "match_type": "regex",
                "response_strategy": "prompt_user",
                "tags": ["generic", "confirmation"],
                "metadata": {"category": "user_confirmation"},
            },
            "password_prompt": {
                "name": "password_prompt",
                "pattern": r"password:|Password:|Enter password",
                "match_type": "regex",
                "response_strategy": "prompt_user",
                "safety_override": True,
                "tags": ["security", "authentication"],
                "metadata": {"category": "security", "sensitive": True},
            },
        }

        for pattern_data in builtin_patterns.values():
            pattern = PromptPattern(**pattern_data)
            self._patterns[pattern.name] = pattern

            # Compile regex patterns
            if pattern.match_type == MatchType.REGEX:
                try:
                    self._compiled_patterns[pattern.name] = re.compile(
                        pattern.pattern, re.IGNORECASE | re.MULTILINE
                    )
                except re.error as e:
                    print(f"Failed to compile regex pattern '{pattern.name}': {e}")

    def _load_pattern_file(self, pattern_file: Path):
        """Load patterns from a configuration file."""
        try:
            with open(pattern_file, "r", encoding="utf-8") as f:
                if pattern_file.suffix == ".json":
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)

            if isinstance(data, dict) and "patterns" in data:
                patterns_data = data["patterns"]
            elif isinstance(data, list):
                patterns_data = data
            else:
                patterns_data = [data]

            for pattern_data in patterns_data:
                if isinstance(pattern_data, dict):
                    pattern = PromptPattern(**pattern_data)
                    self._patterns[pattern.name] = pattern

                    # Compile regex patterns
                    if pattern.match_type == MatchType.REGEX:
                        try:
                            self._compiled_patterns[pattern.name] = re.compile(
                                pattern.pattern, re.IGNORECASE | re.MULTILINE
                            )
                        except re.error as e:
                            print(
                                f"Failed to compile regex pattern '{pattern.name}': {e}"
                            )

        except Exception as e:
            print(f"Failed to load pattern file {pattern_file}: {e}")

    def detect_prompt(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> DetectionResult:
        """Detect prompts in the given text.

        Args:
            text: The text to analyze for prompts
            context: Optional context information

        Returns:
            DetectionResult: The detection result

        """
        self._stats["total_detections"] += 1

        # Clean and normalize text
        normalized_text = text.strip()

        # Try to match against all patterns
        best_match = DetectionResult(matched=False)
        best_confidence = 0.0

        for pattern in self._patterns.values():
            result = self._match_pattern(pattern, normalized_text)
            if result.matched and result.confidence > best_confidence:
                best_match = result
                best_confidence = result.confidence

        # Apply safety checks
        if best_match.matched and best_match.pattern:
            if self._is_safety_blocked(best_match.pattern, context):
                best_match.safety_blocked = True
                best_match.suggested_response = None
                self._stats["safety_blocks"] += 1

        # Learning mode - capture unknown prompts
        if not best_match.matched and self.enable_learning:
            self._capture_unknown_prompt(normalized_text, context)

        if best_match.matched:
            self._stats["successful_matches"] += 1

        return best_match

    def _match_pattern(self, pattern: PromptPattern, text: str) -> DetectionResult:
        """Match a single pattern against text.

        Args:
            pattern: The pattern to match
            text: The text to match against

        Returns:
            DetectionResult: The match result

        """
        result = DetectionResult(matched=False, pattern=pattern)

        if pattern.match_type == MatchType.REGEX:
            compiled_pattern = self._compiled_patterns.get(pattern.name)
            if compiled_pattern:
                match = compiled_pattern.search(text)
                if match:
                    result.matched = True
                    result.confidence = 1.0
                    result.match_groups = list(match.groups())

        elif pattern.match_type == MatchType.LITERAL:
            if pattern.pattern.lower() in text.lower():
                result.matched = True
                result.confidence = 1.0

        elif pattern.match_type == MatchType.SUBSTRING:
            if pattern.pattern in text:
                result.matched = True
                result.confidence = 1.0

        elif pattern.match_type == MatchType.STARTSWITH:
            if text.lower().startswith(pattern.pattern.lower()):
                result.matched = True
                result.confidence = 1.0

        elif pattern.match_type == MatchType.ENDSWITH:
            if text.lower().endswith(pattern.pattern.lower()):
                result.matched = True
                result.confidence = 1.0

        # Set response strategy details
        if result.matched:
            result.suggested_response = self._get_suggested_response(
                pattern, result.match_groups
            )
            result.requires_user_input = (
                pattern.response_strategy == ResponseStrategy.PROMPT_USER
            )

        return result

    def _get_suggested_response(
        self, pattern: PromptPattern, match_groups: List[str]
    ) -> Optional[str]:
        """Get suggested response based on pattern configuration.

        Args:
            pattern: The matched pattern
            match_groups: Regex match groups if any

        Returns:
            Optional[str]: Suggested response text

        """
        if pattern.response_strategy == ResponseStrategy.AUTO_APPROVE:
            return pattern.response_text or "yes"

        elif pattern.response_strategy == ResponseStrategy.DENY:
            return pattern.response_text or "no"

        elif pattern.response_strategy == ResponseStrategy.CUSTOM_RESPONSE:
            response = pattern.response_text or ""
            # Simple template substitution for match groups
            for i, group in enumerate(match_groups):
                response = response.replace(f"{{group{i}}}", group)
            return response

        elif pattern.response_strategy == ResponseStrategy.PROMPT_USER:
            return None  # Requires user input

        return None

    def _is_safety_blocked(
        self, pattern: PromptPattern, context: Optional[Dict[str, Any]]
    ) -> bool:
        """Check if pattern execution should be blocked for safety.

        Args:
            pattern: The pattern to check
            context: Optional context information

        Returns:
            bool: True if should be blocked

        """
        # Check if pattern has dangerous tags
        dangerous_tags = {"dangerous", "git", "system", "security"}
        if dangerous_tags.intersection(pattern.tags):
            # Check if safety override is enabled
            if not pattern.safety_override:
                return True

        # Check configuration-based safety rules
        if self.config_manager:
            blocked_operations = self.config_manager.get(
                "security.blocked_operations", []
            )
            for blocked_op in blocked_operations:
                if blocked_op.lower() in pattern.pattern.lower():
                    return True

        return False

    def _capture_unknown_prompt(self, text: str, context: Optional[Dict[str, Any]]):
        """Capture unknown prompts for learning purposes.

        Args:
            text: The unknown prompt text
            context: Optional context information

        """
        if len(text.strip()) > 5:
            # Always add to learning buffer for frequency counting
            self._learning_buffer.append(
                {
                    "text": text,
                    "timestamp": time.time(),
                    "context": context or {},
                    "length": len(text),
                    "word_count": len(text.split()),
                }
            )
            self._stats["learning_captures"] += 1

            # Track unique prompts separately
            if text not in self._unknown_prompts:
                self._unknown_prompts.add(text)

            # Limit learning buffer size
            if len(self._learning_buffer) > 1000:
                self._learning_buffer = self._learning_buffer[-500:]

    def add_pattern(self, pattern: PromptPattern) -> bool:
        """Add a new pattern to the detector.

        Args:
            pattern: The pattern to add

        Returns:
            bool: True if pattern was added successfully

        """
        try:
            self._patterns[pattern.name] = pattern

            # Compile regex if needed
            if pattern.match_type == MatchType.REGEX:
                self._compiled_patterns[pattern.name] = re.compile(
                    pattern.pattern, re.IGNORECASE | re.MULTILINE
                )

            return True
        except Exception as e:
            print(f"Failed to add pattern '{pattern.name}': {e}")
            return False

    def remove_pattern(self, pattern_name: str) -> bool:
        """Remove a pattern from the detector.

        Args:
            pattern_name: Name of the pattern to remove

        Returns:
            bool: True if pattern was removed

        """
        if pattern_name in self._patterns:
            del self._patterns[pattern_name]
            if pattern_name in self._compiled_patterns:
                del self._compiled_patterns[pattern_name]
            return True
        return False

    def save_patterns(self, filename: Optional[str] = None):
        """Save current patterns to configuration file.

        Args:
            filename: Optional filename to save to

        """
        if filename is None:
            filename = "custom_patterns.yaml"

        pattern_file = self.patterns_dir / filename
        pattern_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert patterns to serializable format
        patterns_data = []
        for pattern in self._patterns.values():
            pattern_dict = {
                "name": pattern.name,
                "pattern": pattern.pattern,
                "match_type": pattern.match_type.value,
                "response_strategy": pattern.response_strategy.value,
                "response_text": pattern.response_text,
                "confidence_threshold": pattern.confidence_threshold,
                "tags": list(pattern.tags),
                "metadata": pattern.metadata,
                "safety_override": pattern.safety_override,
            }
            patterns_data.append(pattern_dict)

        data = {"patterns": patterns_data}

        with open(pattern_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def get_learning_data(self) -> Dict[str, Any]:
        """Get data captured during learning mode.

        Returns:
            Dict[str, Any]: Learning data and statistics

        """
        return {
            "unknown_prompts": list(self._unknown_prompts),
            "learning_buffer": self._learning_buffer.copy(),
            "statistics": self._stats.copy(),
            "pattern_count": len(self._patterns),
        }

    def generate_pattern_suggestions(
        self, min_frequency: int = 3
    ) -> List[Dict[str, Any]]:
        """Generate pattern suggestions based on learning data.

        Args:
            min_frequency: Minimum frequency for pattern suggestion

        Returns:
            List[Dict[str, Any]]: List of suggested patterns

        """
        suggestions = []

        # Analyze learning buffer for common patterns
        text_frequency = {}
        for entry in self._learning_buffer:
            text = entry["text"].strip()
            if len(text) > 10:  # Only consider substantial prompts
                text_frequency[text] = text_frequency.get(text, 0) + 1

        # Create suggestions for frequent patterns
        for text, frequency in text_frequency.items():
            if frequency >= min_frequency:
                suggestion = {
                    "suggested_name": f"learned_pattern_{hash(text) & 0x7fffffff}",
                    "pattern": re.escape(text[:50]),  # Truncate long patterns
                    "match_type": "literal",
                    "response_strategy": "prompt_user",
                    "frequency": frequency,
                    "sample_text": text,
                    "confidence": min(frequency / 10.0, 1.0),
                }
                suggestions.append(suggestion)

        return sorted(suggestions, key=lambda x: x["frequency"], reverse=True)

    def get_statistics(self) -> Dict[str, Any]:
        """Get detection statistics.

        Returns:
            Dict[str, Any]: Statistics data

        """
        success_rate = 0.0
        if self._stats["total_detections"] > 0:
            success_rate = (
                self._stats["successful_matches"] / self._stats["total_detections"]
            )

        return {
            **self._stats,
            "success_rate": success_rate,
            "pattern_count": len(self._patterns),
            "compiled_patterns": len(self._compiled_patterns),
            "learning_enabled": self.enable_learning,
            "unknown_prompts_count": len(self._unknown_prompts),
        }

    def list_patterns(self, tag_filter: Optional[str] = None) -> List[PromptPattern]:
        """List all loaded patterns, optionally filtered by tag.

        Args:
            tag_filter: Optional tag to filter patterns

        Returns:
            List[PromptPattern]: List of patterns

        """
        patterns = list(self._patterns.values())

        if tag_filter:
            patterns = [p for p in patterns if tag_filter in p.tags]

        return patterns

    def clear_learning_data(self):
        """Clear all learning mode data."""
        self._learning_buffer.clear()
        self._unknown_prompts.clear()
        self._stats["learning_captures"] = 0


class PromptHandler:
    """High-level prompt handler that combines detection and response."""

    def __init__(self, detector: PromptDetector):
        """Initialize prompt handler.

        Args:
            detector: PromptDetector instance to use

        """
        self.detector = detector
        self._response_callbacks = {}

    def handle_prompt(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Handle a prompt with automatic response generation.

        Args:
            text: The prompt text
            context: Optional context information

        Returns:
            str: The response to send

        """
        result = self.detector.detect_prompt(text, context)

        if not result.matched:
            return self._handle_unknown_prompt(text, context)

        if result.safety_blocked:
            return "Operation blocked for safety reasons."

        if result.requires_user_input:
            return self._prompt_user(text, result)

        return result.suggested_response or "yes"

    def _handle_unknown_prompt(
        self, text: str, context: Optional[Dict[str, Any]]
    ) -> str:
        """Handle an unknown prompt.

        Args:
            text: The prompt text
            context: Optional context information

        Returns:
            str: Default response for unknown prompts

        """
        # Default to asking the user for unknown prompts
        return self._prompt_user(text, None)

    def _prompt_user(self, text: str, result: Optional[DetectionResult]) -> str:
        """Prompt the user for input.

        Args:
            text: The original prompt text
            result: Optional detection result

        Returns:
            str: User's response

        """
        print(f"\nPrompt detected: {text}")
        if result and result.pattern:
            print(
                f"Pattern: {result.pattern.name} (confidence: {result.confidence:.2f})"
            )

        response = input("Your response: ").strip()
        return response or "no"

    def set_response_callback(self, pattern_name: str, callback: callable):
        """Set a custom response callback for a pattern.

        Args:
            pattern_name: Name of the pattern
            callback: Callback function that takes (text, result) and returns response

        """
        self._response_callbacks[pattern_name] = callback
