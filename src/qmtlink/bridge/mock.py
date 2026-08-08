from __future__ import annotations

import time

from qmtlink.errors import QMTLinkError
from qmtlink.models import (
    AccountAsset,
    CancelResult,
    EventBatch,
    HistoricalData,
    HistoryRequest,
    OrderPreview,
    OrderRecord,
    OrderRequest,
    OrderResult,
    Position,
    Quote,
    QuoteSubscription,
    TradeRecord,
)

from .events import EventJournal
from .idempotency import IdempotencyStore


class MockBridge:
    mode = "mock"

    def __init__(self, idempotency_db: str = ":memory:") -> None:
        self._orders: dict[str, OrderRecord] = {}
        self._idempotency = IdempotencyStore(idempotency_db)
        self._events = EventJournal()

    def health(self) -> dict[str, object]:
        return {"mode": self.mode, "qmt_connected": False, "mock": True}

    def capabilities(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "market_data": True,
            "realtime_stream": True,
            "trading": True,
            "real_trading": False,
            "account_queries": True,
            "cancel_orders": True,
            "supported_order_types": ["limit"],
            "historical_data": True,
            "supported_periods": [
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
            ],
            "supported_dividend_types": ["none", "front", "back", "front_ratio", "back_ratio"],
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

    def get_history(self, request: HistoryRequest) -> HistoricalData:
        bars: dict[str, list[dict[str, object]]] = {}
        for symbol in request.symbols:
            seed = sum(map(ord, symbol)) % 100
            rows = [
                {
                    "time": 1_704_067_200_000,
                    "date": 20240101,
                    "open": 10.0 + seed / 100,
                    "high": 10.4 + seed / 100,
                    "low": 9.8 + seed / 100,
                    "close": 10.2 + seed / 100,
                    "volume": 100_000,
                    "amount": 1_020_000.0,
                    "preClose": 9.9 + seed / 100,
                    "suspendFlag": 0,
                },
                {
                    "time": 1_704_153_600_000,
                    "date": 20240102,
                    "open": 10.2 + seed / 100,
                    "high": 10.6 + seed / 100,
                    "low": 10.1 + seed / 100,
                    "close": 10.5 + seed / 100,
                    "volume": 120_000,
                    "amount": 1_260_000.0,
                    "preClose": 10.2 + seed / 100,
                    "suspendFlag": 0,
                },
            ]
            if request.count >= 0:
                rows = rows[-request.count :]
            if request.fields:
                rows = [
                    {
                        key: value
                        for key, value in row.items()
                        if key in {"time", "date"} or key in request.fields
                    }
                    for row in rows
                ]
            bars[symbol] = rows
        return HistoricalData(
            period=request.period,
            start_time=request.start_time,
            end_time=request.end_time,
            count=request.count,
            dividend_type=request.dividend_type,
            fill_data=request.fill_data,
            bars=bars,
            bar_count={symbol: len(rows) for symbol, rows in bars.items()},
        )


    def subscribe_quotes(self, symbols: list[str]) -> QuoteSubscription:
        cursor = self._events.cursor
        quotes = self.get_quotes(symbols)
        for quote in quotes:
            self._events.publish("quote", quote.model_dump(mode="json"))
        return QuoteSubscription(symbols=[quote.symbol for quote in quotes], cursor=cursor)

    def poll_events(
        self, *, after_sequence: int, timeout: float = 0.0, limit: int = 200
    ) -> EventBatch:
        return self._events.poll(
            after_sequence=after_sequence,
            timeout=timeout,
            limit=limit,
        )

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
        self._events.publish(
            "order", self._orders[result.order_id].model_dump(mode="json")
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
        self._events.publish("order", order.model_dump(mode="json"))
        return CancelResult(order_id=order_id, status="cancel_requested", submitted=True)

    def close(self) -> None:
        self._idempotency.close()
