import sys
from types import ModuleType, SimpleNamespace

import pytest

from qmtlink.bridge.xtquant import XtQuantBridge
from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError
from qmtlink.models import HistoryRequest, OrderRequest


class FakeCallback:
    pass


class FakeAccount:
    def __init__(self, account_id: str, account_type: str) -> None:
        self.account_id = account_id
        self.account_type = account_type


class FakeTrader:
    instances: list["FakeTrader"] = []

    def __init__(self, path: str, session_id: int) -> None:
        self.path = path
        self.session_id = session_id
        self.callback = None
        self.stopped = False
        self.order_calls = 0
        self.__class__.instances.append(self)

    def register_callback(self, callback) -> None:
        self.callback = callback

    def start(self) -> None:
        pass

    def connect(self) -> int:
        return 0

    def subscribe(self, _account) -> int:
        return 0

    def stop(self) -> None:
        self.stopped = True

    def query_stock_asset(self, account):
        return SimpleNamespace(
            account_id=account.account_id,
            cash=900_000,
            frozen_cash=10_000,
            market_value=90_000,
            total_asset=1_000_000,
        )

    def query_stock_positions(self, account):
        return [
            SimpleNamespace(
                account_id=account.account_id,
                stock_code="000001.SZ",
                volume=1000,
                can_use_volume=800,
                frozen_volume=200,
                on_road_volume=0,
                yesterday_volume=1000,
                avg_price=10.0,
                open_price=9.8,
                market_value=11_000,
            )
        ]

    @staticmethod
    def _order(account, order_id: int):
        return SimpleNamespace(
            account_id=account.account_id,
            stock_code="000001.SZ",
            order_id=order_id,
            order_sysid="sys-123",
            order_time=1_786_000_000,
            order_type=23,
            order_volume=100,
            price_type=11,
            price=10.5,
            traded_volume=0,
            traded_price=0,
            order_status=50,
            status_msg="",
            strategy_name="qmtlink",
            order_remark="client-001",
        )

    def query_stock_orders(self, account, _cancelable_only: bool):
        return [self._order(account, 123)]

    def query_stock_order(self, account, order_id: int):
        return self._order(account, order_id)

    def query_stock_trades(self, account):
        return [
            SimpleNamespace(
                account_id=account.account_id,
                traded_id="trade-1",
                order_id=123,
                order_sysid="sys-123",
                order_remark="client-001",
                stock_code="000001.SZ",
                order_type=23,
                traded_volume=100,
                traded_price=10.5,
                traded_amount=1050,
                commission=0.5,
                traded_time=1_786_000_001,
            )
        ]

    def order_stock(self, *_args) -> int:
        self.order_calls += 1
        return 123

    def cancel_order_stock(self, _account, _order_id: int) -> int:
        return 0


