"""
Conversation CRUD operations.

Handles creation and listing of conversations.
"""
import json
from datetime import UTC, datetime

from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import Conversation


@db_write_transaction
def create_conversation(conv_id: str, conv_type: str, name: str, avatar: str,
                        agent_id: str | None = None, agents: list[str] | None = None, preview: str = ""):
    with Session(_engine_mod.engine) as session:
        existing = session.get(Conversation, conv_id)
        if not existing:
            conv = Conversation(
                id=conv_id,
                type=conv_type,
                name=name,
                avatar=avatar,
                agent_id=agent_id,
                agents=json.dumps(agents, ensure_ascii=False) if agents else None,
                preview=preview
            )
            session.add(conv)
            session.commit()


def get_conversations():
    with Session(_engine_mod.engine) as session:
        statement = select(Conversation).order_by(
            Conversation.pinned.desc(),
            Conversation.sort_order.asc(),
            Conversation.updated_at.desc(),
        )
        results = session.exec(statement).all()
        result = []
        for row in results:
            conv = row.model_dump()
            if conv["agents"]:
                conv["agents"] = json.loads(conv["agents"])
            result.append(conv)
        return result


@db_write_transaction
def update_conversation(conversation_id: str, updates: dict) -> bool:
    allowed = {"name", "pinned", "archived", "sort_order"}
    with Session(_engine_mod.engine) as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return False
        for key, value in updates.items():
            if key in allowed:
                setattr(conversation, key, value)
        conversation.updated_at = datetime.now(UTC).isoformat()
        session.add(conversation)
        session.commit()
        return True


@db_write_transaction
def reorder_conversations(conversation_ids: list[str]) -> None:
    with Session(_engine_mod.engine) as session:
        for index, conversation_id in enumerate(conversation_ids):
            conversation = session.get(Conversation, conversation_id)
            if conversation is not None:
                conversation.sort_order = index
                session.add(conversation)
        session.commit()
