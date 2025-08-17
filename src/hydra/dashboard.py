"""Real-time monitoring dashboard for Hydra."""

import asyncio
import json
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .monitoring import monitoring, profiler


class DashboardWebSocket:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections.remove(websocket)

    async def broadcast(self, message: dict):
        if self.connections:
            disconnected = []
            for connection in self.connections:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception:
                    disconnected.append(connection)

            for connection in disconnected:
                self.connections.remove(connection)


dashboard_ws = DashboardWebSocket()
app = FastAPI(title="Hydra Monitoring Dashboard")


@app.get("/")
async def dashboard():
    return HTMLResponse(
        """
<!DOCTYPE html>
<html>
<head>
    <title>Hydra Monitoring Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .metrics-grid { display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px; }
        .metric-card { background: white; padding: 20px; border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric-card h3 { margin-top: 0; color: #333; }
        .metric-value { font-size: 2em; font-weight: bold; color: #2196F3; }
        .metric-label { color: #666; font-size: 0.9em; }
        .alert { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .alert-critical { background: #ffebee; border-left: 4px solid #f44336; }
        .alert-high { background: #fff3e0; border-left: 4px solid #ff9800; }
        .alert-warning { background: #f3e5f5; border-left: 4px solid #9c27b0; }
        .chart-container { height: 300px; margin: 20px 0; }
        .status-indicator { display: inline-block; width: 12px; height: 12px;
            border-radius: 50%; margin-right: 8px; }
        .status-healthy { background: #4caf50; }
        .status-unhealthy { background: #f44336; }
        .bottlenecks { max-height: 300px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Hydra Monitoring Dashboard</h1>
            <div id="status">
                <span id="status-indicator"
                      class="status-indicator status-healthy"></span>
                <span id="status-text">System Healthy</span>
                <span id="last-update" style="margin-left: 20px; color: #666;"></span>
            </div>
        </div>

        <div id="alerts-section"></div>

        <div class="metrics-grid">
            <div class="metric-card">
                <h3>Active Agents</h3>
                <div class="metric-value" id="active-agents">0</div>
                <div class="metric-label">Currently Running</div>
            </div>

            <div class="metric-card">
                <h3>Total Operations</h3>
                <div class="metric-value" id="total-operations">0</div>
                <div class="metric-label">Operations Completed</div>
            </div>

            <div class="metric-card">
                <h3>Success Rate</h3>
                <div class="metric-value" id="success-rate">0%</div>
                <div class="metric-label">Operation Success</div>
            </div>

            <div class="metric-card">
                <h3>Average Response Time</h3>
                <div class="metric-value" id="avg-response-time">0ms</div>
                <div class="metric-label">Request Processing</div>
            </div>

            <div class="metric-card">
                <h3>Memory Usage</h3>
                <div class="metric-value" id="memory-usage">0GB</div>
                <div class="metric-label">System Memory</div>
            </div>

            <div class="metric-card">
                <h3>CPU Usage</h3>
                <div class="metric-value" id="cpu-usage">0%</div>
                <div class="metric-label">System CPU</div>
            </div>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <h3>Agent Operations Timeline</h3>
                <div class="chart-container">
                    <canvas id="operations-chart"></canvas>
                </div>
            </div>

            <div class="metric-card">
                <h3>Response Time Distribution</h3>
                <div class="chart-container">
                    <canvas id="response-time-chart"></canvas>
                </div>
            </div>

            <div class="metric-card">
                <h3>Performance Bottlenecks</h3>
                <div class="bottlenecks" id="bottlenecks-list">
                    <div class="metric-label">No bottlenecks detected</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const ws = new WebSocket('ws://localhost:8001/ws');

        const operationsChart = new Chart(document.getElementById('operations-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Operations/min',
                    data: [],
                    borderColor: '#2196F3',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });

        const responseTimeChart = new Chart(
            document.getElementById('response-time-chart'), {
            type: 'bar',
            data: {
                labels: ['< 100ms', '100-500ms', '500ms-1s', '1-5s', '> 5s'],
                datasets: [{
                    label: 'Request Count',
                    data: [0, 0, 0, 0, 0],
                    backgroundColor: '#4caf50'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });

        function updateDashboard(data) {
            document.getElementById('last-update').textContent =
                'Last updated: ' + new Date().toLocaleTimeString();

            if (data.status === 'healthy') {
                document.getElementById('status-indicator').className =
                    'status-indicator status-healthy';
                document.getElementById('status-text').textContent = 'System Healthy';
            } else {
                document.getElementById('status-indicator').className =
                    'status-indicator status-unhealthy';
                document.getElementById('status-text').textContent =
                    'System Issues Detected';
            }

            const metrics = data.metrics || {};

            document.getElementById('active-agents').textContent =
                metrics.agent_started?.current || 0;

            document.getElementById('total-operations').textContent =
                metrics.agent_operations_total?.current || 0;

            const successRate = metrics.workflow_success_rate?.current || 0;
            document.getElementById('success-rate').textContent =
                (successRate * 100).toFixed(1) + '%';

            const avgResponseTime = metrics.agent_execution_time?.average || 0;
            document.getElementById('avg-response-time').textContent =
                (avgResponseTime * 1000).toFixed(0) + 'ms';

            const memoryGB = (metrics.memory_usage?.current || 0) / (1024 ** 3);
            document.getElementById('memory-usage').textContent =
                memoryGB.toFixed(2) + 'GB';

            document.getElementById('cpu-usage').textContent =
                (metrics.cpu_usage?.current || 0).toFixed(1) + '%';

            updateAlerts(data.alerts);
        }

        function updateAlerts(alerts) {
            const alertsSection = document.getElementById('alerts-section');

            if (alerts && alerts.active && alerts.active.length > 0) {
                alertsSection.innerHTML = '<h3>Active Alerts</h3>';

                alerts.active.forEach(alert => {
                    const alertDiv = document.createElement('div');
                    alertDiv.className = `alert alert-${alert.severity}`;
                    alertDiv.innerHTML = `
                        <strong>${alert.metric}</strong>: ${alert.value.toFixed(2)}
                        (threshold: ${alert.threshold}) -
                        ${alert.severity.toUpperCase()}
                    `;
                    alertsSection.appendChild(alertDiv);
                });
            } else {
                alertsSection.innerHTML = '';
            }
        }

        function updateBottlenecks(bottlenecks) {
            const bottlenecksList = document.getElementById('bottlenecks-list');

            if (bottlenecks && bottlenecks.length > 0) {
                bottlenecksList.innerHTML = '';

                bottlenecks.forEach((bottleneck, index) => {
                    const item = document.createElement('div');
                    item.innerHTML = `
                        <strong>${bottleneck.bottleneck}</strong><br>
                        <small>Duration: ${bottleneck.duration.toFixed(2)}s</small>
                    `;
                    item.style.marginBottom = '10px';
                    bottlenecksList.appendChild(item);
                });
            } else {
                bottlenecksList.innerHTML =
                    '<div class="metric-label">No bottlenecks detected</div>';
            }
        }

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);

            if (data.type === 'health_update') {
                updateDashboard(data.data);
            } else if (data.type === 'bottlenecks_update') {
                updateBottlenecks(data.data);
            }
        };

        ws.onopen = function() {
            console.log('Connected to monitoring dashboard');
        };

        ws.onclose = function() {
            console.log('Disconnected from monitoring dashboard');
            setTimeout(() => location.reload(), 3000);
        };
    </script>
</body>
</html>
    """
    )


@app.get("/health")
async def health():
    return monitoring.get_health_status()


@app.get("/metrics")
async def metrics():
    return monitoring.dashboard.get_dashboard_data()


@app.get("/bottlenecks")
async def bottlenecks():
    return profiler.get_bottlenecks()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await dashboard_ws.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        dashboard_ws.disconnect(websocket)


async def broadcast_updates():
    while True:
        try:
            health_data = monitoring.get_health_status()
            await dashboard_ws.broadcast({"type": "health_update", "data": health_data})

            bottlenecks_data = profiler.get_bottlenecks()
            await dashboard_ws.broadcast(
                {"type": "bottlenecks_update", "data": bottlenecks_data}
            )

        except Exception as e:
            print(f"Error broadcasting updates: {e}")

        await asyncio.sleep(5)


def start_dashboard(host: str = "127.0.0.1", port: int = 8001):
    """Start the monitoring dashboard server."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.create_task(broadcast_updates())

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    loop.run_until_complete(server.serve())


if __name__ == "__main__":
    start_dashboard()
