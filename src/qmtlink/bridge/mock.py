from __future__ import annotations

import time

from qmtlink.errors import QMTLinkError
from qmtlink.models import (
    AccountAsset,
    CancelResult,
    OrderPreview,
    OrderRecord,
    OrderRequest,
    OrderResult,
    Position,
    Quote,
    TradeRecord,
)

from .idempotency import IdempotencyStore


class MockBridge:
    mode = "mock"

    def __init__(self, idempotency_db: str = ":memory:") -> None:
        self._orders: dict[str, OrderRecord] = {}
        self._idempotency = IdempotencyStore(idempotency_db)

    def health(self) -> dict[str, object]:
        return {"mode": self.mode, "qmt_connected": False, "mock": True}

    def capabilities(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "market_data": True,
            "realtime_stream": False,
            "trading": True,
            "real_trading": False,
            "account_queries": True,
            "cancel_orders": True,
        }

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        now = int(time.time() * 1000)
        return [
            Quote(
                symbol=symbol,
                last_price=round(8 + (sum(map(ord, symbol)) % 5000) / 100, 2),
                volume=0,
                timestamp=now,
            )
            for symbol in symbols
        ]

    def get_asset(self) -> AccountAsset:
        return AccountAsset(
            account_id="mock-account",
            cash=1_000_000.0,
            frozen_cash=0.0,
            market_value=0.0,
            total_asset=1_000_000.0,
        )

    def get_positions(self) -> list[Position]:
        return []

    def get_orders(self, *, cancelable_only: bool = False) -> list[OrderRecord]:
        orders = list(self._orders.values())
        if cancelable_only:
            return [order for order in orders if order.status in {"accepted", "partial_filled"}]
        return orders

    def get_order(self, order_id: str) -> OrderRecord | None:
        return self._orders.get(order_id)

    def get_trades(self) -> list[TradeRecord]:
        return []

    def preview_order(self, order: OrderRequest) -> OrderPreview:
        estimated = None if order.price is None else round(order.price * order.quantity, 2)
        return OrderPreview(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            order_type=order.order_type,
            estimated_amount=estimated,
            risk_checks={
                "valid_quantity": True,
                "valid_price": True,
                "real_trading": False,
            },
        )

    def place_order(self, order: OrderRequest) -> OrderResult:
        existing = self._idempotency.reserve(order)
        if existing is not None:
            return existing
        result = OrderResult(
            client_order_id=order.client_order_id,
            order_id=f"mock-{order.client_order_id}",
            status="accepted",
            submitted=True,
        )
        self._orders[result.order_id] = OrderRecord(
            account_id="mock-account",
            order_id=result.order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price or 0.0,
            order_type=order.order_type,
            traded_quantity=0,
            traded_price=0.0,
            status="accepted",
        )
        self._idempotency.complete(result)
        return result

    def cancel_order(self, order_id: str) -> CancelResult:
        order = self._orders.get(order_id)
        if order is None:
            raise QMTLinkError(
                "ORDER_NOT_FOUND", f"order {order_id} was not found", status_code=404
            )
        order.status = "canceled"
        return CancelResult(order_id=order_id, status="cancel_requested", submitted=True)

    def close(self) -> None:
        self._idempotency.close()
