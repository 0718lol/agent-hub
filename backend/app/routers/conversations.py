"""Conversation and message CRUD endpoints."""
import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.async_wrappers import (
    async_clear_messages,
    async_get_conversations,
    async_get_messages,
    async_search_messages,
)
from app.core.database import (
    DEFAULT_CONVERSATION_IDS,
    async_clear_messages_cached,
    async_get_conversations_cached,
    async_get_messages_cached,
    clear_messages,
    create_conversation,
    delete_message,
    get_conversations,
    get_messages,
    reorder_conversations,
    search_messages,
    update_conversation,
    update_message_pin,
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


class ConversationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    pinned: bool | None = None
    archived: bool | None = None


class ConversationReorderRequest(BaseModel):
    ids: list[str] = Field(max_length=500)


class MessagePinRequest(BaseModel):
    pinned: bool


GoalStage = Literal["not_started", "planning", "building", "validating", "ready", "blocked"]


class ConversationGoalUpdateRequest(BaseModel):
    objective: str | None = Field(default=None, max_length=2000)
    stage: GoalStage | None = None
    latest_deliverable: str | None = Field(default=None, max_length=500)
    latest_artifact_id: int | None = Field(default=None, ge=1)
    pending_decision: str | None = Field(default=None, max_length=1000)
    next_action: str | None = Field(default=None, max_length=1000)


def _goal_snapshot(row: dict) -> dict:
    return {
        "objective": row.get("goal_objective"),
        "stage": row.get("goal_stage") or "not_started",
        "latest_deliverable": row.get("goal_latest_deliverable"),
        "latest_artifact_id": row.get("goal_latest_artifact_id"),
        "pending_decision": row.get("goal_pending_decision"),
        "next_action": row.get("goal_next_action"),
    }


async def _tenant_conversations(user_id: str) -> list[dict]:
    all_conversations = await async_get_conversations()
    tenant_rows = [row for row in all_conversations if belongs_to_user(row["id"], user_id)]
    if not tenant_rows:
        templates = [row for row in all_conversations if row["id"] in DEFAULT_CONVERSATION_IDS]
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


@router.patch("/conversations/{conversation_id}")
async def update_conv(conversation_id: str, payload: ConversationUpdateRequest, request: Request):
    updates = payload.model_dump(exclude_none=True)
    updated = await asyncio.to_thread(update_conversation, _scoped_id(request, conversation_id), updates)
    if not updated:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok"}


@router.get("/conversations/{conversation_id}/goal")
async def get_conversation_goal(conversation_id: str, request: Request):
    scoped_id = _scoped_id(request, conversation_id)
    rows = await async_get_conversations()
    row = next((item for item in rows if item["id"] == scoped_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _goal_snapshot(row)


@router.patch("/conversations/{conversation_id}/goal")
async def update_conversation_goal(
    conversation_id: str,
    payload: ConversationGoalUpdateRequest,
    request: Request,
):
    values = payload.model_dump(exclude_unset=True)
    if values.get("stage") is None:
        values.pop("stage", None)
    updates = {f"goal_{key}": value.strip() if isinstance(value, str) else value for key, value in values.items()}
    updated = await asyncio.to_thread(update_conversation, _scoped_id(request, conversation_id), updates)
    if not updated:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = await async_get_conversations()
    row = next((item for item in rows if item["id"] == _scoped_id(request, conversation_id)), updates)
    return {"status": "ok", "goal": _goal_snapshot(row)}


@router.put("/conversations/order")
async def reorder_conv(payload: ConversationReorderRequest, request: Request):
    scoped_ids = [_scoped_id(request, conversation_id) for conversation_id in payload.ids]
    await asyncio.to_thread(reorder_conversations, scoped_ids)
    return {"status": "ok"}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
):
    return await async_get_messages_cached(_scoped_id(request, conversation_id), limit, before_id)


@router.delete("/conversations/{conversation_id}/messages")
async def delete_messages(conversation_id: str, request: Request):
    await async_clear_messages_cached(_scoped_id(request, conversation_id))
    return {"status": "cleared"}


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
async def pin_message(conversation_id: str, message_id: int, payload: MessagePinRequest, request: Request):
    updated = await asyncio.to_thread(
        update_message_pin,
        _scoped_id(request, conversation_id),
        message_id,
        payload.pinned,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="消息不存在")
    return {"status": "ok"}


@router.delete("/conversations/{conversation_id}/messages/{message_id}")
async def remove_message(conversation_id: str, message_id: int, request: Request):
    deleted = await asyncio.to_thread(delete_message, _scoped_id(request, conversation_id), message_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="消息不存在")
    return {"status": "deleted"}


@router.get("/messages/search")
async def search(
    request: Request,
    q: str = Query(..., description="FTS5 search query (supports AND, OR, NOT, *)"),
    conversation_id: str = Query(None, description="Optional filter to specific conversation"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """Full-text search across message content using SQLite FTS5."""
    tenant_id = request_user_id(request)
    scoped = _scoped_id(request, conversation_id) if conversation_id else None
    rows = await async_search_messages(q, conversation_id=scoped, limit=limit, tenant_id=tenant_id)
    return [
        {**row, "conversation_id": public_conversation_id(row["conversation_id"])}
        for row in rows
    ]
