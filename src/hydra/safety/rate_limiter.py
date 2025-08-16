"""Rate limiting module for destructive commands.

Provides rate limiting and throttling for potentially dangerous operations
to prevent accidental or malicious damage.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Any, Dict, Optional, Tuple

from hydra.logging_config import get_logger

logger = get_logger(__name__)


class CommandCategory(Enum):
    """Categories of commands for rate limiting."""

    SAFE = "safe"  # No rate limiting
    MODERATE = "moderate"  # Light rate limiting
    DESTRUCTIVE = "destructive"  # Heavy rate limiting
    CRITICAL = "critical"  # Very strict rate limiting


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    max_operations: int  # Maximum operations in time window
    time_window_seconds: int  # Time window in seconds
    burst_limit: int  # Maximum burst operations
    cooldown_seconds: int  # Cooldown after limit reached


class RateLimiter:
    """Rate limiter for controlling operation frequency."""

    # Default rate limit configurations by category
    DEFAULT_CONFIGS = {
        CommandCategory.SAFE: RateLimitConfig(
            max_operations=1000,
            time_window_seconds=60,
            burst_limit=100,
            cooldown_seconds=0,
        ),
        CommandCategory.MODERATE: RateLimitConfig(
            max_operations=100,
            time_window_seconds=60,
            burst_limit=20,
            cooldown_seconds=5,
        ),
        CommandCategory.DESTRUCTIVE: RateLimitConfig(
            max_operations=10,
            time_window_seconds=60,
            burst_limit=3,
            cooldown_seconds=30,
        ),
        CommandCategory.CRITICAL: RateLimitConfig(
            max_operations=3,
            time_window_seconds=300,
            burst_limit=1,
            cooldown_seconds=60,
        ),
    }

    # Command patterns and their categories (ordered from most specific to least)
    COMMAND_CATEGORIES = {
        # Critical commands (check first for most specific patterns)
        r"^rm\s+.*-rf": CommandCategory.CRITICAL,
        r"^git\s+push\s+.*--force": CommandCategory.CRITICAL,
        r"^(format|fdisk|dd|shred)(\s|$)": CommandCategory.CRITICAL,
        r"^sudo\s+": CommandCategory.CRITICAL,

        # Destructive commands
        r"^(rm|rmdir|del)(\s|$)": CommandCategory.DESTRUCTIVE,
        r"^git\s+(reset|clean)": CommandCategory.DESTRUCTIVE,
        r"^truncate\s+": CommandCategory.DESTRUCTIVE,
        r">\s*[^>]": CommandCategory.DESTRUCTIVE,  # File truncation with >

        # Moderate commands
        r"^(cp|mv|mkdir|touch|chmod)(\s|$)": CommandCategory.MODERATE,
        r"^git\s+(add|commit|pull|fetch)": CommandCategory.MODERATE,
        r"^npm\s+(install|update)": CommandCategory.MODERATE,
        r"^pip\s+(install|upgrade)": CommandCategory.MODERATE,

        # Safe commands
        r"^(ls|pwd|echo|cat|grep|find|which|date|whoami)(\s|$)": CommandCategory.SAFE,
        r"^git\s+(status|log|diff|branch|show)": CommandCategory.SAFE,
    }

    def __init__(
        self,
        custom_configs: Optional[Dict[CommandCategory, RateLimitConfig]] = None,
        enable_logging: bool = True,
    ):
        """Initialize RateLimiter.

        Args:
            custom_configs: Custom rate limit configurations
            enable_logging: Whether to enable detailed logging

        """
        self.configs = self.DEFAULT_CONFIGS.copy()
        if custom_configs:
            self.configs.update(custom_configs)

        self.enable_logging = enable_logging
        self._lock = Lock()

        # Track operations per key (command or operation identifier)
        self._operation_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._cooldown_until: Dict[str, datetime] = {}
        self._burst_counters: Dict[str, int] = defaultdict(int)
        self._burst_reset_times: Dict[str, datetime] = {}

        # Compile command patterns
        import re
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), category)
            for pattern, category in self.COMMAND_CATEGORIES.items()
        ]

    def categorize_command(self, command: str) -> CommandCategory:
        """Categorize a command based on its potential for damage.

        Args:
            command: The command to categorize

        Returns:
            Command category

        """
        command = command.strip()

        for pattern, category in self._compiled_patterns:
            if pattern.search(command):
                if self.enable_logging:
                    logger.debug(f"Command '{command}' categorized as {category.value}")
                return category

        # Default to moderate for unknown commands
        return CommandCategory.MODERATE

    def check_rate_limit(
        self,
        identifier: str,
        category: Optional[CommandCategory] = None,
        command: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """Check if an operation is within rate limits.

        Args:
            identifier: Unique identifier for the operation
            category: Command category (if None, will be determined from command)
            command: The command being executed (used for categorization)

        Returns:
            Tuple of (is_allowed, reason, retry_after_seconds)

        """
        with self._lock:
            # Determine category
            if category is None:
                if command:
                    category = self.categorize_command(command)
                else:
                    category = CommandCategory.MODERATE

            config = self.configs[category]
            current_time = datetime.now()

            # Check cooldown
            if identifier in self._cooldown_until:
                cooldown_end = self._cooldown_until[identifier]
                if current_time < cooldown_end:
                    remaining = (cooldown_end - current_time).total_seconds()
                    reason = f"Rate limit cooldown in effect. Retry after {remaining:.1f} seconds"
                    if self.enable_logging:
                        logger.warning(f"Rate limit cooldown for {identifier}: {reason}")
                    return False, reason, remaining
                else:
                    # Cooldown expired
                    del self._cooldown_until[identifier]

            # Check burst limit
            if identifier not in self._burst_reset_times:
                self._burst_reset_times[identifier] = current_time
                self._burst_counters[identifier] = 0

            # Reset burst counter if enough time has passed
            burst_window = timedelta(seconds=10)  # 10-second burst window
            if current_time - self._burst_reset_times[identifier] > burst_window:
                self._burst_counters[identifier] = 0
                self._burst_reset_times[identifier] = current_time

            if self._burst_counters[identifier] >= config.burst_limit:
                reason = f"Burst limit ({config.burst_limit}) exceeded for {category.value} operations"
                retry_after = burst_window.total_seconds()
                if self.enable_logging:
                    logger.warning(f"Burst limit exceeded for {identifier}: {reason}")
                return False, reason, retry_after

            # Check rate limit
            history = self._operation_history[identifier]
            cutoff_time = current_time - timedelta(seconds=config.time_window_seconds)

            # Remove old entries
            while history and history[0] < cutoff_time:
                history.popleft()

            if len(history) >= config.max_operations:
                # Rate limit exceeded - apply cooldown
                self._cooldown_until[identifier] = current_time + timedelta(
                    seconds=config.cooldown_seconds
                )
                reason = (
                    f"Rate limit ({config.max_operations} per {config.time_window_seconds}s) "
                    f"exceeded for {category.value} operations"
                )
                if self.enable_logging:
                    logger.warning(f"Rate limit exceeded for {identifier}: {reason}")
                return False, reason, float(config.cooldown_seconds)

            # Operation allowed - record it
            history.append(current_time)
            self._burst_counters[identifier] += 1

            if self.enable_logging:
                logger.debug(
                    f"Operation allowed for {identifier}: "
                    f"{len(history)}/{config.max_operations} in window, "
                    f"burst: {self._burst_counters[identifier]}/{config.burst_limit}"
                )

            return True, None, None

    def reset_limits(self, identifier: Optional[str] = None) -> None:
        """Reset rate limits for an identifier or all identifiers.

        Args:
            identifier: Specific identifier to reset (None to reset all)

        """
        with self._lock:
            if identifier:
                if identifier in self._operation_history:
                    del self._operation_history[identifier]
                if identifier in self._cooldown_until:
                    del self._cooldown_until[identifier]
                if identifier in self._burst_counters:
                    del self._burst_counters[identifier]
                if identifier in self._burst_reset_times:
                    del self._burst_reset_times[identifier]
                logger.info(f"Reset rate limits for {identifier}")
            else:
                self._operation_history.clear()
                self._cooldown_until.clear()
                self._burst_counters.clear()
                self._burst_reset_times.clear()
                logger.info("Reset all rate limits")

    def get_remaining_capacity(
        self, identifier: str, category: CommandCategory
    ) -> Dict[str, Any]:
        """Get remaining capacity for an identifier.

        Args:
            identifier: The identifier to check
            category: Command category

        Returns:
            Dictionary with capacity information

        """
        with self._lock:
            config = self.configs[category]
            current_time = datetime.now()

            # Check cooldown
            if identifier in self._cooldown_until:
                cooldown_end = self._cooldown_until[identifier]
                if current_time < cooldown_end:
                    cooldown_remaining = (cooldown_end - current_time).total_seconds()
                else:
                    cooldown_remaining = 0
            else:
                cooldown_remaining = 0

            # Count operations in window
            history = self._operation_history[identifier]
            cutoff_time = current_time - timedelta(seconds=config.time_window_seconds)
            recent_operations = sum(1 for t in history if t > cutoff_time)

            # Burst information
            burst_count = self._burst_counters.get(identifier, 0)

            return {
                "category": category.value,
                "operations_used": recent_operations,
                "operations_limit": config.max_operations,
                "operations_remaining": max(0, config.max_operations - recent_operations),
                "burst_used": burst_count,
                "burst_limit": config.burst_limit,
                "burst_remaining": max(0, config.burst_limit - burst_count),
                "cooldown_seconds": cooldown_remaining,
                "time_window_seconds": config.time_window_seconds,
            }

    def get_statistics(self) -> Dict[str, Any]:
        """Get rate limiter statistics.

        Returns:
            Dictionary of statistics

        """
        with self._lock:
            total_operations = sum(len(h) for h in self._operation_history.values())
            active_cooldowns = sum(
                1
                for cd in self._cooldown_until.values()
                if cd > datetime.now()
            )

            return {
                "total_tracked_identifiers": len(self._operation_history),
                "total_operations": total_operations,
                "active_cooldowns": active_cooldowns,
                "configurations": {
                    cat.value: {
                        "max_operations": cfg.max_operations,
                        "time_window": cfg.time_window_seconds,
                        "burst_limit": cfg.burst_limit,
                        "cooldown": cfg.cooldown_seconds,
                    }
                    for cat, cfg in self.configs.items()
                },
            }

    def apply_adaptive_limits(
        self, identifier: str, success_rate: float
    ) -> None:
        """Apply adaptive rate limits based on operation success rate.

        Args:
            identifier: The identifier to adjust
            success_rate: Success rate (0.0 to 1.0)

        """
        with self._lock:
            if success_rate < 0.5:
                # Poor success rate - apply stricter limits
                logger.warning(
                    f"Applying stricter limits for {identifier} due to low success rate: {success_rate:.2%}"
                )
                # Add to cooldown for 60 seconds
                self._cooldown_until[identifier] = datetime.now() + timedelta(seconds=60)
            elif success_rate > 0.95 and identifier in self._cooldown_until:
                # High success rate - consider removing cooldown
                logger.info(
                    f"Removing cooldown for {identifier} due to high success rate: {success_rate:.2%}"
                )
                del self._cooldown_until[identifier]
