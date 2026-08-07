from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"


class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    quantity: int = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    order_type: OrderType = OrderType.LIMIT
    client_order_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8, max_length=128)
    live: bool = False

    @model_validator(mode="after")
    def validate_order(self) -> OrderRequest:
        self.symbol = self.symbol.strip().upper()
        if not self.symbol:
            raise ValueError("symbol is required")
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("price is required for a limit order")
        return self


class OrderPreview(BaseModel):
    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float | None
    order_type: OrderType
    estimated_amount: float | None
    submitted: bool = False
    risk_checks: dict[str, bool]


class OrderResult(BaseModel):
    client_order_id: str
    order_id: str
    status: str
    submitted: bool
