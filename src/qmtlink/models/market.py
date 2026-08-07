from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class QuoteRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=500)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: list[str]) -> list[str]:
        normalized = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
        if not normalized:
            raise ValueError("at least one symbol is required")
        return list(dict.fromkeys(normalized))


class Quote(BaseModel):
    symbol: str
    last_price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    timestamp: int | None = None
