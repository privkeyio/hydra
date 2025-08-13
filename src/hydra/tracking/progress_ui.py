"""Visual progress indicators and real-time UI components for ticket tracking.

This module provides visual progress indicators, terminal-based UI components,
and real-time display capabilities for monitoring ticket execution progress.
"""

import shutil
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .progress_tracker import ProgressStage, ProgressTracker, TicketProgress


class ProgressBar:
    """A visual progress bar for terminal display."""

    def __init__(self, width: int = 40, fill_char: str = "█", empty_char: str = "░"):
        """Initialize progress bar.

        Args:
            width: Width of the progress bar in characters
            fill_char: Character to use for filled portion
            empty_char: Character to use for empty portion

        """
        self.width = width
        self.fill_char = fill_char
        self.empty_char = empty_char

    def render(self, percentage: float, prefix: str = "", suffix: str = "") -> str:
        """Render progress bar as a string.

        Args:
            percentage: Progress percentage (0-100)
            prefix: Text to display before the bar
            suffix: Text to display after the bar

        Returns:
            Formatted progress bar string

        """
        percentage = max(0, min(100, percentage))
        filled_width = int(self.width * percentage / 100)

        bar = (
            self.fill_char * filled_width +
            self.empty_char * (self.width - filled_width)
        )

        return f"{prefix} |{bar}| {percentage:5.1f}% {suffix}"


class StageIndicator:
    """Visual indicator for progress stages."""

    def __init__(self):
        """Initialize stage indicator."""
        self.stage_symbols = {
            ProgressStage.STARTED: "🚀",
            ProgressStage.IMPLEMENTATION: "⚙️",
            ProgressStage.TESTING: "🧪",
            ProgressStage.REVIEW: "👀",
            ProgressStage.COMPLETED: "✅",
            ProgressStage.FAILED: "❌",
        }

    def render_stage(self, stage: ProgressStage, show_name: bool = True) -> str:
        """Render a stage indicator.

        Args:
            stage: Progress stage to render
            show_name: Whether to include stage name

        Returns:
            Formatted stage indicator

        """
        symbol = self.stage_symbols.get(stage, "❓")
        if show_name:
            return f"{symbol} {stage.description}"
        return symbol

    def render_stage_timeline(
        self, stages: List[ProgressStage], current: ProgressStage
    ) -> str:
        """Render a timeline of stages.

        Args:
            stages: List of stages in order
            current: Current stage

        Returns:
            Formatted stage timeline

        """
        parts = []
        current_reached = False

        for stage in stages:
            if stage == current:
                current_reached = True
                parts.append(f"[{self.stage_symbols[stage]}]")
            elif not current_reached and stages.index(stage) < stages.index(current):
                parts.append(f"({self.stage_symbols[stage]})")
            else:
                parts.append(f" {self.stage_symbols[stage]} ")

        return " → ".join(parts)


