from __future__ import annotations

import math
import time
from datetime import datetime
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError
from qmtlink.models import (
    AccountAsset,
    CancelResult,
    DividendData,
    DividendRequest,
    EventBatch,
    FinancialData,
    FinancialRequest,
    HistoricalData,
    HistoricalSTData,
    HistoryRequest,
    InstrumentData,
    InstrumentRequest,
    OrderPreview,
    OrderRecord,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
    Position,
    Quote,
    QuoteSubscription,
    SectorData,
    SectorRequest,
    TradeRecord,
)

from .events import EventJournal
from .idempotency import IdempotencyStore, default_idempotency_path

_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


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
        self._events = EventJournal()
        self._quote_subscriptions: dict[str, int] = {}
        session_id = (time.time_ns() % 2_000_000_000) + 1
        self._account = StockAccount(settings.account_id, settings.account_type)
        self._trader = XtQuantTrader(settings.qmt_path, session_id)

        bridge = self

        class Callback(XtQuantTraderCallback):
            def on_connected(self) -> None:
                bridge._connected = True
                bridge._events.publish("connection", {"connected": True})

            def on_disconnected(self) -> None:
                bridge._connected = False
                bridge._events.publish("connection", {"connected": False})

            def on_stock_order(self, order: Any) -> None:
                mapped = bridge._order(order)
                bridge._events.publish("order", mapped.model_dump(mode="json"))

            def on_stock_trade(self, trade: Any) -> None:
                mapped = bridge._trade(trade)
                bridge._events.publish("trade", mapped.model_dump(mode="json"))

            def on_order_error(self, error: Any) -> None:
                bridge._events.publish(
                    "order_error",
                    {
                        "order_id": str(getattr(error, "order_id", "")),
                        "error_id": int(getattr(error, "error_id", 0)),
                        "error_message": str(getattr(error, "error_msg", "")),
                    },
                )

            def on_cancel_error(self, error: Any) -> None:
                bridge._events.publish(
                    "cancel_error",
                    {
                        "order_id": str(getattr(error, "order_id", "")),
                        "error_id": int(getattr(error, "error_id", 0)),
                        "error_message": str(getattr(error, "error_msg", "")),
                    },
                )

            def on_stock_asset(self, asset: Any) -> None:
                mapped = bridge._asset(asset)
                bridge._events.publish("account", mapped.model_dump(mode="json"))

            def on_account_status(self, status: Any) -> None:
                bridge._events.publish(
                    "account_status",
                    {
                        "account_id": str(getattr(status, "account_id", "")),
                        "account_type": int(getattr(status, "account_type", 0)),
                        "status": int(getattr(status, "status", 0)),
                    },
                )

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
            self._idempotency = IdempotencyStore(default_idempotency_path())
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
            "realtime_stream": True,
            "trading": True,
            "real_trading": True,
            "account_queries": True,
            "cancel_orders": True,
            "supported_order_types": [OrderType.LIMIT.value],
            "historical_data": True,
            "instrument_details": True,
            "financial_data": True,
            "dividend_data": True,
            "historical_st_data": True,
            "historical_limit_prices": True,
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

    def _invoke_xtdata(self, method: str, *args: object) -> Any:
        with self._lock:
            self._ensure_connected()
            try:
                return getattr(self._xtdata, method)(*args)
            except QMTLinkError:
                raise
            except Exception as exc:
                raise QMTLinkError(
                    "QMT_MARKET_DATA_FAILED",
                    f"{method} failed: {exc}",
                    retryable=True,
                    status_code=502,
                ) from exc

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): XtQuantBridge._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [XtQuantBridge._json_value(item) for item in value]
        if isinstance(value, float):
            return None if math.isnan(value) else value
        item = getattr(value, "item", None)
        if callable(item):
            try:
                return XtQuantBridge._json_value(item())
            except (TypeError, ValueError):
                pass
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            return isoformat()
        return str(value)

    @classmethod
    def _history_rows(cls, frame: Any) -> list[dict[str, Any]]:
        if frame is None:
            return []
        if hasattr(frame, "to_dict"):
            try:
                raw_rows = frame.to_dict(orient="records")
            except TypeError:
                raw_rows = frame.to_dict()
        elif isinstance(frame, list):
            raw_rows = frame
        elif isinstance(frame, dict):
            values = list(frame.values())
            if values and all(isinstance(value, (list, tuple)) for value in values):
                length = max(len(value) for value in values)
                raw_rows = [
                    {
                        key: value[index] if index < len(value) else None
                        for key, value in frame.items()
                    }
                    for index in range(length)
                ]
            else:
                raw_rows = [frame]
        else:
            return []

        if isinstance(raw_rows, dict):
            raw_rows = [raw_rows]
        index = getattr(frame, "index", None)
        rows: list[dict[str, Any]] = []
        for position, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, dict):
                continue
            row = {str(key): cls._json_value(value) for key, value in raw_row.items()}
            if "time" not in row and index is not None:
                try:
                    row["time"] = cls._json_value(index[position])
                except (IndexError, KeyError, TypeError):
                    pass
            rows.append(row)
        return rows

    def get_history(self, request: HistoryRequest) -> HistoricalData:
        data_symbols = [
            f"{symbol[:-3]}.SH" if symbol.endswith(".SS") else symbol for symbol in request.symbols
        ]
        raw = self._get_market_data(request, data_symbols)
        if not isinstance(raw, dict):
            raise QMTLinkError(
                "QMT_MARKET_DATA_FAILED",
                "get_market_data_ex returned a non-dict result",
                status_code=502,
            )

        missing_symbols = [
            symbol for symbol in data_symbols if not self._history_rows(raw.get(symbol))
        ]
        if missing_symbols:
            self._download_history(request, missing_symbols)
            raw = self._get_market_data(request, data_symbols)
        if not isinstance(raw, dict):
            raise QMTLinkError(
                "QMT_MARKET_DATA_FAILED",
                "get_market_data_ex returned a non-dict result",
                status_code=502,
            )
        bars: dict[str, list[dict[str, Any]]] = {}
        for requested_symbol, data_symbol in zip(request.symbols, data_symbols, strict=True):
            rows = self._history_rows(raw.get(data_symbol))
            if request.period == "1d":
                for row in rows:
                    timestamp = row.get("time")
                    if isinstance(timestamp, (int, float)) and timestamp > 100_000_000_000:
                        row.setdefault(
                            "date",
                            int(
                                datetime.fromtimestamp(timestamp / 1000, tz=_SHANGHAI_TZ).strftime(
                                    "%Y%m%d"
                                )
                            ),
                        )
            bars[requested_symbol] = rows
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

    def get_instruments(self, request: InstrumentRequest) -> InstrumentData:
        instruments: dict[str, dict[str, Any]] = {}
        for requested_symbol in request.symbols:
            data_symbol = (
                f"{requested_symbol[:-3]}.SH"
                if requested_symbol.endswith(".SS")
                else requested_symbol
            )
            raw = self._invoke_xtdata("get_instrument_detail", data_symbol)
            if isinstance(raw, dict):
                instruments[requested_symbol] = self._json_value(raw)
        return InstrumentData(instruments=instruments)

    def get_financial(self, request: FinancialRequest) -> FinancialData:
        data_symbols = [
            f"{symbol[:-3]}.SH" if symbol.endswith(".SS") else symbol
            for symbol in request.symbols
        ]
        raw = self._invoke_xtdata(
            "get_financial_data",
            data_symbols,
            request.tables,
            request.start_time,
            request.end_time,
            request.report_type,
        )
        if not isinstance(raw, dict):
            raise QMTLinkError(
                "QMT_FINANCIAL_DATA_FAILED",
                "get_financial_data returned a non-dict result",
                status_code=502,
            )
        missing = [
            symbol
            for symbol in data_symbols
            if not isinstance(raw.get(symbol), dict) or not raw[symbol]
        ]
        if missing:
            downloader = getattr(self._xtdata, "download_financial_data2", None)
            if callable(downloader):
                self._invoke_xtdata(
                    "download_financial_data2",
                    missing,
                    request.tables,
                    request.start_time,
                    request.end_time,
                )
            else:
                self._invoke_xtdata("download_financial_data", missing, request.tables)
            raw = self._invoke_xtdata(
                "get_financial_data",
                data_symbols,
                request.tables,
                request.start_time,
                request.end_time,
                request.report_type,
            )
        financial: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for requested_symbol, data_symbol in zip(request.symbols, data_symbols, strict=True):
            tables = raw.get(data_symbol, {})
            if not isinstance(tables, dict):
                continue
            financial[requested_symbol] = {
                str(table): self._history_rows(frame)
                for table, frame in tables.items()
                if self._history_rows(frame)
            }
        return FinancialData(
            start_time=request.start_time,
            end_time=request.end_time,
            report_type=request.report_type,
            financial=financial,
        )

    def get_dividends(self, request: DividendRequest) -> DividendData:
        factors: dict[str, list[dict[str, Any]]] = {}
        for requested_symbol in request.symbols:
            data_symbol = (
                f"{requested_symbol[:-3]}.SH"
                if requested_symbol.endswith(".SS")
                else requested_symbol
            )
            raw = self._invoke_xtdata(
                "get_divid_factors",
                data_symbol,
                request.start_time,
                request.end_time,
            )
            factors[requested_symbol] = self._history_rows(raw)
        return DividendData(
            start_time=request.start_time,
            end_time=request.end_time,
            factors=factors,
        )

    def get_historical_st(self, request: InstrumentRequest) -> HistoricalSTData:
        statuses: dict[str, dict[str, Any]] = {}
        for requested_symbol in request.symbols:
            data_symbol = (
                f"{requested_symbol[:-3]}.SH"
                if requested_symbol.endswith(".SS")
                else requested_symbol
            )
            raw = self._invoke_xtdata("get_his_st_data", data_symbol)
            if isinstance(raw, dict):
                statuses[requested_symbol] = self._json_value(raw)
        return HistoricalSTData(statuses=statuses)

    def get_sector_symbols(self, request: SectorRequest) -> SectorData:
        raw = self._invoke_xtdata("get_stock_list_in_sector", request.sector)
        if not isinstance(raw, (list, tuple)):
            raise QMTLinkError(
                "QMT_SECTOR_DATA_FAILED",
                "get_stock_list_in_sector returned a non-list result",
                status_code=502,
            )
        return SectorData(
            sector=request.sector,
            symbols=[str(symbol).strip().upper() for symbol in raw if str(symbol).strip()],
        )

    def _get_market_data(self, request: HistoryRequest, symbols: list[str]) -> Any:
        return self._invoke_xtdata(
            "get_market_data_ex",
            request.fields,
            symbols,
            request.period,
            request.start_time,
            request.end_time,
            request.count,
            request.dividend_type,
            request.fill_data,
        )

    def _download_history(self, request: HistoryRequest, symbols: list[str]) -> None:
        downloader = getattr(self._xtdata, "download_history_data2", None)
        if callable(downloader):
            self._invoke_xtdata(
                "download_history_data2",
                symbols,
                request.period,
                request.start_time,
                request.end_time,
            )
            return
        for symbol in symbols:
            self._invoke_xtdata(
                "download_history_data",
                symbol,
                request.period,
                request.start_time,
                request.end_time,
            )

    def subscribe_quotes(self, symbols: list[str]) -> QuoteSubscription:
        normalized = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols))
        cursor = self._events.cursor
        created: list[int] = []
        try:
            for symbol in normalized:
                if symbol in self._quote_subscriptions:
                    continue

                def on_quote(payload: Any, *, subscribed_symbol: str = symbol) -> None:
                    quote = self._quote_from_callback(subscribed_symbol, payload)
                    if quote is not None:
                        self._events.publish("quote", quote.model_dump(mode="json"))

                subscription_id = self._xtdata.subscribe_quote(
                    symbol,
                    period="tick",
                    count=0,
                    callback=on_quote,
                )
                if subscription_id is None or int(subscription_id) <= 0:
                    raise QMTLinkError(
                        "QMT_MARKET_SUBSCRIBE_FAILED",
                        f"subscribe_quote failed for {symbol}: {subscription_id}",
                        retryable=True,
                        status_code=502,
                    )
                numeric_id = int(subscription_id)
                self._quote_subscriptions[symbol] = numeric_id
                created.append(numeric_id)
        except Exception:
            for subscription_id in created:
                try:
                    self._xtdata.unsubscribe_quote(subscription_id)
                except Exception:
                    pass
            for symbol, subscription_id in list(self._quote_subscriptions.items()):
                if subscription_id in created:
                    self._quote_subscriptions.pop(symbol, None)
            raise
        return QuoteSubscription(symbols=normalized, cursor=cursor)

    def poll_events(
        self, *, after_sequence: int, timeout: float = 0.0, limit: int = 200
    ) -> EventBatch:
        return self._events.poll(
            after_sequence=after_sequence,
            timeout=timeout,
            limit=limit,
        )

    @classmethod
    def _quote_from_callback(cls, symbol: str, payload: Any) -> Quote | None:
        item: Any = payload
        if isinstance(item, dict) and symbol in item:
            item = item[symbol]
        if isinstance(item, (list, tuple)):
            item = item[-1] if item else None
        if not isinstance(item, dict):
            return None
        last_price = cls._number(item, "lastPrice", "last_price", "close") or 0.0
        if last_price <= 0:
            return None
        return Quote(
            symbol=symbol,
            last_price=last_price,
            open=cls._number(item, "open"),
            high=cls._number(item, "high"),
            low=cls._number(item, "low"),
            volume=cls._number(item, "volume"),
            timestamp=item.get("time") or item.get("timestamp"),
        )

    def get_asset(self) -> AccountAsset:
        asset = self._invoke("query_stock_asset", self._account)
        if asset is None:
            raise QMTLinkError(
                "QMT_ASSET_QUERY_FAILED",
                "query_stock_asset returned no data",
                retryable=True,
                status_code=502,
            )
        return self._asset(asset)

    @staticmethod
    def _asset(asset: Any) -> AccountAsset:
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
            for subscription_id in self._quote_subscriptions.values():
                try:
                    self._xtdata.unsubscribe_quote(subscription_id)
                except Exception:
                    pass
            self._quote_subscriptions.clear()
            trader = getattr(self, "_trader", None)
            try:
                if trader is not None:
                    trader.stop()
            finally:
                self._connected = False
                store = getattr(self, "_idempotency", None)
                if store is not None:
                    store.close()
