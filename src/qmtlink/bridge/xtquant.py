from __future__ import annotations

import time
from threading import RLock
from typing import Any

from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError
from qmtlink.models import (
    AccountAsset,
    CancelResult,
    OrderPreview,
    OrderRecord,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
    Position,
    Quote,
    TradeRecord,
)

from .idempotency import IdempotencyStore, default_idempotency_path


class XtQuantBridge:
    """Adapter around the single local XtQuantTrader runtime."""

    mode = "real"

    def __init__(self, settings: ServerSettings) -> None:
        if not settings.qmt_path or not settings.account_id:
            raise QMTLinkError(
                "QMT_CONFIG_REQUIRED",
                "QMTLINK_QMT_PATH and QMTLINK_ACCOUNT_ID are required in real mode",
                status_code=503,
            )

        try:
            from xtquant import xtconstant, xtdata
            from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
            from xtquant.xttype import StockAccount
        except ImportError as exc:
            raise QMTLinkError(
                "XTQUANT_NOT_INSTALLED",
                "xtquant is unavailable; run `qmt bridge doctor` on the miniQMT machine",
                status_code=503,
            ) from exc

        self._xtconstant = xtconstant
        self._xtdata = xtdata
        self._strategy_name = settings.strategy_name
        self._lock = RLock()
        self._connected = False
        session_id = settings.session_id or (time.time_ns() % 2_000_000_000) + 1
        self._account = StockAccount(settings.account_id, settings.account_type)
        self._trader = XtQuantTrader(settings.qmt_path, session_id)

        bridge = self

        class Callback(XtQuantTraderCallback):
            def on_connected(self) -> None:
                bridge._connected = True

            def on_disconnected(self) -> None:
                bridge._connected = False

        self._callback = Callback()
        try:
            self._trader.register_callback(self._callback)
            self._trader.start()
            connect_result = self._trader.connect()
            if connect_result != 0:
                raise QMTLinkError(
                    "QMT_CONNECT_FAILED",
                    f"XtQuantTrader.connect returned {connect_result}",
                    retryable=True,
                    status_code=503,
                )
            self._connected = True
            subscribe_result = self._trader.subscribe(self._account)
            if subscribe_result != 0:
                raise QMTLinkError(
                    "QMT_SUBSCRIBE_FAILED",
                    f"XtQuantTrader.subscribe returned {subscribe_result}",
                    retryable=True,
                    status_code=503,
                )
            self._idempotency = IdempotencyStore(
                settings.idempotency_db or default_idempotency_path()
            )
        except Exception:
            self.close()
            raise

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise QMTLinkError(
                "QMT_NOT_CONNECTED",
                "XtQuantTrader is disconnected",
                retryable=True,
                status_code=503,
            )

    def _invoke(self, method: str, *args: object) -> Any:
        with self._lock:
            self._ensure_connected()
            try:
                return getattr(self._trader, method)(*args)
            except QMTLinkError:
                raise
            except Exception as exc:
                raise QMTLinkError(
                    "QMT_CALL_FAILED",
                    f"{method} failed: {exc}",
                    retryable=True,
                    status_code=502,
                ) from exc

    def health(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "qmt_connected": self._connected,
            "account_configured": self._account is not None,
            "mock": False,
        }

    def capabilities(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "market_data": True,
            "realtime_stream": False,
            "trading": True,
            "real_trading": True,
            "account_queries": True,
            "cancel_orders": True,
            "supported_order_types": [OrderType.LIMIT.value],
        }

    @staticmethod
    def _number(data: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = data.get(key)
            if value is not None:
                return float(value)
        return None

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        with self._lock:
            self._ensure_connected()
            try:
                raw = self._xtdata.get_full_tick(symbols)
            except Exception as exc:
                raise QMTLinkError(
                    "QMT_MARKET_DATA_FAILED",
                    f"get_full_tick failed: {exc}",
                    retryable=True,
                    status_code=502,
                ) from exc
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

    def get_asset(self) -> AccountAsset:
        asset = self._invoke("query_stock_asset", self._account)
        if asset is None:
            raise QMTLinkError(
                "QMT_ASSET_QUERY_FAILED",
                "query_stock_asset returned no data",
                retryable=True,
                status_code=502,
            )
        return AccountAsset(
            account_id=str(asset.account_id),
            cash=float(asset.cash),
            frozen_cash=float(asset.frozen_cash),
            market_value=float(asset.market_value),
            total_asset=float(asset.total_asset),
        )

    def get_positions(self) -> list[Position]:
        positions = self._invoke("query_stock_positions", self._account) or []
        return [self._position(item) for item in positions]

    def get_orders(self, *, cancelable_only: bool = False) -> list[OrderRecord]:
        orders = self._invoke("query_stock_orders", self._account, cancelable_only) or []
        return [self._order(item) for item in orders]

    def get_order(self, order_id: str) -> OrderRecord | None:
        numeric_id = self._numeric_order_id(order_id)
        order = self._invoke("query_stock_order", self._account, numeric_id)
        return None if order is None else self._order(order)

    def get_trades(self) -> list[TradeRecord]:
        trades = self._invoke("query_stock_trades", self._account) or []
        return [self._trade(item) for item in trades]

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
                "qmt_connected": self._connected,
                "valid_quantity": order.quantity > 0,
                "valid_price": order.price is not None,
            },
        )

    def place_order(self, order: OrderRequest) -> OrderResult:
        with self._lock:
            existing = self._idempotency.reserve(order)
            if existing is not None:
                return existing

            side = (
                self._xtconstant.STOCK_BUY
                if order.side == OrderSide.BUY
                else self._xtconstant.STOCK_SELL
            )
            price_type = self._xtconstant.FIX_PRICE
            try:
                order_id = self._invoke(
                    "order_stock",
                    self._account,
                    order.symbol,
                    side,
                    order.quantity,
                    price_type,
                    order.price or 0.0,
                    self._strategy_name,
                    order.client_order_id,
                )
            except Exception:
                self._idempotency.mark_uncertain(order.client_order_id)
                raise
            if int(order_id) <= 0:
                self._idempotency.release(order.client_order_id)
                raise QMTLinkError(
                    "QMT_ORDER_REJECTED",
                    f"order_stock returned {order_id}",
                    status_code=502,
                )
            result = OrderResult(
                client_order_id=order.client_order_id,
                order_id=str(order_id),
                status="submitted",
                submitted=True,
            )
            self._idempotency.complete(result)
            return result

    def cancel_order(self, order_id: str) -> CancelResult:
        numeric_id = self._numeric_order_id(order_id)
        result = self._invoke("cancel_order_stock", self._account, numeric_id)
        if int(result) != 0:
            raise QMTLinkError(
                "QMT_CANCEL_REJECTED",
                f"cancel_order_stock returned {result}",
                status_code=502,
            )
        return CancelResult(order_id=order_id, status="cancel_requested", submitted=True)

    @staticmethod
    def _numeric_order_id(order_id: str) -> int:
        try:
            return int(order_id)
        except ValueError as exc:
            raise QMTLinkError(
                "INVALID_ORDER_ID",
                "real xtquant order_id must be an integer",
                status_code=400,
            ) from exc

    def _side(self, value: int) -> OrderSide | None:
        if value == self._xtconstant.STOCK_BUY:
            return OrderSide.BUY
        if value == self._xtconstant.STOCK_SELL:
            return OrderSide.SELL
        return None

    def _order_type(self, value: int) -> OrderType | None:
        if value == self._xtconstant.FIX_PRICE:
            return OrderType.LIMIT
        return None

    def _order_status(self, value: int) -> str:
        mapping = {
            self._xtconstant.ORDER_UNREPORTED: "unreported",
            self._xtconstant.ORDER_WAIT_REPORTING: "pending_submit",
            self._xtconstant.ORDER_REPORTED: "accepted",
            self._xtconstant.ORDER_REPORTED_CANCEL: "pending_cancel",
            self._xtconstant.ORDER_PARTSUCC_CANCEL: "partial_filled_pending_cancel",
            self._xtconstant.ORDER_PART_CANCEL: "partial_canceled",
            self._xtconstant.ORDER_CANCELED: "canceled",
            self._xtconstant.ORDER_PART_SUCC: "partial_filled",
            self._xtconstant.ORDER_SUCCEEDED: "filled",
            self._xtconstant.ORDER_JUNK: "rejected",
        }
        return mapping.get(value, "unknown")

    @staticmethod
    def _optional_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text or None

    def _position(self, item: Any) -> Position:
        return Position(
            account_id=str(item.account_id),
            symbol=str(item.stock_code),
            quantity=int(item.volume),
            available_quantity=int(item.can_use_volume),
            frozen_quantity=int(item.frozen_volume),
            on_road_quantity=int(item.on_road_volume),
            yesterday_quantity=int(item.yesterday_volume),
            average_price=float(item.avg_price),
            open_price=float(item.open_price),
            market_value=float(item.market_value),
        )

    def _order(self, item: Any) -> OrderRecord:
        remark = str(item.order_remark or "")
        broker_order_type = int(item.order_type)
        broker_price_type = int(item.price_type)
        broker_order_status = int(item.order_status)
        return OrderRecord(
            account_id=str(item.account_id),
            order_id=str(item.order_id),
            system_order_id=self._optional_text(item.order_sysid),
            client_order_id=remark or None,
            symbol=str(item.stock_code),
            side=self._side(broker_order_type),
            quantity=int(item.order_volume),
            price=float(item.price),
            order_type=self._order_type(broker_price_type),
            traded_quantity=int(item.traded_volume),
            traded_price=float(item.traded_price),
            status=self._order_status(broker_order_status),
            status_message=str(item.status_msg or ""),
            order_time=int(item.order_time),
            broker_order_type=broker_order_type,
            broker_price_type=broker_price_type,
            broker_order_status=broker_order_status,
        )

    def _trade(self, item: Any) -> TradeRecord:
        remark = str(item.order_remark or "")
        broker_order_type = int(item.order_type)
        return TradeRecord(
            account_id=str(item.account_id),
            trade_id=str(item.traded_id),
            order_id=str(item.order_id),
            system_order_id=self._optional_text(item.order_sysid),
            client_order_id=remark or None,
            symbol=str(item.stock_code),
            side=self._side(broker_order_type),
            quantity=int(item.traded_volume),
            price=float(item.traded_price),
            amount=float(item.traded_amount),
            commission=float(getattr(item, "commission", 0.0)),
            trade_time=int(item.traded_time),
            broker_order_type=broker_order_type,
        )

    def close(self) -> None:
        with self._lock:
            trader = getattr(self, "_trader", None)
            try:
                if trader is not None:
                    trader.stop()
            finally:
                self._connected = False
                store = getattr(self, "_idempotency", None)
                if store is not None:
                    store.close()
