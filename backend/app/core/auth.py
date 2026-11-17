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
_MAX_REVOKED_TOKENS = 10_000
_revoked_tokens: dict[str, float] = {}


def _prune_revoked_tokens(now: float) -> None:
    expired = [tok for tok, exp in _revoked_tokens.items() if exp <= now]
    for tok in expired:
        _revoked_tokens.pop(tok, None)
    while len(_revoked_tokens) > _MAX_REVOKED_TOKENS:
        oldest_key = next(iter(_revoked_tokens))
        _revoked_tokens.pop(oldest_key, None)


def revoke_session_token(token: str | None, now: int | None = None) -> None:
    if not token or len(token) > 1024:
        return
    current_time = float(now if now is not None else time.time())
    _prune_revoked_tokens(current_time)
    _revoked_tokens[token] = current_time + SESSION_TTL_SECONDS + 120


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


def create_session_token(
    secret: str,
    now: int | None = None,
    user_id: str | None = None,
    password_tag: str = "",
) -> str:
    if not user_id:
        raise ValueError("A stable user_id is required for account sessions")
    issued_at = int(now if now is not None else time.time())
    if password_tag:
        nonce = secrets.token_hex(6)
        payload = f"{issued_at}.{user_id}.{password_tag}.{nonce}"
    else:
        payload = f"{issued_at}.{user_id}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload}.{encoded_signature}"


def _parse_verified_session(
    token: str | None,
    secret: str,
    now: int | None = None,
) -> tuple[str, str] | None:
    if not token or not secret or len(token) > 1024:
        return None
    current_time = int(now if now is not None else time.time())
    _prune_revoked_tokens(float(current_time))
    if token in _revoked_tokens:
        return None
    parts = token.split(".")
    if len(parts) == 3:
        issued_at_text, subject, supplied_signature = parts
        password_tag = ""
        payload = f"{issued_at_text}.{subject}"
    elif len(parts) == 4:
        issued_at_text, subject, password_tag, supplied_signature = parts
        payload = f"{issued_at_text}.{subject}.{password_tag}"
    elif len(parts) == 5:
        issued_at_text, subject, password_tag, nonce, supplied_signature = parts
        if not nonce:
            return None
        payload = f"{issued_at_text}.{subject}.{password_tag}.{nonce}"
    else:
        return None
    try:
        issued_at = int(issued_at_text)
    except (TypeError, ValueError):
        return None
    if not subject:
        return None
    if issued_at > current_time + 60 or current_time - issued_at > SESSION_TTL_SECONDS:
        return None
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    if not hmac.compare_digest(expected, supplied_signature):
        return None
    return subject, password_tag


def verify_session_token(token: str | None, secret: str, now: int | None = None) -> bool:
    return _parse_verified_session(token, secret, now=now) is not None


def get_session_identity(token: str | None, secret: str, now: int | None = None) -> str | None:
    parsed = _parse_verified_session(token, secret, now=now)
    return parsed[0] if parsed else None


def get_session_account(token: str | None):
    from app.core.accounts import get_account
    from app.core.config import settings

    parsed = _parse_verified_session(token, get_session_secret(settings.api_secret))
    if not parsed:
        return None
    subject, token_password_tag = parsed
    account = get_account(subject)
    if account is None:
        return None
    if account.password_tag and token_password_tag != account.password_tag:
        return None
    return account
