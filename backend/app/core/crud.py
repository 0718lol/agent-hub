"""
Synchronous CRUD operations for the AgentHub database.

All database read/write operations live here. They depend on ``engine``
imported from :mod:`app.core.database` (which must be defined before this
module is first imported).
"""
import json
import logging
import re

_crud_logger = logging.getLogger("crud")
import functools
import threading
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core._engine import engine
from app.core.models import (
    Artifact,
    Conversation,
    CronTask,
    CustomAgent,
    KnowledgeDoc,
    Message,
    PendingHil,
    ProjectEventStream,
    ProjectMemory,
    UploadedFile,
)

# ============================================================
# Helpers
# ============================================================

_MAX_JSON_PARSE_SIZE = 1_000_000  # 1MB -- skip parsing for oversized payloads


def _safe_json_loads(s):
    """Parse JSON with size guard and graceful fallback."""
    if isinstance(s, str) and len(s) > _MAX_JSON_PARSE_SIZE:
        return {"text": s, "_warning": "payload_too_large_skipped"}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {"text": s}


# Global reentrant write lock to serialize all SQLite database writes
_db_write_lock = threading.RLock()


def db_write_transaction(func):
    """
    Decorator to serialize all SQLite database write operations across
    threads/coroutines, ensuring thread-safety and zero database locked
    conflicts.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _db_write_lock:
            return func(*args, **kwargs)
    return wrapper


# ============================================================
# Messages CRUD
# ============================================================

@db_write_transaction
def save_message(conversation_id: str, sender: str, content: dict, streaming: bool = False):
    with Session(engine) as session:
        msg = Message(
            conversation_id=conversation_id,
            sender=sender,
            content=json.dumps(content, ensure_ascii=False),
            streaming=int(streaming)
        )
        session.add(msg)
        session.commit()


def get_messages(conversation_id: str, limit: int = 100):
    with Session(engine) as session:
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


def get_conversations():
    with Session(engine) as session:
        statement = select(Conversation).order_by(Conversation.created_at.asc())
        results = session.exec(statement).all()
        result = []
        for row in results:
            conv = row.model_dump()
            if conv["agents"]:
                conv["agents"] = json.loads(conv["agents"])
            result.append(conv)
        return result


def search_messages(query: str, conversation_id: str | None = None, limit: int = 50) -> list[dict]:
    """Full-text search across message content using FTS5."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
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
        with Session(engine) as session:
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
    with Session(engine) as session:
        statement = select(Message).where(
            Message.conversation_id == conversation_id
        )
        results = session.exec(statement).all()
        for msg in results:
            session.delete(msg)
        session.commit()


# ============================================================
# Custom Agents CRUD
# ============================================================

@db_write_transaction
def save_custom_agent(agent_id: str, name: str, avatar: str, role: str,
                      style: str, system_prompt: str, tools: list[str]):
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
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


@db_write_transaction
def create_conversation(conv_id: str, conv_type: str, name: str, avatar: str,
                        agent_id: str | None = None, agents: list[str] | None = None, preview: str = ""):
    with Session(engine) as session:
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


# ============================================================
# Uploaded Files CRUD
# ============================================================

@db_write_transaction
def save_uploaded_file(file_id: str, original_name: str, stored_name: str,
                       file_path: str, content_type: str = "", size: int = 0,
                       extracted_text: str = ""):
    with Session(engine) as session:
        file = UploadedFile(
            id=file_id,
            original_name=original_name,
            stored_name=stored_name,
            file_path=file_path,
            content_type=content_type,
            size=size,
            extracted_text=extracted_text
        )
        session.merge(file)
        session.commit()


def get_uploaded_file(file_id: str) -> dict | None:
    with Session(engine) as session:
        file = session.get(UploadedFile, file_id)
        return file.model_dump() if file else None


def get_all_uploaded_files() -> list[dict]:
    with Session(engine) as session:
        statement = select(UploadedFile).order_by(
            UploadedFile.uploaded_at.desc()
        )
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


# ============================================================
# Cron Tasks CRUD
# ============================================================

@db_write_transaction
def save_cron_task(task_id: str, conversation_id: str, agent_id: str,
                   task_prompt: str, interval_seconds: int,
                   status: str = "active", last_run: str | None = None,
                   next_run: str | None = None):
    with Session(engine) as session:
        task = CronTask(
            id=task_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            task_prompt=task_prompt,
            interval_seconds=interval_seconds,
            status=status,
            last_run=last_run,
            next_run=next_run
        )
        session.merge(task)
        session.commit()


