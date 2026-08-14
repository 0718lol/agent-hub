"""Tenant-scoped configuration storage with optional authenticated encryption."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.config import deobfuscate_key, obfuscate_key
from app.core.models import TenantConfig


def get_tenant_config(tenant_id: str, key: str) -> str | None:
    with Session(_engine_mod.engine) as session:
        row = session.exec(
            select(TenantConfig).where(
                TenantConfig.user_id == tenant_id,
                TenantConfig.key == key,
            )
        ).first()
        return row.value if row else None


def set_tenant_config(tenant_id: str, key: str, value: str) -> None:
    with Session(_engine_mod.engine) as session:
        row = session.exec(
            select(TenantConfig).where(
                TenantConfig.user_id == tenant_id,
                TenantConfig.key == key,
            )
        ).first()
        if row is None:
            row = TenantConfig(user_id=tenant_id, key=key, value=value)
        else:
            row.value = value
            row.updated_at = datetime.now(UTC).isoformat()
        session.add(row)
        session.commit()


def delete_tenant_config(tenant_id: str, key: str) -> None:
    with Session(_engine_mod.engine) as session:
        row = session.exec(
            select(TenantConfig).where(
                TenantConfig.user_id == tenant_id,
                TenantConfig.key == key,
            )
        ).first()
        if row is not None:
            session.delete(row)
            session.commit()


def get_tenant_json(
    tenant_id: str,
    key: str,
    default: Any = None,
    *,
    encrypted: bool = False,
) -> Any:
    value = get_tenant_config(tenant_id, key)
    if value is None:
        return default
    if encrypted:
        value = deobfuscate_key(value)
        if not value:
            return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def set_tenant_json(tenant_id: str, key: str, value: Any, *, encrypted: bool = False) -> None:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    set_tenant_config(tenant_id, key, obfuscate_key(serialized) if encrypted else serialized)
