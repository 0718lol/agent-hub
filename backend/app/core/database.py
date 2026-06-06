"""
Database engine, connection setup, and schema initialization.

This is the public entry-point for all database symbols.  It re-exports
everything from :mod:`models`, :mod:`crud`, and :mod:`async_wrappers`
so that ``from app.core.database import X`` continues to work unchanged.
"""
import json
import logging as _logging
import os
import sqlite3

from sqlalchemy import text

_db_logger = _logging.getLogger("database")
from sqlmodel import Session, SQLModel, select

# Engine is defined in _engine.py to break the circular dependency
# between database.py and crud.py.
from app.core._engine import DB_PATH, engine
from app.core.crud import *  # noqa: F403 -- brings in db_write_transaction

# ============================================================
# Re-export all public symbols for backward compatibility
# ============================================================
from app.core.models import *  # noqa: F403

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

    # 先确保所有表存在，再执行后续查询
    SQLModel.metadata.create_all(engine)

    try:
        from alembic import command
        from alembic.config import Config
        alembic_cfg = Config(
            os.path.join(os.path.dirname(__file__), '..', '..', 'alembic.ini')
        )
        if not os.environ.get('DATABASE_URL'):
            alembic_cfg.set_main_option('sqlalchemy.url', f'sqlite:///{DB_PATH}')
        command.upgrade(alembic_cfg, 'head')
    except Exception:
        pass

    # 增量迁移：给 knowledge_docs 表添加 knowledge_base_id 列（如果不存在）
    try:
        conn = sqlite3.connect(DB_PATH)
        cols = [row[1] for row in conn.execute('PRAGMA table_info(knowledge_docs)').fetchall()]
        if 'knowledge_base_id' not in cols:
            conn.execute('ALTER TABLE knowledge_docs ADD COLUMN knowledge_base_id TEXT')
            conn.commit()
        conn.close()
    except Exception:
        pass

    # Populate default conversations using SQLModel Sessions
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
        statement = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id.asc()).limit(limit)
        results = session.exec(statement).all()
        return [
            {
                'id': msg.id,
                'conversation_id': msg.conversation_id,
                'sender': msg.sender,
                'content': json.loads(msg.content),
                'streaming': bool(msg.streaming),
                'timestamp': msg.created_at,
            }
            for msg in results
        ]


def get_conversations():
    with Session(engine) as session:
        statement = select(Conversation).order_by(Conversation.created_at.asc())
        results = session.exec(statement).all()
        result = []
        for row in results:
            conv = row.model_dump()
            if conv['agents']:
                conv['agents'] = json.loads(conv['agents'])
            result.append(conv)
        return result



def search_messages(query: str, conversation_id: str = None, limit: int = 50) -> list[dict]:
    """Full-text search across message content using FTS5.

    Args:
        query: Search query string (supports FTS5 syntax: AND, OR, NOT, *)
        conversation_id: Optional filter to specific conversation
        limit: Maximum results to return

    Returns:
        List of message dicts matching the query, ranked by relevance.
    """
    try:
        with engine.connect() as conn:
            if conversation_id:
                sql = text(
                    "SELECT m.id, m.conversation_id, m.sender, m.content, m.streaming, m.created_at, "
                    "rank FROM messages m JOIN messages_fts f ON m.id = f.rowid "
                    "WHERE messages_fts MATCH :query AND m.conversation_id = :conv_id "
                    "ORDER BY rank LIMIT :lim"
                )
                rows = conn.execute(sql, {"query": query, "conv_id": conversation_id, "lim": limit}).fetchall()
            else:
                sql = text(
                    "SELECT m.id, m.conversation_id, m.sender, m.content, m.streaming, m.created_at, "
                    "rank FROM messages m JOIN messages_fts f ON m.id = f.rowid "
                    "WHERE messages_fts MATCH :query "
                    "ORDER BY rank LIMIT :lim"
                )
                rows = conn.execute(sql, {"query": query, "lim": limit}).fetchall()

            return [
                {
                    "id": row[0],
                    "conversation_id": row[1],
                    "sender": row[2],
                    "content": json.loads(row[3]),
                    "streaming": bool(row[4]),
                    "timestamp": row[5],
                    "rank": row[6],
                }
                for row in rows
            ]
    except Exception as e:
        import logging as _logging
        _logging.getLogger("database").warning(f"FTS5 search failed, falling back to LIKE: {e}")
        # Fallback: simple LIKE search if FTS5 not available
        with Session(engine) as session:
            statement = select(Message)
            if conversation_id:
                statement = statement.where(Message.conversation_id == conversation_id)
            statement = statement.where(Message.content.contains(query)).limit(limit)
            results = session.exec(statement).all()
            return [
                {
                    "id": msg.id,
                    "conversation_id": msg.conversation_id,
                    "sender": msg.sender,
                    "content": json.loads(msg.content),
                    "streaming": bool(msg.streaming),
                    "timestamp": msg.created_at,
                }
                for msg in results
            ]


