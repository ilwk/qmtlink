from __future__ import annotations

from typing import Any

from qmtlink.errors import QMTLinkError
from qmtlink.models import OrderPreview, OrderRequest, OrderResult, Quote


class XtQuantBridge:
    """Thin, deliberately limited adapter for a locally installed xtquant."""

    mode = "real"

    def __init__(self) -> None:
        try:
            from xtquant import xtdata
        except ImportError as exc:
            raise QMTLinkError(
                "XTQUANT_NOT_INSTALLED",
                "xtquant is unavailable; run `qmt bridge doctor` on the miniQMT machine",
            ) from exc
        self._xtdata = xtdata

    def health(self) -> dict[str, object]:
        return {"mode": self.mode, "qmt_connected": True, "mock": False}

    def capabilities(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "market_data": True,
            "realtime_stream": False,
            "trading": False,
            "real_trading": False,
        }

    @staticmethod
    def _number(data: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = data.get(key)
            if value is not None:
                return float(value)
        return None

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        raw = self._xtdata.get_full_tick(symbols)
        quotes: list[Quote] = []
        for symbol in symbols:
            item = raw.get(symbol, {})
            quotes.append(
                Quote(
                    symbol=symbol,
                    last_price=self._number(item, "lastPrice", "last_price") or 0.0,
                    open=self._number(item, "open"),
                    high=self._number(item, "high"),
                    low=self._number(item, "low"),
                    volume=self._number(item, "volume"),
                    timestamp=item.get("time") or item.get("timestamp"),
                )
            )
        return quotes

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
            risk_checks={"trading_implemented": False},
        )

    def place_order(self, order: OrderRequest) -> OrderResult:
        raise QMTLinkError(
            "TRADING_NOT_IMPLEMENTED",
            "real xtquant trading is not implemented in this preview release",
        )
