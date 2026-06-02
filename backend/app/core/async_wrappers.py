"""
Async wrappers for all synchronous CRUD operations.

Each wrapper delegates to the corresponding sync function via
``asyncio.to_thread`` so the asyncio event loop is never blocked.
"""
import asyncio

from app.core.crud import (
    save_message,
    get_messages,
    get_conversations,
    clear_messages,
    save_custom_agent,
    get_custom_agents,
    delete_custom_agent,
    create_conversation,
    save_uploaded_file,
    get_uploaded_file,
    save_cron_task,
    get_cron_tasks,
    get_due_cron_tasks,
    update_cron_task_run_time,
    update_cron_task_status,
    delete_cron_task,
    save_memory_item,
    get_project_memory,
    delete_memory_item,
    search_messages,
    save_event_item,
    get_event_items,
    save_hil_checkpoint,
    get_pending_hil_checkpoint,
    delete_hil_checkpoint,
    save_artifact,
    get_artifacts,
)


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


async def async_create_conversation(conv_id, conv_type, name, avatar, agent_id=None, agents=None, preview=""):
    return await asyncio.to_thread(create_conversation, conv_id, conv_type, name, avatar, agent_id, agents, preview)


async def async_save_uploaded_file(file_id, original_name, stored_name, file_path, content_type="", size=0, extracted_text=""):
    return await asyncio.to_thread(save_uploaded_file, file_id, original_name, stored_name, file_path, content_type, size, extracted_text)


async def async_get_uploaded_file(file_id):
    return await asyncio.to_thread(get_uploaded_file, file_id)


async def async_save_cron_task(task_id, conversation_id, agent_id, task_prompt, interval_seconds, status="active", last_run=None, next_run=None):
    return await asyncio.to_thread(save_cron_task, task_id, conversation_id, agent_id, task_prompt, interval_seconds, status, last_run, next_run)


async def async_get_cron_tasks(conversation_id=None):
    return await asyncio.to_thread(get_cron_tasks, conversation_id)


async def async_get_due_cron_tasks(now_str):
    return await asyncio.to_thread(get_due_cron_tasks, now_str)


async def async_update_cron_task_run_time(task_id, last_run, next_run, status="active"):
    return await asyncio.to_thread(update_cron_task_run_time, task_id, last_run, next_run, status)


async def async_update_cron_task_status(task_id, status):
    return await asyncio.to_thread(update_cron_task_status, task_id, status)


async def async_delete_cron_task(task_id):
    return await asyncio.to_thread(delete_cron_task, task_id)


async def async_save_memory_item(conversation_id, key, value, source="system"):
    return await asyncio.to_thread(save_memory_item, conversation_id, key, value, source)


async def async_get_project_memory(conversation_id):
    return await asyncio.to_thread(get_project_memory, conversation_id)


async def async_delete_memory_item(conversation_id, key):
    return await asyncio.to_thread(delete_memory_item, conversation_id, key)


async def async_search_messages(query: str, conversation_id: str = None, limit: int = 50):
    return await asyncio.to_thread(search_messages, query, conversation_id, limit)


async def async_save_event(conversation_id, event_type, timestamp, data):
    return await asyncio.to_thread(save_event_item, conversation_id, event_type, timestamp, data)


async def async_get_events(conversation_id):
    return await asyncio.to_thread(get_event_items, conversation_id)


async def async_save_pending_hil(conversation_id, current_node, next_node, state_data, question, options, original_prompt):
    return await asyncio.to_thread(save_hil_checkpoint, conversation_id, current_node, next_node, state_data, question, options, original_prompt)


async def async_get_pending_hil_checkpoint(conversation_id):
    return await asyncio.to_thread(get_pending_hil_checkpoint, conversation_id)


async def async_clear_pending_hil(conversation_id):
    return await asyncio.to_thread(delete_hil_checkpoint, conversation_id)


async def async_save_artifact(conversation_id, agent_id, language, code, name=None):
    return await asyncio.to_thread(save_artifact, conversation_id, agent_id, language, code, name)


async def async_get_artifacts(conversation_id, limit=50):
    return await asyncio.to_thread(get_artifacts, conversation_id, limit)