@db_write_transaction
def clear_messages(conversation_id: str):
    with Session(engine) as session:
        statement = select(Message).where(Message.conversation_id == conversation_id)
        results = session.exec(statement).all()
        for msg in results:
            session.delete(msg)
        session.commit()


# ---- Custom Agents CRUD ----

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
                'agent_id': row.id,
                'name': row.name,
                'avatar': row.avatar,
                'role': row.role,
                'style': row.style,
                'system_prompt': row.system_prompt,
                'tools': json.loads(row.tools),
                'created_at': row.created_at,
                'custom': True,
            }
            for row in rows
        ]


@db_write_transaction
def delete_custom_agent(agent_id: str):
    with Session(engine) as session:
        agent = session.get(CustomAgent, agent_id)
        if agent:
            session.delete(agent)
        # 删除关联会话（两种 ID 格式都尝试）
        conv = session.get(Conversation, agent_id)
        if conv:
            session.delete(conv)
        conv_c = session.get(Conversation, f"conv_{agent_id}")
        if conv_c:
            session.delete(conv_c)
        # 删除关联消息（两种会话 ID 格式都覆盖）
        conv_ids = [agent_id, f"conv_{agent_id}"]
        statement = select(Message).where(Message.conversation_id.in_(conv_ids))
        results = session.exec(statement).all()
        for msg in results:
            session.delete(msg)
        session.commit()


@db_write_transaction
def create_conversation(conv_id: str, conv_type: str, name: str, avatar: str,
                        agent_id: str = None, agents: list[str] = None, preview: str = ''):
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


# ---- Uploaded Files CRUD ----

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
        statement = select(UploadedFile).order_by(UploadedFile.uploaded_at.desc())
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


# ---- Offline Cron Tasks CRUD ----

@db_write_transaction
def save_cron_task(task_id: str, conversation_id: str, agent_id: str, task_prompt: str,
                   interval_seconds: int, status: str = 'active', last_run: str = None, next_run: str = None):
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


def get_cron_tasks(conversation_id: str = None) -> list[dict]:
    with Session(engine) as session:
        if conversation_id:
            statement = select(CronTask).where(CronTask.conversation_id == conversation_id).order_by(CronTask.created_at.desc())
        else:
            statement = select(CronTask).order_by(CronTask.created_at.desc())
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


def get_due_cron_tasks(now_str: str) -> list[dict]:
    with Session(engine) as session:
        statement = select(CronTask).where(CronTask.status == 'active').where(CronTask.next_run <= now_str)
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def update_cron_task_run_time(task_id: str, last_run: str, next_run: str, status: str = 'active'):
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


# ---- Knowledge Base Documents CRUD ----

@db_write_transaction
def save_knowledge_doc(doc_id: str, filename: str, file_path: str = '',
                       content_type: str = '', chunk_count: int = 0, char_count: int = 0):
    with Session(engine) as session:
        doc = KnowledgeDoc(
            id=doc_id,
            filename=filename,
            file_path=file_path,
            content_type=content_type,
            chunk_count=chunk_count,
            char_count=char_count,
            status='ready'
        )
        session.merge(doc)
        session.commit()


def get_knowledge_docs() -> list[dict]:
    with Session(engine) as session:
        statement = select(KnowledgeDoc).order_by(KnowledgeDoc.created_at.desc())
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def delete_knowledge_doc(doc_id: str):
    with Session(engine) as session:
        doc = session.get(KnowledgeDoc, doc_id)
        if doc:
            session.delete(doc)
            session.commit()


# ---- Project Long-term Memory CRUD ----

@db_write_transaction
def save_memory_item(conversation_id: str, key: str, value: str, source: str = "system"):
    with Session(engine) as session:
        statement = select(ProjectMemory).where(ProjectMemory.conversation_id == conversation_id).where(ProjectMemory.key == key)
        existing = session.exec(statement).first()
        if existing:
            existing.value = value
            existing.source = source
            existing.updated_at = datetime.now(timezone.utc).isoformat()
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
        statement = select(ProjectMemory).where(ProjectMemory.conversation_id == conversation_id)
        results = session.exec(statement).all()
        return {
            row.key: {
                'value': row.value,
                'source': row.source,
                'updated_at': row.updated_at
            }
            for row in results
        }


