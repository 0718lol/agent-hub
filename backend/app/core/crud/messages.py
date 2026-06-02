"""
Message CRUD operations.

Handles saving, retrieving, searching, and clearing messages within
conversations.  Search uses FTS5 when available, with a LIKE fallback.
"""
import json
import logging

from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import _safe_json_loads, db_write_transaction
from app.core.models import Message


@db_write_transaction
def save_message(conversation_id: str, sender: str, content: dict, streaming: bool = False):
    with Session(_engine_mod.engine) as session:
        msg = Message(
            conversation_id=conversation_id,
            sender=sender,
            content=json.dumps(content, ensure_ascii=False),
            streaming=int(streaming)
        )
        session.add(msg)
        session.commit()


def get_messages(conversation_id: str, limit: int = 100):
    with Session(_engine_mod.engine) as session:
        statement = select(Message).where(
            Message.conversation_id == conversation_id
        ).order_by(Message.id.asc()).limit(limit)
        results = session.exec(statement).all()
        messages = []
        for msg in results:
            try:
                content = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                content = {"text": msg.content}
            messages.append({
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "sender": msg.sender,
                "content": content,
                "streaming": bool(msg.streaming),
                "timestamp": msg.created_at,
            })
        return messages


def search_messages(query: str, conversation_id: str | None = None, limit: int = 50) -> list[dict]:
    """Full-text search across message content using FTS5."""
    try:
        from sqlalchemy import text
        with _engine_mod.engine.connect() as conn:
            if conversation_id:
                sql = text(
                    "SELECT m.id, m.conversation_id, m.sender, m.content, "
                    "m.streaming, m.created_at, rank "
                    "FROM messages m JOIN messages_fts f ON m.id = f.rowid "
                    "WHERE messages_fts MATCH :query "
                    "AND m.conversation_id = :conv_id "
                    "ORDER BY rank LIMIT :lim"
                )
                rows = conn.execute(
                    sql, {"query": query, "conv_id": conversation_id, "lim": limit}
                ).fetchall()
            else:
                sql = text(
                    "SELECT m.id, m.conversation_id, m.sender, m.content, "
                    "m.streaming, m.created_at, rank "
                    "FROM messages m JOIN messages_fts f ON m.id = f.rowid "
                    "WHERE messages_fts MATCH :query "
                    "ORDER BY rank LIMIT :lim"
                )
                rows = conn.execute(sql, {"query": query, "lim": limit}).fetchall()

            return [
                {
                    "id": row[0],
                    "conversation_id": row[1],
                    "sender": row[2],
                    "content": _safe_json_loads(row[3]),
                    "streaming": bool(row[4]),
                    "timestamp": row[5],
                    "rank": row[6],
                }
                for row in rows
            ]
    except Exception as e:
        logging.getLogger("database").warning(
            f"FTS5 search failed, falling back to LIKE: {e}"
        )
        with Session(_engine_mod.engine) as session:
            statement = select(Message)
            if conversation_id:
                statement = statement.where(
                    Message.conversation_id == conversation_id
                )
            statement = statement.where(
                Message.content.contains(query)
            ).limit(limit)
            results = session.exec(statement).all()
            return [
                {
                    "id": msg.id,
                    "conversation_id": msg.conversation_id,
                    "sender": msg.sender,
                    "content": _safe_json_loads(msg.content),
                    "streaming": bool(msg.streaming),
                    "timestamp": msg.created_at,
                }
                for msg in results
            ]


@db_write_transaction
def clear_messages(conversation_id: str):
    with Session(_engine_mod.engine) as session:
        statement = select(Message).where(
            Message.conversation_id == conversation_id
        )
        results = session.exec(statement).all()
        for msg in results:
            session.delete(msg)
        session.commit()
