"""Dashboard management commands for Hydra CLI."""

import os
import subprocess
import sys
from pathlib import Path


def add_dashboard_parser(subparsers):
    """Add dashboard management subcommand to the parser."""
    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Manage the Hydra web dashboard"
    )
    dashboard_parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status", "open"],
        help="Dashboard action to perform"
    )
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for dashboard (default: 8080)"
    )
    dashboard_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    dashboard_parser.add_argument(
        "--no-daemon",
        action="store_true",
        help="Run in foreground instead of background"
    )


def handle_dashboard_command(args) -> int:
    """Handle dashboard management commands."""
    action = args.action
    
    if action == "open":
        # Open dashboard in browser
        import webbrowser
        port = getattr(args, 'port', 8080)
        url = f"http://localhost:{port}"
        
        webbrowser.open(url)
        print(f"Dashboard opened in browser: {url}")
        return 0
    
    # Build command for standalone dashboard
    # Use pipx venv Python if available, otherwise fallback to system Python
    import shutil
    pipx_python = "/home/kyle/.local/share/pipx/venvs/hydra-agents/bin/python"
    if os.path.exists(pipx_python):
        python_exe = pipx_python
    else:
        python_exe = sys.executable
    
    cmd = [
        python_exe,
        "-m",
        "hydra.dashboard.standalone",
        action
    ]
    
    if hasattr(args, 'port'):
        cmd.extend(["--port", str(args.port)])
    
    if hasattr(args, 'host'):
        cmd.extend(["--host", args.host])
    
    if action == "start":
        # Default to daemon mode unless --no-daemon is specified
        if not getattr(args, 'no_daemon', False):
            cmd.append("--daemon")
    
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error managing dashboard: {e}")
        return 1
    except FileNotFoundError:
        print("Dashboard module not found. Ensure hydra is properly installed.")
        return 1