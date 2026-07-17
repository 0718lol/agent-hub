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
                      style: str, system_prompt: str, tools: list[str],
                      user_id: str = "legacy"):
    with Session(_engine_mod.engine) as session:
        agent = session.get(CustomAgent, agent_id)
        if agent and agent.user_id != user_id:
            raise PermissionError("Custom agent belongs to another tenant")
        if agent is None:
            agent = CustomAgent(id=agent_id, user_id=user_id, name=name, system_prompt=system_prompt)
        agent.name = name
        agent.avatar = avatar
        agent.role = role
        agent.style = style
        agent.system_prompt = system_prompt
        agent.tools = json.dumps(tools, ensure_ascii=False)
        session.add(agent)
        session.commit()


def get_custom_agents(user_id: str | None = None) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(CustomAgent).order_by(CustomAgent.created_at.asc())
        if user_id is not None:
            statement = statement.where(CustomAgent.user_id == user_id)
        rows = session.exec(statement).all()
        return [
            {
                "agent_id": row.id,
                "user_id": row.user_id,
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
def delete_custom_agent(agent_id: str, user_id: str | None = None) -> bool:
    with Session(_engine_mod.engine) as session:
        statement = select(CustomAgent).where(CustomAgent.id == agent_id)
        if user_id is not None:
            statement = statement.where(CustomAgent.user_id == user_id)
        agent = session.exec(statement).first()
        if agent is None:
            return False
        session.delete(agent)

        public_conv_ids = [agent_id, f"conv_{agent_id}"]
        conv_ids = list(public_conv_ids)
        if user_id and user_id != "legacy":
            from app.core.tenancy import scope_conversation_id
            conv_ids = [scope_conversation_id(user_id, conv_id) for conv_id in public_conv_ids]
        for conv_id in conv_ids:
            conv = session.get(Conversation, conv_id)
            if conv:
                session.delete(conv)
        statement = select(Message).where(
            Message.conversation_id.in_(conv_ids)
        )
        results = session.exec(statement).all()
        for msg in results:
            session.delete(msg)
        session.commit()
        return True
