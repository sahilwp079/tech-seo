"""WebSocket route — streams agent events to the browser in real time."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.connection_manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/audit/{audit_id}")
async def audit_websocket(audit_id: str, websocket: WebSocket):
    await manager.connect(audit_id, websocket)
    try:
        while True:
            # Keep connection alive; events are pushed from the backend
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(audit_id, websocket)
