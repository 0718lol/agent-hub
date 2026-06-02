"""
Conversation CRUD operations.

Handles creation and listing of conversations.
"""
import json

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
        statement = select(Conversation).order_by(Conversation.created_at.asc())
        results = session.exec(statement).all()
        result = []
        for row in results:
            conv = row.model_dump()
            if conv["agents"]:
                conv["agents"] = json.loads(conv["agents"])
            result.append(conv)
        return result
