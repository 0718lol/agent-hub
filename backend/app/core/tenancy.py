"""Tenant-scoped resource identifiers derived from signed browser sessions."""

import hashlib
import re

from fastapi import Request

from app.core.auth import SESSION_COOKIE, get_session_identity, get_session_secret
from app.core.config import settings

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_PREFIX = "tenant__"
_SEPARATOR = "__conv__"
_CLIENT_ID = re.compile(r"^[A-Za-z0-9_.@-]{3,128}$")


def _api_client_user_id(headers) -> str:
    client_id = headers.get("x-agenthub-client-id", "")
    if not _CLIENT_ID.fullmatch(client_id):
        return "api-client"
    digest = hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:24]
    return f"api-client-{digest}"


def has_valid_api_client_id(headers) -> bool:
    return bool(_CLIENT_ID.fullmatch(headers.get("x-agenthub-client-id", "")))


def request_user_id(request: Request) -> str:
    secret = get_session_secret(settings.api_secret)
    identity = get_session_identity(request.cookies.get(SESSION_COOKIE), secret)
    return identity or _api_client_user_id(request.headers)


def websocket_user_id(websocket) -> str:
    secret = get_session_secret(settings.api_secret)
    identity = get_session_identity(websocket.cookies.get(SESSION_COOKIE), secret)
    return identity or _api_client_user_id(websocket.headers)


def scope_conversation_id(user_id: str, conversation_id: str) -> str:
    if not _SAFE_ID.fullmatch(user_id) or not _SAFE_ID.fullmatch(conversation_id):
        raise ValueError("Invalid user or conversation ID")
    return f"{_PREFIX}{user_id}{_SEPARATOR}{conversation_id}"


def public_conversation_id(conversation_id: str) -> str:
    if conversation_id.startswith(_PREFIX) and _SEPARATOR in conversation_id:
        return conversation_id.split(_SEPARATOR, 1)[1]
    return conversation_id


def belongs_to_user(conversation_id: str, user_id: str) -> bool:
    return conversation_id.startswith(f"{_PREFIX}{user_id}{_SEPARATOR}")
