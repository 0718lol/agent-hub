"""Tests for local accounts, signed sessions, and production security policy."""

import pytest
from fastapi import HTTPException, Request
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.auth import SESSION_TTL_SECONDS, create_session_token, verify_session_token
from app.core.config import Settings


@pytest.fixture(autouse=True)
def clear_auth_rate_limits():
    from app.routers import auth

    auth._auth_attempts.clear()
    yield
    auth._auth_attempts.clear()


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


def _request_from(address: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": (address, 1)})


@pytest.mark.asyncio
async def test_login_rate_limit_cannot_be_bypassed_by_rotating_usernames(monkeypatch):
    from app.routers import auth

    monkeypatch.setattr(auth, "_MAX_LOGIN_ATTEMPTS_PER_IP", 3)
    request = _request_from("203.0.113.10")
    for username in ("one", "two", "three"):
        await auth._record_auth_attempt(request, username)

    with pytest.raises(HTTPException) as exc:
        await auth._record_auth_attempt(request, "four")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_auth_rate_limit_expires_and_cleans_all_buckets(monkeypatch):
    from app.routers import auth

    now = 100.0
    monkeypatch.setattr(auth.time, "monotonic", lambda: now)
    monkeypatch.setattr(auth, "_MAX_LOGIN_ATTEMPTS", 1)
    request = _request_from("203.0.113.11")
    identity_key = await auth._record_auth_attempt(request, "someone")
    with pytest.raises(HTTPException):
        await auth._record_auth_attempt(request, "someone")

    now += auth._LOGIN_WINDOW_SECONDS + 1
    await auth._record_auth_attempt(request, "someone")
    assert identity_key in auth._auth_attempts
    assert all(bucket.stamps == [now] for bucket in auth._auth_attempts.values())


@pytest.mark.asyncio
async def test_registration_is_rate_limited_per_ip(monkeypatch):
    from app.routers import auth

    monkeypatch.setattr(auth, "_MAX_REGISTRATIONS_PER_IP", 2)
    request = _request_from("203.0.113.12")
    await auth._record_auth_attempt(request)
    await auth._record_auth_attempt(request)
    with pytest.raises(HTTPException) as exc:
        await auth._record_auth_attempt(request)
    assert exc.value.status_code == 429


def test_environment_admin_bootstrap_is_idempotent(monkeypatch):
    from app.core.accounts import bootstrap_admin_from_env, get_account_by_username

    monkeypatch.setenv("AGENTHUB_BOOTSTRAP_ADMIN_USERNAME", "first-admin")
    monkeypatch.setenv("AGENTHUB_BOOTSTRAP_ADMIN_PASSWORD", "strong-password")
    assert bootstrap_admin_from_env() is True
    assert bootstrap_admin_from_env() is False
    assert get_account_by_username("first-admin").is_admin is True


def test_environment_admin_bootstrap_requires_both_values(monkeypatch):
    from app.core.accounts import bootstrap_admin_from_env

    monkeypatch.setenv("AGENTHUB_BOOTSTRAP_ADMIN_USERNAME", "first-admin")
    monkeypatch.delenv("AGENTHUB_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="must be set together"):
        bootstrap_admin_from_env()
