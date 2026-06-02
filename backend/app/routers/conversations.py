"""Conversation and message CRUD endpoints."""
from fastapi import APIRouter, Query
from fastapi import Query

from app.core.async_wrappers import (
    async_clear_messages,
    async_get_conversations,
    async_get_messages,
    async_search_messages,
)

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations():
    return await async_get_conversations()


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, limit: int = Query(default=100, ge=1, le=500)):
    return await async_get_messages(conversation_id, limit)


@router.delete("/conversations/{conversation_id}/messages")
async def delete_messages(conversation_id: str):
    await async_clear_messages(conversation_id)
    return {"status": "cleared"}


@router.get("/messages/search")
async def search(
    q: str = Query(..., description="FTS5 search query (supports AND, OR, NOT, *)"),
    conversation_id: str = Query(None, description="Optional filter to specific conversation"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """Full-text search across message content using SQLite FTS5."""
    return await async_search_messages(q, conversation_id=conversation_id, limit=limit)
