"""Tests for local accounts, signed sessions, and production security policy."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.auth import SESSION_TTL_SECONDS, create_session_token, verify_session_token
from app.core.config import Settings


def test_signed_session_roundtrip_and_expiry():
    token = create_session_token("a" * 32, now=1_000, user_id="usr_test")
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


def test_worker_rejects_implicit_host_docker_socket(monkeypatch):
    worker = Settings(allow_host_docker_socket=False)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr("app.core.config.os.path.exists", lambda path: path == "/var/run/docker.sock")

    with pytest.raises(RuntimeError, match="Host Docker socket detected"):
        worker.validate_deployment_worker_security()


@pytest.mark.asyncio
async def test_login_sets_httponly_cookie_and_status(monkeypatch):
    from app.core.accounts import create_account
    from app.core.config import settings
    from app.routers.auth import router

    monkeypatch.setattr(settings, "debug", True)
    account = create_account("test-user", "password123")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/login",
            json={"username": "test-user", "password": "password123"},
        )
        assert login.status_code == 200
        assert "httponly" in login.headers["set-cookie"].lower()
        status = await client.get("/api/auth/status")
        assert status.json() == {
            "auth_required": True,
            "authenticated": True,
            "user": account.public_dict(),
        }


@pytest.mark.asyncio
async def test_login_rejects_wrong_secret(monkeypatch):
    from app.core.accounts import create_account
    from app.routers.auth import router

    create_account("test-user", "password123")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"username": "test-user", "password": "wrong-password"},
        )
    assert response.status_code == 401
