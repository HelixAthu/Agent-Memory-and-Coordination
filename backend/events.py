"""SSE event contract, event data models, and event bus for live and mock runs."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class Event:
    """Standardized event envelope matching the spec SSE contract."""

    seq: int
    ts: str
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """Format event for Server-Sent Events stream."""
        payload = json.dumps(asdict(self), ensure_ascii=False)
        return f"event: {self.type}\ndata: {payload}\n\n"


class EventBus:
    """Central event bus sequencing and distributing events to subscribers."""

    def __init__(self) -> None:
        self._seq: int = 0
        self.events: list[Event] = []
        self._listeners: list[Callable[[Event], Any]] = []
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()

    @property
    def current_seq(self) -> int:
        """Return the current event sequence index."""
        return self._seq

    def subscribe(self, listener: Callable[[Event], Any]) -> None:
        """Register an event listener callback."""
        self._listeners.append(listener)

    async def emit(self, event_type: str, data: dict[str, Any]) -> Event:
        """Create, sequence, persist, and broadcast an event."""
        self._seq += 1
        ts = datetime.now(timezone.utc).isoformat()
        evt = Event(seq=self._seq, ts=ts, type=event_type, data=data)
        self.events.append(evt)

        # Notify callbacks
        for listener in self._listeners:
            try:
                res = listener(evt)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

        # Enqueue for async streaming
        await self._queue.put(evt)
        return evt

    async def get_next(self, timeout: float | None = None) -> Event | None:
        """Retrieve the next queued event or None if ended."""
        if timeout is not None:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        return await self._queue.get()

    async def close(self) -> None:
        """Signal end of event stream."""
        await self._queue.put(None)