@db_write_transaction
def delete_memory_item(conversation_id: str, key: str):
    with Session(engine) as session:
        statement = select(ProjectMemory).where(ProjectMemory.conversation_id == conversation_id).where(ProjectMemory.key == key)
        results = session.exec(statement).all()
        for item in results:
            session.delete(item)
        session.commit()


# ---- Project Event Stream CRUD ----

@db_write_transaction
def save_event_item(conversation_id: str, event_type: str, timestamp: float, data_str: str):
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
        statement = select(ProjectEventStream).where(ProjectEventStream.conversation_id == conversation_id).order_by(ProjectEventStream.timestamp.asc())
        results = session.exec(statement).all()
        return [
            {
                'event_type': row.event_type,
                'timestamp': row.timestamp,
                'data': row.data
            }
            for row in results
        ]


@db_write_transaction
def clear_event_items(conversation_id: str):
    with Session(engine) as session:
        statement = select(ProjectEventStream).where(ProjectEventStream.conversation_id == conversation_id)
        results = session.exec(statement).all()
        for item in results:
            session.delete(item)
        session.commit()

# ---- HIL Checkpoints CRUD ----

@db_write_transaction
def save_hil_checkpoint(conversation_id: str, current_node: str, next_node: str,
                        state_data: dict, question: str, options: list, original_prompt: str):
    with Session(engine) as session:
        # Defensively serialize GraphState/Pydantic models if passed
        state_data_dict = state_data.model_dump() if hasattr(state_data, "model_dump") else state_data
        item = PendingHil(
            conversation_id=conversation_id,
            current_node=current_node,
            next_node=next_node,
            state_data=json.dumps(state_data_dict, ensure_ascii=False),
            question=question,
            options=json.dumps(options, ensure_ascii=False),
            original_prompt=original_prompt,
            status='pending'
        )
        session.merge(item)
        session.commit()


def get_pending_hil_checkpoint(conversation_id: str) -> dict | None:
    with Session(engine) as session:
        statement = select(PendingHil).where(PendingHil.conversation_id == conversation_id).where(PendingHil.status == 'pending')
        row = session.exec(statement).first()
        if row is None:
            return None
        res = row.model_dump()
        try:
            res['state_data'] = json.loads(res['state_data'])
        except Exception:
            pass
        try:
            res['options'] = json.loads(res['options'])
        except Exception:
            pass
        return res


def get_pending_hil_checkpoint_fuzzy(conv_prefix: str) -> dict | None:
    with Session(engine) as session:
        statement = select(PendingHil).where(PendingHil.conversation_id.like(f"{conv_prefix}%")).where(PendingHil.status == 'pending')
        row = session.exec(statement).first()
        if row is None:
            return None
        res = row.model_dump()
        try:
            res['state_data'] = json.loads(res['state_data'])
        except Exception:
            pass
        try:
            res['options'] = json.loads(res['options'])
        except Exception:
            pass
        return res


@db_write_transaction
def resolve_hil_checkpoint(conversation_id: str, chosen_action: str):
    with Session(engine) as session:
        item = session.get(PendingHil, conversation_id)
        if item:
            item.status = 'resolved'
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

# ---- Artifacts CRUD ----

@db_write_transaction
def save_artifact(conversation_id: str, agent_id: str, language: str, code: str, name: str = None) -> dict:
    import re
    if not name:
        # Smart dynamic name generation based on language & content
        if language.lower() in ("python", "py"):
            class_match = re.search(r'class\s+(\w+)', code)
            if class_match:
                name = f"{class_match.group(1)}.py"
            else:
                def_match = re.search(r'def\s+(\w+)', code)
                if def_match:
                    name = f"{def_match.group(1)}()"
                else:
                    name = "script.py"
        elif language.lower() in ("javascript", "js", "typescript", "ts", "jsx", "tsx"):
            component_match = re.search(r'function\s+(\w+)|class\s+(\w+)|const\s+(\w+)\s*=\s*\(\)\s*=>', code)
            if component_match:
                name_val = next(g for g in component_match.groups() if g is not None)
                name = f"{name_val}.jsx"
            else:
                name = "component.jsx"
        elif language.lower() in ("html", "htm"):
            title_match = re.search(r'<title>(.*?)</title>', code, re.IGNORECASE)
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


