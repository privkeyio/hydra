"""WebSocket support for real-time dashboard updates."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class WebSocketMessage(BaseModel):
    """WebSocket message schema."""

    type: str
    data: Dict[str, Any]
    timestamp: datetime = None

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow()
        super().__init__(**data)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, client_id: str, metadata: Optional[Dict] = None
    ):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()

        async with self.lock:
            if client_id not in self.active_connections:
                self.active_connections[client_id] = []

            self.active_connections[client_id].append(websocket)
            self.connection_metadata[websocket] = metadata or {}

        logger.info(f"WebSocket connected: {client_id}")

        # Send initial connection message
        await self.send_personal_message(
            WebSocketMessage(
                type="connection", data={"status": "connected", "client_id": client_id}
            ),
            websocket,
        )

    async def disconnect(self, websocket: WebSocket, client_id: str):
        """Remove a WebSocket connection."""
        async with self.lock:
            if client_id in self.active_connections:
                if websocket in self.active_connections[client_id]:
                    self.active_connections[client_id].remove(websocket)

                if not self.active_connections[client_id]:
                    del self.active_connections[client_id]

            if websocket in self.connection_metadata:
                del self.connection_metadata[websocket]

        logger.info(f"WebSocket disconnected: {client_id}")

    async def send_personal_message(
        self, message: WebSocketMessage, websocket: WebSocket
    ):
        """Send a message to a specific WebSocket connection."""
        try:
            # Convert datetime to string for JSON serialization
            message_dict = message.dict()
            if message_dict.get("timestamp"):
                message_dict["timestamp"] = message_dict["timestamp"].isoformat()
            await websocket.send_json(message_dict)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast_to_client(self, message: WebSocketMessage, client_id: str):
        """Broadcast a message to all connections for a specific client."""
        if client_id not in self.active_connections:
            return

        disconnected = []

        for connection in self.active_connections[client_id]:
            try:
                # Convert datetime to string for JSON serialization
                message_dict = message.dict()
                if message_dict.get("timestamp"):
                    message_dict["timestamp"] = message_dict["timestamp"].isoformat()
                await connection.send_json(message_dict)
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {e}")
                disconnected.append(connection)

        # Clean up disconnected connections
        for conn in disconnected:
            await self.disconnect(conn, client_id)

    async def broadcast_to_all(self, message: WebSocketMessage):
        """Broadcast a message to all connected clients."""
        all_connections = []
        for connections in self.active_connections.values():
            all_connections.extend(connections)

        disconnected = []

        for connection in all_connections:
            try:
                await connection.send_json(message.dict())
            except Exception as e:
                logger.error(f"Error broadcasting to all: {e}")
                disconnected.append(connection)

        # Clean up disconnected connections
        for conn in disconnected:
            # Find client_id for this connection
            for client_id, connections in self.active_connections.items():
                if conn in connections:
                    await self.disconnect(conn, client_id)
                    break

    async def broadcast_to_group(self, message: WebSocketMessage, group: str):
        """Broadcast a message to all connections in a specific group."""
        disconnected = []

        for websocket, metadata in self.connection_metadata.items():
            if metadata.get("group") == group:
                try:
                    await websocket.send_json(message.dict())
                except Exception as e:
                    logger.error(f"Error broadcasting to group {group}: {e}")
                    disconnected.append(websocket)

        # Clean up disconnected connections
        for conn in disconnected:
            for client_id, connections in self.active_connections.items():
                if conn in connections:
                    await self.disconnect(conn, client_id)
                    break


class DashboardWebSocketHandler:
    """Handles WebSocket connections for the dashboard."""

    def __init__(self):
        """Initialize WebSocket handler."""
        self.manager = ConnectionManager()
        self.subscriptions: Dict[str, Set[str]] = {}

    async def handle_connection(self, websocket: WebSocket, client_id: str):
        """Handle a WebSocket connection lifecycle."""
        await self.manager.connect(websocket, client_id)

        try:
            while True:
                # Receive message from client
                data = await websocket.receive_json()
                await self.handle_message(websocket, client_id, data)

        except WebSocketDisconnect:
            await self.manager.disconnect(websocket, client_id)
            await self.unsubscribe_all(client_id)
        except Exception as e:
            logger.error(f"WebSocket error for {client_id}: {e}")
            await self.manager.disconnect(websocket, client_id)
            await self.unsubscribe_all(client_id)

    async def handle_message(self, websocket: WebSocket, client_id: str, data: dict):
        """Handle incoming WebSocket messages."""
        message_type = data.get("type")

        if message_type == "subscribe":
            await self.handle_subscribe(client_id, data.get("channel"))
        elif message_type == "unsubscribe":
            await self.handle_unsubscribe(client_id, data.get("channel"))
        elif message_type == "ping":
            await self.manager.send_personal_message(
                WebSocketMessage(type="pong", data={}), websocket
            )
        else:
            logger.warning(f"Unknown message type from {client_id}: {message_type}")

    async def handle_subscribe(self, client_id: str, channel: str):
        """Subscribe a client to a channel."""
        if channel not in self.subscriptions:
            self.subscriptions[channel] = set()

        self.subscriptions[channel].add(client_id)

        # Send confirmation
        await self.manager.broadcast_to_client(
            WebSocketMessage(type="subscribed", data={"channel": channel}), client_id
        )

    async def handle_unsubscribe(self, client_id: str, channel: str):
        """Unsubscribe a client from a channel."""
        if channel in self.subscriptions:
            self.subscriptions[channel].discard(client_id)

            if not self.subscriptions[channel]:
                del self.subscriptions[channel]

        # Send confirmation
        await self.manager.broadcast_to_client(
            WebSocketMessage(type="unsubscribed", data={"channel": channel}), client_id
        )

    async def unsubscribe_all(self, client_id: str):
        """Unsubscribe a client from all channels."""
        for channel in list(self.subscriptions.keys()):
            if client_id in self.subscriptions[channel]:
                self.subscriptions[channel].discard(client_id)

                if not self.subscriptions[channel]:
                    del self.subscriptions[channel]

    async def broadcast_to_channel(self, channel: str, message: WebSocketMessage):
        """Broadcast a message to all subscribers of a channel."""
        if channel not in self.subscriptions:
            return

        for client_id in self.subscriptions[channel]:
            await self.manager.broadcast_to_client(message, client_id)

    # Event broadcasting methods
    async def broadcast_ticket_update(self, ticket_id: int, ticket_data: dict):
        """Broadcast ticket update to relevant channels."""
        message = WebSocketMessage(
            type="ticket_update", data={"ticket_id": ticket_id, "ticket": ticket_data}
        )

        # Broadcast to ticket-specific channel
        await self.broadcast_to_channel(f"ticket:{ticket_id}", message)

        # Broadcast to project channel if available
        if "project_id" in ticket_data:
            await self.broadcast_to_channel(
                f"project:{ticket_data['project_id']}", message
            )

        # Broadcast to global updates channel
        await self.broadcast_to_channel("updates", message)

    async def broadcast_execution_update(self, execution_id: int, execution_data: dict):
        """Broadcast execution update to relevant channels."""
        message = WebSocketMessage(
            type="execution_update",
            data={"execution_id": execution_id, "execution": execution_data},
        )

        # Broadcast to execution-specific channel
        await self.broadcast_to_channel(f"execution:{execution_id}", message)

        # Broadcast to ticket channel if available
        if "ticket_id" in execution_data:
            await self.broadcast_to_channel(
                f"ticket:{execution_data['ticket_id']}", message
            )

        # Broadcast to global updates channel
        await self.broadcast_to_channel("updates", message)

    async def broadcast_session_update(self, session_id: str, session_data: dict):
        """Broadcast session update to relevant channels."""
        message = WebSocketMessage(
            type="session_update",
            data={"session_id": session_id, "session": session_data},
        )

        # Broadcast to session-specific channel
        await self.broadcast_to_channel(f"session:{session_id}", message)

        # Broadcast to project channel if available
        if "project_id" in session_data:
            await self.broadcast_to_channel(
                f"project:{session_data['project_id']}", message
            )

        # Broadcast to global updates channel
        await self.broadcast_to_channel("updates", message)

    async def broadcast_log_message(
        self, level: str, message: str, context: dict = None
    ):
        """Broadcast log message to monitoring channels."""
        log_message = WebSocketMessage(
            type="log",
            data={"level": level, "message": message, "context": context or {}},
        )

        # Broadcast to logs channel
        await self.broadcast_to_channel("logs", log_message)

        # For errors, also broadcast to alerts channel
        if level in ["error", "critical"]:
            await self.broadcast_to_channel("alerts", log_message)


# Global WebSocket handler instance
_ws_handler: Optional[DashboardWebSocketHandler] = None


def get_ws_handler() -> DashboardWebSocketHandler:
    """Get or create WebSocket handler singleton."""
    global _ws_handler
    if _ws_handler is None:
        _ws_handler = DashboardWebSocketHandler()
    return _ws_handler
