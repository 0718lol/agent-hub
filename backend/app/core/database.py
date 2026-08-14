"""Database migrations, default records, and compatibility CRUD exports."""

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
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception as exc:
        logger.warning("Failed to set WAL mode in get_db(): %s", exc)
    return conn


def init_db() -> None:
    """Run real migrations before serving requests; never stamp an unknown schema."""
    _ensure_dir()
    if DB_PATH == ":memory:" and not os.environ.get("DATABASE_URL"):
        # Alembic creates its own connection, which would be a different and
        # immediately discarded SQLite in-memory database.
        SQLModel.metadata.create_all(engine)
        populate_database_defaults()
        return
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

        config = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
        config.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "..", "alembic"))
        config.set_main_option("sqlalchemy.url", database_url or f"sqlite:///{DB_PATH}")
        command.upgrade(config, "head")
    except Exception as exc:
        logger.exception("Alembic migration failed")
        raise RuntimeError("Database migration failed; startup aborted") from exc

    populate_database_defaults()


def populate_database_defaults() -> None:
    defaults = [
        Conversation(id="conv_pm", type="single", name="PM 小助手", avatar="📋", agent_id="agent_pm", preview="需求分析与任务拆解"),
        Conversation(id="conv_frontend", type="single", name="前端工程师", avatar="🎨", agent_id="agent_frontend", preview="React 组件与样式开发"),
        Conversation(id="conv_backend", type="single", name="后端工程师", avatar="⚙️", agent_id="agent_backend", preview="API 接口与数据模型"),
        Conversation(id="conv_tester", type="single", name="测试工程师", avatar="🧪", agent_id="agent_tester", preview="测试用例与 Bug 分析"),
        Conversation(id="conv_devops", type="single", name="运维工程师", avatar="🚀", agent_id="agent_devops", preview="Docker 部署与 CI/CD"),
        Conversation(id="conv_designer", type="single", name="设计顾问", avatar="🎯", agent_id="agent_designer", preview="UI/UX 设计建议"),
        Conversation(id="conv_builder", type="single", name="Agent 工坊", avatar="🔧", agent_id="agent_builder", preview="对话式创建自定义 Agent"),
        Conversation(
            id="conv_group_demo", type="group", name="Demo 项目群", avatar="💬",
            agents=json.dumps([
                "agent_pm", "agent_frontend", "agent_backend", "agent_tester",
                "agent_devops", "agent_designer",
            ]), preview="多 Agent 协作演示",
        ),
    ]
    with Session(engine) as session:
        for conversation in defaults:
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


async def async_get_messages_cached(conversation_id, limit=100, before_id=None):
    from app.core.cache import cache
    cache_key = f"msg:{conversation_id}:{limit}:{before_id or 'latest'}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(get_messages, conversation_id, limit, before_id)  # noqa: F405
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


async def async_create_conversation_cached(conv_id, conv_type, name, avatar, agent_id=None, agents=None, preview=""):
    result = await asyncio.to_thread(
        create_conversation, conv_id, conv_type, name, avatar, agent_id, agents, preview  # noqa: F405
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
    result = await asyncio.to_thread(save_memory_item, conversation_id, key, value, source)  # noqa: F405
    await _async_invalidate_cache(f"mem:{conversation_id}")
    return result


async def async_delete_memory_item_cached(conversation_id, key):
    result = await asyncio.to_thread(delete_memory_item, conversation_id, key)  # noqa: F405
    await _async_invalidate_cache(f"mem:{conversation_id}")
    return result
