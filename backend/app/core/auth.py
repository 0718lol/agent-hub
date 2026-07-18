"""Short-lived signed browser sessions backed by the server API secret."""

import base64
import hashlib
import hmac
import json
import secrets
import time

SESSION_COOKIE = "agenthub_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
DEVICE_COOKIE = "agenthub_device"
DEVICE_TTL_SECONDS = 365 * 24 * 60 * 60
_DEV_SESSION_SECRET = secrets.token_urlsafe(32)


def get_session_secret(api_secret: str) -> str:
    return api_secret or _DEV_SESSION_SECRET


def create_session_token(secret: str, now: int | None = None, user_id: str | None = None) -> str:
    issued_at = int(now if now is not None else time.time())
    payload = f"{issued_at}.{user_id or secrets.token_urlsafe(16)}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload}.{encoded_signature}"


def verify_session_token(
    token: str | None,
    secret: str,
    now: int | None = None,
    *,
    ttl_seconds: int = SESSION_TTL_SECONDS,
) -> bool:
    if not token or not secret:
        return False
    try:
        issued_at_text, nonce, supplied_signature = token.split(".", 2)
        issued_at = int(issued_at_text)
    except (TypeError, ValueError):
        return False
    current_time = int(now if now is not None else time.time())
    if issued_at > current_time + 60 or current_time - issued_at > ttl_seconds:
        return False
    payload = f"{issued_at}.{nonce}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return hmac.compare_digest(expected, supplied_signature)


def get_session_identity(
    token: str | None,
    secret: str,
    now: int | None = None,
    *,
    ttl_seconds: int = SESSION_TTL_SECONDS,
) -> str | None:
    if not verify_session_token(token, secret, now=now, ttl_seconds=ttl_seconds):
        return None
    return token.split(".", 2)[1]


def get_device_identity(token: str | None, secret: str, now: int | None = None) -> str | None:
    return get_session_identity(token, secret, now=now, ttl_seconds=DEVICE_TTL_SECONDS)


def _hashed_identity(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def trusted_proxy_identity(headers) -> str | None:
    """Return an upstream IdP identity only when the proxy signature matches."""
    from app.core.config import settings

    if settings.auth_mode != "proxy" or not settings.trusted_proxy_secret:
        return None
    supplied = headers.get("x-agenthub-proxy-secret", "")
    if not supplied or not hmac.compare_digest(supplied, settings.trusted_proxy_secret):
        return None
    external_id = headers.get(settings.trusted_identity_header, "").strip()
    if not external_id or len(external_id) > 320:
        return None
    return _hashed_identity("user", external_id.casefold())


def trusted_proxy_role(headers) -> str:
    from app.core.config import settings

    if not trusted_proxy_identity(headers):
        return "user"
    role = headers.get(settings.trusted_role_header, "user").strip().lower()
    return role if role in {"user", "admin", "viewer"} else "user"


def _configured_client_tokens() -> dict[str, str]:
    from app.core.config import settings

    if not settings.api_client_tokens_json.strip():
        return {}
    try:
        payload = json.loads(settings.api_client_tokens_json)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(client_id): str(token)
        for client_id, token in payload.items()
        if client_id and token
    }


def bearer_client_identity(headers) -> str | None:
    """Authenticate a machine client with its own token or the legacy secret."""
    from app.core.config import settings

    authorization = headers.get("authorization", "")
    token = authorization.split(" ", 1)[1] if authorization.startswith("Bearer ") else ""
    token = token or headers.get("x-api-secret", "")
    client_id = headers.get("x-agenthub-client-id", "").strip()
    if not token:
        return None

    client_tokens = _configured_client_tokens()
    if client_tokens:
        if not client_id:
            return None
        expected = client_tokens.get(client_id, "")
        if not expected or not hmac.compare_digest(token, expected):
            return None
    elif not settings.api_secret or not hmac.compare_digest(token, settings.api_secret):
        return None
    elif not client_id:
        return "api-client"
    return _hashed_identity("api-client", client_id)
