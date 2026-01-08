"""AI pattern detection module for identifying AI-generated code patterns."""

import ast
import concurrent.futures
import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class SensitivityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PARANOID = "paranoid"


@dataclass
class DetectionResult:
    """Result of AI pattern detection."""

    file_path: str
    detected_patterns: List[Dict[str, Any]] = field(default_factory=list)
    ai_score: float = 0.0
    passes: bool = True
    sensitivity_level: SensitivityLevel = SensitivityLevel.MEDIUM

    @property
    def summary(self) -> str:
        """Generate summary of detection results."""
        if not self.detected_patterns:
            return f"No AI patterns detected in {self.file_path}"
        return f"Found {len(self.detected_patterns)} AI patterns in {self.file_path} (score: {self.ai_score:.2f})"


@dataclass
class AIPatternConfig:
    """Configuration for AI pattern detection."""

    sensitivity: SensitivityLevel = SensitivityLevel.MEDIUM
    whitelist_patterns: Set[str] = field(default_factory=set)
    whitelist_files: Set[str] = field(default_factory=set)
    emoji_allowed: bool = False
    max_workers: int = 4
    cache_size: int = 1000
    custom_patterns: List[Dict[str, Any]] = field(default_factory=list)
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        "low": 0.7,
        "medium": 0.5,
        "high": 0.3,
        "paranoid": 0.1
    })


