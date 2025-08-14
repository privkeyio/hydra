"""Main FastAPI application for Hydra dashboard."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from hydra.dashboard.api import app as api_app
from hydra.dashboard.context_api import router as context_router
from hydra.dashboard.database import get_db_manager
from hydra.dashboard.websocket import get_ws_handler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Hydra Dashboard...")

    # Initialize database
    db_manager = get_db_manager()
    db_manager.create_tables()

    # Initialize WebSocket handler
    ws_handler = get_ws_handler()

    yield

    # Shutdown
    logger.info("Shutting down Hydra Dashboard...")
    db_manager.close()


# Create main FastAPI application
app = FastAPI(
    title="Hydra Dashboard",
    description="Web dashboard for Hydra agent orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API application
app.mount("/api", api_app)

# Include context visualization routes
app.include_router(context_router)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Create default index.html if it doesn't exist
INDEX_HTML = STATIC_DIR / "index.html"
if not INDEX_HTML.exists():
    INDEX_HTML.write_text("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hydra Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            padding: 1rem 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }
        .header h1 {
            color: white;
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .status {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: white;
            font-size: 0.9rem;
        }
        .status-indicator {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #10b981;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .container {
            flex: 1;
            padding: 2rem;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .stat-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            transition: transform 0.3s ease;
        }
        .stat-card:hover {
            transform: translateY(-5px);
        }
        .stat-card h3 {
            color: #6b7280;
            font-size: 0.875rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .stat-card .value {
            color: #1f2937;
            font-size: 2rem;
            font-weight: 700;
        }
        .main-content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
        }
        .panel {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }
        .panel h2 {
            color: #1f2937;
            font-size: 1.25rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #e5e7eb;
        }
        .ticket-list {
            list-style: none;
            max-height: 400px;
            overflow-y: auto;
        }
        .ticket-item {
            padding: 0.75rem;
            border-radius: 8px;
            margin-bottom: 0.5rem;
            background: #f9fafb;
            border-left: 3px solid #6b7280;
            transition: all 0.3s ease;
        }
        .ticket-item:hover {
            background: #f3f4f6;
            transform: translateX(5px);
        }
        .ticket-item.todo { border-left-color: #6b7280; }
        .ticket-item.in-progress { border-left-color: #3b82f6; }
        .ticket-item.done { border-left-color: #10b981; }
        .ticket-title {
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 0.25rem;
        }
        .ticket-meta {
            font-size: 0.875rem;
            color: #6b7280;
            display: flex;
            gap: 1rem;
        }
        .log-output {
            background: #1f2937;
            color: #10b981;
            font-family: 'Courier New', monospace;
            font-size: 0.875rem;
            padding: 1rem;
            border-radius: 8px;
            height: 300px;
            overflow-y: auto;
        }
        .log-line {
            margin-bottom: 0.25rem;
            opacity: 0.8;
        }
        .log-line.error { color: #ef4444; }
        .log-line.warning { color: #f59e0b; }
        .log-line.info { color: #3b82f6; }
        @media (max-width: 768px) {
            .main-content {
                grid-template-columns: 1fr;
            }
            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Hydra Dashboard</h1>
        <div class="status">
            <div class="status-indicator"></div>
            <span id="connection-status">Connected</span>
        </div>
    </div>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Projects</h3>
                <div class="value" id="total-projects">0</div>
            </div>
            <div class="stat-card">
                <h3>Active Tickets</h3>
                <div class="value" id="active-tickets">0</div>
            </div>
            <div class="stat-card">
                <h3>Completed Today</h3>
                <div class="value" id="completed-today">0</div>
            </div>
            <div class="stat-card">
                <h3>Success Rate</h3>
                <div class="value" id="success-rate">0%</div>
            </div>
        </div>
        
        <div class="main-content">
            <div class="panel">
                <h2>Recent Tickets</h2>
                <ul class="ticket-list" id="ticket-list">
                    <li class="ticket-item in-progress">
                        <div class="ticket-title">Loading tickets...</div>
                        <div class="ticket-meta">
                            <span>Please wait</span>
                        </div>
                    </li>
                </ul>
            </div>
            
            <div class="panel">
                <h2>Live Activity</h2>
                <div class="log-output" id="log-output">
                    <div class="log-line info">Dashboard initialized...</div>
                    <div class="log-line">Waiting for WebSocket connection...</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let ws = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 100;  // More attempts for persistent connection
        const baseReconnectDelay = 1000;   // Start with 1 second
        const maxReconnectDelay = 30000;   // Cap at 30 seconds
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            console.log('Attempting to connect to:', wsUrl);
            
            // Update status to show we're connecting
            if (reconnectAttempts > 0) {
                document.getElementById('connection-status').textContent = `Reconnecting... (${reconnectAttempts})`;
                document.querySelector('.status-indicator').style.background = '#f59e0b';
            }
            
            try {
                ws = new WebSocket(wsUrl);
            } catch (e) {
                console.error('Failed to create WebSocket:', e);
                return;
            }
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('connection-status').textContent = 'Connected';
                document.querySelector('.status-indicator').style.background = '#10b981';
                reconnectAttempts = 0;
                
                // Subscribe to channels
                ws.send(JSON.stringify({ type: 'subscribe', channel: 'updates' }));
                ws.send(JSON.stringify({ type: 'subscribe', channel: 'logs' }));
                
                // Request initial data
                fetchDashboardData();
                
                // Add connected message to logs
                addLogMessage({
                    level: 'info',
                    message: 'Dashboard connected to Hydra backend'
                });
            };
            
            ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    handleWebSocketMessage(message);
                } catch (e) {
                    console.error('Failed to parse message:', e);
                }
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                document.getElementById('connection-status').textContent = 'Connection Error';
                document.querySelector('.status-indicator').style.background = '#ef4444';
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected');
                document.getElementById('connection-status').textContent = 'Disconnected';
                document.querySelector('.status-indicator').style.background = '#f59e0b';
                
                // Always attempt to reconnect with exponential backoff
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s, 30s...
                    const delay = Math.min(baseReconnectDelay * Math.pow(2, reconnectAttempts - 1), maxReconnectDelay);
                    
                    console.log(`Reconnecting in ${delay/1000}s... (attempt ${reconnectAttempts}/${maxReconnectAttempts})`);
                    
                    setTimeout(() => {
                        connectWebSocket();
                    }, delay);
                } else {
                    document.getElementById('connection-status').textContent = 'Connection Failed';
                    addLogMessage({
                        level: 'error',
                        message: 'Maximum reconnection attempts reached. Please refresh the page.'
                    });
                }
            };
        }
        
        function handleWebSocketMessage(message) {
            switch (message.type) {
                case 'ticket_update':
                    updateTicket(message.data);
                    break;
                case 'execution_update':
                    updateExecution(message.data);
                    break;
                case 'log':
                    addLogMessage(message.data);
                    break;
                case 'stats_update':
                    updateStats(message.data);
                    break;
            }
        }
        
        function updateTicket(data) {
            // Update ticket in the list
            fetchTickets();
        }
        
        function updateExecution(data) {
            // Add execution log
            addLogMessage({
                level: 'info',
                message: `Execution ${data.execution_id} - ${data.execution.status}`
            });
        }
        
        function addLogMessage(data) {
            const logOutput = document.getElementById('log-output');
            const logLine = document.createElement('div');
            logLine.className = `log-line ${data.level}`;
            logLine.textContent = `[${new Date().toLocaleTimeString()}] ${data.message}`;
            logOutput.appendChild(logLine);
            
            // Keep only last 100 messages
            while (logOutput.children.length > 100) {
                logOutput.removeChild(logOutput.firstChild);
            }
            
            // Scroll to bottom
            logOutput.scrollTop = logOutput.scrollHeight;
        }
        
        function updateStats(stats) {
            document.getElementById('total-projects').textContent = stats.total_projects || 0;
            document.getElementById('active-tickets').textContent = stats.active_tickets || 0;
            document.getElementById('completed-today').textContent = stats.completed_today || 0;
            document.getElementById('success-rate').textContent = `${stats.success_rate || 0}%`;
        }
        
        async function fetchDashboardData() {
            try {
                // Fetch stats
                const statsResponse = await fetch('/api/stats/dashboard');
                if (statsResponse.ok) {
                    const stats = await statsResponse.json();
                    updateStats({
                        total_projects: stats.total_projects || 0,
                        active_tickets: stats.active_tickets || 0,
                        completed_today: stats.completed_today || 0,
                        success_rate: stats.success_rate || 0
                    });
                }
                
                // Fetch tickets
                fetchTickets();
            } catch (error) {
                console.error('Error fetching dashboard data:', error);
            }
        }
        
        async function fetchTickets() {
            try {
                const response = await fetch('/api/tickets?limit=10');
                if (response.ok) {
                    const tickets = await response.json();
                    displayTickets(tickets);
                }
            } catch (error) {
                console.error('Error fetching tickets:', error);
            }
        }
        
        function displayTickets(tickets) {
            const ticketList = document.getElementById('ticket-list');
            ticketList.innerHTML = '';
            
            if (tickets.length === 0) {
                ticketList.innerHTML = '<li class="ticket-item"><div class="ticket-title">No tickets found</div></li>';
                return;
            }
            
            tickets.forEach(ticket => {
                const item = document.createElement('li');
                item.className = `ticket-item ${ticket.status.toLowerCase().replace('_', '-')}`;
                item.innerHTML = `
                    <div class="ticket-title">${ticket.ticket_number}: ${ticket.title}</div>
                    <div class="ticket-meta">
                        <span>Status: ${ticket.status}</span>
                        <span>Priority: ${ticket.priority}</span>
                        <span>Model: ${ticket.model || 'N/A'}</span>
                    </div>
                `;
                ticketList.appendChild(item);
            });
        }
        
        // Initialize
        connectWebSocket();
        
        // Periodic refresh - MORE FREQUENT for better UX
        setInterval(() => {
            fetchDashboardData();  // Always fetch, regardless of WebSocket state
        }, 5000);  // Every 5 seconds instead of 30
    </script>
</body>
</html>""")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard page."""
    return FileResponse(INDEX_HTML)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "hydra-dashboard"}


@app.get("/api/stats/dashboard")
async def get_dashboard_stats():
    """Get dashboard statistics."""
    db_manager = get_db_manager()
    from sqlalchemy import func
    from hydra.dashboard.database import Ticket, Execution, Project
    
    with db_manager.get_session() as db:
        total_projects = db.query(func.count(Project.id)).scalar() or 0
        active_tickets = db.query(func.count(Ticket.id)).filter(
            Ticket.status.in_(["IN_PROGRESS", "TODO"])
        ).scalar() or 0
        completed_today = db.query(func.count(Ticket.id)).filter(
            Ticket.status == "DONE",
            func.date(Ticket.updated_at) == func.date(func.now())
        ).scalar() or 0
        
        total_tickets = db.query(func.count(Ticket.id)).scalar() or 0
        successful_tickets = db.query(func.count(Ticket.id)).filter(
            Ticket.status == "DONE"
        ).scalar() or 0
        
        success_rate = 0
        if total_tickets > 0:
            success_rate = int((successful_tickets / total_tickets) * 100)
    
    return {
        "total_projects": total_projects,
        "active_tickets": active_tickets,
        "completed_today": completed_today,
        "success_rate": success_rate
    }


@app.get("/api/tickets")
async def get_tickets(limit: int = 10, offset: int = 0):
    """Get recent tickets."""
    db_manager = get_db_manager()
    from hydra.dashboard.database import Ticket
    
    with db_manager.get_session() as db:
        tickets = db.query(Ticket).order_by(
            Ticket.created_at.desc()
        ).limit(limit).offset(offset).all()
        
        return [
            {
                "id": t.id,
                "ticket_number": t.ticket_number,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "model": t.model,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None
            }
            for t in tickets
        ]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    ws_handler = get_ws_handler()

    # Generate a unique client ID (in production, use authentication)
    import uuid
    client_id = str(uuid.uuid4())

    await ws_handler.handle_connection(websocket, client_id)


class DashboardServer:
    """Enhanced dashboard server with FastAPI and WebSocket support."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        reload: bool = False,
        log_level: str = "info",
    ):
        """Initialize dashboard server."""
        self.host = host
        self.port = port
        self.reload = reload
        self.log_level = log_level
        self.server = None

    def start(self, background=False):
        """Start the dashboard server.
        
        Args:
            background: If True, run server in background thread (non-blocking)

        """
        logger.info(f"Starting Hydra Dashboard at http://{self.host}:{self.port}")

        # Configure uvicorn
        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            reload=self.reload,
            log_level=self.log_level,
            access_log=False,
        )

        self.server = uvicorn.Server(config)

        if background:
            # Run in background thread for non-blocking operation
            import threading
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            # Give server a moment to start
            import time
            time.sleep(1)
        else:
            try:
                self.server.run()
            except KeyboardInterrupt:
                logger.info("Dashboard server stopped by user")
            except Exception as e:
                logger.error(f"Dashboard server error: {e}")

    def _run_server(self):
        """Internal method to run server in thread."""
        try:
            self.server.run()
        except Exception as e:
            logger.error(f"Dashboard server error: {e}")

    async def start_async(self):
        """Start the dashboard server asynchronously."""
        logger.info(f"Starting Hydra Dashboard at http://{self.host}:{self.port}")

        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            reload=self.reload,
            log_level=self.log_level,
            access_log=False,
        )

        self.server = uvicorn.Server(config)
        await self.server.serve()

    def stop(self):
        """Stop the dashboard server."""
        if self.server:
            self.server.should_exit = True
            logger.info("Dashboard server stopping...")


def run_dashboard(
    host: str = "0.0.0.0",
    port: int = 8080,
    reload: bool = False,
    log_level: str = "info",
):
    """Run the dashboard server."""
    server = DashboardServer(host, port, reload, log_level)
    server.start()


if __name__ == "__main__":
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run dashboard
    run_dashboard(reload="--reload" in sys.argv)
