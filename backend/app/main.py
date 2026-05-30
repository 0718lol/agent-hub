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
import re
import uuid
import asyncio
import logging
from pydantic import BaseModel
from typing import Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from contextlib import asynccontextmanager

from app.core.websocket import manager
from app.core.database import (
    init_db, save_message, get_messages, get_conversations, clear_messages,
    save_custom_agent, get_custom_agents, delete_custom_agent, create_conversation,
)
from app.core.config import settings
from app.core.config_persistence import get_hil_settings, save_hil_settings, save_llm_config, load_llm_config
from app.core.llm_client import llm_client
from app.core.quality_gate import quality_gate
from app.core.quality_retry import evaluate_and_retry
from app.core.prompt_engine import prompt_engine
from app.core.speech import stt_client
from app.core.sandbox import execute_code
from app.core.metrics import metrics
from app.core.benchmark import run_benchmark, get_current_run, BENCHMARK_CASES
from app.routers import (
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
)

from app.core.logging_config import get_logger, RequestIdMiddleware, setup_logging

from app.services.agent_orchestrator import (
    get_agents, stream_agent_reply, run_target_agent_flow,
    run_user_message_flow, resume_graph_from_checkpoint,
    _stop_events, _remove_custom_agent,
)
logger = get_logger("main")

_BACKGROUND_TASKS: set[asyncio.Task] = set()


def create_tracked_task(coro, name: str = None) -> asyncio.Task:
    """Create and strongly reference a background asyncio task to prevent GC."""
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


# ---- Agent imports ----
from app.agents.pm import PMAgent
from app.agents.frontend import FrontendAgent
from app.agents.backend_agent import BackendAgent
from app.agents.tester import TesterAgent
from app.agents.devops import DevopsAgent
from app.agents.designer import DesignerAgent
from app.agents.builder import AgentBuilderAgent
from app.agents.custom import CustomAgent, AVAILABLE_TOOLS
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


# ---- File upload endpoint (kept here due to UPLOAD_DIR dependency) ----
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    is_image = (file.content_type or "").startswith("image/")
    return {
        "status": "uploaded",
        "original_name": file.filename,
        "stored_name": stored_name,
        "url": f"/uploads/{stored_name}",
        "content_type": file.content_type,
        "size": len(content),
        "is_image": is_image,
    }


@app.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    # ---- WebSocket IP/Token 鉴权 ----
    client_host = websocket.client.host if websocket.client else None
    authorized = False
    
    if settings.api_secret:
        query_token = websocket.query_params.get("token")
        if query_token == settings.api_secret:
            authorized = True
    else:
        if client_host in ("127.0.0.1", "::1", "localhost"):
            authorized = True
            
    if not authorized:
        await websocket.accept()
        await websocket.close(code=4001, reason="Unauthorized connection attempt")
        return

    await manager.connect(websocket, conversation_id)
    # Tasks spawned for ongoing generations on this connection, so we can
    # await them at disconnect time. Stop is signalled via _stop_events.
    bg_tasks: set[asyncio.Task] = set()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            msg_type = msg.get("type", "message")
            sender = msg.get("sender", "user")
            content = msg.get("content", {})
            text = content.get("text", "")
            target_agent = content.get("target_agent")

            # Intercept user interaction response if there's a pending interactive judge wait
            from app.tools.judge_tools import _pending_interactions
            is_active_hil = conversation_id in _pending_interactions
            
            # Recovery path check
            is_recovered_hil = False
            if not is_active_hil:
                from app.core.database import get_pending_hil_checkpoint
                try:
                    checkpoint = get_pending_hil_checkpoint(conversation_id)
                    if checkpoint:
                        is_recovered_hil = True
                except Exception:
                    pass

            if is_active_hil or is_recovered_hil:
                reply_text = text
                if reply_text.startswith("[ask_user_reply]"):
                    reply_text = reply_text.replace("[ask_user_reply]", "").strip()
                
                if is_active_hil:
                    fut = _pending_interactions[conversation_id]
                    if not fut.done():
                        fut.set_result(reply_text)
                else:
                    # Recovery path: trigger asynchronous recovery task
                    create_tracked_task(resume_graph_from_checkpoint(conversation_id, reply_text), name=f"resume_graph_{conversation_id}")
                    
                # We still want to save and broadcast this message to display it in the Chat UI as a user reply
                save_message(conversation_id, sender, content, streaming=False)
                await manager.broadcast(conversation_id, {
                    "type": "message",
                    "conversation_id": conversation_id,
                    "sender": sender,
                    "content": {"text": text},
                    "stream": False,
                })
                continue

            # Handle stop generation — must be processed without blocking on
            # the in-flight generation task (which is why generation runs as a
            # background task, not awaited here).
            if msg_type == "stop":
                event = _stop_events.get(conversation_id)
                logger.debug(f"[STOP] conv={conversation_id} event_exists={event is not None} already_set={event.is_set() if event else 'N/A'}")
                if event:
                    event.set()
                continue

            # Handle read receipt
            if msg_type == "read":
                await manager.broadcast(conversation_id, {
                    "type": "read",
                    "conversation_id": conversation_id,
                    "reader": "user",
                })
                continue

            # Handle harness verdict (user裁决指令)
            if msg_type == "harness_verdict":
                await handle_verdict(conversation_id, msg, manager)
                continue

            save_message(conversation_id, sender, content, streaming=False)

            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": sender,
                "content": {"text": text},
                "stream": False,
            })

            # If a previous generation is still running for this conversation,
            # signal it to stop before starting a new one.
            prev_event = _stop_events.get(conversation_id)
            if prev_event and not prev_event.is_set():
                prev_event.set()

            if target_agent and target_agent in AGENTS:
                task = asyncio.create_task(
                    run_target_agent_flow(conversation_id, AGENTS[target_agent], text)
                )
                bg_tasks.add(task)
                task.add_done_callback(bg_tasks.discard)
            elif sender == "user":
                task = asyncio.create_task(
                    run_user_message_flow(conversation_id, text, target_agent)
                )
                bg_tasks.add(task)
                task.add_done_callback(bg_tasks.discard)

    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)
        # Signal any in-flight generation to stop on disconnect
        event = _stop_events.get(conversation_id)
        if event:
            event.set()





@app.get("/api/tools")
async def list_available_tools():
    """List prompt-addon tools (for custom agent builder UI)."""
    return [
        {"id": tid, "name": t["name"], "icon": t["icon"], "description": t["description"]}
        for tid, t in AVAILABLE_TOOLS.items()
    ]


# ---- Runtime Tools (executable) REST API ----

@app.get("/api/runtime-tools")
async def list_runtime_tools():
    """List all registered executable runtime tools."""
    from app.tools import list_tools as _list_tools
    return _list_tools()


@app.post("/api/runtime-tools/{tool_name}/test")
async def test_runtime_tool(tool_name: str, body: dict = {}):
    """Manually test an executable tool with given params."""
    from app.tools import execute_tool_call
    result = await execute_tool_call(tool_name, body)
    return {
        "tool": tool_name,
        "success": result.success,
        "data": result.data,
        "error": result.error,
        "usage": result.usage,
    }


@app.post("/api/runtime-tools/{tool_name}/toggle")
async def toggle_runtime_tool(tool_name: str):
    """Enable/disable a runtime tool."""
    from app.tools import get_tool
    tool = get_tool(tool_name)
    if not tool:
        return {"error": f"Tool not found: {tool_name}"}
    tool.enabled = not tool.enabled
    return {"tool": tool_name, "enabled": tool.enabled}


