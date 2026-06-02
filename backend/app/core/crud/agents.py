"""
Custom Agent CRUD operations.

Handles creation, listing, and deletion of user-defined agents.
Deletion also cleans up associated conversations and messages.
"""
import json

from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import Conversation, CustomAgent, Message


@db_write_transaction
def save_custom_agent(agent_id: str, name: str, avatar: str, role: str,
                      style: str, system_prompt: str, tools: list[str]):
    with Session(_engine_mod.engine) as session:
        agent = CustomAgent(
            id=agent_id,
            name=name,
            avatar=avatar,
            role=role,
            style=style,
            system_prompt=system_prompt,
            tools=json.dumps(tools, ensure_ascii=False)
        )
        session.merge(agent)
        session.commit()


def get_custom_agents() -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(CustomAgent).order_by(CustomAgent.created_at.asc())
        rows = session.exec(statement).all()
        return [
            {
                "agent_id": row.id,
                "name": row.name,
                "avatar": row.avatar,
                "role": row.role,
                "style": row.style,
                "system_prompt": row.system_prompt,
                "tools": json.loads(row.tools),
                "created_at": row.created_at,
                "custom": True,
            }
            for row in rows
        ]


@db_write_transaction
def delete_custom_agent(agent_id: str):
    with Session(_engine_mod.engine) as session:
        agent = session.get(CustomAgent, agent_id)
        if agent:
            session.delete(agent)
        conv = session.get(Conversation, agent_id)
        if conv:
            session.delete(conv)
        conv_c = session.get(Conversation, f"conv_{agent_id}")
        if conv_c:
            session.delete(conv_c)
        conv_ids = [agent_id, f"conv_{agent_id}"]
        statement = select(Message).where(
            Message.conversation_id.in_(conv_ids)
        )
        results = session.exec(statement).all()
        for msg in results:
            session.delete(msg)
        session.commit()
