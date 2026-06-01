"""Conversation and message CRUD endpoints."""
from fastapi import APIRouter, Query
from app.core.database import (
    get_messages, get_conversations, clear_messages, search_messages,
    async_get_messages_cached, async_get_conversations_cached, async_clear_messages_cached,
)

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations():
    return await async_get_conversations_cached()


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, limit: int = 100):
    return await async_get_messages_cached(conversation_id, limit)


@router.delete("/conversations/{conversation_id}/messages")
async def delete_messages(conversation_id: str):
    await async_clear_messages_cached(conversation_id)
    return {"status": "cleared"}


@router.get("/messages/search")
async def search(
    q: str = Query(..., description="FTS5 search query (supports AND, OR, NOT, *)"),
    conversation_id: str = Query(None, description="Optional filter to specific conversation"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """Full-text search across message content using SQLite FTS5."""
    return search_messages(q, conversation_id=conversation_id, limit=limit)
