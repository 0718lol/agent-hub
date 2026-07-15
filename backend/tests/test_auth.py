"""Tests for signed browser sessions and production security policy."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.auth import SESSION_TTL_SECONDS, create_session_token, verify_session_token
from app.core.config import Settings


def test_signed_session_roundtrip_and_expiry():
    token = create_session_token("a" * 32, now=1_000)
    assert verify_session_token(token, "a" * 32, now=1_001)
    assert not verify_session_token(token, "wrong", now=1_001)
    assert not verify_session_token(token, "a" * 32, now=1_000 + SESSION_TTL_SECONDS + 1)


def test_production_requires_api_and_encryption_secrets(monkeypatch):
    monkeypatch.delenv("AGENTHUB_ENCRYPT_KEY", raising=False)
    production = Settings(debug=False, api_secret="")
    with pytest.raises(RuntimeError, match="Production security configuration missing"):
        production.validate_production_security()


def test_development_allows_missing_security_secrets(monkeypatch):
    monkeypatch.delenv("AGENTHUB_ENCRYPT_KEY", raising=False)
    Settings(debug=True, api_secret="").validate_production_security()


@pytest.mark.asyncio
async def test_login_sets_httponly_cookie_and_status(monkeypatch):
    from app.core.config import settings
    from app.routers.auth import router

    monkeypatch.setattr(settings, "api_secret", "s" * 32)
    monkeypatch.setattr(settings, "debug", True)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/api/auth/login", json={"secret": "s" * 32})
        assert login.status_code == 200
        assert "httponly" in login.headers["set-cookie"].lower()
        status = await client.get("/api/auth/status")
        assert status.json() == {"auth_required": True, "authenticated": True}


@pytest.mark.asyncio
async def test_login_rejects_wrong_secret(monkeypatch):
    from app.core.config import settings
    from app.routers.auth import router

    monkeypatch.setattr(settings, "api_secret", "s" * 32)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/login", json={"secret": "wrong"})
    assert response.status_code == 401
