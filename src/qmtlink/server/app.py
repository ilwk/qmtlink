from __future__ import annotations

import asyncio
import hmac
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from qmtlink import __version__
from qmtlink.bridge import Bridge, create_bridge
from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError
from qmtlink.models import CancelRequest, HistoryRequest, OrderRequest, QuoteRequest


def _success(data: object, started: float) -> dict[str, object]:
    return {
        "ok": True,
        "request_id": f"req_{uuid4().hex}",
        "data": data,
        "meta": {"elapsed_ms": round((time.perf_counter() - started) * 1000, 3)},
    }


def create_app(
    bridge: Bridge | None = None,
    settings: ServerSettings | None = None,
) -> FastAPI:
    settings = settings or ServerSettings.from_env()
    backend = bridge or create_bridge(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            backend.close()

    app = FastAPI(title="QmtLink", version=__version__, lifespan=lifespan)
    app.state.bridge = backend
    app.state.settings = settings

    @app.exception_handler(QMTLinkError)
    async def handle_qmtlink_error(_request: Request, exc: QMTLinkError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code or 500,
            content={"ok": False, "error": exc.as_dict()},
        )

    def require_api_key(api_key: str | None) -> None:
        expected = settings.api_key
        if not expected:
            raise HTTPException(
                status_code=503,
                detail={"code": "API_KEY_NOT_CONFIGURED", "message": "API key is required"},
            )
        if api_key is None or not hmac.compare_digest(api_key, expected):
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_API_KEY", "message": "invalid or missing API key"},
            )

    def require_trading_allowed() -> None:
        if settings.mode.strip().lower() == "real" and not settings.allow_trading:
            raise HTTPException(
                status_code=403,
                detail={"code": "TRADING_DISABLED", "message": "trading is disabled"},
            )

    @app.exception_handler(HTTPException)
    async def handle_http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "error": {
                    "code": detail.get("code", "HTTP_ERROR"),
                    "message": detail.get("message", str(exc.detail)),
                    "retryable": False,
                },
            },
        )

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        started = time.perf_counter()
        data = {"version": __version__, **backend.health()}
        return _success(data, started)

    @app.get("/api/v1/capabilities")
    async def capabilities() -> dict[str, object]:
        started = time.perf_counter()
        return _success(backend.capabilities(), started)

    @app.post("/api/v1/market/quotes")
    async def quotes(payload: QuoteRequest) -> dict[str, object]:
        started = time.perf_counter()
        data = [quote.model_dump(mode="json") for quote in backend.get_quotes(payload.symbols)]
        return _success(data, started)

    @app.post("/api/v1/market/history")
    async def market_history(
        payload: HistoryRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        return _success(backend.get_history(payload).model_dump(mode="json"), started)


    @app.post("/api/v1/market/subscriptions")
    async def subscribe_quotes(
        payload: QuoteRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        subscription = backend.subscribe_quotes(payload.symbols)
        return _success(subscription.model_dump(mode="json"), started)

    @app.get("/api/v1/events")
    async def events(
        after_sequence: int = Query(default=0, ge=0),
        timeout: float = Query(default=20.0, ge=0.0, le=30.0),
        limit: int = Query(default=200, ge=1, le=1_000),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        deadline = time.monotonic() + timeout
        while True:
            batch = backend.poll_events(
                after_sequence=after_sequence,
                timeout=0,
                limit=limit,
            )
            if batch.events or time.monotonic() >= deadline:
                break
            await asyncio.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        return _success(batch.model_dump(mode="json"), started)

    @app.get("/api/v1/account/asset")
    async def account_asset(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        return _success(backend.get_asset().model_dump(mode="json"), started)

    @app.get("/api/v1/account/positions")
    async def account_positions(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        data = [item.model_dump(mode="json") for item in backend.get_positions()]
        return _success(data, started)

    @app.get("/api/v1/account/orders")
    async def account_orders(
        cancelable_only: bool = False,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        data = [
            item.model_dump(mode="json")
            for item in backend.get_orders(cancelable_only=cancelable_only)
        ]
        return _success(data, started)

    @app.get("/api/v1/account/trades")
    async def account_trades(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        data = [item.model_dump(mode="json") for item in backend.get_trades()]
        return _success(data, started)

    @app.post("/api/v1/orders/preview")
    async def preview_order(
        payload: OrderRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        return _success(backend.preview_order(payload).model_dump(mode="json"), started)

    @app.post("/api/v1/orders")
    async def place_order(
        payload: OrderRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        if not payload.live:
            raise HTTPException(
                status_code=400,
                detail={"code": "LIVE_FLAG_REQUIRED", "message": "set live=true to submit"},
            )
        require_trading_allowed()
        return _success(backend.place_order(payload).model_dump(mode="json"), started)

    @app.get("/api/v1/orders/{order_id}")
    async def get_order(
        order_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        order = backend.get_order(order_id)
        if order is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "ORDER_NOT_FOUND", "message": f"order {order_id} was not found"},
            )
        return _success(order.model_dump(mode="json"), started)

    @app.post("/api/v1/orders/{order_id}/cancel")
    async def cancel_order(
        order_id: str,
        payload: CancelRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        started = time.perf_counter()
        require_api_key(x_api_key)
        if not payload.live:
            raise HTTPException(
                status_code=400,
                detail={"code": "LIVE_FLAG_REQUIRED", "message": "set live=true to cancel"},
            )
        require_trading_allowed()
        return _success(backend.cancel_order(order_id).model_dump(mode="json"), started)

    return app
