"""AgentHub API — FastAPI application factory.

This module is responsible for:
- App initialization, lifespan, and middleware
- Mounting all API routers
- Root & health endpoints
- Deploy simulation (no dedicated router)

Business logic is delegated to focused router modules and services:
- routers/settings.py — LLM & HIL configuration
- routers/webhook.py — Slack & Telegram callbacks
- routers/conversations.py — Conversation & message CRUD
- routers/quality.py — Quality gate settings & evaluation
- routers/prompt.py — Prompt engine configuration
- routers/speech.py — STT settings & transcription
- routers/sandbox.py — Code sandbox execution
- routers/benchmark.py — Benchmark execution
- routers/agents.py — Agent management
- routers/uploads.py — File uploads
- routers/cron.py — Cron task management
- routers/workflows.py — Workflow import/export/compile
- routers/mcp.py — MCP tools
- routers/ws.py — WebSocket real-time communication
- routers/tools.py — Tool listing & testing
"""
import asyncio
import json
import re
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from starlette.background import BackgroundTask

from app.core.config import settings
from app.core.config_persistence import load_llm_config, save_llm_config
from app.core.database import init_db
from app.core.llm_client import llm_client
from app.core.logging_config import RequestIdMiddleware, get_logger, setup_logging
from app.routers import (
    adapters as adapters_router,
)
from app.routers import (
    agents as agents_router,
)
from app.routers import (
    artifacts as artifacts_router,
)
from app.routers import (
    auth as auth_router,
)
from app.routers import (
    benchmark as benchmark_router,
)
from app.routers import (
    conversations as conversations_router,
)
from app.routers import (
    cron as cron_router,
)
from app.routers import (
    knowledge as knowledge_router,
)
from app.routers import (
    mcp as mcp_router,
)
from app.routers import (
    metrics as metrics_router,
)
from app.routers import (
    previews as previews_router,
)
from app.routers import (
    projects as projects_router,
)
from app.routers import (
    prompt as prompt_router,
)
from app.routers import (
    quality as quality_router,
)
from app.routers import (
    sandbox as sandbox_router,
)
from app.routers import (
    settings as settings_router,
)
from app.routers import (
    speech as speech_router,
)
from app.routers import (
    system as system_router,
)
from app.routers import (
    tools as tools_router,
)
from app.routers import (
    uploads as uploads_router,
)
from app.routers import (
    webhook as webhook_router,
)
from app.routers import (
    workflows as workflows_router,
)
from app.routers import (
    ws as ws_router,
)
from app.services.agent_orchestrator import get_agents

logger = get_logger("main")

# Trigger runtime tool auto-registration
import app.tools  # noqa: F401


# ---- App lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.daemon_scheduler import daemon_scheduler

    if settings.auto_migrate:
        await asyncio.to_thread(init_db)
    # Container deployments run migrations and seed defaults in the one-shot
    # migration service before any API replica starts.

    # Recovery is performed only after the scheduler owns the distributed
    # leader lease. Running it in every API replica can duplicate active jobs.
    daemon_scheduler.start()
    yield
    try:
        from app.services.daemon_scheduler import daemon_scheduler
        await daemon_scheduler.stop()
    except Exception as e:
        logger.warning(f"Failed to stop daemon scheduler during shutdown: {e}")
    try:
        from app.core.terminal import stateful_terminal_manager
        from app.services.preview_runtime import preview_runtime_manager
        from app.tools.browser_tools import browser_session_manager
        await browser_session_manager.close_all()
        await stateful_terminal_manager.close_all()
        await preview_runtime_manager.stop_all()
    except Exception as e:
        logger.warning(f"Failed to close browser/terminal sessions during shutdown: {e}")


app = FastAPI(title="AgentHub API", lifespan=lifespan)
settings.validate_production_security()

