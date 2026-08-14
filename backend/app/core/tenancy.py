"""Stable tenant identity resolution for browser accounts and API clients."""

import hashlib
import hmac
import re
from contextvars import ContextVar, Token

from fastapi import Request

from app.core.auth import SESSION_COOKIE, get_session_account
from app.core.config import settings

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_PREFIX = "tenant__"
_SEPARATOR = "__conv__"
_CLIENT_ID = re.compile(r"^[A-Za-z0-9_.@-]{3,128}$")
_active_tenant_id: ContextVar[str | None] = ContextVar("agenthub_tenant_id", default=None)


def current_tenant_id() -> str | None:
    return _active_tenant_id.get()


def set_current_tenant(tenant_id: str | None) -> Token:
    return _active_tenant_id.set(tenant_id)


def reset_current_tenant(token: Token) -> None:
    _active_tenant_id.reset(token)


def _api_client_user_id(headers) -> str:
    client_id = headers.get("x-agenthub-client-id", "")
    if not _CLIENT_ID.fullmatch(client_id):
        return "api-client"
    digest = hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:24]
    return f"api-client-{digest}"


def has_valid_api_client_id(headers) -> bool:
    return bool(_CLIENT_ID.fullmatch(headers.get("x-agenthub-client-id", "")))


def bearer_tenant_id(headers) -> str | None:
    authorization = headers.get("authorization", "")
    token = authorization.split(" ", 1)[1] if authorization.startswith("Bearer ") else ""
    token = token or headers.get("x-api-secret", "")
    if not token or not settings.api_secret:
        return None
    if not hmac.compare_digest(token, settings.api_secret):
        return None
    if not settings.debug and not has_valid_api_client_id(headers):
        return None
    return _api_client_user_id(headers)


def request_user_id(request: Request) -> str:
    state_tenant = getattr(getattr(request, "state", None), "tenant_id", None)
    if state_tenant:
        return state_tenant
    account = get_session_account(request.cookies.get(SESSION_COOKIE))
    if account:
        return account.tenant_id
    bearer = bearer_tenant_id(request.headers)
    if bearer:
        return bearer
    raise PermissionError("Authenticated tenant is required")


def request_account_id(request: Request) -> str | None:
    state_user = getattr(getattr(request, "state", None), "auth_user_id", None)
    if state_user:
        return state_user
    account = get_session_account(request.cookies.get(SESSION_COOKIE))
    return account.user_id if account else None


def websocket_user_id(websocket) -> str | None:
    account = get_session_account(websocket.cookies.get(SESSION_COOKIE))
    if account:
        return account.tenant_id
    return bearer_tenant_id(websocket.headers)


def scope_conversation_id(user_id: str, conversation_id: str) -> str:
    if not _SAFE_ID.fullmatch(user_id) or not _SAFE_ID.fullmatch(conversation_id):
        raise ValueError("Invalid user or conversation ID")
    return f"{_PREFIX}{user_id}{_SEPARATOR}{conversation_id}"


def public_conversation_id(conversation_id: str) -> str:
    if conversation_id.startswith(_PREFIX) and _SEPARATOR in conversation_id:
        return conversation_id.split(_SEPARATOR, 1)[1]
    return conversation_id


def conversation_user_id(conversation_id: str) -> str | None:
    if conversation_id.startswith(_PREFIX) and _SEPARATOR in conversation_id:
        return conversation_id[len(_PREFIX):].split(_SEPARATOR, 1)[0]
    return None


def belongs_to_user(conversation_id: str, user_id: str) -> bool:
    return conversation_id.startswith(f"{_PREFIX}{user_id}{_SEPARATOR}")
