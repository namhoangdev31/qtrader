import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from qtrader.monitoring.warroom_service import WarRoomService

# Global service instance (in a real app, inject this via Depends)
warroom_service = WarRoomService()
router = APIRouter(prefix="/monitoring", tags=["monitoring"])

class ConnectionManager:
    """Manages active WebSocket connections."""
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# Track active broadcast tasks to avoid garbage collection (RUF006)
_broadcast_tasks: set[asyncio.Task[Any]] = set()

# Add a subscriber to WarRoomService
def broadcast_snapshot(snapshot: dict[str, Any]) -> None:
    """Callback to broadcast snapshot updates to WebSocket clients."""
    if manager.active_connections:
        task = asyncio.create_task(manager.broadcast(json.dumps(snapshot)))
        _broadcast_tasks.add(task)
        task.add_done_callback(_broadcast_tasks.discard)

# Register callback
warroom_service.add_subscriber(broadcast_snapshot)

@router.get("/snapshot")  
async def get_snapshot() -> dict[str, Any]:
    """Get the current dashboard snapshot."""
    return warroom_service.get_dashboard_snapshot()

@router.get("/health") 
async def get_health() -> dict[str, Any]:
    """Get the health status of the WarRoom service."""
    return warroom_service.get_health()

@router.websocket("/ws") 
async def monitoring_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time dashboard updates."""
    await manager.connect(websocket)
    try:
        initial = warroom_service.get_dashboard_snapshot()
        await websocket.send_text(json.dumps(initial))
        
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
