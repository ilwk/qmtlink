import asyncio
import threading
import time

import httpx
import pytest

from qmtlink.bridge.mock import MockBridge
from qmtlink.config import ServerSettings
from qmtlink.server.app import create_app


def make_client(
    *, allow_trading: bool = False, bridge: MockBridge | None = None
) -> httpx.AsyncClient:
    settings = ServerSettings(
        api_key="test-secret",
        allow_trading=allow_trading,
    )
    transport = httpx.ASGITransport(app=create_app(bridge or MockBridge(), settings))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_health() -> None:
    async with make_client() as client:
        unauthorized = await client.get("/api/v1/health")
        invalid = await client.get("/api/v1/health", headers={"X-API-Key": "wrong"})
        response = await client.get("/api/v1/health", headers={"X-API-Key": "test-secret"})
    assert unauthorized.status_code == 401
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "INVALID_API_KEY"
    assert response.status_code == 200
    assert response.json()["data"]["mock"] is True


@pytest.mark.asyncio
async def test_openapi_exposes_one_global_api_key_authorization_scheme() -> None:
    async with make_client() as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["components"]["securitySchemes"] == {
        "QmtLinkApiKey": {
            "type": "apiKey",
            "description": "API key from the QmtLink configuration file.",
            "in": "header",
            "name": "X-API-Key",
        }
    }
    health = document["paths"]["/api/v1/health"]["get"]
    assert health["security"] == [{"QmtLinkApiKey": []}]
    assert all(parameter["name"] != "x-api-key" for parameter in health.get("parameters", []))


@pytest.mark.asyncio
async def test_quotes() -> None:
    async with make_client() as client:
        response = await client.post(
            "/api/v1/market/quotes",
            headers={"X-API-Key": "test-secret"},
            json={"symbols": ["000001.SZ"]},
        )
    assert response.status_code == 200
    assert response.json()["data"][0]["symbol"] == "000001.SZ"


@pytest.mark.asyncio
async def test_history_requires_api_key_and_returns_raw_backtest_fields() -> None:
    async with make_client() as client:
        unauthorized = await client.post(
            "/api/v1/market/history", json={"symbols": ["000001.SZ"], "count": 1}
        )
        response = await client.post(
            "/api/v1/market/history",
            headers={"X-API-Key": "test-secret"},
            json={"symbols": ["000001.SZ"], "count": 1},
        )
    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["data"]["bar_count"] == {"000001.SZ": 1}
    assert "amount" in response.json()["data"]["bars"]["000001.SZ"][0]


@pytest.mark.asyncio
async def test_slow_history_does_not_block_health_check() -> None:
    release_history = threading.Event()

    class SlowHistoryBridge(MockBridge):
        def get_history(self, request):
            release_history.wait(timeout=2)
            return super().get_history(request)

    timer = threading.Timer(1.0, release_history.set)
    timer.start()
    try:
        async with make_client(bridge=SlowHistoryBridge()) as client:
            started = time.perf_counter()
            history_task = asyncio.create_task(
                client.post(
                    "/api/v1/market/history",
                    headers={"X-API-Key": "test-secret"},
                    json={"symbols": ["000001.SZ"], "count": 1},
                )
            )
            health_task = asyncio.create_task(
                client.get("/api/v1/health", headers={"X-API-Key": "test-secret"})
            )

            health = await health_task
            health_elapsed = time.perf_counter() - started
            release_history.set()
            history = await history_task
    finally:
        timer.cancel()

    assert health.status_code == 200
    assert health_elapsed < 0.5
    assert history.status_code == 200


@pytest.mark.asyncio
async def test_research_data_endpoints_require_api_key_and_return_mock_data() -> None:
    headers = {"X-API-Key": "test-secret"}
    async with make_client() as client:
        unauthorized = await client.post(
            "/api/v1/market/financial",
            json={"symbols": ["000001.SZ"], "tables": ["PershareIndex"]},
        )
        instruments = await client.post(
            "/api/v1/market/instruments",
            headers=headers,
            json={"symbols": ["000001.SZ"]},
        )
        financial = await client.post(
            "/api/v1/market/financial",
            headers=headers,
            json={"symbols": ["000001.SZ"], "tables": ["PershareIndex"]},
        )
        dividends = await client.post(
            "/api/v1/market/dividends",
            headers=headers,
            json={"symbols": ["000001.SZ"]},
        )
        historical_st = await client.post(
            "/api/v1/market/historical-st",
            headers=headers,
            json={"symbols": ["000001.SZ"]},
        )
        sectors = await client.post(
            "/api/v1/market/sectors",
            headers=headers,
            json={"sector": "沪深A股"},
        )
    assert unauthorized.status_code == 401
    assert instruments.status_code == 200
    assert instruments.json()["data"]["instruments"]["000001.SZ"]["OpenDate"] == 20200101
    assert financial.status_code == 200
    assert (
        financial.json()["data"]["financial"]["000001.SZ"]["PershareIndex"][0][
            "du_return_on_equity"
        ]
        == 8.0
    )
    assert dividends.status_code == 200
    assert dividends.json()["data"]["factors"]["000001.SZ"][0]["cash_dividend"] == 0.1
    assert historical_st.status_code == 200
    assert historical_st.json()["data"]["statuses"]["000001.SZ"] == {}
    assert sectors.status_code == 200
    assert "688001.SH" in sectors.json()["data"]["symbols"]


