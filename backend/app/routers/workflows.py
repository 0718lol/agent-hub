from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.async_wrappers import async_delete_memory_item, async_get_project_memory, async_save_memory_item
from app.core.database import (
    async_delete_memory_item_cached,
    async_get_project_memory_cached,
    async_save_memory_item_cached,
    delete_memory_item,
    get_project_memory,
    save_memory_item,
)
from app.core.websocket import manager

router = APIRouter(tags=["workflows"])


class MemoryUpdate(BaseModel):
    key: str
    value: str


@router.get("/sandbox/{conversation_id}/commits")
async def get_sandbox_commits(conversation_id: str):
    """Retrieve visual Git commits history in the dynamic vertical timeline."""
    try:
        from app.core.git_sandbox import get_sandbox_commits_log
        commits = await get_sandbox_commits_log(conversation_id)
        return commits
    except Exception as e:
        return {"error": str(e), "commits": []}


class SandboxRollbackRequest(BaseModel):
    commit_hash: str


@router.post("/sandbox/{conversation_id}/rollback")
async def rollback_sandbox(conversation_id: str, body: SandboxRollbackRequest):
    """Trigger manual Git time-travel rollback for visual sandbox recovery."""
    commit_hash = body.commit_hash
    if not commit_hash:
        return {"status": "error", "message": "Missing commit_hash parameter"}

    try:
        from app.core.git_sandbox import rollback_sandbox_to_commit
        success = await rollback_sandbox_to_commit(conversation_id, commit_hash)
        if success:
            # Broadcast update event to frontend to refresh sandbox explorer and show warning log
            await manager.broadcast(conversation_id, {
                "type": "sandbox_rollback",
                "conversation_id": conversation_id,
                "commit_hash": commit_hash,
                "message": f"🔄 已成功手动回滚至 Git 版本检查点: {commit_hash[:7]}"
            })
            return {"status": "ok", "message": f"Successfully rolled back sandbox to {commit_hash}"}
        return {"status": "error", "message": "Rollback failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/memory/{conversation_id}")
async def get_memory_api(conversation_id: str):
    return await async_get_project_memory_cached(conversation_id)


@router.post("/memory/{conversation_id}")
async def save_memory_api(conversation_id: str, body: MemoryUpdate):
    await async_save_memory_item_cached(conversation_id, body.key, body.value, source="user")

    # Broadcast refreshed memory to the client UI immediately
    fresh_memory = await async_get_project_memory_cached(conversation_id)
    await manager.broadcast(conversation_id, {
        "type": "memory_reflected",
        "conversation_id": conversation_id,
        "memory": fresh_memory
    })
    return {"status": "ok", "memory": fresh_memory}


@router.delete("/memory/{conversation_id}/{key}")
async def delete_memory_api(conversation_id: str, key: str):
    await async_delete_memory_item_cached(conversation_id, key)

    # Broadcast deletion update to client UI
    fresh_memory = await async_get_project_memory_cached(conversation_id)
    await manager.broadcast(conversation_id, {
        "type": "memory_reflected",
        "conversation_id": conversation_id,
        "memory": fresh_memory
    })
    return {"status": "ok", "message": f"Key {key} forgotten successfully."}
