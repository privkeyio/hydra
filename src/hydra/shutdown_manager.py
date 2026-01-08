"""Graceful Shutdown Manager for Hydra.

Coordinates shutdown sequence across all system components to ensure:
- Running tasks complete before shutdown
- State is saved before closing connections
- All connections are properly closed
- Background threads are stopped gracefully
- No hanging processes remain
"""

import atexit
import logging
import signal
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ShutdownManager:
    """Manages graceful shutdown sequence for Hydra components."""

    def __init__(self):
        self._shutdown_requested = False
        self._shutdown_complete = False
        self._lock = threading.RLock()
        self._shutdown_handlers: List[Callable[[], None]] = []
        self._active_tasks: Set[str] = set()
        self._background_threads: Set[threading.Thread] = set()
        self._connections: Dict[str, Any] = {}
        self._state_savers: List[Callable[[], None]] = []

        # Setup signal handlers
        self._original_sigint = signal.signal(signal.SIGINT, self._signal_handler)
        self._original_sigterm = signal.signal(signal.SIGTERM, self._signal_handler)

        # Register atexit handler as fallback
        atexit.register(self.shutdown)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        print(f"\n🛑 Received {signal_name}, initiating graceful shutdown...")
        self.shutdown()

    def register_shutdown_handler(self, handler: Callable[[], None]) -> None:
        """Register a function to be called during shutdown."""
        with self._lock:
            self._shutdown_handlers.append(handler)

    def register_task(self, task_id: str) -> None:
        """Register an active task that should complete before shutdown."""
        with self._lock:
            self._active_tasks.add(task_id)
            logger.debug(f"Registered active task: {task_id}")

    def unregister_task(self, task_id: str) -> None:
        """Unregister a completed task."""
        with self._lock:
            self._active_tasks.discard(task_id)
            logger.debug(f"Unregistered task: {task_id}")

    def register_background_thread(self, thread: threading.Thread) -> None:
        """Register a background thread for graceful shutdown."""
        with self._lock:
            self._background_threads.add(thread)

    def unregister_background_thread(self, thread: threading.Thread) -> None:
        """Unregister a background thread."""
        with self._lock:
            self._background_threads.discard(thread)

    def register_connection(self, name: str, connection: Any) -> None:
        """Register a connection for proper cleanup."""
        with self._lock:
            self._connections[name] = connection

    def unregister_connection(self, name: str) -> None:
        """Unregister a connection."""
        with self._lock:
            self._connections.pop(name, None)

    def register_state_saver(self, saver: Callable[[], None]) -> None:
        """Register a state saving function."""
        with self._lock:
            self._state_savers.append(saver)

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested

    def wait_for_tasks_completion(self, timeout: float = 30.0) -> bool:
        """Wait for all active tasks to complete."""
        start_time = time.time()

        while self._active_tasks and (time.time() - start_time) < timeout:
            with self._lock:
                active_count = len(self._active_tasks)

            if active_count > 0:
                print(f"⏳ Waiting for {active_count} active task(s) to complete...")
                logger.info(f"Waiting for tasks: {list(self._active_tasks)}")
                time.sleep(1.0)

        with self._lock:
            if self._active_tasks:
                task_list = list(self._active_tasks)
                logger.warning(f"Tasks still active after timeout: {task_list}")
                count = len(self._active_tasks)
                print(f"⚠️  {count} task(s) did not complete within timeout")
                return False
            else:
                print("✅ All tasks completed successfully")
                return True

    def save_all_state(self) -> None:
        """Save state from all registered state savers."""
        print("💾 Saving application state...")

        for i, saver in enumerate(self._state_savers):
            try:
                saver()
                logger.debug(f"State saver {i} completed successfully")
            except Exception as e:
                logger.error(f"State saver {i} failed: {e}")
                print(f"⚠️  Warning: State saver failed: {e}")

    def close_all_connections(self) -> None:
        """Close all registered connections."""
        if not self._connections:
            return

        print("🔌 Closing connections...")

        for name, connection in list(self._connections.items()):
            try:
                # Try common close methods
                if hasattr(connection, "close"):
                    connection.close()
                elif hasattr(connection, "shutdown"):
                    connection.shutdown()
                elif hasattr(connection, "cleanup"):
                    connection.cleanup()

                logger.debug(f"Closed connection: {name}")
            except Exception as e:
                logger.error(f"Failed to close connection {name}: {e}")
                print(f"⚠️  Warning: Failed to close {name}: {e}")

    def stop_background_threads(self) -> None:
        """Stop all registered background threads gracefully."""
        if not self._background_threads:
            return

        print("🧵 Stopping background threads...")

        # Remove dead threads first
        live_threads = {t for t in self._background_threads if t.is_alive()}
        self._background_threads = live_threads

        if not live_threads:
            return

        # Wait for threads to finish naturally
        for thread in live_threads:
            try:
                thread.join(timeout=5.0)
                if thread.is_alive():
                    logger.warning(f"Thread {thread.name} did not stop gracefully")
                    print(f"⚠️  Thread {thread.name} did not stop within timeout")
                else:
                    logger.debug(f"Thread {thread.name} stopped gracefully")
            except Exception as e:
                logger.error(f"Error stopping thread {thread.name}: {e}")

    def call_shutdown_handlers(self) -> None:
        """Call all registered shutdown handlers."""
        print("🔧 Running cleanup handlers...")

        for i, handler in enumerate(self._shutdown_handlers):
            try:
                handler()
                logger.debug(f"Shutdown handler {i} completed successfully")
            except Exception as e:
                logger.error(f"Shutdown handler {i} failed: {e}")
                print(f"⚠️  Warning: Cleanup handler failed: {e}")

    def shutdown(self) -> None:
        """Execute graceful shutdown sequence."""
        with self._lock:
            if self._shutdown_requested:
                return
            self._shutdown_requested = True

        logger.info("Starting graceful shutdown sequence")
        print("🛑 Starting graceful shutdown...")

        try:
            # Step 1: Wait for running tasks to complete
            self.wait_for_tasks_completion()

            # Step 2: Save state before closing connections
            self.save_all_state()

            # Step 3: Close all connections properly
            self.close_all_connections()

            # Step 4: Stop background threads gracefully
            self.stop_background_threads()

            # Step 5: Call additional shutdown handlers
            self.call_shutdown_handlers()

            print("✅ Graceful shutdown completed")
            logger.info("Graceful shutdown completed successfully")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            print(f"❌ Error during shutdown: {e}")
        finally:
            with self._lock:
                self._shutdown_complete = True

    def is_shutdown_complete(self) -> bool:
        """Check if shutdown process is complete."""
        return self._shutdown_complete

    def restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm:
            signal.signal(signal.SIGTERM, self._original_sigterm)


# Global shutdown manager instance
_shutdown_manager: Optional[ShutdownManager] = None


def get_shutdown_manager() -> ShutdownManager:
    """Get or create the global shutdown manager."""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = ShutdownManager()
    return _shutdown_manager


def cleanup_shutdown_manager() -> None:
    """Cleanup the global shutdown manager."""
    global _shutdown_manager
    if _shutdown_manager is not None:
        _shutdown_manager.shutdown()
        _shutdown_manager = None
