import pytest

from qmtlink.bridge.idempotency import IdempotencyStore
from qmtlink.errors import QMTLinkError
from qmtlink.models import OrderRequest, OrderResult


def make_order(**updates) -> OrderRequest:
    values = {
        "symbol": "000001.SZ",
        "side": "buy",
        "quantity": 100,
        "price": 10.5,
        "client_order_id": "client-001",
        "live": True,
    }
    values.update(updates)
    return OrderRequest.model_validate(values)


def test_completed_order_survives_restart(tmp_path) -> None:
    database = tmp_path / "orders.sqlite3"
    first = IdempotencyStore(database)
    order = make_order()
    assert first.reserve(order) is None
    first.complete(
        OrderResult(
            client_order_id=order.client_order_id,
            order_id="123",
            status="submitted",
            submitted=True,
        )
    )
    first.close()

    second = IdempotencyStore(database)
    existing = second.reserve(order)
    assert existing is not None
    assert existing.order_id == "123"
    with pytest.raises(QMTLinkError, match="different order"):
        second.reserve(make_order(quantity=200))
    second.close()


def test_uncertain_order_cannot_be_resubmitted() -> None:
    store = IdempotencyStore()
    order = make_order()
    assert store.reserve(order) is None
    store.mark_uncertain(order.client_order_id)
    with pytest.raises(QMTLinkError) as error:
        store.reserve(order)
    assert error.value.code == "ORDER_STATUS_UNCERTAIN"
    store.close()
