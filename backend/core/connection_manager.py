"""
WebSocket connection manager — broadcasts agent events to connected browser clients.
"""

from fastapi import WebSocket
from core.event_bus import AgentEvent


class ConnectionManager:
    def __init__(self) -> None:
        # audit_id → list of open WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, audit_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(audit_id, []).append(websocket)

    def disconnect(self, audit_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(audit_id, [])
        if websocket in conns:
            conns.remove(websocket)

    async def broadcast(self, audit_id: str, message: dict) -> None:
        dead = []
        for ws in self._connections.get(audit_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(audit_id, ws)

    async def event_handler(self, event: AgentEvent) -> None:
        """Plug this into EventBus.subscribe_all() to forward all events over WebSocket."""
        await self.broadcast(
            event.audit_id,
            {
                "event":      event.event_type,
                "agent":      event.agent_name,
                "timestamp":  event.timestamp,
                **event.data,
            },
        )


# Singleton shared across the app
manager = ConnectionManager()
