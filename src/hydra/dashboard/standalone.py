#!/usr/bin/env python3
"""Standalone dashboard server that persists between hydra executions."""

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI

from hydra.dashboard.app import app
from hydra.dashboard.database import get_db_manager

logger = logging.getLogger(__name__)

# PID file for process management
PID_FILE = Path.home() / ".hydra" / "dashboard.pid"


def write_pid():
    """Write current process ID to file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def read_pid() -> Optional[int]:
    """Read process ID from file."""
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, FileNotFoundError):
            return None
    return None


def remove_pid():
    """Remove PID file."""
    if PID_FILE.exists():
        PID_FILE.unlink()


def is_running(pid: int) -> bool:
    """Check if process with given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def stop_dashboard():
    """Stop running dashboard server."""
    pid = read_pid()
    if pid and is_running(pid):
        print(f"Stopping dashboard server (PID: {pid})...")
        try:
            os.kill(pid, signal.SIGTERM)
            # Wait a moment for graceful shutdown
            import time
            time.sleep(1)
            
            # Force kill if still running
            if is_running(pid):
                os.kill(pid, signal.SIGKILL)
            
            remove_pid()
            print("Dashboard server stopped.")
            return True
        except Exception as e:
            print(f"Error stopping dashboard: {e}")
            return False
    else:
        print("Dashboard server is not running.")
        remove_pid()
        return False


def start_dashboard(
    host: str = "0.0.0.0",
    port: int = 8080,
    daemon: bool = False,
    log_level: str = "info"
):
    """Start the dashboard server."""
    # Check if already running
    pid = read_pid()
    if pid and is_running(pid):
        print(f"Dashboard already running (PID: {pid})")
        print(f"Access dashboard at http://localhost:{port}")
        return

    if daemon:
        # Fork process to run in background
        pid = os.fork()
        if pid > 0:
            # Parent process
            print(f"Starting dashboard server in background (PID: {pid})...")
            print(f"Access dashboard at http://localhost:{port}")
            print("Stop with: hydra dashboard stop")
            return
        
        # Child process continues
        # Detach from parent
        os.setsid()
        
        # Fork again to prevent zombie processes
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
        
        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Close or redirect file descriptors
        log_file = Path.home() / ".hydra" / "dashboard.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, 'a') as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
            os.dup2(f.fileno(), sys.stderr.fileno())

    # Write PID
    write_pid()

    # Set up signal handlers for graceful shutdown
    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Initialize database - use project-specific database if in a project directory
    if os.path.exists('tickets.md') or os.path.exists('tickets.yaml') or \
       os.path.exists('tickets.yml'):
        # We're in a project directory, use local database
        os.environ['DATABASE_URL'] = f"sqlite:///{os.getcwd()}/.hydra/dashboard/hydra.db"
        logger.info(f"Using project database: {os.getcwd()}/.hydra/dashboard/")
    else:
        # Use global database
        logger.info("Using global database: ~/.hydra/dashboard/")
    
    logger.info("Initializing database...")
    db_manager = get_db_manager()
    db_manager.create_tables()

    # Start server
    logger.info(f"Starting Hydra Dashboard at http://{host}:{port}")
    
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=False,
        reload=False,  # Disable reload for production
    )
    
    server = uvicorn.Server(config)
    
    try:
        server.run()
    finally:
        remove_pid()
        db_manager.close()


def status_dashboard():
    """Check dashboard server status."""
    pid = read_pid()
    if pid and is_running(pid):
        print(f"Dashboard server is running (PID: {pid})")
        print("Access dashboard at http://localhost:8080")
        return True
    else:
        print("Dashboard server is not running")
        remove_pid()
        return False


def main():
    """Main entry point for standalone dashboard."""
    parser = argparse.ArgumentParser(description="Hydra Dashboard Server")
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status"],
        help="Action to perform"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind to (default: 8080)"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in background (daemon mode)"
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level (default: info)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if args.action == "start":
        start_dashboard(args.host, args.port, args.daemon, args.log_level)
    elif args.action == "stop":
        stop_dashboard()
    elif args.action == "restart":
        stop_dashboard()
        import time
        time.sleep(1)
        start_dashboard(args.host, args.port, args.daemon, args.log_level)
    elif args.action == "status":
        status_dashboard()


if __name__ == "__main__":
    main()