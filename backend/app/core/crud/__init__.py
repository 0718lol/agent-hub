"""
Synchronous CRUD operations for the AgentHub database.

This package re-exports all public CRUD functions so that existing
``from app.core.crud import xxx`` imports continue to work unchanged.
"""
# Engine -- must be imported BEFORE sub-modules so that
# ``from app.core.crud import engine`` works and test monkeypatching
# of ``crud_mod.engine`` propagates to every sub-module.
from app.core._engine import DB_PATH, engine  # noqa: F401 -- re-exported

# Custom Agents
from app.core.crud.agents import delete_custom_agent, get_custom_agents, save_custom_agent

# Artifacts
from app.core.crud.artifacts import (
    get_artifacts,
    get_artifacts_grouped,
    save_artifact,
    update_latest_artifact_quality,
)

# Conversations
from app.core.crud.conversations import create_conversation, get_conversations

# Cron Tasks
from app.core.crud.cron import (
    claim_cron_task,
    delete_cron_task,
    get_cron_tasks,
    get_due_cron_tasks,
    recover_running_cron_tasks,
    save_cron_task,
    update_cron_task_run_time,
    update_cron_task_status,
)

# Events, HIL Checkpoints, and Project Memory
from app.core.crud.events import (
    clear_event_items,
    delete_hil_checkpoint,
    delete_memory_item,
    get_event_items,
    get_pending_hil_checkpoint,
    get_pending_hil_checkpoint_fuzzy,
    get_project_memory,
    resolve_hil_checkpoint,
    save_event_item,
    save_hil_checkpoint,
    save_memory_item,
)

# Knowledge Base Documents
from app.core.crud.knowledge import delete_knowledge_doc, get_knowledge_docs, save_knowledge_doc

# Messages
from app.core.crud.messages import clear_messages, get_messages, save_message, search_messages

# Uploaded Files
from app.core.crud.uploads import get_all_uploaded_files, get_uploaded_file, save_uploaded_file

# Utils
from app.core.crud.utils import _MAX_JSON_PARSE_SIZE, _safe_json_loads, db_write_transaction

__all__ = [
    # Engine
    "DB_PATH",
    "engine",
    # Utils
    "_MAX_JSON_PARSE_SIZE",
    "_safe_json_loads",
    "db_write_transaction",
    # Conversations
    "create_conversation",
    "get_conversations",
    # Messages
    "clear_messages",
    "get_messages",
    "save_message",
    "search_messages",
    # Custom Agents
    "delete_custom_agent",
    "get_custom_agents",
    "save_custom_agent",
    # Cron Tasks
    "claim_cron_task",
    "delete_cron_task",
    "get_cron_tasks",
    "get_due_cron_tasks",
    "recover_running_cron_tasks",
    "save_cron_task",
    "update_cron_task_run_time",
    "update_cron_task_status",
    # Knowledge Base Documents
    "delete_knowledge_doc",
    "get_knowledge_docs",
    "save_knowledge_doc",
    # Events, HIL Checkpoints, and Project Memory
    "clear_event_items",
    "delete_hil_checkpoint",
    "delete_memory_item",
    "get_event_items",
    "get_pending_hil_checkpoint",
    "get_pending_hil_checkpoint_fuzzy",
    "get_project_memory",
    "resolve_hil_checkpoint",
    "save_event_item",
    "save_hil_checkpoint",
    "save_memory_item",
    # Artifacts
    "get_artifacts",
    "get_artifacts_grouped",
    "save_artifact",
    "update_latest_artifact_quality",
    # Uploaded Files
    "get_all_uploaded_files",
    "get_uploaded_file",
    "save_uploaded_file",
]
