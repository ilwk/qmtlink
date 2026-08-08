from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BridgeEvent(BaseModel):
    sequence: int = Field(ge=1)
    event_type: str
    timestamp_ms: int
    payload: dict[str, Any]


class EventBatch(BaseModel):
    events: list[BridgeEvent]
    next_sequence: int = Field(ge=0)


class QuoteSubscription(BaseModel):
    symbols: list[str]
    cursor: int = Field(ge=0)
