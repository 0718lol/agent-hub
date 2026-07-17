"""
SQLModel table definitions for the AgentHub database.

This module contains ONLY declarative table classes -- no engine, no CRUD, no I/O.
"""
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    id: str = Field(primary_key=True)
    type: str
    name: str
    avatar: str | None = None
    agent_id: str | None = None
    agents: str | None = None
    preview: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    sender: str
    content: str
    streaming: int = Field(default=0)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CustomAgent(SQLModel, table=True):
    __tablename__ = "custom_agents"
    id: str = Field(primary_key=True)
    user_id: str = Field(default="legacy", index=True)
    name: str
    avatar: str = Field(default=chr(129302))
    role: str = Field(default="")
    style: str = Field(default="")
    system_prompt: str
    tools: str = Field(default="[]")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ProjectMemory(SQLModel, table=True):
    __tablename__ = "project_memory"
    __table_args__ = (UniqueConstraint("conversation_id", "key", name="idx_mem_conv_key"),)
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    key: str
    value: str
    source: str = Field(default="system")
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class UploadedFile(SQLModel, table=True):
    __tablename__ = "uploaded_files"
    id: str = Field(primary_key=True)
    original_name: str
    stored_name: str
    file_path: str
    content_type: str = Field(default="")
    size: int = Field(default=0)
    extracted_text: str = Field(default="")
    uploaded_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TenantConfig(SQLModel, table=True):
    __tablename__ = "tenant_configs"
    __table_args__ = (UniqueConstraint("user_id", "key", name="idx_tenant_config_key"),)
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    key: str
    value: str
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CronTask(SQLModel, table=True):
    __tablename__ = "cron_tasks"
    id: str = Field(primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    agent_id: str
    task_prompt: str
    interval_seconds: int
    last_run: str | None = None
    next_run: str | None = None
    status: str = Field(default="active")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class KnowledgeBase(SQLModel, table=True):
    __tablename__ = "knowledge_bases"
    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    name: str
    description: str = Field(default="")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class KnowledgeDoc(SQLModel, table=True):
    __tablename__ = "knowledge_docs"
    id: str = Field(primary_key=True)
    user_id: str = Field(default="legacy", index=True)
    filename: str
    file_path: str = Field(default="")
    content_type: str = Field(default="")
    chunk_count: int = Field(default=0)
    char_count: int = Field(default=0)
    status: str = Field(default="ready")
    knowledge_base_id: str | None = Field(default=None, index=True)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ProjectEventStream(SQLModel, table=True):
    __tablename__ = "project_event_stream"
    id: int | None = Field(default=None, primary_key=True)
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
    status: str = Field(default="pending")
    chosen_action: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    agent_id: str
    name: str
    language: str
    code: str
    quality_score: int | None = Field(default=None)
    sandbox_status: str = Field(default="untested")
    sandbox_output: str | None = Field(default=None)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