# ---- CORS ----
setup_logging()

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- API security middleware ----
@app.middleware("http")
async def api_security_middleware(request: Request, call_next):
    path = request.url.path
    if path in ("/", "/docs", "/openapi.json", "/redoc", "/api/health") or path.startswith("/api/auth/") or path.startswith("/api/webhook/callback/"):
        return await call_next(request)
    if not (
        path.startswith("/api")
        or path.startswith("/uploads")
        or path == "/upload"
    ):
        return await call_next(request)
    auth_required = bool(settings.api_secret or settings.api_client_tokens_json) or settings.auth_mode == "proxy"
    if auth_required:
        from app.core.auth import (
            SESSION_COOKIE,
            bearer_client_identity,
            get_session_identity,
            trusted_proxy_identity,
            trusted_proxy_role,
            verify_session_token,
        )
        proxy_identity = trusted_proxy_identity(request.headers)
        bearer_identity = bearer_client_identity(request.headers)
        session_valid = bool(settings.api_secret) and verify_session_token(
            request.cookies.get(SESSION_COOKIE), settings.api_secret
        )
        session_identity = (
            get_session_identity(request.cookies.get(SESSION_COOKIE), settings.api_secret)
            if settings.api_secret
            else None
        )
        if not proxy_identity and not bearer_identity and not session_valid:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized: Sign in or provide a valid bearer token"})
        request.state.auth_user_id = proxy_identity or bearer_identity or session_identity
        request.state.auth_role = trusted_proxy_role(request.headers) if proxy_identity else "user"
        if request.state.auth_role == "viewer" and request.method not in {"GET", "HEAD", "OPTIONS"}:
            return JSONResponse(status_code=403, content={"detail": "Viewer role is read-only"})
    # No secret means authentication is deliberately disabled. Docker/Nginx
    # proxy requests originate from the proxy container, not localhost.
    return await call_next(request)


# ---- Agent registry ----
from app.services.agent_registry import agent_registry

AGENTS = get_agents()

# ---- Mount all routers ----
app.include_router(auth_router.router, prefix="/api")
app.include_router(agents_router.router, prefix="/api")
app.include_router(artifacts_router.router, prefix="/api")
app.include_router(uploads_router.router, prefix="/api")
app.include_router(uploads_router.router)
app.include_router(settings_router.router, prefix="/api")
app.include_router(cron_router.router, prefix="/api")
app.include_router(workflows_router.router, prefix="/api")
app.include_router(mcp_router.router, prefix="/api")
app.include_router(webhook_router.router, prefix="/api")
app.include_router(conversations_router.router, prefix="/api")
app.include_router(projects_router.router, prefix="/api")
app.include_router(previews_router.router, prefix="/api")
app.include_router(quality_router.router, prefix="/api")
app.include_router(prompt_router.router, prefix="/api")
app.include_router(speech_router.router, prefix="/api")
app.include_router(system_router.router, prefix="/api")
app.include_router(sandbox_router.router, prefix="/api")
app.include_router(benchmark_router.router, prefix="/api")
app.include_router(ws_router.router)
app.include_router(tools_router.router, prefix="/api")
app.include_router(knowledge_router.router, prefix="/api")
app.include_router(adapters_router.router, prefix="/api")
app.include_router(metrics_router.router, prefix="/api")

# ---- Load LLM config at startup ----
load_llm_config(llm_client, settings)

# ---- Load saved adapters and register as agents ----
from app.adapters.adapter_agent import AdapterAgent
from app.adapters.registry import adapter_registry as _ar
from app.routers.adapters import ADAPTER_CLASSES, create_adapter, load_saved_adapters

load_saved_adapters()

# 预注册默认外部 Agent 适配器（即使未配置 API Key 也注册，前端靠它判断配置状态）
_DEFAULT_ADAPTERS = {
    "claude_code": {"adapter_type": "claude", "name": "Claude Code", "avatar": "/avatars/claude-code.svg"},
    "codex": {"adapter_type": "codex", "name": "Codex", "avatar": "/avatars/codex.svg"},
    "coze": {"adapter_type": "coze", "name": "Coze", "avatar": "🤖"},
    "self_deployed": {"adapter_type": "self_deployed", "name": "本地 Agent", "avatar": "🔧"},
}
for _aid, _meta in _DEFAULT_ADAPTERS.items():
    if _aid not in _ar._adapters:
        saved = _ar.get_config(_aid)
        if saved:
            create_adapter(_aid, saved, save=False)
        else:
            create_adapter(_aid, {"adapter_type": _meta["adapter_type"]}, save=False)

