"""Tenant-scoped generated project inspection and version endpoints."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.tenancy import request_user_id, scope_conversation_id
from app.core.workspace import resolve_workspace
from app.services.project_workspace import (
    project_summary,
    read_project_file,
    restore_project_snapshot,
)

router = APIRouter(tags=["projects"])


def _workspace_for_request(request: Request, conversation_id: str):
    try:
        scoped_id = scope_conversation_id(request_user_id(request), conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return resolve_workspace(scoped_id, create=False)


@router.get("/projects/{conversation_id}")
async def get_project(request: Request, conversation_id: str):
    workspace = _workspace_for_request(request, conversation_id)
    if workspace is None or not workspace.is_dir():
        return {"exists": False, "manifest": {}, "files": [], "snapshots": []}
    return await project_summary(workspace)


@router.get("/projects/{conversation_id}/files")
async def get_project_file(
    request: Request,
    conversation_id: str,
    path: str = Query(min_length=1, max_length=240),
):
    workspace = _workspace_for_request(request, conversation_id)
    if workspace is None or not workspace.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return read_project_file(workspace, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{conversation_id}/snapshots/{snapshot_id}/restore")
async def restore_snapshot(request: Request, conversation_id: str, snapshot_id: str):
    workspace = _workspace_for_request(request, conversation_id)
    if workspace is None or not workspace.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    restored = await restore_project_snapshot(workspace, snapshot_id)
    if not restored:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"restored": True, "snapshot_id": snapshot_id}
