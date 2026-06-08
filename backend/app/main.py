"""AgentHub API — FastAPI application factory.

This module is responsible for:
- App initialization, lifespan, and middleware
- Mounting all API routers
- Root & health endpoints
- Deploy simulation (no dedicated router)

Business logic is delegated to focused router modules:
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
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

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
    daemon_scheduler.start()
    yield
    try:
        from app.services.daemon_scheduler import daemon_scheduler
        await daemon_scheduler.stop()
    except Exception as e:
        logger.warning(f"Failed to stop daemon scheduler during shutdown: {e}")
    try:
        from app.core.terminal import stateful_terminal_manager
        from app.tools.browser_tools import browser_session_manager
        await browser_session_manager.close_all()
        await stateful_terminal_manager.close_all()
    except Exception as e:
        logger.warning(f"Failed to close browser/terminal sessions during shutdown: {e}")


app = FastAPI(title="AgentHub API", lifespan=lifespan)

# ---- File upload directory ----
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

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
    if path in ("/", "/docs", "/openapi.json", "/redoc", "/api/health") or path.startswith("/api/webhook/callback/"):
        return await call_next(request)
    if not path.startswith("/api"):
        return await call_next(request)
    if settings.api_secret:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized: Missing or invalid Authorization header"})
        token = auth_header.split(" ", 1)[1]
        if token != settings.api_secret:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized: Invalid API secret token"})
    else:
        client_host = request.client.host if request.client else None
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            return JSONResponse(status_code=403, content={"detail": f"Forbidden: Access from external IP '{client_host}' is blocked."})
    return await call_next(request)


# ---- Agent registry ----
from app.services.agent_registry import agent_registry

AGENTS = get_agents()

# ---- Mount all routers ----
app.include_router(agents_router.router, prefix="/api")
app.include_router(uploads_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(cron_router.router, prefix="/api")
app.include_router(workflows_router.router, prefix="/api")
app.include_router(mcp_router.router, prefix="/api")
app.include_router(webhook_router.router, prefix="/api")
app.include_router(conversations_router.router, prefix="/api")
app.include_router(quality_router.router, prefix="/api")
app.include_router(prompt_router.router, prefix="/api")
app.include_router(speech_router.router, prefix="/api")
app.include_router(sandbox_router.router, prefix="/api")
app.include_router(benchmark_router.router, prefix="/api")
app.include_router(ws_router.router)
app.include_router(tools_router.router, prefix="/api")
app.include_router(knowledge_router.router, prefix="/api")
app.include_router(adapters_router.router, prefix="/api")
app.include_router(metrics_router.router, prefix="/api")

# ---- Initialize database ----
init_db()

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


# ---- Deploy simulation (no dedicated router module) ----
from app.core.websocket import manager


@app.post("/api/deploy/{conversation_id}")
async def deploy_project(conversation_id: str):
    asyncio.create_task(_simulate_deploy(conversation_id))
    return {"status": "started"}


async def _simulate_deploy(conversation_id: str):
    logs = [
        "🚀 正在初始化云部署沙盒环境...",
        "📦 检查工作目录并拉取最新依赖包...",
        "🧪 运行自动化冒烟测试 (Tester Agent 验证通过)...",
        "🐳 构建生产环境 Docker 容器镜像...",
        "🐳 正在向远端镜像仓库推送镜像 agenthub/app:latest...",
        "☸️ Kubernetes 资源调度与健康状态检查...",
        "🌎 域名解析与 SSL 证书(Let's Encrypt) 自动配置...",
        "🎉 一键部署成功！静态资源与 API 服务均已上线。"
    ]

    for i, log in enumerate(logs):
        await asyncio.sleep(1.2)
        status = "success" if i == len(logs) - 1 else "running"
        url = f"https://agenthub-app-{conversation_id[:6]}.netlify.app" if status == "success" else None

        await manager.broadcast(conversation_id, {
            "type": "deploy_status",
            "conversation_id": conversation_id,
            "status": status,
            "log": log,
            "url": url
        })

    url = f"https://agenthub-app-{conversation_id[:6]}.netlify.app"
    await asyncio.sleep(0.5)
    await manager.broadcast(conversation_id, {
        "type": "message",
        "conversation_id": conversation_id,
        "sender": "agent_devops",
        "content": {"text": f"✅ 报告！项目已成功一键部署上线！\n\n🌍 线上访问地址：{url}\n⚠️ 生产集群运行平稳，SSL 证书配置正确，CDN 分发已全球生效！"},
        "stream": False
    })