class TicketDisplay:
    """Display component for individual ticket progress."""

    def __init__(self, compact: bool = False):
        """Initialize ticket display.

        Args:
            compact: Whether to use compact display mode

        """
        self.compact = compact
        self.progress_bar = ProgressBar(width=30 if compact else 40)
        self.stage_indicator = StageIndicator()

    def render_ticket(self, progress: TicketProgress, show_details: bool = True) -> str:
        """Render a ticket's progress.

        Args:
            progress: TicketProgress to render
            show_details: Whether to show detailed information

        Returns:
            Formatted ticket display

        """
        lines = []

        # Header with ticket ID and current stage
        stage_display = self.stage_indicator.render_stage(progress.current_stage)
        lines.append(f"Ticket {progress.ticket_id}: {stage_display}")

        if show_details and not self.compact:
            # Progress bar
            progress_line = self.progress_bar.render(
                progress.progress_percentage,
                prefix="Progress:",
                suffix=f"({progress.current_stage.description})"
            )
            lines.append(f"  {progress_line}")

            # Duration
            duration_str = self._format_duration(progress.duration)
            lines.append(f"  Duration: {duration_str}")

            # Latest update
            latest_update = progress.get_latest_update()
            if latest_update and latest_update.message:
                lines.append(f"  Status: {latest_update.message}")

        return "\n".join(lines)

    def render_compact_ticket(self, progress: TicketProgress) -> str:
        """Render a compact single-line ticket display.

        Args:
            progress: TicketProgress to render

        Returns:
            Compact ticket display line

        """
        stage_symbol = self.stage_indicator.render_stage(
            progress.current_stage, show_name=False
        )
        duration = self._format_duration(progress.duration)

        return (
            f"{stage_symbol} Ticket {progress.ticket_id:>3} "
            f"[{progress.progress_percentage:5.1f}%] {duration}"
        )

    def _format_duration(self, seconds: float) -> str:
        """Format duration in a human-readable way.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string

        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"


class ProgressDashboard:
    """Real-time progress dashboard for multiple tickets."""

    def __init__(self, tracker: ProgressTracker, refresh_interval: float = 1.0):
        """Initialize progress dashboard.

        Args:
            tracker: ProgressTracker instance to monitor
            refresh_interval: How often to refresh display (seconds)

        """
        self.tracker = tracker
        self.refresh_interval = refresh_interval
        self.ticket_display = TicketDisplay()
        self.compact_display = TicketDisplay(compact=True)
        self.running = False
        self._display_thread: Optional[threading.Thread] = None

    def start_display(self, mode: str = "summary") -> None:
        """Start real-time display.

        Args:
            mode: Display mode ('summary', 'detailed', 'compact')

        """
        if self.running:
            return

        self.running = True
        self._display_thread = threading.Thread(
            target=self._display_loop,
            args=(mode,),
            daemon=True
        )
        self._display_thread.start()

    def stop_display(self) -> None:
        """Stop real-time display."""
        self.running = False
        if self._display_thread:
            self._display_thread.join(timeout=2.0)

    def _display_loop(self, mode: str) -> None:
        """Display loop for real-time updates.

        Args:
            mode: Display mode

        """
        try:
            while self.running:
                self._refresh_display(mode)
                time.sleep(self.refresh_interval)
        except KeyboardInterrupt:
            self.running = False

    def _refresh_display(self, mode: str) -> None:
        """Refresh the display.

        Args:
            mode: Display mode

        """
        # Clear screen (move cursor to top)
        print("\033[H\033[J", end="")

        if mode == "summary":
            print(self.render_summary())
        elif mode == "detailed":
            print(self.render_detailed())
        elif mode == "compact":
            print(self.render_compact())

        sys.stdout.flush()

    def render_summary(self) -> str:
        """Render summary dashboard.

        Returns:
            Formatted summary display

        """
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append("HYDRA TICKET PROGRESS DASHBOARD")
        lines.append("=" * 60)
        lines.append(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Summary statistics
        summary = self.tracker.get_summary()
        lines.append(f"Total Tickets: {summary['total_tickets']}")
        lines.append(f"Active: {summary['active_tickets']}")
        lines.append(f"Completed: {summary['completed_tickets']}")
        lines.append(f"Failed: {summary['failed_tickets']}")
        lines.append("")

        # Stage breakdown
        lines.append("Stage Breakdown:")
        for stage in ProgressStage:
            count = summary['stage_counts'].get(stage.value, 0)
            if count > 0:
                lines.append(f"  {stage.emoji} {stage.description}: {count}")
        lines.append("")

        # Active tickets
        active_tickets = self.tracker.get_active_tickets()
        if active_tickets:
            lines.append("Active Tickets:")
            lines.append("-" * 40)
            for progress in active_tickets.values():
                lines.append(self.compact_display.render_compact_ticket(progress))
        else:
            lines.append("No active tickets")

        return "\n".join(lines)

    def render_detailed(self) -> str:
        """Render detailed dashboard.

        Returns:
            Formatted detailed display

        """
        lines = []

        # Header
        lines.append("=" * 80)
        lines.append("DETAILED TICKET PROGRESS")
        lines.append("=" * 80)
        lines.append(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        all_tickets = self.tracker.get_all_tickets()
        if not all_tickets:
            lines.append("No tickets being tracked")
            return "\n".join(lines)

        # Sort tickets by status (active first, then by start time)
        sorted_tickets = sorted(
            all_tickets.values(),
            key=lambda t: (t.is_completed, t.start_time)
        )

        for i, progress in enumerate(sorted_tickets):
            if i > 0:
                lines.append("")
            lines.append(self.ticket_display.render_ticket(progress))

        return "\n".join(lines)

    def render_compact(self) -> str:
        """Render compact dashboard.

        Returns:
            Formatted compact display

        """
        lines = []

        # Header
        terminal_width = shutil.get_terminal_size().columns
        header = "HYDRA PROGRESS"
        padding = (terminal_width - len(header)) // 2
        lines.append(" " * padding + header)
        lines.append("-" * terminal_width)

        # Summary line
        summary = self.tracker.get_summary()
        summary_line = (
            f"Total: {summary['total_tickets']} | "
            f"Active: {summary['active_tickets']} | "
            f"Done: {summary['completed_tickets']} | "
            f"Failed: {summary['failed_tickets']}"
        )
        lines.append(summary_line)
        lines.append("")

        # Ticket list
        all_tickets = self.tracker.get_all_tickets()
        if all_tickets:
            # Sort by status and ID
            sorted_tickets = sorted(
                all_tickets.values(),
                key=lambda t: (t.is_completed, int(t.ticket_id))
            )

            for progress in sorted_tickets:
                lines.append(self.compact_display.render_compact_ticket(progress))
        else:
            lines.append("No tickets tracked")

        return "\n".join(lines)

    def print_snapshot(self, mode: str = "summary") -> None:
        """Print a single snapshot of the current progress.

        Args:
            mode: Display mode ('summary', 'detailed', 'compact')

        """
        if mode == "summary":
            print(self.render_summary())
        elif mode == "detailed":
            print(self.render_detailed())
        elif mode == "compact":
            print(self.render_compact())


class ProgressNotifier:
    """Progress notification system for updates."""

    def __init__(self, tracker: ProgressTracker):
        """Initialize progress notifier.

        Args:
            tracker: ProgressTracker to monitor

        """
        self.tracker = tracker
        self.last_notifications: Dict[str, datetime] = {}
        self.notification_interval = timedelta(seconds=30)

    def start_notifications(self) -> None:
        """Start progress notifications."""
        self.tracker.add_callback(self._handle_update)

    def stop_notifications(self) -> None:
        """Stop progress notifications."""
        self.tracker.remove_callback(self._handle_update)

    def _handle_update(self, update) -> None:
        """Handle a progress update.

        Args:
            update: ProgressUpdate to handle

        """
        now = datetime.now()
        last_notification = self.last_notifications.get(update.ticket_id)

        # Rate limit notifications
        if (last_notification and
            now - last_notification < self.notification_interval and
            update.stage != ProgressStage.COMPLETED and
            update.stage != ProgressStage.FAILED):
            return

        self.last_notifications[update.ticket_id] = now

        # Print notification
        stage_emoji = update.stage.emoji
        timestamp = now.strftime("%H:%M:%S")

        notification = (
            f"[{timestamp}] {stage_emoji} Ticket {update.ticket_id}: "
            f"{update.message}"
        )
        print(notification)


def create_progress_display(
    tracker: ProgressTracker, mode: str = "summary"
) -> ProgressDashboard:
    """Create and configure a progress display.

    Args:
        tracker: ProgressTracker instance
        mode: Display mode ('summary', 'detailed', 'compact')

    Returns:
        Configured ProgressDashboard

    """
    dashboard = ProgressDashboard(tracker)

    # Set appropriate refresh interval based on mode
    if mode == "compact":
        dashboard.refresh_interval = 0.5  # Faster updates for compact mode
    elif mode == "detailed":
        dashboard.refresh_interval = 2.0  # Slower updates for detailed mode

    return dashboard


def print_progress_report(
    tracker: ProgressTracker, include_history: bool = False
) -> None:
    """Print a comprehensive progress report.

    Args:
        tracker: ProgressTracker instance
        include_history: Whether to include detailed history

    """
    display = TicketDisplay()

    print("=" * 80)
    print("HYDRA TICKET EXECUTION REPORT")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Summary
    summary = tracker.get_summary()
    print("SUMMARY")
    print("-" * 40)
    print(f"Total Tickets: {summary['total_tickets']}")
    print(f"Completed: {summary['completed_tickets']}")
    print(f"Failed: {summary['failed_tickets']}")
    print(f"Active: {summary['active_tickets']}")

    if summary['total_tickets'] > 0:
        success_rate = (summary['completed_tickets'] / summary['total_tickets']) * 100
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"Total Duration: {summary['total_duration']:.1f}s")
        print(f"Average Duration: {summary['average_duration']:.1f}s")

    print()

    # Tickets by status
    all_tickets = tracker.get_all_tickets()
    if all_tickets:
        completed = tracker.get_completed_tickets()
        active = tracker.get_active_tickets()

        if completed:
            print("COMPLETED TICKETS")
            print("-" * 40)
            for progress in completed.values():
                print(display.render_ticket(progress, show_details=include_history))
                print()

        if active:
            print("ACTIVE TICKETS")
            print("-" * 40)
            for progress in active.values():
                print(display.render_ticket(progress, show_details=include_history))
                print()
    else:
        print("No tickets have been tracked.")
