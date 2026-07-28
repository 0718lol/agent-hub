"""Database initialization and backward-compatible CRUD exports.

CRUD implementations live exclusively in :mod:`app.core.crud`. This module
keeps the historical import surface plus the Redis cache wrappers used by the
application.
"""

import asyncio
import json
import logging
import os
import sqlite3

from sqlalchemy import text
from sqlmodel import Session, SQLModel

from app.core._engine import DB_PATH, engine
from app.core.config import settings
from app.core.crud import *  # noqa: F403
from app.core.models import *  # noqa: F403

logger = logging.getLogger("database")


def _ensure_dir() -> None:
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)


def get_db():
    """Return the legacy direct SQLite connection used by external scripts."""
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception as exc:
        logger.warning("Failed to set WAL mode in get_db(): %s", exc)
    return conn


def init_db() -> None:
    """Upgrade the schema and seed built-in conversations."""
    _ensure_dir()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Failed to set WAL mode during init_db(): %s", exc)

    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config(
            os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
        )
        alembic_cfg.set_main_option(
            "sqlalchemy.url", database_url or f"sqlite:///{DB_PATH}"
        )
        command.upgrade(alembic_cfg, "head")
    except Exception as exc:
        logger.exception("Alembic migration failed")
        if not settings.debug:
            raise RuntimeError("Database migration failed; startup aborted") from exc

    populate_database_defaults()


def populate_database_defaults() -> None:
    """Seed template conversations and initialize SQLite full-text search."""
    default_conversations = [
        Conversation(id="conv_pm", type="single", name="PM \u5c0f\u52a9\u624b", avatar="\U0001f4cb", agent_id="agent_pm", preview="\u9700\u6c42\u5206\u6790\u4e0e\u4efb\u52a1\u62c6\u89e3"),
        Conversation(id="conv_frontend", type="single", name="\u524d\u7aef\u5de5\u7a0b\u5e08", avatar="\U0001f3a8", agent_id="agent_frontend", preview="React \u7ec4\u4ef6\u4e0e\u6837\u5f0f\u5f00\u53d1"),
        Conversation(id="conv_backend", type="single", name="\u540e\u7aef\u5de5\u7a0b\u5e08", avatar="\u2699\ufe0f", agent_id="agent_backend", preview="API \u63a5\u53e3\u4e0e\u6570\u636e\u6a21\u578b"),
        Conversation(id="conv_tester", type="single", name="\u6d4b\u8bd5\u5de5\u7a0b\u5e08", avatar="\U0001f9ea", agent_id="agent_tester", preview="\u6d4b\u8bd5\u7528\u4f8b\u4e0e Bug \u5206\u6790"),
        Conversation(id="conv_devops", type="single", name="\u8fd0\u7ef4\u5de5\u7a0b\u5e08", avatar="\U0001f680", agent_id="agent_devops", preview="Docker \u90e8\u7f72\u4e0e CI/CD"),
        Conversation(id="conv_designer", type="single", name="\u8bbe\u8ba1\u987e\u95ee", avatar="\U0001f3af", agent_id="agent_designer", preview="UI/UX \u8bbe\u8ba1\u5efa\u8bae"),
        Conversation(id="conv_builder", type="single", name="Agent \u5de5\u574a", avatar="\U0001f527", agent_id="agent_builder", preview="\u5bf9\u8bdd\u5f0f\u521b\u5efa\u81ea\u5b9a\u4e49 Agent"),
        Conversation(
            id="conv_group_demo",
            type="group",
            name="Demo \u9879\u76ee\u7fa4",
            avatar="\U0001f4ac",
            agents=json.dumps([
                "agent_pm", "agent_frontend", "agent_backend",
                "agent_tester", "agent_devops", "agent_designer",
            ]),
            preview="\u591a Agent \u534f\u4f5c\u6f14\u793a",
        ),
    ]
    with Session(engine) as session:
        for conversation in default_conversations:
            if session.get(Conversation, conversation.id) is None:
                session.add(conversation)
        session.commit()

    if os.environ.get("DATABASE_URL"):
        return
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                "content_text, content='messages', content_rowid='id', tokenize='unicode61')"
            ))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN "
                "INSERT INTO messages_fts(rowid, content_text) VALUES "
                "(new.id, COALESCE(json_extract(new.content, '$.text'), '')); END"
            ))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN "
                "INSERT INTO messages_fts(messages_fts, rowid, content_text) VALUES"
                "('delete', old.id, COALESCE(json_extract(old.content, '$.text'), '')); END"
            ))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN "
                "INSERT INTO messages_fts(messages_fts, rowid, content_text) VALUES"
                "('delete', old.id, COALESCE(json_extract(old.content, '$.text'), '')); "
                "INSERT INTO messages_fts(rowid, content_text) VALUES "
                "(new.id, COALESCE(json_extract(new.content, '$.text'), '')); END"
            ))
            conn.commit()
    except Exception as exc:
        logger.warning("FTS5 setup skipped: %s", exc)


async def _async_invalidate_cache(pattern: str) -> None:
    try:
        from app.core.cache import cache

        if "*" in pattern:
            await cache.delete_pattern(pattern)
        else:
            await cache.delete(pattern)
    except Exception:
        pass


async def async_save_message_cached(conversation_id, sender, content, streaming=False):
    result = await asyncio.to_thread(save_message, conversation_id, sender, content, streaming)  # noqa: F405
    await _async_invalidate_cache(f"msg:{conversation_id}:*")
    return result


async def async_get_messages_cached(conversation_id, limit=100):
    from app.core.cache import cache

    cache_key = f"msg:{conversation_id}:{limit}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(get_messages, conversation_id, limit)  # noqa: F405
    if result:
        await cache.set_json(cache_key, result, ttl=30)
    return result


async def async_get_conversations_cached():
    from app.core.cache import cache

    cached = await cache.get_json("conv:list")
    if cached is not None:
        return cached
    result = await asyncio.to_thread(get_conversations)  # noqa: F405
    if result:
        await cache.set_json("conv:list", result, ttl=60)
    return result


async def async_clear_messages_cached(conversation_id):
    result = await asyncio.to_thread(clear_messages, conversation_id)  # noqa: F405
    await _async_invalidate_cache(f"msg:{conversation_id}:*")
    return result


async def async_create_conversation_cached(
    conv_id, conv_type, name, avatar, agent_id=None, agents=None, preview=""
):
    result = await asyncio.to_thread(
        create_conversation,  # noqa: F405
        conv_id, conv_type, name, avatar, agent_id, agents, preview,
    )
    await _async_invalidate_cache("conv:list")
    return result


async def async_delete_custom_agent_cached(agent_id, user_id=None):
    result = await asyncio.to_thread(delete_custom_agent, agent_id, user_id)  # noqa: F405
    await _async_invalidate_cache("conv:list")
    return result


async def async_get_project_memory_cached(conversation_id):
    from app.core.cache import cache

    cache_key = f"mem:{conversation_id}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(get_project_memory, conversation_id)  # noqa: F405
    if result:
        await cache.set_json(cache_key, result, ttl=60)
    return result


async def async_save_memory_item_cached(conversation_id, key, value, source="system"):
    result = await asyncio.to_thread(  # noqa: F405
        save_memory_item, conversation_id, key, value, source
    )
    await _async_invalidate_cache(f"mem:{conversation_id}")
    return result


async def async_delete_memory_item_cached(conversation_id, key):
    result = await asyncio.to_thread(delete_memory_item, conversation_id, key)  # noqa: F405
    await _async_invalidate_cache(f"mem:{conversation_id}")
    return result
