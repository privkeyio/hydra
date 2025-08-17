"""Hydra Dashboard Module with FastAPI, WebSocket and database support."""

# Core imports that don't require external dependencies
from .database import (
    DatabaseManager,
    Execution,
    Project,
    Session,
    Ticket,
    User,
    get_db_manager,
)
from .state import DashboardState, TicketStatus

# Try to import FastAPI-dependent modules
try:
    from .app import DashboardServer, run_dashboard
    from .export import DataExporter
    from .websocket import DashboardWebSocketHandler, get_ws_handler
except ImportError as e:
    import logging

    logger = logging.getLogger(__name__)
    logger.warning(f"Some dashboard features unavailable: {e}")

    # Provide fallback implementations
    DashboardServer = None
    run_dashboard = None
    DataExporter = None
    DashboardWebSocketHandler = None
    get_ws_handler = None

__all__ = [
    "DashboardServer",
    "run_dashboard",
    "DashboardState",
    "TicketStatus",
    "DatabaseManager",
    "Project",
    "Ticket",
    "Session",
    "Execution",
    "User",
    "get_db_manager",
    "DataExporter",
    "DashboardWebSocketHandler",
    "get_ws_handler",
]
