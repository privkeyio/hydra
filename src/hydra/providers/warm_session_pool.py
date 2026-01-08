"""Warm Session Pool for Claude Code providers.

Pre-warms Claude Code sessions for instant allocation to reduce startup overhead
from 30 seconds to under 1 second.
"""

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock, RLock
from typing import Any, Dict, Optional

from .interactive_base import InteractiveAIProvider, SessionState

logger = logging.getLogger(__name__)


class PoolSessionState(Enum):
    """States for sessions in the warm pool."""

    WARMING = "warming"
    READY = "ready"
    ALLOCATED = "allocated"
    UNHEALTHY = "unhealthy"
    RECYCLING = "recycling"


@dataclass
class PooledSession:
    """A session managed by the warm pool."""

    session_id: str
    provider: InteractiveAIProvider
    state: PoolSessionState
    created_at: float
    last_health_check: float
    last_used: float
    allocation_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        """Get session age in seconds."""
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        """Get time since last use in seconds."""
        return time.time() - self.last_used


class WarmSessionPool:
    """Pool of pre-warmed Claude Code sessions for instant allocation.

    Maintains 3-5 pre-initialized sessions that are health-checked and recycled
    automatically. Provides <1s session acquisition time vs 30s cold start.
    """

    def __init__(
        self,
        provider_factory,
        min_pool_size: int = 3,
        max_pool_size: int = 5,
        idle_timeout: int = 300,  # 5 minutes
        health_check_interval: int = 60,  # 1 minute
        max_allocation_count: int = 10,
    ):
        """Initialize the warm session pool.

        Args:
            provider_factory: Factory function to create new providers
            min_pool_size: Minimum number of sessions to maintain
            max_pool_size: Maximum number of sessions to maintain
            idle_timeout: Seconds before idle sessions are recycled
            health_check_interval: Seconds between health checks
            max_allocation_count: Max times a session can be reused

        """
        self.provider_factory = provider_factory
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.idle_timeout = idle_timeout
        self.health_check_interval = health_check_interval
        self.max_allocation_count = max_allocation_count

        self._sessions: Dict[str, PooledSession] = {}
        self._ready_queue: deque = deque()
        self._lock = RLock()
        self._stats_lock = Lock()

        # Statistics
        self._stats = {
            "sessions_created": 0,
            "sessions_allocated": 0,
            "sessions_recycled": 0,
            "health_checks_passed": 0,
            "health_checks_failed": 0,
            "allocation_time_avg": 0.0,
            "workload_history": deque(maxlen=100),
        }

        # Background threads
        self._health_checker_running = False
        self._recycler_running = False
        self._health_thread: Optional[threading.Thread] = None
        self._recycler_thread: Optional[threading.Thread] = None

        # Workload tracking for dynamic sizing
        self._workload_samples: deque = deque(maxlen=20)
        self._last_workload_adjustment = time.time()

        self._start_background_threads()
        self._warm_initial_pool()

    def _start_background_threads(self):
        """Start background maintenance threads."""
        try:
            self._health_checker_running = True
            self._recycler_running = True

            self._health_thread = threading.Thread(
                target=self._health_check_loop,
                daemon=True,
                name="WarmPool-HealthChecker",
            )
            self._health_thread.start()

            self._recycler_thread = threading.Thread(
                target=self._recycler_loop, daemon=True, name="WarmPool-Recycler"
            )
            self._recycler_thread.start()
        except RuntimeError as e:
            # Handle thread creation failures gracefully (e.g., in test environments)
            logger.warning(f"Failed to start background threads: {e}")
            self._health_checker_running = False
            self._recycler_running = False
            self._health_thread = None
            self._recycler_thread = None

    def _warm_initial_pool(self):
        """Pre-warm the initial pool of sessions."""
        logger.info(f"Warming initial pool with {self.min_pool_size} sessions")

        for _ in range(self.min_pool_size):
            self._create_warm_session()

    def _create_warm_session(self) -> Optional[PooledSession]:
        """Create a new warm session."""
        try:
            provider = self.provider_factory()
            session_id = f"warm_{uuid.uuid4().hex[:8]}"

            # Start the session in background
            actual_session_id = provider.start_session(session_id)

            pooled_session = PooledSession(
                session_id=actual_session_id,
                provider=provider,
                state=PoolSessionState.WARMING,
                created_at=time.time(),
                last_health_check=time.time(),
                last_used=time.time(),
            )

            with self._lock:
                self._sessions[actual_session_id] = pooled_session

            # Mark as ready after successful creation
            pooled_session.state = PoolSessionState.READY

            with self._lock:
                self._ready_queue.append(actual_session_id)

            with self._stats_lock:
                self._stats["sessions_created"] += 1

            logger.debug(f"Created warm session: {actual_session_id}")
            return pooled_session

        except Exception as e:
            logger.error(f"Failed to create warm session: {e}")
            return None

    def acquire_session(self, timeout: float = 1.0) -> Optional[InteractiveAIProvider]:
        """Acquire a warm session for use.

        Args:
            timeout: Maximum seconds to wait for a session

        Returns:
            InteractiveAIProvider instance or None if timeout

        """
        start_time = time.time()

        try:
            session = self._get_ready_session(timeout)
            if session:
                # Mark as allocated
                with self._lock:
                    session.state = PoolSessionState.ALLOCATED
                    session.last_used = time.time()
                    session.allocation_count += 1

                # Update statistics
                allocation_time = time.time() - start_time
                with self._stats_lock:
                    self._stats["sessions_allocated"] += 1
                    self._update_avg_allocation_time(allocation_time)

                logger.debug(
                    f"Allocated session {session.session_id} in "
                    f"{allocation_time:.3f}s"
                )
                return session.provider

        except Exception as e:
            logger.error(f"Failed to acquire session: {e}")

        return None

    def _get_ready_session(self, timeout: float) -> Optional[PooledSession]:
        """Get a ready session from the pool."""
        deadline = time.time() + timeout

        while time.time() < deadline:
            with self._lock:
                if self._ready_queue:
                    session_id = self._ready_queue.popleft()
                    session = self._sessions.get(session_id)

                    if session and session.state == PoolSessionState.READY:
                        # Health check before allocation
                        if self._quick_health_check(session):
                            return session
                        else:
                            # Mark unhealthy and try next
                            session.state = PoolSessionState.UNHEALTHY
                            continue

            # No ready sessions, wait briefly
            time.sleep(0.01)

        return None

    def release_session(self, provider: InteractiveAIProvider):
        """Release a session back to the pool.

        Args:
            provider: The provider instance to release

        """
        session_id = None

        # Find session by provider
        with self._lock:
            for sid, session in self._sessions.items():
                if session.provider is provider:
                    session_id = sid
                    break

        if not session_id:
            logger.warning("Attempted to release unknown session")
            return

        session = self._sessions[session_id]

        # Check if session should be recycled
        should_recycle = (
            session.allocation_count >= self.max_allocation_count
            or session.age_seconds > (self.idle_timeout * 2)
            or not self._quick_health_check(session)
        )

        if should_recycle:
            self._recycle_session(session)
        else:
            # Return to pool
            with self._lock:
                session.state = PoolSessionState.READY
                session.last_used = time.time()
                self._ready_queue.append(session_id)

            logger.debug(f"Released session {session_id} back to pool")

    def _quick_health_check(self, session: PooledSession) -> bool:
        """Perform a quick health check on a session.

        Args:
            session: Session to check

        Returns:
            bool: True if session is healthy

        """
        try:
            # Check if session is still valid
            session_info = session.provider.get_session_info(session.session_id)
            if session_info.state in [SessionState.ERROR, SessionState.TERMINATED]:
                return False

            session.last_health_check = time.time()

            with self._stats_lock:
                self._stats["health_checks_passed"] += 1

            return True

        except Exception as e:
            logger.debug(f"Health check failed for {session.session_id}: {e}")

            with self._stats_lock:
                self._stats["health_checks_failed"] += 1

            return False

    def _recycle_session(self, session: PooledSession):
        """Recycle an old or unhealthy session.

        Args:
            session: Session to recycle

        """
        try:
            logger.debug(f"Recycling session {session.session_id}")

            with self._lock:
                session.state = PoolSessionState.RECYCLING

            # Stop the old session
            try:
                session.provider.stop_session(session.session_id)
            except Exception as e:
                logger.debug(f"Error stopping session during recycle: {e}")

            # Remove from tracking
            with self._lock:
                if session.session_id in self._sessions:
                    del self._sessions[session.session_id]

            with self._stats_lock:
                self._stats["sessions_recycled"] += 1

            # Create replacement if below minimum
            with self._lock:
                ready_count = len(
                    [
                        s
                        for s in self._sessions.values()
                        if s.state == PoolSessionState.READY
                    ]
                )

            if ready_count < self.min_pool_size:
                self._create_warm_session()

        except Exception as e:
            logger.error(f"Error recycling session: {e}")

    def _health_check_loop(self):
        """Background thread for periodic health checks."""
        while self._health_checker_running:
            try:
                self._perform_health_checks()
                time.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                time.sleep(5)

    def _perform_health_checks(self):
        """Perform health checks on all sessions."""
        sessions_to_check = []

        with self._lock:
            for session in self._sessions.values():
                states = [PoolSessionState.READY, PoolSessionState.ALLOCATED]
                time_since_check = time.time() - session.last_health_check
                if (
                    session.state in states
                    and time_since_check > self.health_check_interval
                ):
                    sessions_to_check.append(session)

        for session in sessions_to_check:
            if not self._quick_health_check(session):
                session.state = PoolSessionState.UNHEALTHY
                logger.warning(f"Session {session.session_id} marked unhealthy")

    def _recycler_loop(self):
        """Background thread for recycling old sessions."""
        while self._recycler_running:
            try:
                self._recycle_old_sessions()
                self._adjust_pool_size()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Recycler loop error: {e}")
                time.sleep(5)

    def _recycle_old_sessions(self):
        """Recycle sessions that are too old or idle."""
        sessions_to_recycle = []

        with self._lock:
            for session in self._sessions.values():
                if (
                    session.state == PoolSessionState.READY
                    and session.idle_seconds > self.idle_timeout
                ):
                    sessions_to_recycle.append(session)
                elif session.state == PoolSessionState.UNHEALTHY:
                    sessions_to_recycle.append(session)

        for session in sessions_to_recycle:
            self._recycle_session(session)

    def _adjust_pool_size(self):
        """Dynamically adjust pool size based on workload."""
        if time.time() - self._last_workload_adjustment < 60:
            return  # Adjust at most once per minute

        # Sample current workload
        with self._lock:
            allocated_count = len(
                [
                    s
                    for s in self._sessions.values()
                    if s.state == PoolSessionState.ALLOCATED
                ]
            )
            total_count = len(self._sessions)

        utilization = allocated_count / max(total_count, 1)
        self._workload_samples.append(utilization)

        # Calculate average utilization
        if len(self._workload_samples) >= 5:
            avg_utilization = sum(self._workload_samples) / len(self._workload_samples)

            # Adjust pool size based on utilization
            if avg_utilization > 0.8 and total_count < self.max_pool_size:
                # High utilization, grow pool
                self._create_warm_session()
                logger.info(
                    f"Growing pool size due to high utilization: "
                    f"{avg_utilization:.2f}"
                )
            elif avg_utilization < 0.3 and total_count > self.min_pool_size:
                # Low utilization, consider shrinking
                ready_sessions = [
                    s
                    for s in self._sessions.values()
                    if s.state == PoolSessionState.READY
                ]
                oldest_session = min(
                    ready_sessions, key=lambda s: s.last_used, default=None
                )
                if oldest_session:
                    self._recycle_session(oldest_session)
                    logger.info(
                        f"Shrinking pool size due to low utilization: "
                        f"{avg_utilization:.2f}"
                    )

        self._last_workload_adjustment = time.time()

    def _update_avg_allocation_time(self, allocation_time: float):
        """Update average allocation time statistic."""
        current_avg = self._stats["allocation_time_avg"]
        allocation_count = self._stats["sessions_allocated"]

        # Running average
        new_avg = (
            (current_avg * (allocation_count - 1)) + allocation_time
        ) / allocation_count
        self._stats["allocation_time_avg"] = new_avg

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.

        Returns:
            Dict with pool statistics

        """
        with self._lock:
            ready_count = len(
                [
                    s
                    for s in self._sessions.values()
                    if s.state == PoolSessionState.READY
                ]
            )
            allocated_count = len(
                [
                    s
                    for s in self._sessions.values()
                    if s.state == PoolSessionState.ALLOCATED
                ]
            )
            warming_count = len(
                [
                    s
                    for s in self._sessions.values()
                    if s.state == PoolSessionState.WARMING
                ]
            )
            unhealthy_count = len(
                [
                    s
                    for s in self._sessions.values()
                    if s.state == PoolSessionState.UNHEALTHY
                ]
            )

        with self._stats_lock:
            stats = self._stats.copy()

        stats.update(
            {
                "pool_size_current": len(self._sessions),
                "pool_size_min": self.min_pool_size,
                "pool_size_max": self.max_pool_size,
                "sessions_ready": ready_count,
                "sessions_allocated": allocated_count,
                "sessions_warming": warming_count,
                "sessions_unhealthy": unhealthy_count,
                "idle_timeout": self.idle_timeout,
                "health_check_interval": self.health_check_interval,
            }
        )

        return stats

    def shutdown(self):
        """Gracefully shutdown the pool."""
        logger.info("Shutting down warm session pool")

        # Stop background threads
        self._health_checker_running = False
        self._recycler_running = False

        if self._health_thread:
            self._health_thread.join(timeout=5)
        if self._recycler_thread:
            self._recycler_thread.join(timeout=5)

        # Stop all sessions
        with self._lock:
            for session in self._sessions.values():
                try:
                    session.provider.stop_session(session.session_id)
                except Exception as e:
                    logger.debug(f"Error stopping session during shutdown: {e}")

            self._sessions.clear()
            self._ready_queue.clear()

        logger.info("Warm session pool shutdown complete")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()
