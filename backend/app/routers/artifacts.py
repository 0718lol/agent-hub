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


from pydantic import BaseModel, Field

from app.core.crud.artifacts import get_artifact, record_artifact_validation, save_artifact


class ArtifactEdit(BaseModel):
    code: str = Field(max_length=1_000_000)


@router.get("/artifacts/{artifact_id}")
async def read_artifact(artifact_id: int, request: Request):
    artifact = get_artifact(artifact_id, request_user_id(request))
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.post("/artifacts/{artifact_id}/versions", status_code=201)
async def edit_artifact(artifact_id: int, payload: ArtifactEdit, request: Request):
    source = await read_artifact(artifact_id, request)
    return save_artifact(
        source["conversation_id"],
        source["agent_id"],
        source["language"],
        payload.code,
        source["name"],
        parent_id=artifact_id,
    )


@router.post("/artifacts/{artifact_id}/validate")
async def validate_artifact(artifact_id: int, request: Request):
    from app.core.sandbox import execute_code

    artifact = await read_artifact(artifact_id, request)
    language = artifact["language"].lower()
    if language not in {"python", "py", "javascript", "js"}:
        raise HTTPException(
            status_code=422, detail="当前支持在隔离沙箱中运行 Python 和 JavaScript；HTML 请使用预览检查。"
        )
    result = await execute_code(
        artifact["code"], "python" if language in {"python", "py"} else "javascript", timeout=10
    )
    # Infrastructure errors remain errors; a missing sandbox never counts as passing.
    return record_artifact_validation(
        artifact_id, request_user_id(request), result.status, result.stdout + "\n" + result.stderr
    )
