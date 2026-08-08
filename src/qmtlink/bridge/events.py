from __future__ import annotations

import time
from collections import deque
from threading import Condition
from typing import Any

from qmtlink.errors import QMTLinkError
from qmtlink.models import BridgeEvent, EventBatch


class EventJournal:
    """Bounded, resumable event journal for bridge callbacks."""

    def __init__(self, max_events: int = 10_000) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        self._events: deque[BridgeEvent] = deque(maxlen=max_events)
        self._condition = Condition()
        self._next_sequence = 1

    @property
    def cursor(self) -> int:
        with self._condition:
            return self._next_sequence - 1

    def publish(self, event_type: str, payload: dict[str, Any]) -> BridgeEvent:
        with self._condition:
            event = BridgeEvent(
                sequence=self._next_sequence,
                event_type=event_type,
                timestamp_ms=time.time_ns() // 1_000_000,
                payload=payload,
            )
            self._next_sequence += 1
            self._events.append(event)
            self._condition.notify_all()
            return event

    def poll(
        self,
        *,
        after_sequence: int,
        timeout: float = 0.0,
        limit: int = 200,
    ) -> EventBatch:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        if timeout < 0 or timeout > 30:
            raise ValueError("timeout must be between 0 and 30 seconds")
        if limit <= 0 or limit > 1_000:
            raise ValueError("limit must be between 1 and 1000")

        deadline = time.monotonic() + timeout
        with self._condition:
            while not self._has_events_after(after_sequence):
                self._ensure_cursor_available(after_sequence)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return EventBatch(events=[], next_sequence=after_sequence)
                self._condition.wait(remaining)

            self._ensure_cursor_available(after_sequence)
            events = [event for event in self._events if event.sequence > after_sequence][:limit]
            next_sequence = events[-1].sequence if events else after_sequence
            return EventBatch(events=events, next_sequence=next_sequence)

    def _has_events_after(self, sequence: int) -> bool:
        return bool(self._events and self._events[-1].sequence > sequence)

    def _ensure_cursor_available(self, sequence: int) -> None:
        current = self._next_sequence - 1
        if sequence > current:
            raise QMTLinkError(
                "EVENT_CURSOR_INVALID",
                "event cursor is ahead of this bridge process; resynchronize account state",
                retryable=True,
                status_code=409,
            )
        if self._events and sequence < self._events[0].sequence - 1:
            raise QMTLinkError(
                "EVENT_CURSOR_EXPIRED",
                "event cursor is older than the retained journal; resynchronize account state",
                retryable=True,
                status_code=409,
            )