def get_cron_tasks(conversation_id: str | None = None) -> list[dict]:
    with Session(engine) as session:
        if conversation_id:
            statement = select(CronTask).where(
                CronTask.conversation_id == conversation_id
            ).order_by(CronTask.created_at.desc())
        else:
            statement = select(CronTask).order_by(CronTask.created_at.desc())
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


def get_due_cron_tasks(now_str: str) -> list[dict]:
    with Session(engine) as session:
        statement = select(CronTask).where(
            CronTask.status == "active"
        ).where(CronTask.next_run <= now_str)
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def update_cron_task_run_time(task_id: str, last_run: str, next_run: str, status: str = "active"):
    with Session(engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            task.last_run = last_run
            task.next_run = next_run
            task.status = status
            session.add(task)
            session.commit()


@db_write_transaction
def update_cron_task_status(task_id: str, status: str):
    with Session(engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            task.status = status
            session.add(task)
            session.commit()


@db_write_transaction
def delete_cron_task(task_id: str):
    with Session(engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            session.delete(task)
            session.commit()


# ============================================================
# Knowledge Base Documents CRUD
# ============================================================

@db_write_transaction
def save_knowledge_doc(doc_id: str, filename: str, file_path: str = "",
                       content_type: str = "", chunk_count: int = 0,
                       char_count: int = 0):
    with Session(engine) as session:
        doc = KnowledgeDoc(
            id=doc_id,
            filename=filename,
            file_path=file_path,
            content_type=content_type,
            chunk_count=chunk_count,
            char_count=char_count,
            status="ready"
        )
        session.merge(doc)
        session.commit()


def get_knowledge_docs() -> list[dict]:
    with Session(engine) as session:
        statement = select(KnowledgeDoc).order_by(
            KnowledgeDoc.created_at.desc()
        )
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def delete_knowledge_doc(doc_id: str):
    with Session(engine) as session:
        doc = session.get(KnowledgeDoc, doc_id)
        if doc:
            session.delete(doc)
            session.commit()


# ============================================================
# Project Long-term Memory CRUD
# ============================================================

@db_write_transaction
def save_memory_item(conversation_id: str, key: str, value: str, source: str = "system"):
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
        statement = select(ProjectMemory).where(
            ProjectMemory.conversation_id == conversation_id
        ).where(ProjectMemory.key == key)
        results = session.exec(statement).all()
        for item in results:
            session.delete(item)
        session.commit()


# ============================================================
# Project Event Stream CRUD
# ============================================================

@db_write_transaction
def save_event_item(conversation_id: str, event_type: str,
                    timestamp: float, data_str: str):
    with Session(engine) as session:
        item = ProjectEventStream(
            conversation_id=conversation_id,
            event_type=event_type,
            timestamp=timestamp,
            data=data_str
        )
        session.add(item)
        session.commit()


def get_event_items(conversation_id: str) -> list[dict]:
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
        item = session.get(PendingHil, conversation_id)
        if item:
            item.status = "resolved"
            item.chosen_action = chosen_action
            session.add(item)
            session.commit()


@db_write_transaction
def delete_hil_checkpoint(conversation_id: str):
    with Session(engine) as session:
        item = session.get(PendingHil, conversation_id)
        if item:
            session.delete(item)
            session.commit()


# ============================================================
# Artifacts CRUD
# ============================================================

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

    with Session(engine) as session:
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
        return art.model_dump()


def get_artifacts(conversation_id: str | None = None,
                  limit: int = 50) -> list[dict]:
    with Session(engine) as session:
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
                                    score: int, sandbox_status: str,
                                    sandbox_output: str | None = None):
    with Session(engine) as session:
        statement = select(Artifact).where(
            Artifact.conversation_id == conversation_id,
            Artifact.agent_id == agent_id,
            Artifact.quality_score is None,
        )
        results = session.exec(statement).all()
        for art in results:
            art.quality_score = score
            art.sandbox_status = sandbox_status
            art.sandbox_output = sandbox_output
            session.add(art)
        session.commit()


def get_artifacts_grouped(conversation_id: str | None = None,
                          limit: int = 50) -> list[dict]:
    with Session(engine) as session:
        if conversation_id:
            statement = select(Artifact).where(
                Artifact.conversation_id == conversation_id
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

