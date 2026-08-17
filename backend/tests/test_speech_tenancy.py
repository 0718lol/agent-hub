"""Tenant isolation tests for speech-to-text configuration."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.tenancy import reset_current_tenant, set_current_tenant
from app.routers.speech import router


@pytest.fixture
def speech_app():
    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request: Request, call_next):
        token = set_current_tenant(request.headers.get("x-test-tenant"))
        try:
            return await call_next(request)
        finally:
            reset_current_tenant(token)

    app.include_router(router, prefix="/api")
    return app


@pytest.mark.asyncio
async def test_speech_settings_are_isolated_between_tenants(speech_app):
    transport = ASGITransport(app=speech_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/settings/stt",
            headers={"x-test-tenant": "tenant-speech-a"},
            json={"api_key": "tenant-a-stt", "base_url": "https://a.example", "model": "model-a", "language": "en"},
        )
        assert first.status_code == 200

        second_status = await client.get(
            "/api/settings/stt",
            headers={"x-test-tenant": "tenant-speech-b"},
        )
        assert second_status.status_code == 200
        assert second_status.json() == {
            "configured": False,
            "base_url": "",
            "model": "whisper-1",
            "language": "zh",
        }

        first_status = await client.get(
            "/api/settings/stt",
            headers={"x-test-tenant": "tenant-speech-a"},
        )
        assert first_status.status_code == 200
        assert first_status.json() == {
            "configured": True,
            "base_url": "https://a.example",
            "model": "model-a",
            "language": "en",
        }
