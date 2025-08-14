"""Operation validation module with whitelist/blacklist support.

Provides a flexible system for validating operations based on configurable
whitelists and blacklists.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of operations that can be validated."""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    COMMAND_EXECUTE = "command_execute"
    NETWORK_REQUEST = "network_request"
    DATABASE_QUERY = "database_query"
    API_CALL = "api_call"


@dataclass
class ValidationRule:
    """A validation rule for operations."""

    pattern: str
    operation_types: List[OperationType]
    is_whitelist: bool
    description: str = ""
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Compile the pattern for efficiency."""
        self.compiled_pattern = re.compile(self.pattern, re.IGNORECASE)


class OperationValidator:
    """Validates operations against whitelist/blacklist rules."""

    def __init__(
        self,
        config_file: Optional[Path] = None,
        default_allow: bool = False,
    ):
        """Initialize OperationValidator.

        Args:
            config_file: Path to JSON configuration file
            default_allow: Default behavior when no rules match (False = deny by default)

        """
        self.default_allow = default_allow
        self.whitelist_rules: List[ValidationRule] = []
        self.blacklist_rules: List[ValidationRule] = []
        self.operation_counters: Dict[OperationType, int] = {}

        # Load default rules
        self._load_default_rules()

        # Load custom configuration if provided
        if config_file and config_file.exists():
            self._load_config(config_file)

    def _load_default_rules(self) -> None:
        """Load default validation rules."""
        # Default whitelist rules (always allowed)
        default_whitelist = [
            ValidationRule(
                pattern=r"^/tmp/.*",
                operation_types=[OperationType.FILE_WRITE, OperationType.FILE_DELETE],
                is_whitelist=True,
                description="Allow operations in /tmp directory",
                priority=10,
            ),
            ValidationRule(
                pattern=r".*\.(py|js|ts|java|cpp|c|h|go|rs|rb)$",
                operation_types=[OperationType.FILE_READ],
                is_whitelist=True,
                description="Allow reading source code files",
                priority=5,
            ),
            ValidationRule(
                pattern=r"^(ls|pwd|echo|cat|grep|find|which)(\s|$)",
                operation_types=[OperationType.COMMAND_EXECUTE],
                is_whitelist=True,
                description="Allow safe shell commands",
                priority=5,
            ),
        ]

        # Default blacklist rules (always denied)
        default_blacklist = [
            ValidationRule(
                pattern=r".*\.(pem|key|crt|p12|pfx)$",
                operation_types=[OperationType.FILE_WRITE, OperationType.FILE_DELETE],
                is_whitelist=False,
                description="Deny operations on certificate/key files",
                priority=20,
            ),
            ValidationRule(
                pattern=r"^(rm|del|format|fdisk|dd)(\s|$)",
                operation_types=[OperationType.COMMAND_EXECUTE],
                is_whitelist=False,
                description="Deny destructive commands",
                priority=20,
            ),
            ValidationRule(
                pattern=r"(DROP|TRUNCATE|DELETE\s+FROM)\s",
                operation_types=[OperationType.DATABASE_QUERY],
                is_whitelist=False,
                description="Deny destructive database operations",
                priority=15,
            ),
            ValidationRule(
                pattern=r"https?://.*\.(onion|i2p|bit)(/|$)",
                operation_types=[OperationType.NETWORK_REQUEST],
                is_whitelist=False,
                description="Deny requests to dark web domains",
                priority=25,
            ),
        ]

        self.whitelist_rules.extend(default_whitelist)
        self.blacklist_rules.extend(default_blacklist)

    def _load_config(self, config_file: Path) -> None:
        """Load validation rules from a configuration file.

        Args:
            config_file: Path to JSON configuration file

        """
        try:
            with open(config_file, "r") as f:
                config = json.load(f)

            # Load whitelist rules
            for rule_data in config.get("whitelist", []):
                rule = ValidationRule(
                    pattern=rule_data["pattern"],
                    operation_types=[
                        OperationType(op) for op in rule_data["operation_types"]
                    ],
                    is_whitelist=True,
                    description=rule_data.get("description", ""),
                    priority=rule_data.get("priority", 0),
                    metadata=rule_data.get("metadata", {}),
                )
                self.whitelist_rules.append(rule)

            # Load blacklist rules
            for rule_data in config.get("blacklist", []):
                rule = ValidationRule(
                    pattern=rule_data["pattern"],
                    operation_types=[
                        OperationType(op) for op in rule_data["operation_types"]
                    ],
                    is_whitelist=False,
                    description=rule_data.get("description", ""),
                    priority=rule_data.get("priority", 0),
                    metadata=rule_data.get("metadata", {}),
                )
                self.blacklist_rules.append(rule)

            # Update default behavior
            if "default_allow" in config:
                self.default_allow = config["default_allow"]

            logger.info(f"Loaded validation config from {config_file}")

        except Exception as e:
            logger.error(f"Error loading validation config: {e}")

    def validate_operation(
        self,
        operation_type: OperationType,
        target: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[ValidationRule]]:
        """Validate an operation against the rules.

        Args:
            operation_type: Type of operation to validate
            target: Target of the operation (file path, command, URL, etc.)
            context: Additional context for validation

        Returns:
            Tuple of (is_allowed, reason, matching_rule)

        """
        # Track operation attempt
        self.operation_counters[operation_type] = (
            self.operation_counters.get(operation_type, 0) + 1
        )

        # Sort rules by priority (higher priority first)
        all_rules = sorted(
            self.whitelist_rules + self.blacklist_rules,
            key=lambda r: r.priority,
            reverse=True,
        )

        # Check rules in priority order
        for rule in all_rules:
            if operation_type in rule.operation_types:
                if rule.compiled_pattern.search(target):
                    if rule.is_whitelist:
                        logger.debug(
                            f"Operation allowed by whitelist rule: {rule.description}"
                        )
                        return True, f"Allowed: {rule.description}", rule
                    else:
                        logger.warning(
                            f"Operation denied by blacklist rule: {rule.description}"
                        )
                        return False, f"Denied: {rule.description}", rule

        # No matching rules - use default behavior
        if self.default_allow:
            logger.debug(f"Operation allowed by default: {operation_type} on {target}")
            return True, "Allowed by default policy", None
        else:
            logger.info(f"Operation denied by default: {operation_type} on {target}")
            return False, "Denied by default policy", None

    def add_rule(self, rule: ValidationRule) -> None:
        """Add a new validation rule.

        Args:
            rule: The validation rule to add

        """
        if rule.is_whitelist:
            self.whitelist_rules.append(rule)
            logger.info(f"Added whitelist rule: {rule.description}")
        else:
            self.blacklist_rules.append(rule)
            logger.info(f"Added blacklist rule: {rule.description}")

    def remove_rule(self, pattern: str, is_whitelist: bool) -> bool:
        """Remove a validation rule by pattern.

        Args:
            pattern: The pattern of the rule to remove
            is_whitelist: Whether to remove from whitelist or blacklist

        Returns:
            True if a rule was removed, False otherwise

        """
        rules_list = self.whitelist_rules if is_whitelist else self.blacklist_rules

        for i, rule in enumerate(rules_list):
            if rule.pattern == pattern:
                removed_rule = rules_list.pop(i)
                logger.info(f"Removed rule: {removed_rule.description}")
                return True

        return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get validation statistics.

        Returns:
            Dictionary of statistics

        """
        return {
            "total_whitelist_rules": len(self.whitelist_rules),
            "total_blacklist_rules": len(self.blacklist_rules),
            "default_policy": "allow" if self.default_allow else "deny",
            "operation_counts": dict(self.operation_counters),
        }

    def export_rules(self, output_file: Path) -> None:
        """Export current rules to a JSON file.

        Args:
            output_file: Path to the output file

        """
        config = {
            "default_allow": self.default_allow,
            "whitelist": [
                {
                    "pattern": rule.pattern,
                    "operation_types": [op.value for op in rule.operation_types],
                    "description": rule.description,
                    "priority": rule.priority,
                    "metadata": rule.metadata,
                }
                for rule in self.whitelist_rules
            ],
            "blacklist": [
                {
                    "pattern": rule.pattern,
                    "operation_types": [op.value for op in rule.operation_types],
                    "description": rule.description,
                    "priority": rule.priority,
                    "metadata": rule.metadata,
                }
                for rule in self.blacklist_rules
            ],
        }

        with open(output_file, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Exported validation rules to {output_file}")

    def batch_validate(
        self,
        operations: List[Tuple[OperationType, str]],
        stop_on_first_denial: bool = True,
    ) -> List[Tuple[bool, Optional[str]]]:
        """Validate multiple operations in batch.

        Args:
            operations: List of (operation_type, target) tuples
            stop_on_first_denial: If True, stop validating after first denial

        Returns:
            List of (is_allowed, reason) tuples

        """
        results = []

        for op_type, target in operations:
            is_allowed, reason, _ = self.validate_operation(op_type, target)
            results.append((is_allowed, reason))

            if not is_allowed and stop_on_first_denial:
                # Fill remaining with denials
                remaining_count = len(operations) - len(results)
                results.extend(
                    [(False, "Skipped due to previous denial")] * remaining_count
                )
                break

        return results
