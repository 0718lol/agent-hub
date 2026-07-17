"""Browser session authentication endpoints."""

import hmac
import secrets

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
    verify_session_token,
)
from app.core.config import settings

router = APIRouter(tags=["auth"])


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


@router.get("/auth/status")
async def auth_status(request: Request, response: Response):
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
    if not settings.api_secret:
        session_secret = get_session_secret(settings.api_secret)
        identity = _persistent_identity(request, response, session_secret)
        _set_session(response, session_secret, identity)
        return {"status": "ok", "auth_required": False}
    if not hmac.compare_digest(payload.secret, settings.api_secret):
        raise HTTPException(status_code=401, detail="Invalid API secret")
    session_secret = get_session_secret(settings.api_secret)
    identity = _persistent_identity(request, response, session_secret)
    _set_session(response, session_secret, identity)
    return {"status": "ok", "auth_required": True}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return {"status": "ok"}