def get_artifacts(conversation_id: str = None, limit: int = 50) -> list[dict]:
    with Session(engine) as session:
        if conversation_id:
            statement = select(Artifact).where(Artifact.conversation_id == conversation_id).order_by(Artifact.created_at.desc()).limit(limit)
        else:
            statement = select(Artifact).order_by(Artifact.created_at.desc()).limit(limit)
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def update_latest_artifact_quality(conversation_id: str, agent_id: str, score: int, sandbox_status: str, sandbox_output: str = None):
    with Session(engine) as session:
        statement = select(Artifact).where(
            Artifact.conversation_id == conversation_id,
            Artifact.agent_id == agent_id,
            Artifact.quality_score.is_(None)
        )
        results = session.exec(statement).all()
        for art in results:
            art.quality_score = score
            art.sandbox_status = sandbox_status
            art.sandbox_output = sandbox_output
            session.add(art)
        session.commit()


def get_artifacts_grouped(conversation_id: str = None, limit: int = 50) -> list[dict]:
    with Session(engine) as session:
        if conversation_id:
            statement = select(Artifact).where(Artifact.conversation_id == conversation_id).order_by(Artifact.created_at.asc())
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
                "sandbox_output": v["sandbox_output"]
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
            "history": history[::-1]  # latest version first
        })
        
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result[:limit]



# ============================================================
# Async Wrappers - Run sync DB operations in thread pool
# to avoid blocking the asyncio event loop
# ============================================================

import asyncio


async def async_save_message(conversation_id, sender, content, streaming=False):
    return await asyncio.to_thread(save_message, conversation_id, sender, content, streaming)

async def async_get_messages(conversation_id, limit=100):
    return await asyncio.to_thread(get_messages, conversation_id, limit)

async def async_get_conversations():
    return await asyncio.to_thread(get_conversations)

async def async_clear_messages(conversation_id):
    return await asyncio.to_thread(clear_messages, conversation_id)

async def async_save_custom_agent(agent_id, name, avatar, role, style, system_prompt, tools):
    return await asyncio.to_thread(save_custom_agent, agent_id, name, avatar, role, style, system_prompt, tools)

async def async_get_custom_agents():
    return await asyncio.to_thread(get_custom_agents)

async def async_delete_custom_agent(agent_id):
    return await asyncio.to_thread(delete_custom_agent, agent_id)

async def async_create_conversation(conv_id, conv_type, name, avatar, agent_id=None, agents=None, preview=''):
    return await asyncio.to_thread(create_conversation, conv_id, conv_type, name, avatar, agent_id, agents, preview)

async def async_save_uploaded_file(file_id, original_name, stored_name, file_path, content_type="", size=0, extracted_text=""):
    return await asyncio.to_thread(save_uploaded_file, file_id, original_name, stored_name, file_path, content_type, size, extracted_text)

async def async_get_uploaded_file(file_id):
    return await asyncio.to_thread(get_uploaded_file, file_id)

async def async_save_cron_task(task_id, conversation_id, agent_id, task_prompt, interval_seconds, status='active', last_run=None, next_run=None):
    return await asyncio.to_thread(save_cron_task, task_id, conversation_id, agent_id, task_prompt, interval_seconds, status, last_run, next_run)

async def async_get_cron_tasks(conversation_id=None):
    return await asyncio.to_thread(get_cron_tasks, conversation_id)

async def async_get_due_cron_tasks(now_str):
    return await asyncio.to_thread(get_due_cron_tasks, now_str)

async def async_update_cron_task_run_time(task_id, last_run, next_run, status='active'):
    return await asyncio.to_thread(update_cron_task_run_time, task_id, last_run, next_run, status)

async def async_update_cron_task_status(task_id, status):
    return await asyncio.to_thread(update_cron_task_status, task_id, status)

async def async_delete_cron_task(task_id):
    return await asyncio.to_thread(delete_cron_task, task_id)

async def async_save_memory(conversation_id, key, value, source="system"):
    return await asyncio.to_thread(save_memory, conversation_id, key, value, source)

async def async_get_memory(conversation_id, key):
    return await asyncio.to_thread(get_memory, conversation_id, key)

async def async_get_all_memory(conversation_id):
    return await asyncio.to_thread(get_all_memory, conversation_id)

async def async_save_event(conversation_id, event_type, data):
    return await asyncio.to_thread(save_event, conversation_id, event_type, data)

