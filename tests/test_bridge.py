import pytest
from pydantic import ValidationError

from qmtlink.bridge.mock import MockBridge
from qmtlink.models import HistoryRequest, OrderRequest, OrderSide


def test_mock_quote_is_deterministic() -> None:
    bridge = MockBridge()
    first = bridge.get_quotes(["000001.SZ"])[0]
    second = bridge.get_quotes(["000001.SZ"])[0]
    assert first.symbol == "000001.SZ"
    assert first.last_price == second.last_price


def test_mock_history_preserves_backtest_fields() -> None:
    result = MockBridge().get_history(HistoryRequest(symbols=["000001.SZ"], count=1))

    assert result.bar_count == {"000001.SZ": 1}
    assert result.bars["000001.SZ"][0]["amount"] == 1_260_000.0
    assert result.bars["000001.SZ"][0]["preClose"] is not None


def test_order_preview_calculates_amount() -> None:
    bridge = MockBridge()
    order = OrderRequest(
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        price=10.5,
    )
    preview = bridge.preview_order(order)
    assert preview.estimated_amount == 1050
    assert preview.submitted is False


def test_market_order_is_not_accepted_as_latest_price() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="000001.SZ",
            side=OrderSide.BUY,
            quantity=100,
            order_type="market",
        )
