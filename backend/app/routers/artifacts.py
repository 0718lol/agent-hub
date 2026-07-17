"""Tenant-scoped generated artifact endpoints."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.crud.artifacts import get_artifacts_grouped
from app.core.tenancy import request_user_id, scope_conversation_id

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts")
async def list_artifacts(
    request: Request,
    conversation_id: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=15, ge=1, le=100),
):
    """Return version-grouped artifacts belonging to the current tenant."""
    user_id = request_user_id(request)
    scoped_conversation_id = None
    if conversation_id:
        try:
            scoped_conversation_id = scope_conversation_id(user_id, conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return get_artifacts_grouped(
        conversation_id=scoped_conversation_id,
        limit=limit,
        user_id=user_id if scoped_conversation_id is None else None,
    )
