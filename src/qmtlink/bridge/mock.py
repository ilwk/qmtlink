from __future__ import annotations

import time

from qmtlink.models import OrderPreview, OrderRequest, OrderResult, Quote


class MockBridge:
    mode = "mock"

    def health(self) -> dict[str, object]:
        return {"mode": self.mode, "qmt_connected": False, "mock": True}

    def capabilities(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "market_data": True,
            "realtime_stream": False,
            "trading": True,
            "real_trading": False,
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
        return OrderResult(
            client_order_id=order.client_order_id,
            order_id=f"mock-{order.client_order_id}",
            status="accepted",
            submitted=True,
        )
