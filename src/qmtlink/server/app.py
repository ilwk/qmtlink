from __future__ import annotations

import hmac
import time
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from qmtlink import __version__
from qmtlink.bridge import Bridge, create_bridge
from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError
from qmtlink.models import OrderRequest, QuoteRequest


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
    backend = bridge or create_bridge(settings.mode)
    app = FastAPI(title="QmtLink", version=__version__)
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
        if not settings.allow_live_orders:
            raise HTTPException(
                status_code=403,
                detail={"code": "LIVE_ORDERS_DISABLED", "message": "live orders are disabled"},
            )
        return _success(backend.place_order(payload).model_dump(mode="json"), started)

    return app
