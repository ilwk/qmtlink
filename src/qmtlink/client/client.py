from __future__ import annotations

from typing import Any

import httpx

from qmtlink.config import ClientSettings
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
    Position,
    Quote,
    QuoteSubscription,
    SectorData,
    SectorRequest,
    TradeRecord,
)


class QMTClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = ClientSettings.from_env()
        self._api_key = api_key if api_key is not None else settings.api_key
        self._client = httpx.Client(
            base_url=(base_url or settings.base_url).rstrip("/"),
            timeout=timeout if timeout is not None else settings.timeout,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            raise QMTLinkError("REQUEST_TIMEOUT", str(exc), retryable=True) from exc
        except httpx.HTTPError as exc:
            raise QMTLinkError("NETWORK_ERROR", str(exc), retryable=True) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise QMTLinkError(
                "INVALID_RESPONSE", f"server returned HTTP {response.status_code} without JSON"
            ) from exc

        if response.is_error or not payload.get("ok", False):
            error = payload.get("error") or {}
            raise QMTLinkError(
                error.get("code", "HTTP_ERROR"),
                error.get("message", f"HTTP {response.status_code}"),
                retryable=bool(error.get("retryable", False)),
                status_code=response.status_code,
            )
        return payload

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/health")["data"]

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/capabilities")["data"]

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        data = self._request("POST", "/api/v1/market/quotes", json={"symbols": symbols})["data"]
        return [Quote.model_validate(item) for item in data]

    def get_history(self, request: HistoryRequest) -> HistoricalData:
        data = self._request(
            "POST", "/api/v1/market/history", json=request.model_dump(mode="json")
        )["data"]
        return HistoricalData.model_validate(data)

    def get_instruments(self, request: InstrumentRequest) -> InstrumentData:
        data = self._request(
            "POST", "/api/v1/market/instruments", json=request.model_dump(mode="json")
        )["data"]
        return InstrumentData.model_validate(data)

    def get_financial(self, request: FinancialRequest) -> FinancialData:
        data = self._request(
            "POST", "/api/v1/market/financial", json=request.model_dump(mode="json")
        )["data"]
        return FinancialData.model_validate(data)

    def get_dividends(self, request: DividendRequest) -> DividendData:
        data = self._request(
            "POST", "/api/v1/market/dividends", json=request.model_dump(mode="json")
        )["data"]
        return DividendData.model_validate(data)

    def get_historical_st(self, request: InstrumentRequest) -> HistoricalSTData:
        data = self._request(
            "POST", "/api/v1/market/historical-st", json=request.model_dump(mode="json")
        )["data"]
        return HistoricalSTData.model_validate(data)

    def get_sector_symbols(self, request: SectorRequest) -> SectorData:
        data = self._request(
            "POST", "/api/v1/market/sectors", json=request.model_dump(mode="json")
        )["data"]
        return SectorData.model_validate(data)

    def subscribe_quotes(self, symbols: list[str]) -> QuoteSubscription:
        data = self._request("POST", "/api/v1/market/subscriptions", json={"symbols": symbols})[
            "data"
        ]
        return QuoteSubscription.model_validate(data)

    def poll_events(
        self,
        *,
        after_sequence: int,
        timeout: float = 20.0,
        limit: int = 200,
    ) -> EventBatch:
        data = self._request(
            "GET",
            "/api/v1/events",
            params={
                "after_sequence": after_sequence,
                "timeout": timeout,
                "limit": limit,
            },
        )["data"]
        return EventBatch.model_validate(data)

    def get_asset(self) -> AccountAsset:
        data = self._request("GET", "/api/v1/account/asset")["data"]
        return AccountAsset.model_validate(data)

    def get_positions(self) -> list[Position]:
        data = self._request("GET", "/api/v1/account/positions")["data"]
        return [Position.model_validate(item) for item in data]

    def get_orders(self, *, cancelable_only: bool = False) -> list[OrderRecord]:
        data = self._request(
            "GET",
            "/api/v1/account/orders",
            params={"cancelable_only": cancelable_only},
        )["data"]
        return [OrderRecord.model_validate(item) for item in data]

    def get_order(self, order_id: str) -> OrderRecord:
        data = self._request("GET", f"/api/v1/orders/{order_id}")["data"]
        return OrderRecord.model_validate(data)

    def get_trades(self) -> list[TradeRecord]:
        data = self._request("GET", "/api/v1/account/trades")["data"]
        return [TradeRecord.model_validate(item) for item in data]

    def preview_order(self, order: OrderRequest) -> OrderPreview:
        data = self._request(
            "POST",
            "/api/v1/orders/preview",
            json=order.model_dump(mode="json"),
        )["data"]
        return OrderPreview.model_validate(data)

    def place_order(self, order: OrderRequest) -> OrderResult:
        data = self._request("POST", "/api/v1/orders", json=order.model_dump(mode="json"))["data"]
        return OrderResult.model_validate(data)

    def cancel_order(self, order_id: str, *, live: bool = False) -> CancelResult:
        data = self._request(
            "POST",
            f"/api/v1/orders/{order_id}/cancel",
            json={"live": live},
        )["data"]
        return CancelResult.model_validate(data)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> QMTClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
