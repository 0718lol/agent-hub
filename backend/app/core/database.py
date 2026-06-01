"""
Database engine, connection setup, and schema initialization.

This is the public entry-point for all database symbols.  It re-exports
everything from :mod:`models`, :mod:`crud`, and :mod:`async_wrappers`
so that ``from app.core.database import X`` continues to work unchanged.
"""
import sqlite3
import json
import os
from sqlalchemy import text
import logging as _logging

_db_logger = _logging.getLogger("database")
from sqlmodel import SQLModel, Session

# Engine is defined in _engine.py to break the circular dependency
# between database.py and crud.py.
from app.core._engine import engine, DB_PATH  # noqa: F401


# ============================================================
# Re-export all public symbols for backward compatibility
# ============================================================
from app.core.models import *          # noqa: F401,F403
from app.core.crud import *            # noqa: F401,F403 -- brings in db_write_transaction

# ============================================================
# Database Initialization
# ============================================================

def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_db():
    """Retained for backward compatibility with external direct SQLite connections."""
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL;')
    except Exception as e:
        _db_logger.warning(f"Failed to set WAL mode in get_db(): {e}")
    return conn


def init_db():
    _ensure_dir()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.commit()
        conn.close()
    except Exception as e:
        _db_logger.warning(f"Failed to set WAL mode during init_db(): {e}")

    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config(
            os.path.join(os.path.dirname(__file__), '..', '..', 'alembic.ini')
        )
        if not os.environ.get('DATABASE_URL'):
            alembic_cfg.set_main_option('sqlalchemy.url', f'sqlite:///{DB_PATH}')
        command.upgrade(alembic_cfg, 'head')
    except Exception:
        SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        default_convs = [
            Conversation(id='conv_pm', type='single', name='PM \u5c0f\u52a9\u624b', avatar='\U0001f4cb', agent_id='agent_pm', preview='\u9700\u6c42\u5206\u6790\u4e0e\u4efb\u52a1\u62c6\u89e3'),
            Conversation(id='conv_frontend', type='single', name='\u524d\u7aef\u5de5\u7a0b\u5e08', avatar='\U0001f3a8', agent_id='agent_frontend', preview='React \u7ec4\u4ef6\u4e0e\u6837\u5f0f\u5f00\u53d1'),
            Conversation(id='conv_backend', type='single', name='\u540e\u7aef\u5de5\u7a0b\u5e08', avatar='\u2699\ufe0f', agent_id='agent_backend', preview='API \u63a5\u53e3\u4e0e\u6570\u636e\u6a21\u578b'),
            Conversation(id='conv_tester', type='single', name='\u6d4b\u8bd5\u5de5\u7a0b\u5e08', avatar='\U0001f9ea', agent_id='agent_tester', preview='\u6d4b\u8bd5\u7528\u4f8b\u4e0e Bug \u5206\u6790'),
            Conversation(id='conv_devops', type='single', name='\u8fd0\u7ef4\u5de5\u7a0b\u5e08', avatar='\U0001f680', agent_id='agent_devops', preview='Docker \u90e8\u7f72\u4e0e CI/CD'),
            Conversation(id='conv_designer', type='single', name='\u8bbe\u8ba1\u987e\u95ee', avatar='\U0001f3af', agent_id='agent_designer', preview='UI/UX \u8bbe\u8ba1\u5efa\u8bae'),
            Conversation(id='conv_builder', type='single', name='Agent \u5de5\u574a', avatar='\U0001f527', agent_id='agent_builder', preview='\u5bf9\u8bdd\u5f0f\u521b\u5efa\u81ea\u5b9a\u4e49 Agent'),
            Conversation(id='conv_group_demo', type='group', name='Demo \u9879\u76ee\u7fa4', avatar='\U0001f4ac', agents=json.dumps(['agent_pm', 'agent_frontend', 'agent_backend', 'agent_tester', 'agent_devops', 'agent_designer']), preview='\u591a Agent \u534f\u4f5c\u6f14\u793a'),
        ]
        for conv in default_convs:
            existing = session.get(Conversation, conv.id)
            if not existing:
                session.add(conv)
        session.commit()

    try:
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                "content_text, content='messages', content_rowid='id', tokenize='unicode61')"
            ))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN "
                "INSERT INTO messages_fts(rowid, content_text) VALUES (new.id, COALESCE(json_extract(new.content, '$.text'), '')); END"
            ))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN "
                "INSERT INTO messages_fts(messages_fts, rowid, content_text) VALUES('delete', old.id, COALESCE(json_extract(old.content, '$.text'), '')); END"
            ))
            conn.execute(text(
                "CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN "
                "INSERT INTO messages_fts(messages_fts, rowid, content_text) VALUES('delete', old.id, COALESCE(json_extract(old.content, '$.text'), '')); "
                "INSERT INTO messages_fts(rowid, content_text) VALUES (new.id, COALESCE(json_extract(new.content, '$.text'), '')); END"
            ))
            conn.commit()
    except Exception as e:
        import logging as _logging
        _logging.getLogger("database").warning(f"FTS5 setup skipped: {e}")


# Re-export async wrappers AFTER init_db is defined (no circular dep issue)
# async_wrappers imported lazily to avoid circular dependency
# Use: from app.core.async_wrappers import async_save_event, ...