# 把所有适配器 Agent 注册到全局 AGENTS 字典
for _aid, _adapter in _ar._adapters.items():
    if _aid not in AGENTS:
        _meta = _DEFAULT_ADAPTERS.get(_aid, {})
        AGENTS[_aid] = AdapterAgent(
            agent_id=_aid,
            name=_meta.get("name", _adapter.name),
            adapter=_adapter,
            avatar=_meta.get("avatar", "🤖"),
            role=_adapter.description,
        )
_registered = [a for a in AGENTS if a in _ar._adapters]
if _registered:
    logger.info(f"外部 Agent 已注册: {', '.join(_registered)}")


# ---- Root & health endpoints ----
@app.get("/")
async def root():
    return {"name": "AgentHub API", "version": "1.0.0", "docs": "/docs"}


@app.get("/api/health")
async def health():
    checks = {}

    # Database check
    try:
        from app.core.database import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    # Redis check
    try:
        from app.core.redis import redis_manager
        client = redis_manager.get_client()
        if client:
            await client.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_configured"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:100]}"

    # LLM check
    from app.core.llm_client import llm_client
    checks["llm"] = "configured" if llm_client.is_configured() else "not_configured"

    all_ok = all(v == "ok" or v == "configured" or v == "not_configured" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "agents": list(AGENTS.keys()),
    }


# ---- Persistent deployment queue ----
from app.core.tenancy import request_user_id, scope_conversation_id
from app.services.deployment import DEPLOY_TARGETS
from app.services.deployment_queue import (
    DeploymentAlreadyQueued,
    DeploymentQueueUnavailable,
    deployment_queue,
)
from app.services.project_workspace import (
    ProjectSnapshotError,
    create_project_snapshot,
)


class DeployRequest(BaseModel):
    target: str = "auto"
    signing_mode: str = "demo"
    keystore_file_id: str = ""
    key_alias: str = ""
    store_password: str = ""
    key_password: str = ""
    mini_appid: str = ""
    mini_private_key_file_id: str = ""
    mini_action: str = "upload"
    version: str = "1.0.0"
    description: str = "AgentHub 演示发布"


def _owned_upload(user_id: str, file_id: str) -> bool:
    from app.core.file_storage import FileStorageManager
    return bool(
        file_id
        and file_id.startswith(f"tenantfile__{user_id}__")
        and FileStorageManager.exists(file_id)
    )


def _deployment_options(user_id: str, options: DeployRequest) -> dict:
    from app.core.config import obfuscate_key
    if options.signing_mode not in {"demo", "uploaded"}:
        raise HTTPException(status_code=422, detail="Unsupported APK signing mode")
    if options.signing_mode == "uploaded":
        if not _owned_upload(user_id, options.keystore_file_id):
            raise HTTPException(status_code=422, detail="请选择当前用户上传的 keystore 文件")
        if not options.key_alias or not options.store_password:
            raise HTTPException(status_code=422, detail="用户签名需要别名和 keystore 密码")
    if options.mini_private_key_file_id and not _owned_upload(user_id, options.mini_private_key_file_id):
        raise HTTPException(status_code=422, detail="请选择当前用户上传的小程序私钥")
    if options.mini_action not in {"upload", "preview"}:
        raise HTTPException(status_code=422, detail="Unsupported Mini Program action")
    return {
        "signing_mode": options.signing_mode,
        "keystore_file_id": options.keystore_file_id,
        "key_alias": options.key_alias,
        "store_password": obfuscate_key(options.store_password),
        "key_password": obfuscate_key(options.key_password or options.store_password),
        "mini_appid": options.mini_appid.strip(),
        "mini_private_key_file_id": options.mini_private_key_file_id,
        "mini_action": options.mini_action,
        "version": options.version.strip() or "1.0.0",
        "description": options.description.strip()[:100],
    }


