"""Persistent tenant settings and task-local LLM client registry."""

import json
import re
import threading
from datetime import UTC, datetime

from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.config import deobfuscate_key, obfuscate_key
from app.core.crud.utils import db_write_transaction
from app.core.llm_client import LLMClient, llm_client
from app.core.models import TenantConfig
from app.core.quality_gate import QualityGate, quality_gate
from app.core.speech import STTClient, stt_client

_SAFE_USER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SAFE_CONFIG_KEY = re.compile(r"^[a-z0-9_.-]{1,80}$")
_client_cache: dict[str, LLMClient] = {}
_stt_client_cache: dict[str, STTClient] = {}
_quality_gate_cache: dict[str, QualityGate] = {}
_disabled_tools_cache: dict[str, frozenset[str]] = {}
_client_cache_lock = threading.RLock()


def _validate(user_id: str, key: str) -> None:
    if not _SAFE_USER_ID.fullmatch(user_id) or not _SAFE_CONFIG_KEY.fullmatch(key):
        raise ValueError("Invalid tenant setting identifier")


def get_tenant_config(user_id: str, key: str, default=None):
    _validate(user_id, key)
    with Session(_engine_mod.engine) as session:
        row = session.exec(
            select(TenantConfig).where(
                TenantConfig.user_id == user_id,
                TenantConfig.key == key,
            )
        ).first()
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return default


@db_write_transaction
def save_tenant_config(user_id: str, key: str, value) -> None:
    _validate(user_id, key)
    encoded = json.dumps(value, ensure_ascii=False)
    with Session(_engine_mod.engine) as session:
        row = session.exec(
            select(TenantConfig).where(
                TenantConfig.user_id == user_id,
                TenantConfig.key == key,
            )
        ).first()
        if row is None:
            row = TenantConfig(user_id=user_id, key=key, value=encoded)
        else:
            row.value = encoded
            row.updated_at = datetime.now(UTC).isoformat()
        session.add(row)
        session.commit()


def _clone_default_client() -> LLMClient:
    default = llm_client.default_client
    client = LLMClient()
    client.configure(
        provider=default.provider,
        api_key=default.api_key,
        base_url=default.base_url,
        model=default.model,
        temperature=default.temperature,
        max_tokens=default.max_tokens,
    )
    return client


def get_tenant_llm_client(user_id: str) -> LLMClient:
    _validate(user_id, "llm")
    with _client_cache_lock:
        cached = _client_cache.get(user_id)
        if cached is not None:
            return cached

        client = _clone_default_client()
        client.tenant_id = user_id
        config = get_tenant_config(user_id, "llm", {}) or {}
        if config:
            client.configure(
                provider=config.get("provider") or client.provider,
                api_key=deobfuscate_key(config.get("api_key", "")) or client.api_key,
                base_url=config.get("base_url") or client.base_url,
                model=config.get("model") or client.model,
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
            )
        _client_cache[user_id] = client
        return client


def save_tenant_llm_client(user_id: str, client: LLMClient) -> None:
    save_tenant_config(user_id, "llm", {
        "provider": client.provider,
        "api_key": obfuscate_key(client.api_key),
        "base_url": client.base_url,
        "model": client.model,
        "temperature": client.temperature,
        "max_tokens": client.max_tokens,
    })
    with _client_cache_lock:
        _client_cache[user_id] = client


def get_tenant_stt_client(user_id: str) -> STTClient:
    _validate(user_id, "stt")
    with _client_cache_lock:
        cached = _stt_client_cache.get(user_id)
        if cached is not None:
            return cached

        client = STTClient()
        client.configure(
            api_key=stt_client.api_key,
            base_url=stt_client.base_url,
            model=stt_client.model,
            language=stt_client.language,
        )
        config = get_tenant_config(user_id, "stt", {}) or {}
        if config:
            client.configure(
                api_key=deobfuscate_key(config.get("api_key", "")) or client.api_key,
                base_url=config.get("base_url") or client.base_url,
                model=config.get("model") or client.model,
                language=config.get("language") or client.language,
            )
        _stt_client_cache[user_id] = client
        return client


def save_tenant_stt_client(user_id: str, client: STTClient) -> None:
    save_tenant_config(user_id, "stt", {
        "api_key": obfuscate_key(client.api_key),
        "base_url": client.base_url,
        "model": client.model,
        "language": client.language,
    })
    with _client_cache_lock:
        _stt_client_cache[user_id] = client


def get_tenant_quality_gate(user_id: str) -> QualityGate:
    _validate(user_id, "quality")
    with _client_cache_lock:
        cached = _quality_gate_cache.get(user_id)
        if cached is not None:
            return cached

        default = quality_gate.default_gate
        config = get_tenant_config(user_id, "quality", {}) or {}
        gate = QualityGate(
            enabled=config.get("enabled", default.enabled),
            max_retries=config.get("max_retries", default.max_retries),
            use_llm_judge=config.get("use_llm_judge", default.use_llm_judge),
            best_of_n=config.get("best_of_n", default.best_of_n),
        )
        _quality_gate_cache[user_id] = gate
        return gate


def save_tenant_quality_gate(user_id: str, gate: QualityGate) -> None:
    save_tenant_config(user_id, "quality", {
        "enabled": gate.enabled,
        "max_retries": gate.max_retries,
        "use_llm_judge": gate.use_llm_judge,
        "best_of_n": gate.best_of_n,
    })
    with _client_cache_lock:
        _quality_gate_cache[user_id] = gate


def get_tenant_disabled_tools(user_id: str) -> frozenset[str]:
    _validate(user_id, "tools")
    with _client_cache_lock:
        cached = _disabled_tools_cache.get(user_id)
        if cached is not None:
            return cached
        config = get_tenant_config(user_id, "tools", {}) or {}
        disabled = frozenset(str(name) for name in config.get("disabled", []))
        _disabled_tools_cache[user_id] = disabled
        return disabled


def save_tenant_disabled_tools(user_id: str, disabled: set[str] | frozenset[str]) -> None:
    normalized = frozenset(str(name) for name in disabled)
    save_tenant_config(user_id, "tools", {"disabled": sorted(normalized)})
    with _client_cache_lock:
        _disabled_tools_cache[user_id] = normalized


def clear_tenant_client_cache() -> None:
    with _client_cache_lock:
        _client_cache.clear()
        _stt_client_cache.clear()
        _quality_gate_cache.clear()
        _disabled_tools_cache.clear()
