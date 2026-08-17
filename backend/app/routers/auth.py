"""Username/password registration, login, account status, and logout."""

import asyncio
import hashlib
import math
import time
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.accounts import (
    AccountError,
    InvalidCredentialsError,
    UsernameTakenError,
    authenticate,
    create_account,
    update_password,
)
from app.core.auth import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    create_session_token,
    get_session_account,
    get_session_secret,
)
from app.core.config import settings

router = APIRouter(tags=["auth"])
_auth_attempts: dict[str, "_AttemptBucket"] = {}
_auth_rate_lock = asyncio.Lock()
_MAX_LOGIN_ATTEMPTS = 10
_MAX_LOGIN_ATTEMPTS_PER_IP = 30
_MAX_REGISTRATIONS_PER_IP = 5
_LOGIN_WINDOW_SECONDS = 60
_REGISTRATION_WINDOW_SECONDS = 10 * 60
_MAX_RATE_LIMIT_BUCKETS = 10_000


@dataclass
class _AttemptBucket:
    window: int
    stamps: list[float]


class CredentialsRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


def _set_session(response: Response, user_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(get_session_secret(settings.api_secret), user_id=user_id),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=not settings.debug,
        samesite="strict",
        path="/",
    )


def _rate_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()[:32]
    return f"{prefix}:{digest}"


async def _record_auth_attempt(request: Request, username: str | None = None) -> str | None:
    address = request.client.host if request.client else "unknown"
    now = time.monotonic()
    if username is None:
        identity_key = None
        rules = [
            (_rate_key("register-ip", address), _REGISTRATION_WINDOW_SECONDS, _MAX_REGISTRATIONS_PER_IP),
        ]
    else:
        identity_key = _rate_key("login-account", f"{address}:{username.casefold()}")
        rules = [
            (_rate_key("login-ip", address), _LOGIN_WINDOW_SECONDS, _MAX_LOGIN_ATTEMPTS_PER_IP),
            (identity_key, _LOGIN_WINDOW_SECONDS, _MAX_LOGIN_ATTEMPTS),
        ]

    async with _auth_rate_lock:
        for key, bucket in list(_auth_attempts.items()):
            bucket.stamps = [stamp for stamp in bucket.stamps if stamp > now - bucket.window]
            if not bucket.stamps:
                del _auth_attempts[key]

        for key, window, limit in rules:
            bucket = _auth_attempts.get(key)
            stamps = bucket.stamps if bucket else []
            if len(stamps) >= limit:
                retry_after = max(1, math.ceil(stamps[0] + window - now))
                raise HTTPException(
                    status_code=429,
                    detail="请求过于频繁，请稍后重试",
                    headers={"Retry-After": str(retry_after)},
                )

        new_keys = sum(1 for key, _, _ in rules if key not in _auth_attempts)
        if len(_auth_attempts) + new_keys > _MAX_RATE_LIMIT_BUCKETS:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后重试",
                headers={"Retry-After": "60"},
            )
        for key, window, _ in rules:
            bucket = _auth_attempts.setdefault(key, _AttemptBucket(window=window, stamps=[]))
            bucket.stamps.append(now)
    return identity_key


async def _clear_login_identity(identity_key: str) -> None:
    async with _auth_rate_lock:
        _auth_attempts.pop(identity_key, None)


@router.get("/auth/status")
async def auth_status(request: Request):
    account = get_session_account(request.cookies.get(SESSION_COOKIE))
    return {
        "auth_required": True,
        "authenticated": account is not None,
        "user": account.public_dict() if account else None,
    }


@router.post("/auth/register", status_code=201)
async def register(payload: CredentialsRequest, request: Request, response: Response):
    await _record_auth_attempt(request)
    try:
        account = await asyncio.to_thread(create_account, payload.username, payload.password)
    except UsernameTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AccountError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _set_session(response, account.user_id)
    return {"status": "ok", "user": account.public_dict()}


@router.post("/auth/login")
async def login(payload: CredentialsRequest, request: Request, response: Response):
    identity_key = await _record_auth_attempt(request, payload.username)
    try:
        account = await asyncio.to_thread(authenticate, payload.username, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    await _clear_login_identity(identity_key)
    _set_session(response, account.user_id)
    return {"status": "ok", "user": account.public_dict()}


@router.post("/auth/change-password")
async def change_password(payload: PasswordChangeRequest, request: Request):
    account = get_session_account(request.cookies.get(SESSION_COOKIE))
    if account is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        await asyncio.to_thread(
            update_password,
            account.user_id,
            payload.current_password,
            payload.new_password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AccountError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return {"status": "ok"}