@pytest.mark.asyncio
async def test_subscribe_and_poll_quote_events() -> None:
    headers = {"X-API-Key": "test-secret"}
    async with make_client() as client:
        subscribed = await client.post(
            "/api/v1/market/subscriptions",
            headers=headers,
            json={"symbols": ["000001.SZ"]},
        )
        cursor = subscribed.json()["data"]["cursor"]
        events = await client.get(
            "/api/v1/events",
            headers=headers,
            params={"after_sequence": cursor, "timeout": 0},
        )
    assert events.status_code == 200
    assert events.json()["data"]["events"][0]["event_type"] == "quote"
    assert events.json()["data"]["events"][0]["payload"]["symbol"] == "000001.SZ"


@pytest.mark.asyncio
async def test_events_require_api_key() -> None:
    async with make_client() as client:
        response = await client.get("/api/v1/events", params={"timeout": 0})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_order_preview_requires_api_key() -> None:
    async with make_client() as client:
        response = await client.post(
            "/api/v1/orders/preview",
            json={
                "symbol": "000001.SZ",
                "side": "buy",
                "quantity": 100,
                "price": 10.5,
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mock_order_submission() -> None:
    async with make_client(allow_trading=True) as client:
        response = await client.post(
            "/api/v1/orders",
            headers={"X-API-Key": "test-secret"},
            json={
                "symbol": "000001.SZ",
                "side": "buy",
                "quantity": 100,
                "price": 10.5,
                "live": True,
                "client_order_id": "test-order-001",
            },
        )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "accepted"


@pytest.mark.asyncio
async def test_account_queries_require_key_and_return_models() -> None:
    async with make_client() as client:
        unauthorized = await client.get("/api/v1/account/asset")
        asset = await client.get("/api/v1/account/asset", headers={"X-API-Key": "test-secret"})
        positions = await client.get(
            "/api/v1/account/positions", headers={"X-API-Key": "test-secret"}
        )
    assert unauthorized.status_code == 401
    assert asset.status_code == 200
    assert asset.json()["data"]["account_id"] == "mock-account"
    assert positions.json()["data"] == []


@pytest.mark.asyncio
async def test_order_get_and_cancel() -> None:
    headers = {"X-API-Key": "test-secret"}
    async with make_client(allow_trading=True) as client:
        placed = await client.post(
            "/api/v1/orders",
            headers=headers,
            json={
                "symbol": "000001.SZ",
                "side": "buy",
                "quantity": 100,
                "price": 10.5,
                "live": True,
                "client_order_id": "test-order-002",
            },
        )
        order_id = placed.json()["data"]["order_id"]
        fetched = await client.get(f"/api/v1/orders/{order_id}", headers=headers)
        canceled = await client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers=headers,
            json={"live": True},
        )
    assert fetched.json()["data"]["client_order_id"] == "test-order-002"
    assert canceled.json()["data"]["status"] == "cancel_requested"


@pytest.mark.asyncio
async def test_real_order_submission_requires_allow_trading() -> None:
    async with make_client() as client:
        response = await client.post(
            "/api/v1/orders",
            headers={"X-API-Key": "test-secret"},
            json={
                "symbol": "000001.SZ",
                "side": "buy",
                "quantity": 100,
                "price": 10.5,
                "live": True,
                "client_order_id": "test-order-disabled",
            },
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TRADING_DISABLED"


@pytest.mark.asyncio
async def test_real_order_submission_allows_explicit_trading() -> None:
    async with make_client(allow_trading=True) as client:
        response = await client.post(
            "/api/v1/orders",
            headers={"X-API-Key": "test-secret"},
            json={
                "symbol": "000001.SZ",
                "side": "buy",
                "quantity": 100,
                "price": 10.5,
                "live": True,
                "client_order_id": "test-order-enabled",
            },
        )
    assert response.status_code == 200
