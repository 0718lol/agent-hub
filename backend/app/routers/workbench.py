"""Personal Workbench endpoints: local folder binding, Personal AI OS live bridge, and local model discovery."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

import app.core._engine as engine_mod
from app.core.config import settings
from app.core.crud.conversations import create_conversation, update_conversation
from app.core.mcp_bridge import mcp_bridge_manager
from app.core.models import Conversation, DeliveryRecord
from app.core.runtime_mode import is_workbench_mode, require_workbench_mode
from app.core.tenancy import request_user_id, scope_conversation_id
from app.core.workspace import (
    REPO_ROOT,
    WORKSPACE_ROOT,
    resolve_workspace,
    validate_local_workspace_path,
)
from app.routers.handoff import TaskBrief, build_receipt_sync, import_task_brief_sync

router = APIRouter(tags=["workbench"])

_SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "dist", ".pytest_cache"}


class BindWorkspaceRequest(BaseModel):
    path: str = Field(default="", max_length=1024)
    create: bool = False


class PullPersonalAIProjectRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    personal_ai_os_url: str | None = Field(default=None, max_length=300)
    workspace_path: str | None = Field(default=None, max_length=1024)
    create_workspace: bool = False


class PushReceiptRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    project_id: str | None = Field(default=None, max_length=128)
    personal_ai_os_url: str | None = Field(default=None, max_length=300)


class ConnectPersonalAIMCPRequest(BaseModel):
    personal_ai_os_dir: str | None = Field(default=None, max_length=1024)
    data_dir: str | None = Field(default=None, max_length=1024)


def _detect_personal_ai_os_dir(override: str | None = None) -> Path | None:
    candidates: list[Path] = []
    for raw in (override, settings.personal_ai_os_dir, os.environ.get("PERSONAL_AI_OS_DIR")):
        if raw and raw.strip():
            candidates.append(Path(raw.strip()).expanduser())
    candidates.extend(
        [
            REPO_ROOT.parent / "personal-ai-os",
            Path.home() / "Projects" / "personal-ai-os",
            Path.home() / "personal-ai-os",
        ]
    )
    for cand in candidates:
        try:
            resolved = cand.resolve()
            if (resolved / "mcp_server.py").is_file() and (resolved / "server.py").is_file():
                return resolved
        except OSError:
            continue
    return None


def _read_projects_from_sqlite(paios_dir: Path) -> list[dict[str, Any]]:
    data_dir = Path(os.environ.get("PERSONAL_AI_OS_DATA_DIR", str(paios_dir / "data"))).expanduser()
    db_path = data_dir / "personal_ai_os.sqlite3"
    if not db_path.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, name, description FROM collections ORDER BY updated_at DESC LIMIT 30"
            ).fetchall()
            return [
                {"id": r["id"], "name": r["name"], "goal": r["description"] or ""}
                for r in rows
            ]
        finally:
            conn.close()
    except Exception:
        return []


def _git_summary(folder: Path) -> dict[str, Any]:
    if not folder.is_dir():
        return {"is_git": False, "branch": "", "dirty": False}
    try:
        branch_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(folder),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if branch_res.returncode != 0:
            return {"is_git": False, "branch": "", "dirty": False}
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(folder),
            capture_output=True,
            text=True,
            timeout=3,
        )
        return {
            "is_git": True,
            "branch": branch_res.stdout.strip(),
            "dirty": bool(status_res.stdout.strip()),
        }
    except Exception:
        return {"is_git": False, "branch": "", "dirty": False}


def _inspect_conversation_workspace_sync(scoped_id: str, public_id: str) -> dict[str, Any]:
    bound_path = ""
    source_project_id = ""
    has_handoff = False
    with Session(engine_mod.engine) as session:
        conv = session.get(Conversation, scoped_id)
        if conv:
            bound_path = conv.workspace_path or ""
            source_project_id = conv.source_project_id or ""
        origin = session.get(DeliveryRecord, "handoff:" + scoped_id)
        if origin is not None:
            has_handoff = True

    ws = resolve_workspace(scoped_id, create=False)
    entries: list[dict[str, Any]] = []
    if ws and ws.is_dir():
        raw_items = []
        try:
            for item in ws.iterdir():
                if item.name in _SKIP_DIR_NAMES:
                    continue
                is_dir = item.is_dir()
                raw_items.append(
                    {
                        "name": item.name,
                        "is_dir": is_dir,
                        "size": item.stat().st_size if item.is_file() else 0,
                    }
                )
        except OSError:
            pass
        raw_items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        entries = raw_items[:30]

    git_info = _git_summary(ws) if ws else {"is_git": False, "branch": "", "dirty": False}
    return {
        "conversation_id": public_id,
        "path": str(ws) if ws else "",
        "is_bound": bool(bound_path),
        "bound_path": bound_path,
        "source_project_id": source_project_id,
        "has_handoff": has_handoff,
        "exists": bool(ws and ws.exists()),
        "git": git_info,
        "entries": entries,
    }


def _validated_loopback_paios_url(override: str | None) -> str:
    raw = (override or settings.personal_ai_os_url or "http://127.0.0.1:8000").strip().rstrip("/")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").strip("[]").lower()
    if parsed.scheme not in {"http", "https"} or host not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=400, detail="知序地址仅允许本机回环地址（127.0.0.1 / localhost）")
    return raw


@router.get("/workbench/status")
async def workbench_status(request: Request, personal_ai_os_url: str | None = None):
    require_workbench_mode()
    user_id = request_user_id(request)
    base_url = _validated_loopback_paios_url(personal_ai_os_url)
    paios_dir = _detect_personal_ai_os_dir()

    online = False
    projects: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=1.2, trust_env=False) as client:
            health = await client.get(f"{base_url}/api/health")
            if health.status_code == 200:
                online = True
                proj_resp = await client.get(f"{base_url}/api/projects")
                if proj_resp.status_code == 200 and isinstance(proj_resp.json(), list):
                    projects = [
                        {
                            "id": p.get("id", ""),
                            "name": p.get("name", ""),
                            "goal": p.get("goal") or p.get("description") or "",
                        }
                        for p in proj_resp.json()
                    ]
    except Exception:
        online = False

    if not projects and paios_dir is not None:
        projects = await asyncio.to_thread(_read_projects_from_sqlite, paios_dir)

    mcp_servers = await mcp_bridge_manager.get_servers_status(user_id)
    mcp_connected = any(s["name"] == "personal-ai-os" and s["running"] for s in mcp_servers)

    return {
        "workbench_mode": is_workbench_mode(),
        "host": settings.host,
        "default_workspace_root": str(WORKSPACE_ROOT),
        "home_dir": str(Path.home()),
        "personal_ai_os": {
            "url": base_url,
            "online": online,
            "local_dir": str(paios_dir) if paios_dir else "",
            "mcp_available": bool(paios_dir and (paios_dir / "mcp_server.py").is_file()),
            "mcp_connected": mcp_connected,
            "projects": projects,
        },
    }


@router.get("/conversations/{conversation_id}/workspace")
async def get_conversation_workspace(conversation_id: str, request: Request):
    require_workbench_mode()
    user = request_user_id(request)
    try:
        scoped = scope_conversation_id(user, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(_inspect_conversation_workspace_sync, scoped, conversation_id)


@router.post("/conversations/{conversation_id}/workspace")
async def bind_conversation_workspace(
    conversation_id: str,
    payload: BindWorkspaceRequest,
    request: Request,
):
    require_workbench_mode()
    user = request_user_id(request)
    try:
        scoped = scope_conversation_id(user, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raw = payload.path.strip()
    resolved_str: str | None = None
    if raw:
        try:
            resolved_str = str(validate_local_workspace_path(raw, create=payload.create))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _apply() -> dict[str, Any]:
        create_conversation(scoped, "single", conversation_id, "", "agent_pm")
        updated = update_conversation(scoped, {"workspace_path": resolved_str})
        if not updated:
            raise HTTPException(status_code=404, detail="没有找到这个会话")
        return _inspect_conversation_workspace_sync(scoped, conversation_id)

    return await asyncio.to_thread(_apply)


@router.post("/workbench/personal-ai-os/connect-mcp")
async def connect_personal_ai_os_mcp(payload: ConnectPersonalAIMCPRequest, request: Request):
    require_workbench_mode()
    user = request_user_id(request)
    paios_dir = _detect_personal_ai_os_dir(payload.personal_ai_os_dir)
    if paios_dir is None:
        raise HTTPException(status_code=404, detail="未找到本地 personal-ai-os 仓库目录（可通过参数指定）")
    mcp_script = paios_dir / "mcp_server.py"
    data_dir = (
        Path(payload.data_dir).expanduser().resolve()
        if payload.data_dir and payload.data_dir.strip()
        else (paios_dir / "data").resolve()
    )
    ok = await mcp_bridge_manager.register_server(
        tenant_id=user,
        name="personal-ai-os",
        command=sys.executable,
        args=[str(mcp_script)],
        env={"PERSONAL_AI_OS_DATA_DIR": str(data_dir)},
    )
    if not ok:
        raise HTTPException(status_code=500, detail="启动 personal-ai-os MCP 只读服务失败（请确认其知识库已初始化）")
    return {
        "status": "connected",
        "server": "personal-ai-os",
        "script": str(mcp_script),
        "data_dir": str(data_dir),
    }


@router.post("/workbench/personal-ai-os/pull")
async def pull_project_from_personal_ai_os(payload: PullPersonalAIProjectRequest, request: Request):
    require_workbench_mode()
    user = request_user_id(request)
    base_url = _validated_loopback_paios_url(payload.personal_ai_os_url)
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/api/projects/{payload.project_id}/handoff",
                headers={"Content-Type": "application/json"},
                content=b"{}",
            )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"无法连接本地知序服务 ({base_url})，请先启动 personal-ai-os 或使用任务包 JSON 导入",
        ) from exc

    if resp.status_code != 200:
        detail = resp.json().get("detail", "导出项目任务失败") if resp.headers.get("content-type", "").startswith("application/json") else "导出项目任务失败"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    raw_brief = resp.json()
    brief = TaskBrief(
        **raw_brief,
        workspace_path=payload.workspace_path,
        create_workspace=payload.create_workspace,
    )
    return await asyncio.to_thread(import_task_brief_sync, brief, user)


@router.post("/workbench/personal-ai-os/push-receipt")
async def push_receipt_to_personal_ai_os(payload: PushReceiptRequest, request: Request):
    require_workbench_mode()
    user = request_user_id(request)
    receipt, source_project_id = await asyncio.to_thread(
        build_receipt_sync, user, payload.conversation_id
    )
    target_project = (payload.project_id or source_project_id or "").strip()
    if not target_project:
        raise HTTPException(status_code=400, detail="缺少目标知序项目 ID（project_id）")

    base_url = _validated_loopback_paios_url(payload.personal_ai_os_url)
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/api/projects/{target_project}/receipts",
                json=receipt,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"无法连接本地知序服务 ({base_url})，你可以先点击「下载执行回执 JSON」稍后导入",
        ) from exc

    if resp.status_code != 200:
        detail = resp.json().get("detail", "回执投递失败") if resp.headers.get("content-type", "").startswith("application/json") else "回执投递失败"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return {
        "status": "staged",
        "project_id": target_project,
        "receipt": resp.json(),
    }


@router.get("/workbench/discover-models")
async def discover_local_llm_endpoints():
    """Probe local Ollama, LM Studio, LocalAI, and Jan endpoints on 127.0.0.1 (workbench mode only)."""
    require_workbench_mode()
    candidates = [
        ("ollama", "Ollama", "http://127.0.0.1:11434/v1", "http://127.0.0.1:11434/api/tags", "ollama"),
        ("openai", "LM Studio", "http://127.0.0.1:1234/v1", "http://127.0.0.1:1234/v1/models", "openai"),
        ("openai", "LocalAI", "http://127.0.0.1:8080/v1", "http://127.0.0.1:8080/v1/models", "openai"),
        ("openai", "Jan", "http://127.0.0.1:1337/v1", "http://127.0.0.1:1337/v1/models", "openai"),
    ]
    found: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=0.9, trust_env=False) as client:
        for provider_key, label, base_url, probe_url, fmt in candidates:
            try:
                r = await client.get(probe_url)
                if r.status_code != 200:
                    continue
                data = r.json()
                if fmt == "ollama":
                    models = [m.get("name") for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
                else:
                    models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
                if models:
                    found.append(
                        {
                            "provider": provider_key,
                            "label": label,
                            "base_url": base_url,
                            "model": models[0],
                            "models": models[:15],
                        }
                    )
            except Exception:
                continue
    return {"found": found, "recommended": found[0] if found else None}
