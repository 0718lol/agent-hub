"""
Artifact CRUD operations.

Handles saving, retrieving, and grouping code artifacts produced by
agents during conversations.
"""
import re
from datetime import UTC, datetime

from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import Artifact, Conversation


@db_write_transaction
def save_artifact(conversation_id: str, agent_id: str, language: str,
                  code: str, name: str | None = None) -> dict:
    if not name:
        if language.lower() in ("python", "py"):
            class_match = re.search(r"class\s+(\w+)", code)
            if class_match:
                name = f"{class_match.group(1)}.py"
            else:
                def_match = re.search(r"def\s+(\w+)", code)
                if def_match:
                    name = f"{def_match.group(1)}()"
                else:
                    name = "script.py"
        elif language.lower() in ("javascript", "js", "typescript", "ts",
                                   "jsx", "tsx"):
            component_match = re.search(
                r"function\s+(\w+)|class\s+(\w+)|const\s+(\w+)\s*=\s*\(\)\s*=>",
                code,
            )
            if component_match:
                name_val = next(
                    g for g in component_match.groups() if g is not None
                )
                name = f"{name_val}.jsx"
            else:
                name = "component.jsx"
        elif language.lower() in ("html", "htm"):
            title_match = re.search(
                r"<title>(.*?)</title>", code, re.IGNORECASE
            )
            if title_match:
                name = f"{title_match.group(1)}.html"
            else:
                name = "index.html"
        else:
            name = f"code_snippet.{language}"

    with Session(_engine_mod.engine) as session:
        art = Artifact(
            conversation_id=conversation_id,
            agent_id=agent_id,
            name=name,
            language=language,
            code=code
        )
        session.add(art)
        session.commit()
        session.refresh(art)
        artifact_data = art.model_dump()
        conversation = session.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.goal_latest_deliverable = art.name
            conversation.goal_latest_artifact_id = art.id
            conversation.goal_stage = "validating"
            conversation.goal_next_action = "审阅并验证最新产物"
            conversation.updated_at = datetime.now(UTC).isoformat()
            session.add(conversation)
            session.commit()
        return artifact_data


def get_artifacts(conversation_id: str | None = None,
                  limit: int = 50) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        if conversation_id:
            statement = select(Artifact).where(
                Artifact.conversation_id == conversation_id
            ).order_by(Artifact.created_at.desc()).limit(limit)
        else:
            statement = select(Artifact).order_by(
                Artifact.created_at.desc()
            ).limit(limit)
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def update_latest_artifact_quality(conversation_id: str, agent_id: str,
                                    score: int | None, sandbox_status: str,
                                    sandbox_output: str | None = None):
    with Session(_engine_mod.engine) as session:
        statement = select(Artifact).where(
            Artifact.conversation_id == conversation_id,
            Artifact.agent_id == agent_id,
            Artifact.quality_score.is_(None),
            Artifact.sandbox_status == "untested",
        )
        results = session.exec(statement).all()
        for art in results:
            art.quality_score = score
            art.sandbox_status = sandbox_status
            art.sandbox_output = sandbox_output
            session.add(art)
        session.commit()


def get_artifacts_grouped(
    conversation_id: str | None = None,
    limit: int = 50,
    user_id: str | None = None,
) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        if conversation_id:
            statement = select(Artifact).where(
                Artifact.conversation_id == conversation_id
            ).order_by(Artifact.created_at.asc())
        elif user_id:
            prefix = f"tenant__{user_id}__conv__"
            statement = select(Artifact).where(
                Artifact.conversation_id.startswith(prefix)
            ).order_by(Artifact.created_at.asc())
        else:
            statement = select(Artifact).order_by(Artifact.created_at.asc())
        rows = session.exec(statement).all()

    grouped = {}
    for row in rows:
        key = (row.conversation_id, row.name)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(row.model_dump())

    result = []
    for (conv_id, name), versions in grouped.items():
        latest = versions[-1]
        history = []
        for idx, v in enumerate(versions):
            v_num = f"v{idx + 1}"
            history.append({
                "version_label": v_num,
                "id": v["id"],
                "agent_id": v["agent_id"],
                "created_at": v["created_at"],
                "code": v["code"],
                "quality_score": v["quality_score"],
                "sandbox_status": v["sandbox_status"],
                "sandbox_output": v["sandbox_output"],
            })

        result.append({
            "name": name,
            "conversation_id": conv_id,
            "agent_id": latest["agent_id"],
            "language": latest["language"],
            "code": latest["code"],
            "quality_score": latest["quality_score"],
            "sandbox_status": latest["sandbox_status"],
            "sandbox_output": latest["sandbox_output"],
            "created_at": latest["created_at"],
            "latest_id": latest["id"],
            "total_versions": len(versions),
            "history": history[::-1],
        })

    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result[:limit]
