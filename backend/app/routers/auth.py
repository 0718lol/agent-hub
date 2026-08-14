"""Username/password registration, login, account status, and logout."""

import asyncio
import hashlib
import time

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
_login_attempts: dict[str, list[float]] = {}
_login_lock = asyncio.Lock()
_MAX_LOGIN_ATTEMPTS = 10


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


async def _check_login_rate(request: Request, username: str) -> str:
    address = request.client.host if request.client else "unknown"
    key = hashlib.sha256(f"{address}:{username.casefold()}".encode()).hexdigest()[:32]
    cutoff = time.monotonic() - 60
    async with _login_lock:
        attempts = [stamp for stamp in _login_attempts.get(key, []) if stamp > cutoff]
        if len(attempts) >= _MAX_LOGIN_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail="登录尝试过于频繁，请一分钟后重试",
                headers={"Retry-After": "60"},
            )
        attempts.append(time.monotonic())
        _login_attempts[key] = attempts
    return key


@router.get("/auth/status")
async def auth_status(request: Request):
    account = get_session_account(request.cookies.get(SESSION_COOKIE))
    return {
        "auth_required": True,
        "authenticated": account is not None,
        "user": account.public_dict() if account else None,
    }


@router.post("/auth/register", status_code=201)
async def register(payload: CredentialsRequest, response: Response):
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
    attempt_key = await _check_login_rate(request, payload.username)
    try:
        account = await asyncio.to_thread(authenticate, payload.username, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _login_attempts.pop(attempt_key, None)
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
