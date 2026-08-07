from __future__ import annotations

from pydantic import BaseModel

from .order import OrderSide, OrderType


class AccountAsset(BaseModel):
    account_id: str
    cash: float
    frozen_cash: float
    market_value: float
    total_asset: float


class Position(BaseModel):
    account_id: str
    symbol: str
    quantity: int
    available_quantity: int
    frozen_quantity: int
    on_road_quantity: int
    yesterday_quantity: int
    average_price: float
    open_price: float
    market_value: float


class OrderRecord(BaseModel):
    account_id: str
    order_id: str
    system_order_id: str | None = None
    client_order_id: str | None = None
    symbol: str
    side: OrderSide | None = None
    quantity: int
    price: float
    order_type: OrderType | None = None
    traded_quantity: int
    traded_price: float
    status: str
    status_message: str = ""
    order_time: int | None = None


class TradeRecord(BaseModel):
    account_id: str
    trade_id: str
    order_id: str
    system_order_id: str | None = None
    client_order_id: str | None = None
    symbol: str
    side: OrderSide | None = None
    quantity: int
    price: float
    amount: float
    commission: float = 0.0
    trade_time: int | None = None
