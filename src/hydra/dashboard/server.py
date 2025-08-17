"""Dashboard HTTP server."""

import json
import logging
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from hydra.dashboard.state import DashboardState

logger = logging.getLogger(__name__)


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for dashboard."""

    def do_GET(self):  # noqa: N802
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/":
            self.serve_html()
        elif path == "/api/state":
            self.serve_state()
        elif path == "/api/events":
            self.serve_events()
        elif path.startswith("/static/"):
            self.serve_static(path)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):  # noqa: N802
        """Handle POST requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/api/clear":
            self.handle_clear()
        else:
            self.send_error(404, "Not Found")

    def serve_html(self):
        """Serve main HTML page."""
        html_path = Path(__file__).parent / "static" / "index.html"

        if not html_path.exists():
            self.send_error(404, "Dashboard HTML not found")
            return

        with open(html_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_state(self):
        """Serve current state as JSON."""
        state = self.server.dashboard_state.get_state()
        content = json.dumps(state).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def serve_events(self):
        """Serve Server-Sent Events stream."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                state = self.server.dashboard_state.get_state()
                event_data = f"data: {json.dumps(state)}\n\n"
                self.wfile.write(event_data.encode("utf-8"))
                self.wfile.flush()
                time.sleep(1)  # Update every second
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_static(self, path):
        """Serve static files."""
        file_path = Path(__file__).parent / path[1:]  # Remove leading /

        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File not found")
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def handle_clear(self):
        """Handle clear state request."""
        self.server.dashboard_state.clear()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "cleared"}')

    def log_message(self, format, *args):
        """Suppress request logging."""
        pass


class DashboardServer:
    """Dashboard web server."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        state: Optional[DashboardState] = None,
    ):
        self.host = host
        self.port = port
        self.dashboard_state = state or DashboardState()
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False

    def start(self):
        """Start the dashboard server."""
        if self.running:
            return

        # Create static directory if it doesn't exist
        static_dir = Path(__file__).parent / "static"
        static_dir.mkdir(exist_ok=True)

        # Try to start server with better error handling
        try:
            self.server = HTTPServer((self.host, self.port), DashboardHandler)
            self.server.dashboard_state = self.dashboard_state
        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning(
                    f"Port {self.port} is already in use, trying to find an available port"
                )
                # Try a few alternative ports
                for alt_port in [8081, 8082, 8083, 8084, 8085]:
                    try:
                        self.port = alt_port
                        self.server = HTTPServer(
                            (self.host, self.port), DashboardHandler
                        )
                        self.server.dashboard_state = self.dashboard_state
                        logger.info(f"Using alternative port {self.port}")
                        break
                    except OSError:
                        continue
                else:
                    # If all ports are taken, raise the original error
                    raise Exception(
                        "Could not find an available port. Try: lsof -ti:8080 | xargs kill -9"
                    )
            else:
                raise

        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        self.running = True

        logger.info(f"Dashboard server started at http://{self.host}:{self.port}")
        print(f"\n📊 Dashboard available at: http://{self.host}:{self.port}\n")

    def _run_server(self):
        """Run the server."""
        try:
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"Dashboard server error: {e}")

    def stop(self):
        """Stop the dashboard server."""
        if self.server and self.running:
            try:
                self.server.shutdown()
                self.server.server_close()
                self.running = False
                logger.info("Dashboard server stopped")
            except Exception as e:
                logger.error(f"Error stopping server: {e}")
                # Force close if graceful shutdown fails
                try:
                    self.server.socket.close()
                except:
                    pass
                self.running = False

    def update_state(self, **kwargs):
        """Update dashboard state."""
        for key, value in kwargs.items():
            if hasattr(self.dashboard_state, key):
                getattr(self.dashboard_state, key)(**value)
