"""Health endpoint regression tests."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_when_redis_probe_hangs(monkeypatch):
    async def _slow_probe():
        await asyncio.sleep(5)
        return False

    monkeypatch.setattr("app.core.redis.redis_manager.check_connection", _slow_probe)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["redis"] == "timeout"
