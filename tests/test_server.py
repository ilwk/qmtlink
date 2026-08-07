import httpx
import pytest

from qmtlink.bridge.mock import MockBridge
from qmtlink.config import ServerSettings
from qmtlink.server.app import create_app


def make_client(*, allow_live_orders: bool = False) -> httpx.AsyncClient:
    settings = ServerSettings(
        mode="mock",
        api_key="test-secret",
        allow_live_orders=allow_live_orders,
    )
    transport = httpx.ASGITransport(app=create_app(MockBridge(), settings))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_health() -> None:
    async with make_client() as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"]["mock"] is True


@pytest.mark.asyncio
async def test_quotes() -> None:
    async with make_client() as client:
        response = await client.post("/api/v1/market/quotes", json={"symbols": ["000001.SZ"]})
    assert response.status_code == 200
    assert response.json()["data"][0]["symbol"] == "000001.SZ"


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
    async with make_client(allow_live_orders=True) as client:
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
    async with make_client(allow_live_orders=True) as client:
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
