"""Browser session authentication endpoints."""

import asyncio
import hashlib
import hmac
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.auth import (
    DEVICE_COOKIE,
    DEVICE_TTL_SECONDS,
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    create_session_token,
    get_device_identity,
    get_session_identity,
    get_session_secret,
    trusted_proxy_identity,
    trusted_proxy_role,
    verify_session_token,
)
from app.core.config import settings

router = APIRouter(tags=["auth"])
_local_login_attempts: dict[str, list[float]] = {}
_login_lock = asyncio.Lock()


class LoginRequest(BaseModel):
    secret: str


def _persistent_identity(request: Request, response: Response, secret: str) -> str:
    identity = get_device_identity(request.cookies.get(DEVICE_COOKIE), secret)
    if identity:
        return identity
    identity = f"device-{secrets.token_urlsafe(16)}"
    response.set_cookie(
        DEVICE_COOKIE,
        create_session_token(secret, user_id=identity),
        max_age=DEVICE_TTL_SECONDS,
        httponly=True,
        secure=not settings.debug,
        samesite="strict",
        path="/",
    )
    return identity


def _set_session(response: Response, secret: str, identity: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(secret, user_id=identity),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=not settings.debug,
        samesite="strict",
        path="/",
    )


async def _record_login_attempt(request: Request) -> str:
    address = request.client.host if request.client else "unknown"
    digest = hashlib.sha256(address.encode("utf-8")).hexdigest()[:24]
    key = f"agenthub:auth:attempts:{digest}"
    try:
        from app.core.redis import redis_manager

        if await redis_manager.check_connection():
            client = redis_manager.get_client()
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, 60)
            if count > settings.login_attempts_per_minute:
                raise HTTPException(
                    status_code=429,
                    detail="Too many login attempts",
                    headers={"Retry-After": "60"},
                )
            return key
    except HTTPException:
        raise
    except Exception:
        pass

    cutoff = time.monotonic() - 60
    async with _login_lock:
        attempts = [stamp for stamp in _local_login_attempts.get(key, []) if stamp > cutoff]
        if len(attempts) >= settings.login_attempts_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts",
                headers={"Retry-After": "60"},
            )
        attempts.append(time.monotonic())
        _local_login_attempts[key] = attempts
    return key


async def _clear_login_attempts(key: str) -> None:
    _local_login_attempts.pop(key, None)
    try:
        from app.core.redis import redis_manager

        if await redis_manager.check_connection():
            await redis_manager.get_client().delete(key)
    except Exception:
        pass


@router.get("/auth/status")
async def auth_status(request: Request, response: Response):
    if settings.auth_mode == "proxy":
        identity = trusted_proxy_identity(request.headers)
        return {
            "auth_required": True,
            "authenticated": bool(identity),
            "auth_mode": "proxy",
            "role": trusted_proxy_role(request.headers) if identity else "",
        }
    session_secret = get_session_secret(settings.api_secret)
    token = request.cookies.get(SESSION_COOKIE)
    identity = get_session_identity(token, session_secret)
    authenticated = not settings.api_secret or bool(identity)
    if not identity and not settings.api_secret:
        identity = _persistent_identity(request, response, session_secret)
        _set_session(response, session_secret, identity)
    return {"auth_required": bool(settings.api_secret), "authenticated": authenticated}


@router.post("/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    if settings.auth_mode == "proxy":
        raise HTTPException(status_code=409, detail="Login is managed by the configured identity proxy")
    if not settings.api_secret:
        session_secret = get_session_secret(settings.api_secret)
        identity = _persistent_identity(request, response, session_secret)
        _set_session(response, session_secret, identity)
        return {"status": "ok", "auth_required": False}
    attempt_key = await _record_login_attempt(request)
    if not hmac.compare_digest(payload.secret, settings.api_secret):
        raise HTTPException(status_code=401, detail="Invalid API secret")
    await _clear_login_attempts(attempt_key)
    session_secret = get_session_secret(settings.api_secret)
    identity = _persistent_identity(request, response, session_secret)
    _set_session(response, session_secret, identity)
    return {"status": "ok", "auth_required": True}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return {"status": "ok"}
