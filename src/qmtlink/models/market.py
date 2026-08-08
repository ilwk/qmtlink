from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

HistoryPeriod = Literal[
    "tick",
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "1d",
    "1w",
    "1mon",
    "1q",
    "1hy",
    "1y",
    "stoppricedata",
]
DividendType = Literal["none", "front", "back", "front_ratio", "back_ratio"]


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


class HistoryRequest(BaseModel):
    """Parameters for retrieving historical data from xtdata."""

    symbols: list[str] = Field(min_length=1, max_length=200)
    period: HistoryPeriod = "1d"
    start_time: str = ""
    end_time: str = ""
    count: int = Field(default=-1, ge=-1, le=5_000_000)
    dividend_type: DividendType = "none"
    fill_data: bool = False
    fields: list[str] = Field(default_factory=list, max_length=100)
    download: bool = True

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: list[str]) -> list[str]:
        normalized = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
        if not normalized:
            raise ValueError("at least one symbol is required")
        return list(dict.fromkeys(normalized))

    @field_validator("fields")
    @classmethod
    def normalize_fields(cls, fields: list[str]) -> list[str]:
        return list(dict.fromkeys(field.strip() for field in fields if field.strip()))


class HistoricalData(BaseModel):
    period: str
    start_time: str
    end_time: str
    count: int
    dividend_type: str
    fill_data: bool
    bars: dict[str, list[dict[str, Any]]]
    bar_count: dict[str, int]
