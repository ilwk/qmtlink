from __future__ import annotations

from typing import Protocol

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
    Position,
    Quote,
    QuoteSubscription,
    SectorData,
    SectorRequest,
    TradeRecord,
)


class Bridge(Protocol):
    mode: str

    def health(self) -> dict[str, object]: ...

    def capabilities(self) -> dict[str, object]: ...

    def get_quotes(self, symbols: list[str]) -> list[Quote]: ...

    def get_history(self, request: HistoryRequest) -> HistoricalData: ...

    def get_instruments(self, request: InstrumentRequest) -> InstrumentData: ...

    def get_financial(self, request: FinancialRequest) -> FinancialData: ...

    def get_dividends(self, request: DividendRequest) -> DividendData: ...

    def get_historical_st(self, request: InstrumentRequest) -> HistoricalSTData: ...

    def get_sector_symbols(self, request: SectorRequest) -> SectorData: ...

    def subscribe_quotes(self, symbols: list[str]) -> QuoteSubscription: ...

    def poll_events(
        self, *, after_sequence: int, timeout: float = 0.0, limit: int = 200
    ) -> EventBatch: ...

    def get_asset(self) -> AccountAsset: ...

    def get_positions(self) -> list[Position]: ...

    def get_orders(self, *, cancelable_only: bool = False) -> list[OrderRecord]: ...

    def get_order(self, order_id: str) -> OrderRecord | None: ...

    def get_trades(self) -> list[TradeRecord]: ...

    def preview_order(self, order: OrderRequest) -> OrderPreview: ...

    def place_order(self, order: OrderRequest) -> OrderResult: ...

    def cancel_order(self, order_id: str) -> CancelResult: ...

    def close(self) -> None: ...
