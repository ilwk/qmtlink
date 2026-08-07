from qmtlink.bridge.mock import MockBridge
from qmtlink.models import OrderRequest, OrderSide


def test_mock_quote_is_deterministic() -> None:
    bridge = MockBridge()
    first = bridge.get_quotes(["000001.SZ"])[0]
    second = bridge.get_quotes(["000001.SZ"])[0]
    assert first.symbol == "000001.SZ"
    assert first.last_price == second.last_price


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