@app.post("/api/deploy/{conversation_id}")
async def deploy_project(conversation_id: str, request: Request, options: DeployRequest | None = None):
    options = options or DeployRequest()
    target = options.target
    if target not in DEPLOY_TARGETS:
        raise HTTPException(status_code=422, detail=f"Unsupported deployment target: {target}")
    user_id = request_user_id(request)
    try:
        scoped_id = scope_conversation_id(user_id, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        deployment_options = await asyncio.to_thread(_deployment_options, user_id, options)
        snapshot_id = await create_project_snapshot(scoped_id)
        job = await deployment_queue.enqueue(
            scoped_id,
            user_id,
            target,
            snapshot_id=snapshot_id,
            options=deployment_options,
        )
    except (FileNotFoundError, ProjectSnapshotError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DeploymentAlreadyQueued as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "queued", "target": target, "job_id": job.id}


@app.get("/api/deployments/{job_id}")
async def deployment_status(job_id: str, request: Request):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Invalid deployment ID")
    try:
        job = await deployment_queue.get(job_id)
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not job or job.user_id != request_user_id(request):
        raise HTTPException(status_code=404, detail="Deployment not found")
    return job.public_dict()


@app.get("/api/deployments/{job_id}/logs")
async def download_deployment_logs(job_id: str, request: Request):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Invalid deployment ID")
    try:
        job = await deployment_queue.get(job_id)
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not job or job.user_id != request_user_id(request):
        raise HTTPException(status_code=404, detail="Deployment not found")
    labels = {
        "queued": "排队",
        "generate": "生成",
        "dependencies": "依赖安装",
        "build": "构建",
        "sign": "签名",
        "upload": "上传",
        "complete": "完成",
    }
    lines = [
        "AgentHub deployment log",
        f"job_id: {job.id}",
        f"target: {job.target}",
        f"status: {job.status}",
        f"created_at: {job.created_at}",
        "",
    ]
    for entry in job.log_entries or []:
        timestamp = entry.get("timestamp", "")
        stage = labels.get(entry.get("stage", ""), entry.get("stage", "unknown"))
        level = str(entry.get("level", "info")).upper()
        message = str(entry.get("message", ""))
        lines.append(f"[{timestamp}] [{stage}] [{level}] {message}")
    if not job.log_entries and job.log:
        lines.append(job.log)
    return Response(
        "\n".join(lines) + "\n",
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="deployment-{job.id}.log"'},
    )


@app.get("/api/deployments")
async def deployment_history(request: Request, limit: int = 30):
    try:
        jobs = await deployment_queue.list_for_user(request_user_id(request), min(max(limit, 1), 100))
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"deployments": [job.public_dict(include_logs=False) for job in jobs]}


@app.post("/api/deployments/{job_id}/retry")
async def retry_deployment(job_id: str, request: Request):
    try:
        source = await deployment_queue.get(job_id)
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    user_id = request_user_id(request)
    if not source or source.user_id != user_id or source.action != "deploy":
        raise HTTPException(status_code=404, detail="Deployment not found")
    try:
        job = await deployment_queue.enqueue(
            source.conversation_id,
            user_id,
            source.target,
            source_job_id=source.id,
            snapshot_id=source.snapshot_id,
            options=source.options,
        )
    except DeploymentAlreadyQueued as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "queued", "job_id": job.id}


@app.post("/api/deployments/{job_id}/cancel")
async def cancel_deployment(job_id: str, request: Request):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Invalid deployment ID")
    try:
        job = await deployment_queue.get(job_id)
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    user_id = request_user_id(request)
    if not job or job.user_id != user_id or job.action != "deploy":
        raise HTTPException(status_code=404, detail="Deployment not found")
    if job.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="该任务已经结束，无法取消")
    try:
        await deployment_queue.request_cancel(job)
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "cancellation_requested", "job_id": job.id}


@app.post("/api/deployments/{job_id}/{action}")
async def deployment_action(job_id: str, action: str, request: Request):
    if action not in {"rollback", "offline"}:
        raise HTTPException(status_code=404, detail="Unsupported deployment action")
    try:
        source = await deployment_queue.get(job_id)
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    user_id = request_user_id(request)
    if not source or source.user_id != user_id or source.provider != "docker-runtime":
        raise HTTPException(status_code=404, detail="API deployment not found")
    try:
        job = await deployment_queue.enqueue(
            source.conversation_id,
            user_id,
            source.target,
            action=action,
            source_job_id=source.id,
        )
    except DeploymentAlreadyQueued as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "queued", "job_id": job.id}


@app.post("/api/deployments/cleanup")
async def cleanup_deployments(request: Request):
    user_id = request_user_id(request)
    conversation_id = scope_conversation_id(user_id, "deployment-maintenance")
    try:
        job = await deployment_queue.enqueue(
            conversation_id, user_id, "maintenance", action="cleanup"
        )
    except DeploymentAlreadyQueued as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DeploymentQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "queued", "job_id": job.id}


