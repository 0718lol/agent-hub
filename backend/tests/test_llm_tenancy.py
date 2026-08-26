"""Tenant LLM disconnect regression tests."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.llm_client import llm_client
from app.core.tenant_config import get_tenant_config
from app.core.tenancy import reset_current_tenant, set_current_tenant
from app.routers.settings import router


@pytest.mark.asyncio
async def test_disconnect_removes_tenant_llm_credentials(monkeypatch):
    tenant_id = "tenant-llm-disconnect"
    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request: Request, call_next):
        token = set_current_tenant(tenant_id)
        try:
            return await call_next(request)
        finally:
            reset_current_tenant(token)

    app.include_router(router, prefix="/api")
    from app.core.config import settings
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "llm_model", "")
    llm_client.evict(tenant_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        saved = await client.post(
            "/api/settings/llm",
            json={
                "provider": "openai",
                "api_key": "tenant-secret",
                "base_url": "https://llm.example/v1",
                "model": "test-model",
            },
        )
        assert saved.json()["configured"] is True
        disconnected = await client.delete("/api/settings/llm")
        status = await client.get("/api/settings/llm")

    assert disconnected.status_code == 200
    assert disconnected.json()["configured"] is False
    assert status.json()["api_key_set"] is False
    assert get_tenant_config(tenant_id, "llm") is None
    llm_client.evict(tenant_id)


@pytest.mark.asyncio
async def test_deepseek_flash_settings_persist_non_thinking_mode():
    tenant_id = "tenant-deepseek-flash"
    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request: Request, call_next):
        token = set_current_tenant(tenant_id)
        try:
            return await call_next(request)
        finally:
            reset_current_tenant(token)

    app.include_router(router, prefix="/api")
    llm_client.evict(tenant_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        saved = await client.post(
            "/api/settings/llm",
            json={
                "provider": "openai",
                "api_key": "tenant-secret",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
            },
        )
        status = await client.get("/api/settings/llm")

    assert saved.status_code == 200
    assert status.json()["thinking_enabled"] is False
    llm_client.evict(tenant_id)
