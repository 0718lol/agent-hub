"""Tenant-scoped generated project previews and runtime proxies."""

import json
import mimetypes
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.core.redis import redis_manager
from app.core.tenancy import request_user_id, scope_conversation_id
from app.core.workspace import resolve_workspace
from app.services.deployment import DeploymentError, _web_root, detect_project_type
from app.services.deployment_queue import deployment_queue
from app.services.preview_runtime import (
    PreviewRuntimeError,
    preview_runtime_manager,
    validate_runtime_url,
)

router = APIRouter(tags=["previews"])
_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}
_PREVIEW_CSP = (
    "default-src * data: blob:; "
    "script-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
    "style-src * 'unsafe-inline'; "
    "img-src * data: blob:; font-src * data:; "
    "connect-src https: wss:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
)


def _workspace(request: Request, conversation_id: str) -> tuple[str, Path]:
    user_id = request_user_id(request)
    try:
        scoped_id = scope_conversation_id(user_id, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    workspace = resolve_workspace(scoped_id, create=False)
    if workspace is None or not workspace.is_dir():
        raise HTTPException(status_code=404, detail="Generated project not found")
    return scoped_id, workspace


def _project_type(workspace: Path) -> str:
    try:
        return detect_project_type(workspace)
    except DeploymentError:
        manifest = workspace / ".agenthub" / "project.json"
        try:
            return json.loads(manifest.read_text(encoding="utf-8")).get("project_type", "unknown")
        except (OSError, ValueError):
            return "unknown"


async def _live_api(scoped_id: str, user_id: str) -> dict | None:
    try:
        if not await redis_manager.check_connection():
            return None
        job_id = await redis_manager.get_client().get(
            f"agenthub:published:current:{scoped_id}"
        )
        if not job_id:
            return None
        job = await deployment_queue.get(job_id)
        if not job or job.user_id != user_id or job.status != "success":
            return None
        base = f"/published/{job.id}/"
        return {
            "job_id": job.id,
            "base_url": base,
            "docs_url": base + "docs",
            "openapi_url": base + "openapi.json",
        }
    except Exception:
        return None


@router.get("/previews/{conversation_id}")
async def preview_summary(conversation_id: str, request: Request):
    scoped_id, workspace = _workspace(request, conversation_id)
    project_type = _project_type(workspace)
    runtime = preview_runtime_manager.get(scoped_id)
    static_url = ""
    try:
        _web_root(workspace)
        static_url = f"/api/previews/{conversation_id}/files/index.html"
    except DeploymentError:
        pass
    return {
        "project_type": project_type,
        "web": {
            "static_url": static_url,
            "runtime_url": runtime.public_path if runtime else "",
            "runtime_active": bool(runtime),
            "can_start_runtime": (
                preview_runtime_manager.supports_vite(workspace)
                and await preview_runtime_manager.docker_available()
            ),
            "vite_project": preview_runtime_manager.supports_vite(workspace),
        },
        "api": await _live_api(scoped_id, request_user_id(request)),
        "miniprogram": {
            "credential_required": True,
            "preview_supported": project_type == "miniprogram",
        },
        "apk": {
            "browser_preview_supported": False,
            "build_supported": project_type == "apk",
        },
    }


@router.post("/previews/{conversation_id}/runtime")
async def start_preview_runtime(conversation_id: str, request: Request):
    scoped_id, workspace = _workspace(request, conversation_id)
    try:
        runtime = await preview_runtime_manager.start(scoped_id, conversation_id, workspace)
    except PreviewRuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "running", "url": runtime.public_path}


@router.delete("/previews/{conversation_id}/runtime")
async def stop_preview_runtime(conversation_id: str, request: Request):
    scoped_id, _workspace_path = _workspace(request, conversation_id)
    await preview_runtime_manager.stop(scoped_id)
    return {"status": "stopped"}


async def _proxy_runtime(conversation_id: str, path: str, request: Request):
    scoped_id, _workspace_path = _workspace(request, conversation_id)
    runtime = preview_runtime_manager.get(scoped_id)
    if runtime is None or not validate_runtime_url(runtime.runtime_url):
        raise HTTPException(status_code=404, detail="Preview runtime is not running")
    query = f"?{request.url.query}" if request.url.query else ""
    target = f"{runtime.runtime_url}{runtime.public_path}{path}{query}"
    body = await request.body()
    if len(body) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Preview request body exceeds 10 MB")
    client = httpx.AsyncClient(timeout=60.0)
    try:
        upstream = await client.send(
            client.build_request(
                request.method,
                target,
                headers={
                    key: value for key, value in request.headers.items()
                    if key.lower() not in _HOP_HEADERS
                    and key.lower() not in {"host", "cookie", "content-length"}
                },
                content=body,
            ),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="Preview runtime is unavailable") from exc

    async def close_upstream():
        await upstream.aclose()
        await client.aclose()

    headers = {
        key: value for key, value in upstream.headers.items()
        if key.lower() not in _HOP_HEADERS
        and key.lower() not in {"content-length", "set-cookie", "content-security-policy"}
    }
    headers["Content-Security-Policy"] = _PREVIEW_CSP
    headers["Cache-Control"] = "no-store"
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=headers,
        background=BackgroundTask(close_upstream),
    )


@router.api_route(
    "/previews/{conversation_id}/runtime/",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_runtime_root(conversation_id: str, request: Request):
    return await _proxy_runtime(conversation_id, "", request)


@router.api_route(
    "/previews/{conversation_id}/runtime/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_runtime_path(conversation_id: str, path: str, request: Request):
    return await _proxy_runtime(conversation_id, path, request)


def _static_file_response(workspace: Path, conversation_id: str, relative_path: str):
    root = _web_root(workspace).resolve()
    safe_path = relative_path.lstrip("/") or "index.html"
    if any(part.startswith(".") for part in Path(safe_path).parts):
        raise HTTPException(status_code=404, detail="Preview file not found")
    target = (root / safe_path).resolve(strict=False)
    if target != root and root not in target.parents:
        raise HTTPException(status_code=404, detail="Preview file not found")
    if target.is_symlink() or not target.is_file():
        raise HTTPException(status_code=404, detail="Preview file not found")
    if target.stat().st_size > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Preview file is too large")

    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": _PREVIEW_CSP,
    }
    if target.suffix.lower() in {".html", ".htm"}:
        html = target.read_text(encoding="utf-8", errors="replace")
        base = f'<base href="/api/previews/{conversation_id}/files/">'
        if "<head" in html.lower():
            head_end = html.lower().find(">", html.lower().find("<head"))
            html = html[:head_end + 1] + base + html[head_end + 1:]
        else:
            html = base + html
        return HTMLResponse(html, headers=headers)
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type, headers=headers)


@router.get("/previews/{conversation_id}/files/")
async def preview_index(conversation_id: str, request: Request):
    _scoped_id, workspace = _workspace(request, conversation_id)
    return _static_file_response(workspace, conversation_id, "index.html")


@router.get("/previews/{conversation_id}/files/{path:path}")
async def preview_file(conversation_id: str, path: str, request: Request):
    _scoped_id, workspace = _workspace(request, conversation_id)
    return _static_file_response(workspace, conversation_id, path)
