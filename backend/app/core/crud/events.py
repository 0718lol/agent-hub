"""
Event Stream, HIL Checkpoint, and Project Memory CRUD operations.

Handles project-level event logging, human-in-the-loop checkpoint
management, and long-term conversation memory.
"""
import json
import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import PendingHil, ProjectEventStream, ProjectMemory

_crud_logger = logging.getLogger("crud")


# ============================================================
# Project Event Stream CRUD
# ============================================================

@db_write_transaction
def save_event_item(conversation_id: str, event_type: str,
                    timestamp: float, data_str: str):
    with Session(_engine_mod.engine) as session:
        item = ProjectEventStream(
            conversation_id=conversation_id,
            event_type=event_type,
            timestamp=timestamp,
            data=data_str
        )
        session.add(item)
        session.commit()


def get_event_items(conversation_id: str) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(ProjectEventStream).where(
            ProjectEventStream.conversation_id == conversation_id
        ).order_by(ProjectEventStream.timestamp.asc())
        results = session.exec(statement).all()
        return [
            {
                "event_type": row.event_type,
                "timestamp": row.timestamp,
                "data": row.data,
            }
            for row in results
        ]


@db_write_transaction
def clear_event_items(conversation_id: str):
    with Session(_engine_mod.engine) as session:
        statement = select(ProjectEventStream).where(
            ProjectEventStream.conversation_id == conversation_id
        )
        results = session.exec(statement).all()
        for item in results:
            session.delete(item)
        session.commit()


# ============================================================
# HIL Checkpoints CRUD
# ============================================================

@db_write_transaction
def save_hil_checkpoint(conversation_id: str, current_node: str,
                        next_node: str, state_data: dict, question: str,
                        options: list, original_prompt: str):
    with Session(_engine_mod.engine) as session:
        state_data_dict = (
            state_data.model_dump()
            if hasattr(state_data, "model_dump")
            else state_data
        )
        item = PendingHil(
            conversation_id=conversation_id,
            current_node=current_node,
            next_node=next_node,
            state_data=json.dumps(state_data_dict, ensure_ascii=False),
            question=question,
            options=json.dumps(options, ensure_ascii=False),
            original_prompt=original_prompt,
            status="pending"
        )
        session.merge(item)
        session.commit()


def get_pending_hil_checkpoint(conversation_id: str) -> dict | None:
    with Session(_engine_mod.engine) as session:
        statement = select(PendingHil).where(
            PendingHil.conversation_id == conversation_id
        ).where(PendingHil.status == "pending")
        row = session.exec(statement).first()
        if row is None:
            return None
        res = row.model_dump()
        try:
            res["state_data"] = json.loads(res["state_data"])
        except Exception as e:
            _crud_logger.debug(f"state_data JSON parse failed, keeping raw string: {e}")
        try:
            res["options"] = json.loads(res["options"])
        except Exception as e:
            _crud_logger.debug(f"options JSON parse failed, keeping raw string: {e}")
        return res


def get_pending_hil_checkpoint_fuzzy(conv_prefix: str) -> dict | None:
    with Session(_engine_mod.engine) as session:
        statement = select(PendingHil).where(
            PendingHil.conversation_id.like(f"{conv_prefix}%")
        ).where(PendingHil.status == "pending")
        row = session.exec(statement).first()
        if row is None:
            return None
        res = row.model_dump()
        try:
            res["state_data"] = json.loads(res["state_data"])
        except Exception as e:
            _crud_logger.debug(f"state_data JSON parse failed (fuzzy), keeping raw string: {e}")
        try:
            res["options"] = json.loads(res["options"])
        except Exception as e:
            _crud_logger.debug(f"options JSON parse failed (fuzzy), keeping raw string: {e}")
        return res


@db_write_transaction
def resolve_hil_checkpoint(conversation_id: str, chosen_action: str):
    with Session(_engine_mod.engine) as session:
        item = session.get(PendingHil, conversation_id)
        if item:
            item.status = "resolved"
            item.chosen_action = chosen_action
            session.add(item)
            session.commit()


@db_write_transaction
def delete_hil_checkpoint(conversation_id: str):
    with Session(_engine_mod.engine) as session:
        item = session.get(PendingHil, conversation_id)
        if item:
            session.delete(item)
            session.commit()


# ============================================================
# Project Long-term Memory CRUD
# ============================================================

@db_write_transaction
def save_memory_item(conversation_id: str, key: str, value: str, source: str = "system"):
    with Session(_engine_mod.engine) as session:
        statement = select(ProjectMemory).where(
            ProjectMemory.conversation_id == conversation_id
        ).where(ProjectMemory.key == key)
        existing = session.exec(statement).first()
        if existing:
            existing.value = value
            existing.source = source
            existing.updated_at = datetime.now(UTC).isoformat()
            session.add(existing)
        else:
            item = ProjectMemory(
                conversation_id=conversation_id,
                key=key,
                value=value,
                source=source
            )
            session.add(item)
        session.commit()


def get_project_memory(conversation_id: str) -> dict:
    with Session(_engine_mod.engine) as session:
        statement = select(ProjectMemory).where(
            ProjectMemory.conversation_id == conversation_id
        )
        results = session.exec(statement).all()
        return {
            row.key: {
                "value": row.value,
                "source": row.source,
                "updated_at": row.updated_at,
            }
            for row in results
        }


@db_write_transaction
def delete_memory_item(conversation_id: str, key: str):
    with Session(_engine_mod.engine) as session:
        statement = select(ProjectMemory).where(
            ProjectMemory.conversation_id == conversation_id
        ).where(ProjectMemory.key == key)
        results = session.exec(statement).all()
        for item in results:
            session.delete(item)
        session.commit()