def install_fake_xtquant(monkeypatch) -> None:
    constants = ModuleType("xtquant.xtconstant")
    values = {
        "STOCK_BUY": 23,
        "STOCK_SELL": 24,
        "LATEST_PRICE": 5,
        "FIX_PRICE": 11,
        "ORDER_UNREPORTED": 48,
        "ORDER_WAIT_REPORTING": 49,
        "ORDER_REPORTED": 50,
        "ORDER_REPORTED_CANCEL": 51,
        "ORDER_PARTSUCC_CANCEL": 52,
        "ORDER_PART_CANCEL": 53,
        "ORDER_CANCELED": 54,
        "ORDER_PART_SUCC": 55,
        "ORDER_SUCCEEDED": 56,
        "ORDER_JUNK": 57,
    }
    for name, value in values.items():
        setattr(constants, name, value)

    data = ModuleType("xtquant.xtdata")
    data.callbacks = {}
    data.unsubscribed = []
    data.download_calls = []
    data.get_full_tick = lambda symbols: {
        symbol: {"lastPrice": 10.5, "volume": 1000, "time": 1_786_000_000_000} for symbol in symbols
    }
    data.download_history_data2 = lambda symbols, period, start, end: data.download_calls.append(
        (symbols, period, start, end)
    )
    data.get_market_data_ex = lambda fields, symbols, period, start, end, count, dividend, fill: {
        symbol: [
            {
                "time": 1_704_643_200_000,
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 1000,
                "amount": 10200.0,
                "preClose": 9.9,
                "suspendFlag": 0,
            }
        ]
        for symbol in symbols
    }

    def subscribe_quote(symbol, **kwargs):
        subscription_id = len(data.callbacks) + 1
        data.callbacks[subscription_id] = (symbol, kwargs["callback"])
        return subscription_id

    def unsubscribe_quote(subscription_id):
        data.unsubscribed.append(subscription_id)
        data.callbacks.pop(subscription_id, None)

    data.subscribe_quote = subscribe_quote
    data.unsubscribe_quote = unsubscribe_quote
    trader = ModuleType("xtquant.xttrader")
    trader.XtQuantTrader = FakeTrader
    trader.XtQuantTraderCallback = FakeCallback
    types = ModuleType("xtquant.xttype")
    types.StockAccount = FakeAccount
    package = ModuleType("xtquant")
    package.xtconstant = constants
    package.xtdata = data

    for name, module in {
        "xtquant": package,
        "xtquant.xtconstant": constants,
        "xtquant.xtdata": data,
        "xtquant.xttrader": trader,
        "xtquant.xttype": types,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_xtquant_bridge_lifecycle_queries_and_orders(monkeypatch) -> None:
    install_fake_xtquant(monkeypatch)
    monkeypatch.setattr("qmtlink.bridge.xtquant.default_idempotency_path", lambda: ":memory:")
    FakeTrader.instances.clear()
    bridge = XtQuantBridge(
        ServerSettings(
            qmt_path="C:/miniQMT/userdata_mini",
            account_id="test-account",
        )
    )

    assert bridge.health()["qmt_connected"] is True
    assert bridge.get_asset().total_asset == 1_000_000
    assert bridge.get_positions()[0].available_quantity == 800
    queried_order = bridge.get_orders()[0]
    assert queried_order.status == "accepted"
    assert queried_order.broker_order_type == 23
    assert queried_order.broker_price_type == 11
    assert queried_order.broker_order_status == 50
    assert bridge.get_order("123").client_order_id == "client-001"
    assert bridge.get_trades()[0].commission == 0.5
    assert bridge.get_quotes(["000001.SZ"])[0].last_price == 10.5
    history = bridge.get_history(
        HistoryRequest(
            symbols=["000001.SZ"],
            period="1d",
            start_time="20240101",
            end_time="20240131",
        )
    )
    assert history.bar_count == {"000001.SZ": 1}
    assert history.bars["000001.SZ"][0]["suspendFlag"] == 0
    assert history.bars["000001.SZ"][0]["date"] == 20240108
    assert bridge._xtdata.download_calls == [(["000001.SZ"], "1d", "20240101", "20240131")]

    subscription = bridge.subscribe_quotes(["000001.SZ"])
    _, quote_callback = bridge._xtdata.callbacks[1]
    quote_callback(
        {
            "000001.SZ": [
                {"lastPrice": 10.6, "volume": 1100, "time": 1_786_000_001_000}
            ]
        }
    )
    quote_batch = bridge.poll_events(
        after_sequence=subscription.cursor, timeout=0
    )
    assert quote_batch.events[-1].payload["last_price"] == 10.6

    bridge._callback.on_stock_order(FakeTrader._order(bridge._account, 123))
    bridge._callback.on_stock_trade(bridge._trader.query_stock_trades(bridge._account)[0])
    bridge._callback.on_order_error(
        SimpleNamespace(order_id=123, error_id=42, error_msg="rejected")
    )
    bridge._callback.on_cancel_error(
        SimpleNamespace(order_id=123, error_id=43, error_msg="not cancelable")
    )
    broker_events = bridge.poll_events(
        after_sequence=quote_batch.next_sequence, timeout=0
    )
    assert [event.event_type for event in broker_events.events] == [
        "order",
        "trade",
        "order_error",
        "cancel_error",
    ]
    assert broker_events.events[0].payload["client_order_id"] == "client-001"
    assert broker_events.events[1].payload["trade_id"] == "trade-1"
    assert broker_events.events[2].payload["error_id"] == 42
    assert broker_events.events[3].payload["error_message"] == "not cancelable"

    order = OrderRequest(
        symbol="000001.SZ",
        side="buy",
        quantity=100,
        price=10.5,
        client_order_id="client-001",
        live=True,
    )
    first = bridge.place_order(order)
    second = bridge.place_order(order)
    assert first == second
    assert FakeTrader.instances[-1].order_calls == 1
    assert bridge.cancel_order("123").submitted is True

    with pytest.raises(QMTLinkError, match="already used"):
        bridge.place_order(order.model_copy(update={"quantity": 200}))

    bridge.close()
    assert FakeTrader.instances[-1].stopped is True
    assert bridge._xtdata.unsubscribed == [1]


def test_xtquant_bridge_does_not_guess_unknown_broker_values(monkeypatch) -> None:
    install_fake_xtquant(monkeypatch)
    monkeypatch.setattr("qmtlink.bridge.xtquant.default_idempotency_path", lambda: ":memory:")
    bridge = XtQuantBridge(
        ServerSettings(
            qmt_path="C:/miniQMT/userdata_mini",
            account_id="test-account",
        )
    )
    raw_order = FakeTrader._order(bridge._account, 456)
    raw_order.order_type = 999
    raw_order.price_type = 998
    raw_order.order_status = 997

    order = bridge._order(raw_order)

    assert order.side is None
    assert order.order_type is None
    assert order.status == "unknown"
    assert order.broker_order_type == 999
    assert order.broker_price_type == 998
    assert order.broker_order_status == 997
    bridge.close()


def test_xtquant_bridge_requires_real_mode_configuration() -> None:
    with pytest.raises(QMTLinkError, match="QMTLINK_QMT_PATH"):
        XtQuantBridge(ServerSettings())