class AIDetector:
    """Main AI pattern detection engine."""

    # Common AI-generated code patterns
    AI_PATTERNS = {
        "verbose_names": [
            r"\b[a-z]+_[a-z]+_[a-z]+_[a-z]+_[a-z]+\b",  # overly_long_descriptive_variable_names
            r"\bhandle[A-Z][a-zA-Z]+Error\b",  # handleSomethingError pattern
            r"\bprocess[A-Z][a-zA-Z]+Data\b",  # processUserInputData pattern
            r"\b[a-z]+Manager[A-Z][a-zA-Z]+\b",  # dataManagerInstance pattern
        ],
        "placeholder_text": [
            r"(?i)\b(todo|fixme|hack|xxx|placeholder|dummy|temp|sample|example|test)\b",
            r"(?i)your.*here",
            r"(?i)replace.*with",
            r"(?i)insert.*code",
            r"Lorem ipsum",
        ],
        "excessive_comments": [
            r"^(\s*#.*\n){5,}",  # 5+ consecutive comment lines
            r"#\s*[A-Z][^.!?]*$",  # Comments without punctuation
            r"#\s*(Step|Part|Section)\s*\d+",  # Step 1, Part 2 comments
            r"#\s*-{3,}",  # Separator comments
        ],
        "ai_style_docstrings": [
            r'"""[^"]*\b(comprehensive|robust|sophisticated|elegant|powerful)\b[^"]*"""',
            r'"""[^"]*\b(handles?|performs?|executes?|processes?)\s+various\b[^"]*"""',
            r'"""[^"]*\b(utility|helper|manager|handler|processor)\s+for\b[^"]*"""',
        ],
        "generic_exceptions": [
            r"except\s+Exception\s*:",
            r"except\s*:",
            r"raise\s+Exception\s*\(",
            r"except\s+.*as\s+e\s*:\s*pass",
        ],
        "boilerplate_structures": [
            r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:\s*main\(\)",
            r"def\s+main\(\)\s*:\s*pass",
            r"class\s+[A-Z][a-zA-Z]+\(\)\s*:\s*pass",
        ],
        "ai_comments": [
            r"#\s*Initialize",
            r"#\s*Setup",
            r"#\s*Configure",
            r"#\s*Process",
            r"#\s*Handle",
            r"#\s*Validate",
            r"#\s*Helper function",
            r"#\s*Utility method",
            r"#\s*Main logic",
        ]
    }

    # Emoji patterns
    EMOJI_PATTERNS = [
        r"[\U0001F300-\U0001F9FF]",  # Emoticons, symbols, pictographs
        r"[\U00002600-\U000027BF]",  # Miscellaneous symbols
        r"[\U0001F600-\U0001F64F]",  # Emoticons
        r"[\U0001F680-\U0001F6FF]",  # Transport and map symbols
        r"[\U00002700-\U000027BF]",  # Dingbats
    ]

    def __init__(self, config: Optional[AIPatternConfig] = None):
        """Initialize AI detector with configuration."""
        self.config = config or AIPatternConfig()
        self._pattern_cache = {}
        self._compile_patterns()
        self._load_whitelist()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        for category, patterns in self.AI_PATTERNS.items():
            self._pattern_cache[category] = [
                re.compile(pattern, re.MULTILINE)
                for pattern in patterns
            ]

        self._pattern_cache["emoji"] = [
            re.compile(pattern)
            for pattern in self.EMOJI_PATTERNS
        ]

        # Compile custom patterns
        for custom in self.config.custom_patterns:
            category = custom.get("category", "custom")
            pattern = custom.get("pattern")
            if pattern:
                if category not in self._pattern_cache:
                    self._pattern_cache[category] = []
                self._pattern_cache[category].append(re.compile(pattern, re.MULTILINE))

    def _load_whitelist(self):
        """Load whitelist patterns from configuration."""
        self.whitelist_hashes = set()
        for pattern in self.config.whitelist_patterns:
            self.whitelist_hashes.add(hashlib.md5(pattern.encode()).hexdigest())

    @lru_cache(maxsize=1000)
    def _is_whitelisted(self, text: str) -> bool:
        """Check if text matches any whitelist pattern."""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in self.whitelist_hashes:
            return True

        for pattern in self.config.whitelist_patterns:
            if re.search(pattern, text):
                return True
        return False

    def detect_ai_patterns(self, code: str) -> Tuple[bool, List[str]]:
        """Detect AI patterns in code string.
        
        Returns: (has_patterns, list_of_patterns)
        """
        detected = []

        # Check all pattern categories
        for category, patterns in self._pattern_cache.items():
            for pattern in patterns:
                if pattern.search(code):
                    detected.append(f"{category} pattern detected")
                    break  # One match per category is enough

        return len(detected) > 0, detected

    def detect_file(self, file_path: Path) -> DetectionResult:
        """Detect AI patterns in a single file."""
        if str(file_path) in self.config.whitelist_files:
            return DetectionResult(
                file_path=str(file_path),
                passes=True,
                sensitivity_level=self.config.sensitivity
            )

        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception:
            return DetectionResult(
                file_path=str(file_path),
                passes=True,
                sensitivity_level=self.config.sensitivity
            )

        detected_patterns = []

        # Check for emoji usage
        if not self.config.emoji_allowed:
            emoji_matches = self._detect_emojis(content)
            if emoji_matches:
                detected_patterns.extend(emoji_matches)

        # Check for AI code patterns
        for category, patterns in self._pattern_cache.items():
            if category == "emoji":
                continue

            for pattern in patterns:
                matches = pattern.finditer(content)
                for match in matches:
                    if not self._is_whitelisted(match.group()):
                        detected_patterns.append({
                            "category": category,
                            "pattern": pattern.pattern,
                            "match": match.group()[:100],
                            "line": content[:match.start()].count('\n') + 1,
                            "severity": self._get_severity(category)
                        })

        # Python-specific checks
        if file_path.suffix == '.py':
            ast_patterns = self._detect_ast_patterns(content)
            detected_patterns.extend(ast_patterns)

        # Calculate AI score
        ai_score = self._calculate_ai_score(detected_patterns, len(content.splitlines()))

        # Determine if it passes based on sensitivity
        threshold = self.config.thresholds[self.config.sensitivity.value]
        passes = ai_score < threshold

        return DetectionResult(
            file_path=str(file_path),
            detected_patterns=detected_patterns,
            ai_score=ai_score,
            passes=passes,
            sensitivity_level=self.config.sensitivity
        )

    def _detect_emojis(self, content: str) -> List[Dict[str, Any]]:
        """Detect emoji usage in content."""
        emoji_matches = []
        for pattern in self._pattern_cache.get("emoji", []):
            matches = pattern.finditer(content)
            for match in matches:
                emoji_matches.append({
                    "category": "emoji",
                    "pattern": "emoji_character",
                    "match": match.group(),
                    "line": content[:match.start()].count('\n') + 1,
                    "severity": "high"
                })
        return emoji_matches

    def _detect_ast_patterns(self, content: str) -> List[Dict[str, Any]]:
        """Detect AI patterns using AST analysis for Python code."""
        patterns = []
        try:
            tree = ast.parse(content)

            # Check for overly nested functions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    nesting_level = self._get_nesting_level(node)
                    if nesting_level > 3:
                        patterns.append({
                            "category": "deep_nesting",
                            "pattern": "excessive_nesting",
                            "match": f"Function '{node.name}' has nesting level {nesting_level}",
                            "line": node.lineno,
                            "severity": "medium"
                        })

                    # Check for generic function names
                    if re.match(r"^(process|handle|manage|execute|run|do)_", node.name):
                        patterns.append({
                            "category": "generic_names",
                            "pattern": "generic_function_name",
                            "match": f"Function '{node.name}'",
                            "line": node.lineno,
                            "severity": "low"
                        })

                # Check for empty except blocks
                if isinstance(node, ast.ExceptHandler):
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        patterns.append({
                            "category": "empty_except",
                            "pattern": "empty_exception_handler",
                            "match": "Empty except block",
                            "line": node.lineno,
                            "severity": "high"
                        })
        except:
            pass

        return patterns

    def _get_nesting_level(self, node: ast.AST, level: int = 0) -> int:
        """Calculate nesting level of an AST node."""
        max_level = level
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                child_level = self._get_nesting_level(child, level + 1)
                max_level = max(max_level, child_level)
            else:
                # Continue checking children without incrementing level
                child_level = self._get_nesting_level(child, level)
                max_level = max(max_level, child_level)
        return max_level

    def _get_severity(self, category: str) -> str:
        """Get severity level for a pattern category."""
        severity_map = {
            "emoji": "high",
            "placeholder_text": "high",
            "generic_exceptions": "high",
            "empty_except": "high",
            "excessive_comments": "medium",
            "ai_style_docstrings": "medium",
            "verbose_names": "low",
            "boilerplate_structures": "low",
            "ai_comments": "medium",
            "generic_names": "low",
            "deep_nesting": "medium"
        }
        return severity_map.get(category, "low")

    def _calculate_ai_score(self, patterns: List[Dict], line_count: int) -> float:
        """Calculate overall AI score based on detected patterns."""
        if not patterns or line_count == 0:
            return 0.0

        severity_weights = {
            "high": 3.0,
            "medium": 2.0,
            "low": 1.0
        }

        total_weight = sum(
            severity_weights.get(p.get("severity", "low"), 1.0)
            for p in patterns
        )

        # Normalize by line count
        normalized_score = min(1.0, total_weight / max(line_count, 1))

        # Apply sensitivity multiplier
        sensitivity_multipliers = {
            SensitivityLevel.LOW: 0.5,
            SensitivityLevel.MEDIUM: 1.0,
            SensitivityLevel.HIGH: 1.5,
            SensitivityLevel.PARANOID: 2.0
        }

        return normalized_score * sensitivity_multipliers[self.config.sensitivity]

    def detect_directory(self, directory: Path, extensions: Optional[Set[str]] = None) -> List[DetectionResult]:
        """Detect AI patterns in all files in a directory."""
        if extensions is None:
            extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs'}

        files = []
        for ext in extensions:
            files.extend(directory.rglob(f"*{ext}"))

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_file = {
                executor.submit(self.detect_file, file): file
                for file in files
            }

            for future in concurrent.futures.as_completed(future_to_file):
                result = future.result()
                results.append(result)

        return results

    def generate_report(self, results: List[DetectionResult]) -> Dict[str, Any]:
        """Generate summary report of detection results."""
        total_files = len(results)
        failed_files = [r for r in results if not r.passes]

        pattern_counts = {}
        for result in results:
            for pattern in result.detected_patterns:
                category = pattern["category"]
                pattern_counts[category] = pattern_counts.get(category, 0) + 1

        avg_score = sum(r.ai_score for r in results) / max(total_files, 1)

        return {
            "summary": {
                "total_files": total_files,
                "passed": total_files - len(failed_files),
                "failed": len(failed_files),
                "average_ai_score": avg_score,
                "sensitivity_level": self.config.sensitivity.value
            },
            "pattern_distribution": pattern_counts,
            "failed_files": [
                {
                    "file": r.file_path,
                    "score": r.ai_score,
                    "pattern_count": len(r.detected_patterns)
                }
                for r in failed_files
            ],
            "recommendations": self._generate_recommendations(results)
        }

    def _generate_recommendations(self, results: List[DetectionResult]) -> List[str]:
        """Generate recommendations based on detection results."""
        recommendations = []

        emoji_count = sum(
            1 for r in results
            for p in r.detected_patterns
            if p["category"] == "emoji"
        )
        if emoji_count > 0:
            recommendations.append(f"Remove {emoji_count} emoji occurrences from code")

        placeholder_count = sum(
            1 for r in results
            for p in r.detected_patterns
            if p["category"] == "placeholder_text"
        )
        if placeholder_count > 0:
            recommendations.append(f"Replace {placeholder_count} placeholder text occurrences")

        exception_count = sum(
            1 for r in results
            for p in r.detected_patterns
            if p["category"] in ["generic_exceptions", "empty_except"]
        )
        if exception_count > 0:
            recommendations.append(f"Improve {exception_count} exception handlers")

        if not recommendations:
            recommendations.append("Code appears to be production-ready")

        return recommendations

    def check_single_file(self, file_path: str) -> Tuple[bool, str]:
        """Quick check for a single file - returns (passes, message)."""
        result = self.detect_file(Path(file_path))
        return result.passes, result.summary

    def update_config(self, **kwargs):
        """Update configuration dynamically."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        # Recompile patterns if needed
        if 'custom_patterns' in kwargs:
            self._compile_patterns()

        if 'whitelist_patterns' in kwargs:
            self._load_whitelist()


def create_detector(config_path: Optional[str] = None) -> AIDetector:
    """Factory function to create AI detector with optional config file."""
    config = AIPatternConfig()

    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            config_data = json.load(f)

            if "sensitivity" in config_data:
                config.sensitivity = SensitivityLevel(config_data["sensitivity"])

            if "whitelist_patterns" in config_data:
                config.whitelist_patterns = set(config_data["whitelist_patterns"])

            if "whitelist_files" in config_data:
                config.whitelist_files = set(config_data["whitelist_files"])

            if "emoji_allowed" in config_data:
                config.emoji_allowed = config_data["emoji_allowed"]

            if "custom_patterns" in config_data:
                config.custom_patterns = config_data["custom_patterns"]

            if "thresholds" in config_data:
                config.thresholds.update(config_data["thresholds"])

    return AIDetector(config)
