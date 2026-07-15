"""Conversation and message CRUD endpoints."""
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.async_wrappers import (
    async_clear_messages,
    async_get_conversations,
    async_get_messages,
    async_search_messages,
)
from app.core.database import (
    async_clear_messages_cached,
    async_get_conversations_cached,
    async_get_messages_cached,
    clear_messages,
    create_conversation,
    get_conversations,
    get_messages,
    search_messages,
)
from app.core.tenancy import belongs_to_user, public_conversation_id, request_user_id, scope_conversation_id

router = APIRouter(tags=["conversations"])


class ConversationCreateRequest(BaseModel):
    id: str
    type: str = "single"
    name: str
    avatar: Optional[str] = None
    agent_id: Optional[str] = None
    agents: Optional[list[str]] = None
    preview: str = ""


async def _tenant_conversations(user_id: str) -> list[dict]:
    all_conversations = await async_get_conversations()
    tenant_rows = [row for row in all_conversations if belongs_to_user(row["id"], user_id)]
    if not tenant_rows:
        templates = [row for row in all_conversations if not row["id"].startswith("tenant__")]
        for template in templates:
            await asyncio.to_thread(
                create_conversation,
                scope_conversation_id(user_id, template["id"]),
                template["type"],
                template["name"],
                template.get("avatar") or "",
                template.get("agent_id"),
                template.get("agents"),
                template.get("preview") or "",
            )
        all_conversations = await async_get_conversations()
        tenant_rows = [row for row in all_conversations if belongs_to_user(row["id"], user_id)]
    return [{**row, "id": public_conversation_id(row["id"])} for row in tenant_rows]


def _scoped_id(request: Request, conversation_id: str) -> str:
    try:
        return scope_conversation_id(request_user_id(request), conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/conversations")
async def list_conversations(request: Request):
    return await _tenant_conversations(request_user_id(request))


@router.post("/conversations")
async def create_conv(req: ConversationCreateRequest, request: Request):
    """创建新对话。"""
    create_conversation(
        conv_id=_scoped_id(request, req.id),
        conv_type=req.type,
        name=req.name,
        avatar=req.avatar or '',
        agent_id=req.agent_id,
        agents=req.agents,
        preview=req.preview,
    )
    return {"status": "created", "id": req.id}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request, limit: int = 100):
    return await async_get_messages_cached(_scoped_id(request, conversation_id), limit)


@router.delete("/conversations/{conversation_id}/messages")
async def delete_messages(conversation_id: str, request: Request):
    await async_clear_messages_cached(_scoped_id(request, conversation_id))
    return {"status": "cleared"}


@router.get("/messages/search")
async def search(
    request: Request,
    q: str = Query(..., description="FTS5 search query (supports AND, OR, NOT, *)"),
    conversation_id: str = Query(None, description="Optional filter to specific conversation"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """Full-text search across message content using SQLite FTS5."""
    scoped = _scoped_id(request, conversation_id) if conversation_id else None
    return await async_search_messages(q, conversation_id=scoped, limit=limit)
