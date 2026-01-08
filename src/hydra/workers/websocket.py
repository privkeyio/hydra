"""WebSocket functionality for real-time task progress updates."""

import asyncio
import json
import logging
from typing import Dict, Set

import websockets

logger = logging.getLogger(__name__)

connected_clients: Dict[str, Set] = {}
progress_updates: Dict[str, dict] = {}


async def register_client(websocket, task_id: str):
    """Register a client for task progress updates."""
    if task_id not in connected_clients:
        connected_clients[task_id] = set()
    connected_clients[task_id].add(websocket)

    if task_id in progress_updates:
        await websocket.send(json.dumps(progress_updates[task_id]))


async def unregister_client(websocket, task_id: str):
    """Unregister a client from task progress updates."""
    if task_id in connected_clients:
        connected_clients[task_id].discard(websocket)
        if not connected_clients[task_id]:
            del connected_clients[task_id]


async def handle_client(websocket, path: str):
    """Handle WebSocket client connections."""
    task_id = None
    try:
        message = await websocket.recv()
        data = json.loads(message)

        if data.get("action") == "subscribe" and "task_id" in data:
            task_id = data["task_id"]
            await register_client(websocket, task_id)

            async for _message in websocket:
                pass

    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if task_id:
            await unregister_client(websocket, task_id)


async def broadcast_progress(task_id: str, progress: dict):
    """Broadcast progress update to all connected clients."""
    if task_id in connected_clients:
        message = json.dumps(progress)
        dead_clients = set()

        for client in connected_clients[task_id]:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                dead_clients.add(client)

        connected_clients[task_id] -= dead_clients


def send_progress_update(task_id: str, progress: int, message: str):
    """Send progress update to WebSocket clients."""
    update = {
        "task_id": task_id,
        "progress": progress,
        "message": message,
        "timestamp": asyncio.get_event_loop().time(),
    }

    progress_updates[task_id] = update

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(broadcast_progress(task_id, update))
    except RuntimeError:
        asyncio.run(broadcast_progress(task_id, update))


async def start_websocket_server(host: str = "0.0.0.0", port: int = 8765):
    """Start the WebSocket server for progress updates."""
    async with websockets.serve(handle_client, host, port):
        logger.info(f"WebSocket server started on ws://{host}:{port}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(start_websocket_server())
