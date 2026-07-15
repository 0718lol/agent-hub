"""Tenant-scoped resource identifiers derived from signed browser sessions."""

import re

from fastapi import Request

from app.core.auth import SESSION_COOKIE, get_session_identity, get_session_secret
from app.core.config import settings

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_PREFIX = "tenant__"
_SEPARATOR = "__conv__"


def request_user_id(request: Request) -> str:
    secret = get_session_secret(settings.api_secret)
    identity = get_session_identity(request.cookies.get(SESSION_COOKIE), secret)
    return identity or "api-client"


def websocket_user_id(websocket) -> str:
    secret = get_session_secret(settings.api_secret)
    identity = get_session_identity(websocket.cookies.get(SESSION_COOKIE), secret)
    return identity or "api-client"


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
