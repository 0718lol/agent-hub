"""AgentHub API — FastAPI application factory.

This module is responsible for:
- App initialization, lifespan, and middleware
- WebSocket endpoint (orchestration delegated to agent_orchestrator.py)
- Mounting all API routers

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
"""
import json
import os
import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.websocket import manager
from app.core.database import (
    init_db, get_conversations,
)
from app.core.config import settings
from app.core.config_persistence import save_llm_config, load_llm_config
from app.core.llm_client import llm_client
from app.routers import (
    ws as ws_router,
    agents as agents_router,
    uploads as uploads_router,
    settings as settings_router,
    cron as cron_router,
    workflows as workflows_router,
    mcp as mcp_router,
    webhook as webhook_router,
    conversations as conversations_router,
    quality as quality_router,
    prompt as prompt_router,
    speech as speech_router,
    sandbox as sandbox_router,
    benchmark as benchmark_router,
    tools as tools_router,
)

from app.core.logging_config import get_logger, RequestIdMiddleware, setup_logging

from app.routers.harness_handler import handle_verdict
from app.services.agent_orchestrator import (
    get_agents, stream_agent_reply, run_target_agent_flow,
    run_user_message_flow, resume_graph_from_checkpoint,
    _stop_events, _remove_custom_agent,
)
logger = get_logger("main")

# ---- Agent tools (used by /api/tools endpoint) ----
import app.tools  # noqa: F401 — trigger auto-registration of runtime tools


# ---- App lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.daemon_scheduler import daemon_scheduler
    daemon_scheduler.start()
    yield
    try:
        from app.services.daemon_scheduler import daemon_scheduler
        await daemon_scheduler.stop()
    except Exception:
        pass
    try:
        from app.tools.browser_tools import browser_session_manager
        from app.core.terminal import stateful_terminal_manager
        await browser_session_manager.close_all()
        await stateful_terminal_manager.close_all()
    except Exception:
        pass


app = FastAPI(title="AgentHub API", lifespan=lifespan)

# ---- File upload directory ----
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ---- CORS ----
# Initialize structured logging
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
    if path in ("/", "/docs", "/openapi.json", "/redoc", "/api/health") or path.startswith("/api/webhook/callback/") or path.startswith("/uploads/"):
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


# ---- Agent registry & stop events ----
from app.services.agent_registry import agent_registry
AGENTS = get_agents()

# ---- Mount all routers ----
app.include_router(agents_router.router, prefix="/api")
app.include_router(uploads_router.router)
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

# ---- Initialize database ----
init_db()

# ---- Load LLM config ----
def _load_llm_config():
    load_llm_config(llm_client, settings)

def _save_llm_config():
    save_llm_config(llm_client, settings)

_load_llm_config()


# ---- Root & health endpoints ----
@app.get("/")
async def root():
    return {"name": "AgentHub API", "version": "1.0.0", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "agents": list(AGENTS.keys())}

