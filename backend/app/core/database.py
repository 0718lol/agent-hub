import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Any
from sqlmodel import SQLModel, Field, Session, select, create_engine, UniqueConstraint

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'agenthub.db')

from sqlalchemy import event

# Define SQLModel engine supporting dynamic PostgreSQL cloud backend and local SQLite WAL mode
db_url = os.environ.get("DATABASE_URL")
if db_url:
    # Production cloud deployment (e.g. PostgreSQL)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(db_url)
else:
    # Local SQLite with multi-threading, 30s busy lock timeout, and WAL journal mode
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={
            "check_same_thread": False,
            "timeout": 30.0  # Wait up to 30s for database locks to clear
        }
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.close()
        except Exception:
            pass



# ============================================================
# Declarative SQLModel Database Tables
# ============================================================

class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    id: str = Field(primary_key=True)
    type: str
    name: str
    avatar: Optional[str] = None
    agent_id: Optional[str] = None
    agents: Optional[str] = None  # JSON list string
    preview: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    sender: str
    content: str
    streaming: int = Field(default=0)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CustomAgent(SQLModel, table=True):
    __tablename__ = "custom_agents"
    id: str = Field(primary_key=True)
    name: str
    avatar: str = Field(default='🤖')
    role: str = Field(default='')
    style: str = Field(default='')
    system_prompt: str
    tools: str = Field(default='[]')
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ProjectMemory(SQLModel, table=True):
    __tablename__ = "project_memory"
    __table_args__ = (
        UniqueConstraint("conversation_id", "key", name="idx_mem_conv_key"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    key: str
    value: str
    source: str = Field(default="system")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class UploadedFile(SQLModel, table=True):
    __tablename__ = "uploaded_files"
    id: str = Field(primary_key=True)
    original_name: str
    stored_name: str
    file_path: str
    content_type: str = Field(default='')
    size: int = Field(default=0)
    extracted_text: str = Field(default='')
    uploaded_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CronTask(SQLModel, table=True):
    __tablename__ = "cron_tasks"
    id: str = Field(primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    agent_id: str
    task_prompt: str
    interval_seconds: int
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    status: str = Field(default='active')
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class KnowledgeDoc(SQLModel, table=True):
    __tablename__ = "knowledge_docs"
    id: str = Field(primary_key=True)
    filename: str
    file_path: str = Field(default='')
    content_type: str = Field(default='')
    chunk_count: int = Field(default=0)
    char_count: int = Field(default=0)
    status: str = Field(default='ready')
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ProjectEventStream(SQLModel, table=True):
    __tablename__ = "project_event_stream"
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    event_type: str
    timestamp: float
    data: str


class PendingHil(SQLModel, table=True):
    __tablename__ = "pending_hils"
    conversation_id: str = Field(primary_key=True)
    current_node: str
    next_node: str
    state_data: str
    question: str
    options: str
    original_prompt: str
    status: str = Field(default='pending')
    chosen_action: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    agent_id: str
    name: str
    language: str
    code: str
    quality_score: Optional[int] = Field(default=None)
    sandbox_status: str = Field(default="untested")
    sandbox_output: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ============================================================
# Database Initializers & Base Connection
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
    except Exception:
        pass
    return conn


def init_db():
    _ensure_dir()
    # Configure SQLite direct WAL mode
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.commit()
        conn.close()
    except Exception:
        pass
        
    # Auto-create all tables managed by SQLModel
    SQLModel.metadata.create_all(engine)

    # Populate default conversations using SQLModel Sessions
    with Session(engine) as session:
        default_convs = [
            Conversation(id='conv_pm', type='single', name='PM 小助手', avatar='📋', agent_id='agent_pm', preview='需求分析与任务拆解'),
            Conversation(id='conv_frontend', type='single', name='前端工程师', avatar='🎨', agent_id='agent_frontend', preview='React 组件与样式开发'),
            Conversation(id='conv_backend', type='single', name='后端工程师', avatar='⚙️', agent_id='agent_backend', preview='API 接口与数据模型'),
            Conversation(id='conv_tester', type='single', name='测试工程师', avatar='🧪', agent_id='agent_tester', preview='测试用例与 Bug 分析'),
            Conversation(id='conv_devops', type='single', name='运维工程师', avatar='🚀', agent_id='agent_devops', preview='Docker 部署与 CI/CD'),
            Conversation(id='conv_designer', type='single', name='设计顾问', avatar='🎯', agent_id='agent_designer', preview='UI/UX 设计建议'),
            Conversation(id='conv_builder', type='single', name='Agent 工坊', avatar='🔧', agent_id='agent_builder', preview='对话式创建自定义 Agent'),
            Conversation(id='conv_group_demo', type='group', name='Demo 项目群', avatar='💬', agents=json.dumps(['agent_pm', 'agent_frontend', 'agent_backend', 'agent_tester', 'agent_devops', 'agent_designer']), preview='多 Agent 协作演示'),
        ]
        for conv in default_convs:
            existing = session.get(Conversation, conv.id)
            if not existing:
                session.add(conv)
        session.commit()


# ============================================================
# Type-Safe CRUD Operations
# ============================================================


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


def clear_messages(conversation_id: str):
    with Session(engine) as session:
        statement = select(Message).where(Message.conversation_id == conversation_id)
        results = session.exec(statement).all()
        for msg in results:
            session.delete(msg)
        session.commit()


# ---- Custom Agents CRUD ----

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
            
        statement = select(Message).where(Message.conversation_id == f"conv_{agent_id}")
        results = session.exec(statement).all()
        for msg in results:
            session.delete(msg)
        session.commit()


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


def update_cron_task_run_time(task_id: str, last_run: str, next_run: str, status: str = 'active'):
    with Session(engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            task.last_run = last_run
            task.next_run = next_run
            task.status = status
            session.add(task)
            session.commit()


def update_cron_task_status(task_id: str, status: str):
    with Session(engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            task.status = status
            session.add(task)
            session.commit()


def delete_cron_task(task_id: str):
    with Session(engine) as session:
        task = session.get(CronTask, task_id)
        if task:
            session.delete(task)
            session.commit()


# ---- Knowledge Base Documents CRUD ----

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


def delete_knowledge_doc(doc_id: str):
    with Session(engine) as session:
        doc = session.get(KnowledgeDoc, doc_id)
        if doc:
            session.delete(doc)
            session.commit()


# ---- Project Long-term Memory CRUD ----

def save_memory_item(conversation_id: str, key: str, value: str, source: str = "system"):
    with Session(engine) as session:
        statement = select(ProjectMemory).where(ProjectMemory.conversation_id == conversation_id).where(ProjectMemory.key == key)
        existing = session.exec(statement).first()
        if existing:
            existing.value = value
            existing.source = source
            existing.updated_at = datetime.utcnow().isoformat()
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


def delete_memory_item(conversation_id: str, key: str):
    with Session(engine) as session:
        statement = select(ProjectMemory).where(ProjectMemory.conversation_id == conversation_id).where(ProjectMemory.key == key)
        results = session.exec(statement).all()
        for item in results:
            session.delete(item)
        session.commit()


# ---- Project Event Stream CRUD ----

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


def clear_event_items(conversation_id: str):
    with Session(engine) as session:
        statement = select(ProjectEventStream).where(ProjectEventStream.conversation_id == conversation_id)
        results = session.exec(statement).all()
        for item in results:
            session.delete(item)
        session.commit()

# ---- HIL Checkpoints CRUD ----

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


def resolve_hil_checkpoint(conversation_id: str, chosen_action: str):
    with Session(engine) as session:
        item = session.get(PendingHil, conversation_id)
        if item:
            item.status = 'resolved'
            item.chosen_action = chosen_action
            session.add(item)
            session.commit()


def delete_hil_checkpoint(conversation_id: str):
    with Session(engine) as session:
        item = session.get(PendingHil, conversation_id)
        if item:
            session.delete(item)
            session.commit()

# ---- Artifacts CRUD ----

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


def update_latest_artifact_quality(conversation_id: str, agent_id: str, score: int, sandbox_status: str, sandbox_output: str = None):
    with Session(engine) as session:
        statement = select(Artifact).where(
            Artifact.conversation_id == conversation_id,
            Artifact.agent_id == agent_id,
            Artifact.quality_score == None
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

