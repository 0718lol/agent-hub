"""Signed account sessions with a persistent local signing secret."""

import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

SESSION_COOKIE = "agenthub_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
_SESSION_SECRET_PATH = Path(__file__).resolve().parents[2] / "data" / ".session_secret"


def _persistent_local_secret() -> str:
    configured = os.environ.get("AGENTHUB_SESSION_SECRET", "").strip()
    if configured:
        return configured
    try:
        existing = _SESSION_SECRET_PATH.read_text(encoding="ascii").strip()
        if len(existing) >= 32:
            return existing
    except FileNotFoundError:
        pass

    _SESSION_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(48)
    try:
        descriptor = os.open(
            _SESSION_SECRET_PATH,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(generated)
        return generated
    except FileExistsError:
        existing = _SESSION_SECRET_PATH.read_text(encoding="ascii").strip()
        if len(existing) < 32:
            raise RuntimeError("Persistent session secret is invalid")
        return existing


def get_session_secret(api_secret: str = "") -> str:
    return os.environ.get("AGENTHUB_SESSION_SECRET", "").strip() or api_secret or _persistent_local_secret()


def create_session_token(secret: str, now: int | None = None, user_id: str | None = None) -> str:
    if not user_id:
        raise ValueError("A stable user_id is required for account sessions")
    issued_at = int(now if now is not None else time.time())
    payload = f"{issued_at}.{user_id}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload}.{encoded_signature}"


def verify_session_token(token: str | None, secret: str, now: int | None = None) -> bool:
    if not token or not secret or len(token) > 1024:
        return False
    try:
        issued_at_text, subject, supplied_signature = token.split(".", 2)
        issued_at = int(issued_at_text)
    except (TypeError, ValueError):
        return False
    if not subject:
        return False
    current_time = int(now if now is not None else time.time())
    if issued_at > current_time + 60 or current_time - issued_at > SESSION_TTL_SECONDS:
        return False
    payload = f"{issued_at}.{subject}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return hmac.compare_digest(expected, supplied_signature)


def get_session_identity(token: str | None, secret: str, now: int | None = None) -> str | None:
    if not verify_session_token(token, secret, now=now):
        return None
    return token.split(".", 2)[1]


def get_session_account(token: str | None):
    from app.core.accounts import get_account
    from app.core.config import settings

    subject = get_session_identity(token, get_session_secret(settings.api_secret))
    return get_account(subject)
