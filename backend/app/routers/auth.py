"""Browser session authentication endpoints."""

import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.auth import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    create_session_token,
    get_session_identity,
    get_session_secret,
    verify_session_token,
)
from app.core.config import settings

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    secret: str


@router.get("/auth/status")
async def auth_status(request: Request, response: Response):
    session_secret = get_session_secret(settings.api_secret)
    token = request.cookies.get(SESSION_COOKIE)
    identity = get_session_identity(token, session_secret)
    authenticated = not settings.api_secret or bool(identity)
    if not identity and not settings.api_secret:
        response.set_cookie(
            SESSION_COOKIE,
            create_session_token(session_secret),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            secure=False,
            samesite="strict",
            path="/",
        )
    return {"auth_required": bool(settings.api_secret), "authenticated": authenticated}


@router.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    if not settings.api_secret:
        return {"status": "ok", "auth_required": False}
    if not hmac.compare_digest(payload.secret, settings.api_secret):
        raise HTTPException(status_code=401, detail="Invalid API secret")
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(get_session_secret(settings.api_secret)),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=not settings.debug,
        samesite="strict",
        path="/",
    )
    return {"status": "ok", "auth_required": True}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return {"status": "ok"}
