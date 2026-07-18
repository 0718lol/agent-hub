"""Tests for signed browser sessions and production security policy."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.auth import (
    DEVICE_COOKIE,
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    bearer_client_identity,
    create_session_token,
    get_session_identity,
    trusted_proxy_identity,
    trusted_proxy_role,
    verify_session_token,
)
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


def test_production_s3_storage_requires_a_bucket(monkeypatch):
    monkeypatch.setenv("AGENTHUB_ENCRYPT_KEY", "production-key")
    production = Settings(
        debug=False,
        api_secret="s" * 32,
        storage_backend="s3",
        s3_bucket="",
    )

    with pytest.raises(RuntimeError, match="AGENTHUB_S3_BUCKET"):
        production.validate_production_security()


def test_trusted_proxy_identity_requires_the_proxy_secret(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_mode", "proxy")
    monkeypatch.setattr(settings, "trusted_proxy_secret", "p" * 32)
    headers = {
        "x-agenthub-proxy-secret": "p" * 32,
        "x-agenthub-auth-user": "Leader@example.com",
        "x-agenthub-auth-role": "admin",
    }

    identity = trusted_proxy_identity(headers)
    assert identity and identity.startswith("user-")
    assert trusted_proxy_role(headers) == "admin"
    assert trusted_proxy_identity({**headers, "x-agenthub-proxy-secret": "wrong"}) is None


def test_machine_clients_use_independent_tokens(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_client_tokens_json", '{"builder":"token-a"}')
    monkeypatch.setattr(settings, "api_secret", "legacy-secret")
    valid = {"authorization": "Bearer token-a", "x-agenthub-client-id": "builder"}
    invalid = {"authorization": "Bearer legacy-secret", "x-agenthub-client-id": "builder"}

    assert bearer_client_identity(valid).startswith("api-client-")
    assert bearer_client_identity(invalid) is None


def test_worker_rejects_implicit_host_docker_socket(monkeypatch):
    worker = Settings(allow_host_docker_socket=False)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr("app.core.config.os.path.exists", lambda path: path == "/var/run/docker.sock")

    with pytest.raises(RuntimeError, match="Host Docker socket detected"):
        worker.validate_deployment_worker_security()


def test_worker_rejects_host_build_network(monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr("app.core.config.os.path.exists", lambda _path: False)
    worker = Settings(deployment_build_network="host")

    with pytest.raises(RuntimeError, match="DEPLOYMENT_BUILD_NETWORK"):
        worker.validate_deployment_worker_security()


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


@pytest.mark.asyncio
async def test_relogin_preserves_the_browser_tenant_identity(monkeypatch):
    from app.core.config import settings
    from app.routers.auth import router

    secret = "s" * 32
    monkeypatch.setattr(settings, "api_secret", secret)
    monkeypatch.setattr(settings, "debug", True)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/login", json={"secret": secret})
        first_identity = get_session_identity(client.cookies.get(SESSION_COOKIE), secret)
        device_cookie = client.cookies.get(DEVICE_COOKIE)
        await client.post("/api/auth/logout")
        await client.post("/api/auth/login", json={"secret": secret})
        second_identity = get_session_identity(client.cookies.get(SESSION_COOKIE), secret)

    assert device_cookie
    assert first_identity == second_identity


@pytest.mark.asyncio
async def test_proxy_mode_disables_shared_secret_login(monkeypatch):
    from app.core.config import settings
    from app.routers.auth import router

    monkeypatch.setattr(settings, "auth_mode", "proxy")
    monkeypatch.setattr(settings, "trusted_proxy_secret", "p" * 32)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/login", json={"secret": "anything"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_proxy_viewer_cannot_mutate_api_resources(monkeypatch):
    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "auth_mode", "proxy")
    monkeypatch.setattr(settings, "trusted_proxy_secret", "p" * 32)
    headers = {
        "x-agenthub-proxy-secret": "p" * 32,
        "x-agenthub-auth-user": "viewer@example.com",
        "x-agenthub-auth-role": "viewer",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/conversations",
            headers=headers,
            json={"id": "viewer-write", "name": "denied"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Viewer role is read-only"
