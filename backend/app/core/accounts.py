"""Local account authentication and stable level-one tenant ownership."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.models import Tenant, User

logger = logging.getLogger("accounts")

_USERNAME_PATTERN = re.compile(r"^[\w.-]{2,32}$", re.UNICODE)
_PASSWORD_MIN_LENGTH = 8
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


class AccountError(ValueError):
    """Base account validation error."""


class UsernameTakenError(AccountError):
    pass


class InvalidCredentialsError(AccountError):
    pass


@dataclass(frozen=True)
class AccountIdentity:
    user_id: str
    tenant_id: str
    username: str
    is_admin: bool

    def public_dict(self) -> dict:
        return {
            "id": self.user_id,
            "username": self.username,
            "tenant_id": self.tenant_id,
            "is_admin": self.is_admin,
        }


def normalize_username(username: str) -> str:
    value = unicodedata.normalize("NFKC", username or "").strip()
    if not _USERNAME_PATTERN.fullmatch(value):
        raise AccountError("用户名须为 2-32 个中文、字母、数字、点、横线或下划线")
    return value.casefold()


def validate_password(password: str) -> None:
    if len(password or "") < _PASSWORD_MIN_LENGTH:
        raise AccountError(f"密码至少需要 {_PASSWORD_MIN_LENGTH} 位")
    if len(password) > 256:
        raise AccountError("密码不能超过 256 位")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, salt.hex(), digest.hex()
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def _identity(user: User) -> AccountIdentity:
    return AccountIdentity(
        user_id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        is_admin=bool(user.is_admin),
    )


def create_account(username: str, password: str, *, is_admin: bool = False) -> AccountIdentity:
    normalized = normalize_username(username)
    display_name = unicodedata.normalize("NFKC", username).strip()
    password_hash = hash_password(password)
    tenant = Tenant(id=f"tn_{uuid.uuid4().hex}", name=display_name)
    user = User(
        id=f"usr_{uuid.uuid4().hex}",
        tenant_id=tenant.id,
        username=display_name,
        username_normalized=normalized,
        password_hash=password_hash,
        is_admin=is_admin,
    )
    try:
        with Session(_engine_mod.engine) as session:
            session.add(tenant)
            session.add(user)
            session.commit()
            session.refresh(user)
    except IntegrityError as exc:
        raise UsernameTakenError("用户名已存在") from exc
    return _identity(user)


def authenticate(username: str, password: str) -> AccountIdentity:
    try:
        normalized = normalize_username(username)
    except AccountError as exc:
        raise InvalidCredentialsError("用户名或密码错误") from exc
    with Session(_engine_mod.engine) as session:
        user = session.exec(
            select(User).where(User.username_normalized == normalized)
        ).first()
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("用户名或密码错误")
    return _identity(user)


def get_account(user_id: str | None) -> AccountIdentity | None:
    if not user_id:
        return None
    with Session(_engine_mod.engine) as session:
        user = session.get(User, user_id)
        return _identity(user) if user else None


def get_account_by_username(username: str) -> AccountIdentity | None:
    try:
        normalized = normalize_username(username)
    except AccountError:
        return None
    with Session(_engine_mod.engine) as session:
        user = session.exec(
            select(User).where(User.username_normalized == normalized)
        ).first()
        return _identity(user) if user else None


def ensure_admin_account(username: str, password: str) -> bool:
    """Create an administrator once without changing an existing account."""
    existing = get_account_by_username(username)
    if existing:
        if not existing.is_admin:
            raise AccountError("同名普通账户已存在，拒绝自动提升权限")
        return False
    create_account(username, password, is_admin=True)
    return True


def bootstrap_admin_from_env() -> bool | None:
    """Optionally create the first administrator from one-shot deployment secrets."""
    username = os.environ.get("AGENTHUB_BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.environ.get("AGENTHUB_BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username and not password:
        return None
    if not username or not password:
        raise RuntimeError(
            "AGENTHUB_BOOTSTRAP_ADMIN_USERNAME and AGENTHUB_BOOTSTRAP_ADMIN_PASSWORD must be set together"
        )
    try:
        created = ensure_admin_account(username, password)
    except AccountError as exc:
        raise RuntimeError(f"Administrator bootstrap failed: {exc}") from exc
    if created:
        logger.info("Bootstrap administrator created for username %s", username)
    else:
        logger.info("Bootstrap administrator already exists for username %s", username)
    return created


def update_password(user_id: str, current_password: str, new_password: str) -> None:
    validate_password(new_password)
    with Session(_engine_mod.engine) as session:
        user = session.get(User, user_id)
        if user is None or not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("当前密码错误")
        user.password_hash = hash_password(new_password)
        session.add(user)
        session.commit()


def list_legacy_tenants() -> list[dict]:
    """List old conversation namespaces that are not owned by an account tenant."""
    from sqlalchemy import text

    prefix = "tenant__"
    separator = "__conv__"
    with Session(_engine_mod.engine) as session:
        current = set(session.exec(select(Tenant.id)).all())
        rows = session.exec(text(
            "SELECT id FROM conversations WHERE id LIKE 'tenant__%__conv__%'"
        )).all()
        result: dict[str, int] = {}
        for row in rows:
            conversation_id = row[0]
            owner = conversation_id[len(prefix):].split(separator, 1)[0]
            if owner not in current:
                result[owner] = result.get(owner, 0) + 1
        return [
            {"legacy_tenant_id": owner, "conversation_count": count}
            for owner, count in sorted(result.items())
        ]
