"""
SQLModel table definitions for the AgentHub database.

This module contains ONLY declarative table classes -- no engine, no CRUD, no I/O.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, UniqueConstraint


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    id: str = Field(primary_key=True)
    type: str
    name: str
    avatar: Optional[str] = None
    agent_id: Optional[str] = None
    agents: Optional[str] = None
    preview: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    sender: str
    content: str
    streaming: int = Field(default=0)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CustomAgent(SQLModel, table=True):
    __tablename__ = "custom_agents"
    id: str = Field(primary_key=True)
    name: str
    avatar: str = Field(default=chr(129302))
    role: str = Field(default="")
    style: str = Field(default="")
    system_prompt: str
    tools: str = Field(default="[]")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProjectMemory(SQLModel, table=True):
    __tablename__ = "project_memory"
    __table_args__ = (UniqueConstraint("conversation_id", "key", name="idx_mem_conv_key"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    key: str
    value: str
    source: str = Field(default="system")
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class UploadedFile(SQLModel, table=True):
    __tablename__ = "uploaded_files"
    id: str = Field(primary_key=True)
    original_name: str
    stored_name: str
    file_path: str
    content_type: str = Field(default="")
    size: int = Field(default=0)
    extracted_text: str = Field(default="")
    uploaded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CronTask(SQLModel, table=True):
    __tablename__ = "cron_tasks"
    id: str = Field(primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    agent_id: str
    task_prompt: str
    interval_seconds: int
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    status: str = Field(default="active")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class KnowledgeDoc(SQLModel, table=True):
    __tablename__ = "knowledge_docs"
    id: str = Field(primary_key=True)
    filename: str
    file_path: str = Field(default="")
    content_type: str = Field(default="")
    chunk_count: int = Field(default=0)
    char_count: int = Field(default=0)
    status: str = Field(default="ready")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
    status: str = Field(default="pending")
    chosen_action: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
