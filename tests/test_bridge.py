import pytest
from pydantic import ValidationError

from qmtlink.bridge.mock import MockBridge
from qmtlink.models import (
    DividendRequest,
    FinancialRequest,
    HistoryRequest,
    InstrumentRequest,
    OrderRequest,
    OrderSide,
    SectorRequest,
)


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


def test_mock_research_data_is_available_through_bridge_protocol() -> None:
    bridge = MockBridge()
    instrument = bridge.get_instruments(InstrumentRequest(symbols=["000001.SZ"]))
    financial = bridge.get_financial(
        FinancialRequest(symbols=["000001.SZ"], tables=["PershareIndex"])
    )
    dividends = bridge.get_dividends(DividendRequest(symbols=["000001.SZ"]))
    historical_st = bridge.get_historical_st(InstrumentRequest(symbols=["000001.SZ"]))
    sectors = bridge.get_sector_symbols(SectorRequest(sector="沪深A股"))

    assert instrument.instruments["000001.SZ"]["OpenDate"] == 20200101
    assert financial.financial["000001.SZ"]["PershareIndex"][0][
        "adjusted_net_profit_rate"
    ] == 12.0
    assert dividends.factors["000001.SZ"][0]["cash_dividend"] == 0.1
    assert historical_st.statuses["000001.SZ"] == {}
    assert "688001.SH" in sectors.symbols


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