async def async_get_events(conversation_id, event_type=None, limit=100):
    return await asyncio.to_thread(get_events, conversation_id, event_type, limit)

async def async_save_pending_hil(conversation_id, current_node, next_node, state_data, question, options, original_prompt):
    return await asyncio.to_thread(save_pending_hil, conversation_id, current_node, next_node, state_data, question, options, original_prompt)

async def async_get_pending_hil_checkpoint(conversation_id):
    return await asyncio.to_thread(get_pending_hil_checkpoint, conversation_id)

async def async_clear_pending_hil(conversation_id):
    return await asyncio.to_thread(clear_pending_hil, conversation_id)

async def async_save_artifact(conversation_id, agent_id, name, language, code, quality_score=None, sandbox_status="untested", sandbox_output=None):
    return await asyncio.to_thread(save_artifact, conversation_id, agent_id, name, language, code, quality_score, sandbox_status, sandbox_output)

async def async_get_artifacts(conversation_id, limit=50):
    return await asyncio.to_thread(get_artifacts, conversation_id, limit)


# ============================================================
# Redis 缓存层 — Cache-Aside 读取 + Write-Through 失效
# ============================================================

def _invalidate_cache(pattern: str):
    """后台异步清除缓存，不阻塞调用方。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_async_invalidate_cache(pattern))
    except RuntimeError:
        pass  # 无事件循环时跳过（如测试环境）


async def _async_invalidate_cache(pattern: str):
    """实际执行缓存清除。"""
    try:
        from app.core.cache import cache
        if "*" in pattern:
            await cache.delete_pattern(pattern)
        else:
            await cache.delete(pattern)
    except Exception:
        pass  # 缓存失效失败不影响主流程


async def async_save_message_cached(conversation_id, sender, content, streaming=False):
    """带缓存失效的 save_message。写入 DB 后清除消息缓存。"""
    result = await asyncio.to_thread(save_message, conversation_id, sender, content, streaming)
    await _async_invalidate_cache(f"msg:{conversation_id}:*")
    return result


async def async_get_messages_cached(conversation_id, limit=100):
    """带 Redis 缓存的 get_messages。Cache-Aside 模式：先查缓存，miss 则查 DB 并回填。"""
    from app.core.cache import cache
    cache_key = f"msg:{conversation_id}:{limit}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(get_messages, conversation_id, limit)
    if result:  # 非空才缓存，避免缓存空列表
        await cache.set_json(cache_key, result, ttl=30)
    return result


async def async_get_conversations_cached():
    """带 Redis 缓存的 get_conversations。Cache-Aside 模式。"""
    from app.core.cache import cache
    cache_key = "conv:list"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(get_conversations)
    if result:
        await cache.set_json(cache_key, result, ttl=60)
    return result


async def async_clear_messages_cached(conversation_id):
    """带缓存失效的 clear_messages。"""
    result = await asyncio.to_thread(clear_messages, conversation_id)
    await _async_invalidate_cache(f"msg:{conversation_id}:*")
    return result


async def async_create_conversation_cached(conv_id, conv_type, name, avatar, agent_id=None, agents=None, preview=''):
    """带缓存失效的 create_conversation。"""
    result = await asyncio.to_thread(create_conversation, conv_id, conv_type, name, avatar, agent_id, agents, preview)
    await _async_invalidate_cache("conv:list")
    return result


async def async_delete_custom_agent_cached(agent_id):
    """带缓存失效的 delete_custom_agent。"""
    result = await asyncio.to_thread(delete_custom_agent, agent_id)
    await _async_invalidate_cache("conv:list")
    return result


async def async_get_project_memory_cached(conversation_id):
    """带 Redis 缓存的 get_project_memory。Cache-Aside 模式。"""
    from app.core.cache import cache
    cache_key = f"mem:{conversation_id}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(get_project_memory, conversation_id)
    if result:
        await cache.set_json(cache_key, result, ttl=60)
    return result


async def async_save_memory_item_cached(conversation_id, key, value, source="system"):
    """带缓存失效的 save_memory_item。"""
    result = await asyncio.to_thread(save_memory_item, conversation_id, key, value, source)
    await _async_invalidate_cache(f"mem:{conversation_id}")
    return result


async def async_delete_memory_item_cached(conversation_id, key):
    """带缓存失效的 delete_memory_item。"""
    result = await asyncio.to_thread(delete_memory_item, conversation_id, key)
    await _async_invalidate_cache(f"mem:{conversation_id}")
    return result