_RUNTIME_URL = re.compile(r"^http://agenthub-api-[a-f0-9]{16}:\d{2,5}$")
_HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


@app.get("/published-artifacts/{artifact_id}")
async def download_published_artifact(artifact_id: str):
    """Download a build artifact through an unguessable, expiring capability URL."""
    if not re.fullmatch(r"[a-f0-9]{32}", artifact_id):
        raise HTTPException(status_code=404, detail="Published artifact not found")
    from app.core.file_storage import FileStorageManager
    from app.core.redis import redis_manager

    if not await redis_manager.check_connection():
        raise HTTPException(status_code=503, detail="Published artifact registry is unavailable")
    try:
        raw = await redis_manager.get_client().get(
            f"agenthub:published-artifact:{artifact_id}"
        )
    except Exception as exc:
        redis_manager.mark_unavailable(exc, "published artifact lookup")
        raise HTTPException(
            status_code=503, detail="Published artifact registry is unavailable"
        ) from exc
    if not raw:
        raise HTTPException(status_code=404, detail="Published artifact not found")
    try:
        file_id = json.loads(raw).get("file_id", "")
    except (TypeError, json.JSONDecodeError):
        file_id = ""
    if not re.fullmatch(
        r"tenantfile__[a-zA-Z0-9_-]+__build_[a-f0-9]{32}\.[a-zA-Z0-9]+",
        file_id,
    ):
        raise HTTPException(status_code=404, detail="Published artifact not found")
    try:
        exists = await asyncio.to_thread(FileStorageManager.exists, file_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Published artifact not found")
        path = await asyncio.to_thread(FileStorageManager.get_absolute_path, file_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Could not resolve published artifact %s: %s", artifact_id, exc)
        raise HTTPException(
            status_code=503, detail="Published artifact storage is unavailable"
        ) from exc
    return FileResponse(
        path,
        filename=file_id.split("__", 2)[-1],
        media_type="application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@app.api_route(
    "/published/{deployment_id}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_published_api(deployment_id: str, path: str, request: Request):
    """Expose an isolated generated API without publishing random host ports."""
    if not re.fullmatch(r"[a-f0-9]{32}", deployment_id):
        raise HTTPException(status_code=404, detail="Published service not found")
    from app.core.redis import redis_manager
    if not await redis_manager.check_connection():
        raise HTTPException(status_code=503, detail="Published service registry is unavailable")
    try:
        raw = await redis_manager.get_client().get(
            f"agenthub:published:{deployment_id}"
        )
    except Exception as exc:
        redis_manager.mark_unavailable(exc, "published service lookup")
        raise HTTPException(
            status_code=503, detail="Published service registry is unavailable"
        ) from exc
    if not raw:
        raise HTTPException(status_code=404, detail="Published service not found")
    runtime_url = json.loads(raw).get("runtime_url", "")
    if not _RUNTIME_URL.fullmatch(runtime_url):
        logger.error("Rejected invalid generated runtime URL for deployment %s", deployment_id)
        raise HTTPException(status_code=502, detail="Invalid published service target")

    query = f"?{request.url.query}" if request.url.query else ""
    target = f"{runtime_url}/{path}{query}"
    body = await request.body()
    if len(body) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Request body exceeds 10 MB")
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in _HOP_HEADERS and key.lower() not in {"host", "content-length", "cookie"}
    }
    client = httpx.AsyncClient(timeout=60.0)
    try:
        upstream = await client.send(
            client.build_request(request.method, target, headers=headers, content=body),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="Published service is unavailable") from exc

    async def close_upstream() -> None:
        await upstream.aclose()
        await client.aclose()

    response_headers = {
        key: value for key, value in upstream.headers.items()
        if key.lower() not in _HOP_HEADERS and key.lower() not in {"content-length", "set-cookie"}
    }
    location = response_headers.get("location")
    if location and location.startswith(runtime_url):
        response_headers["location"] = f"/published/{deployment_id}{location.removeprefix(runtime_url)}"
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=response_headers,
        background=BackgroundTask(close_upstream),
    )
