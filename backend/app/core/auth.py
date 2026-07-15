"""Short-lived signed browser sessions backed by the server API secret."""

import base64
import hashlib
import hmac
import secrets
import time

SESSION_COOKIE = "agenthub_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
_DEV_SESSION_SECRET = secrets.token_urlsafe(32)


def get_session_secret(api_secret: str) -> str:
    return api_secret or _DEV_SESSION_SECRET


def create_session_token(secret: str, now: int | None = None, user_id: str | None = None) -> str:
    issued_at = int(now if now is not None else time.time())
    payload = f"{issued_at}.{user_id or secrets.token_urlsafe(16)}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload}.{encoded_signature}"


def verify_session_token(token: str | None, secret: str, now: int | None = None) -> bool:
    if not token or not secret:
        return False
    try:
        issued_at_text, nonce, supplied_signature = token.split(".", 2)
        issued_at = int(issued_at_text)
    except (TypeError, ValueError):
        return False
    current_time = int(now if now is not None else time.time())
    if issued_at > current_time + 60 or current_time - issued_at > SESSION_TTL_SECONDS:
        return False
    payload = f"{issued_at}.{nonce}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return hmac.compare_digest(expected, supplied_signature)


def get_session_identity(token: str | None, secret: str, now: int | None = None) -> str | None:
    if not verify_session_token(token, secret, now=now):
        return None
    return token.split(".", 2)[1]
