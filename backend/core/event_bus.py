"""
Async EventBus — pub/sub backbone for the multi-agent platform.

Agents publish events; the bus fans them out to all subscribers for
that event type (including the WebSocket connection manager).
"""

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Awaitable
from datetime import datetime


@dataclass
class AgentEvent:
    audit_id: str
    agent_name: str
    event_type: str          # agent.started | agent.completed | agent.failed | issue.found | audit.completed
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


Handler = Callable[[AgentEvent], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = {}

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: Handler) -> None:
        """Subscribe to every event type (wildcard)."""
        self._subscribers.setdefault("*", []).append(handler)

    async def publish(self, event: AgentEvent) -> None:
        handlers = (
            self._subscribers.get(event.event_type, [])
            + self._subscribers.get("*", [])
        )
        if handlers:
            await asyncio.gather(*[h(event) for h in handlers], return_exceptions=True)

    def clear(self) -> None:
        self._subscribers.clear()
