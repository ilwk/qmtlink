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
