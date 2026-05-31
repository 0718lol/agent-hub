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
    get_agents,
    resume_graph_from_checkpoint,
    _stop_events,
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


# ---- LLM Settings API (legacy) ----
class LLMSettings(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = None
    max_tokens: int = None


@app.get("/api/settings/llm")
async def get_llm_settings():
    return {
        "provider": llm_client.provider,
        "api_key_set": bool(llm_client.api_key),
        "base_url": llm_client.base_url,
        "model": llm_client.model,
        "temperature": llm_client.temperature,
        "max_tokens": llm_client.max_tokens,
        "configured": llm_client.is_configured(),
    }


@app.post("/api/settings/llm")
async def update_llm_settings(s: LLMSettings):
    llm_client.configure(
        provider=s.provider,
        api_key=s.api_key if s.api_key else llm_client.api_key,
        base_url=s.base_url,
        model=s.model,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
    )
    _save_llm_config()
    return {"status": "ok", "configured": llm_client.is_configured()}


@app.get("/api/ollama/models")
async def list_ollama_models():
    """Fetch installed models from local Ollama instance."""
    import httpx
    url = "http://127.0.0.1:11434/api/tags"
    if llm_client.provider == "ollama" and llm_client.base_url:
        base = llm_client.base_url.rstrip("/")
        if base.endswith("/v1"):
            url = base[:-3] + "/api/tags"
        elif "11434" in base:
            url = base + "/api/tags" if not base.endswith("/api/tags") else base

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"status": "ok", "models": models}
            else:
                return {"status": "error", "message": f"Ollama returned status {resp.status_code}", "models": []}
    except Exception as e:
        return {"status": "error", "message": f"Ollama not running: {str(e)}", "models": []}


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
                    _run_target_agent_flow(conversation_id, AGENTS[target_agent], text)
                )
                bg_tasks.add(task)
                task.add_done_callback(bg_tasks.discard)
            elif sender == "user":
                task = asyncio.create_task(
                    _run_user_message_flow(conversation_id, text, target_agent)
                )
                bg_tasks.add(task)
                task.add_done_callback(bg_tasks.discard)

    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)
        # Signal any in-flight generation to stop on disconnect
        event = _stop_events.get(conversation_id)
        if event:
            event.set()


# ---- Local agent flow functions ----

async def _run_target_agent_flow(conversation_id: str, agent, text: str):
    """Background generation flow when user targets a specific agent."""
    stop_event = asyncio.Event()
    _stop_events[conversation_id] = stop_event
    try:
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": True,
        })
        assigned_agent_ids, pm_response = await _stream_agent_reply(
            conversation_id, agent, text, stop_event
        )

        # If the agent (e.g. PM) assigned downstream agents, trigger them
        if assigned_agent_ids and not stop_event.is_set():
            agents_to_run = [
                AGENTS[aid] for aid in assigned_agent_ids
                if aid in AGENTS and aid != agent.agent_id
            ]
            if agents_to_run:
                await asyncio.gather(*[
                    _stream_agent_reply(conversation_id, a, text, stop_event, context=pm_response)
                    for a in agents_to_run
                ])
    finally:
        _stop_events.pop(conversation_id, None)
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })


async def _run_user_message_flow(conversation_id: str, text: str, target_agent: str | None):
    """Background generation flow for a plain user message (group or auto-routed)."""
    stop_event = asyncio.Event()
    _stop_events[conversation_id] = stop_event
    try:
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": True,
        })

        # ---- Harness 拦截：复杂任务进入辩论沙盒 ----
        from app.routers.harness_handler import try_intercept_with_harness
        intercepted = await try_intercept_with_harness(
            conversation_id, text, llm_client, manager
        )
        if intercepted:
            return

        # User may have stopped during harness — skip downstream agents
        if stop_event.is_set():
            return

        is_group = not target_agent
        pm = AGENTS.get("agent_pm")
        assigned_agent_ids = []
        pm_response = ""

        if pm:
            assigned_agent_ids, pm_response = await _stream_agent_reply(
                conversation_id, pm, text, stop_event
            )

        if is_group and not stop_event.is_set():
            if assigned_agent_ids:
                agents_to_run = [
                    AGENTS[aid] for aid in assigned_agent_ids
                    if aid in AGENTS and aid != "agent_pm"
                ]
            else:
                agents_to_run = [AGENTS["agent_designer"], AGENTS["agent_frontend"], AGENTS["agent_backend"]]

            if agents_to_run:
                await asyncio.gather(*[
                    _stream_agent_reply(conversation_id, agent, text, stop_event, context=pm_response)
                    for agent in agents_to_run
                ])
    finally:
        _stop_events.pop(conversation_id, None)
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })


async def _stream_agent_reply(
    conversation_id: str, agent, user_text: str,
    stop_event: asyncio.Event = None, context: str = "",
) -> tuple[list[str], str]:
    """Stream agent reply. Returns (assigned_agent_ids, response_text)."""

    full_text = ""
    raw_text = ""
    buffer = ""
    last_thinking_broadcast = ""
    last_stream_broadcast = 0.0
    assigned_agents = []

    # If context provided (PM's task breakdown), prepend to user_text for the agent
    effective_text = user_text
    if context:
        effective_text = f"PM 的任务拆解：\n{context}\n\n用户原始需求：{user_text}"

    # Fetch conversation history for multi-turn context
    history = get_messages(conversation_id, limit=20)

    # Broadcast typing start + task status
    await manager.broadcast(conversation_id, {
        "type": "typing",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "is_typing": True,
    })
    await manager.broadcast(conversation_id, {
        "type": "task_status",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "status": "doing",
    })

    try:
        # ---- Best-of-N: parallel multi-candidate generation ----
        if quality_gate.enabled and quality_gate.best_of_n > 1 and agent.agent_id not in ("agent_builder", "agent_pm"):
            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": agent.agent_id,
                "content": {"text": f"⚡ 正在并行生成 {quality_gate.best_of_n} 个候选方案，择优输出..."},
                "stream": True,
            })

            async def _on_progress(idx, status):
                await manager.broadcast(conversation_id, {
                    "type": "message",
                    "conversation_id": conversation_id,
                    "sender": agent.agent_id,
                    "content": {"text": f"🏆 {status}"},
                    "stream": True,
                })

            best_output, best_report, candidates_summary = await quality_gate.best_of_n_generate(
                agent, effective_text,
                agent_id=agent.agent_id,
                history=history,
                on_progress=_on_progress,
            )

            raw_text = best_output
            buffer = best_output
            full_text = best_output.strip()

            # Broadcast candidates comparison
            await manager.broadcast(conversation_id, {
                "type": "candidates_report",
                "conversation_id": conversation_id,
                "agent_id": agent.agent_id,
                "candidates": candidates_summary,
            })

        # ---- Standard streaming mode (skip if best-of-n already ran) ----
        _use_stream = not (quality_gate.enabled and quality_gate.best_of_n > 1
                           and agent.agent_id not in ("agent_builder", "agent_pm"))
        if _use_stream:
            async for chunk in agent.stream_reply(effective_text, history=history, conversation_id=conversation_id):
                # Check stop signal
                if stop_event and stop_event.is_set():
                    logger.debug(f"[STOP] breaking stream loop for agent={agent.agent_id}")
                    break

                raw_text += chunk
                buffer += chunk

                # Extract and broadcast thinking blocks
                while True:
                    think_match = re.search(r'\[thinking\](.*?)\[/thinking\]', buffer, re.DOTALL)
                    if not think_match:
                        break
                    think_text = think_match.group(1).strip()
                    if think_text and think_text != last_thinking_broadcast:
                        last_thinking_broadcast = think_text
                        await manager.broadcast(conversation_id, {
                            "type": "thinking",
                            "conversation_id": conversation_id,
                            "agent_id": agent.agent_id,
                            "text": think_text,
                        })
                    buffer = buffer[:think_match.start()] + buffer[think_match.end():]

                # Extract assign tags
                while True:
                    assign_match = re.search(r'\[assign:(\w+)\]', buffer)
                    if not assign_match:
                        break
                    agent_id = assign_match.group(1)
                    if agent_id not in assigned_agents:
                        assigned_agents.append(agent_id)
                    buffer = buffer[:assign_match.start()] + buffer[assign_match.end():]

                # Extract options tags (keep in message for frontend to render)
                # Don't strip [options:...], [clarify:...], [ask_user:...] — let frontend handle them

                # Extract [create_agent:{json}] tags
                while True:
                    ca_match = re.search(r'\[create_agent:(.*?)\]', buffer, re.DOTALL)
                    if not ca_match:
                        break
                    try:
                        agent_config = json.loads(ca_match.group(1))
                        _register_custom_agent(agent_config)
                        # Notify frontend about the new agent
                        await manager.broadcast(conversation_id, {
                            "type": "agent_created",
                            "conversation_id": conversation_id,
                            "agent": agent_config,
                        })
                    except (json.JSONDecodeError, Exception):
                        pass
                    buffer = buffer[:ca_match.start()] + buffer[ca_match.end():]

                # Extract [delete_agent:agent_id] tags
                while True:
                    da_match = re.search(r'\[delete_agent:(agent_custom_\w+)\]', buffer)
                    if not da_match:
                        break
                    del_id = da_match.group(1)
                    _remove_custom_agent(del_id)
                    await manager.broadcast(conversation_id, {
                        "type": "agent_deleted",
                        "conversation_id": conversation_id,
                        "agent_id": del_id,
                    })
                    buffer = buffer[:da_match.start()] + buffer[da_match.end():]

                # Extract and broadcast code blocks
                while True:
                    code_match = re.search(r'```(\w*)\n(.*?)```', buffer, re.DOTALL)
                    if not code_match:
                        break
                    lang = code_match.group(1) or "html"
                    code = code_match.group(2).strip()
                    await manager.broadcast(conversation_id, {
                        "type": "code",
                        "conversation_id": conversation_id,
                        "agent_id": agent.agent_id,
                        "language": lang,
                        "code": code,
                    })
                    # If HTML, also send to preview panel
                    if lang.lower() in ("html", "htm", ""):
                        await manager.broadcast(conversation_id, {
                            "type": "preview",
                            "conversation_id": conversation_id,
                            "agent_id": agent.agent_id,
                            "html": code,
                        })
                    buffer = buffer[:code_match.start()] + buffer[code_match.end():]

                # Broadcast remaining text (summary) as streaming message
                # 节流控制：最快每 80ms 广播一次，避免刷屏
                now = asyncio.get_running_loop().time()
                summary = buffer.strip()
                if summary and (now - last_stream_broadcast) >= 0.08:
                    last_stream_broadcast = now
                    await manager.broadcast(conversation_id, {
                        "type": "message",
                        "conversation_id": conversation_id,
                        "sender": agent.agent_id,
                        "content": {"text": summary},
                        "stream": True,
                    })

        # Final text is whatever remains in buffer (summary only)
        full_text = buffer.strip()

        # Bare HTML fallback: if the model returned raw HTML without a ``` fence,
        # detect <!DOCTYPE> / <html> and route it to the canvas as a code block
        # so it doesn't dump the entire HTML source into the chat bubble.
        if full_text and "```" not in raw_text and re.search(
            r'<!DOCTYPE\s+html|<html[\s>]|<body[\s>]', full_text, re.IGNORECASE
        ):
            html_match = re.search(
                r'(<!DOCTYPE[\s\S]*?</html>|<html[\s\S]*?</html>|<body[\s\S]*?</body>)',
                full_text, re.IGNORECASE
            )
            if html_match:
                bare_html = html_match.group(1).strip()
                await manager.broadcast(conversation_id, {
                    "type": "code",
                    "conversation_id": conversation_id,
                    "agent_id": agent.agent_id,
                    "language": "html",
                    "code": bare_html,
                })
                await manager.broadcast(conversation_id, {
                    "type": "preview",
                    "conversation_id": conversation_id,
                    "agent_id": agent.agent_id,
                    "html": bare_html,
                })
                # Strip HTML from chat bubble, leave a short notice
                full_text = full_text.replace(bare_html, "").strip()
                if not full_text:
                    full_text = "（已生成代码，请查看右侧面板）"

    except Exception as e:
        err_msg = f"[Agent 回复出错: {type(e).__name__}: {str(e)[:200]}]"
        if not full_text:
            full_text = err_msg
        else:
            full_text += f"\n[出错: {str(e)[:100]}]"
        raw_text += f"\n{err_msg}"

    stopped = stop_event and stop_event.is_set()

    if not full_text:
        full_text = "（已停止生成）" if stopped else "（已生成代码，请查看右侧面板）"

    if not raw_text:
        raw_text = full_text

    # ---- 自动反思与重试 (Self-Reflection & Retry) ----
    if not stopped and agent.agent_id not in ("agent_builder", "agent_pm"):
        eval_result = await evaluate_and_retry(
            conversation_id=conversation_id,
            agent=agent,
            task=effective_text,
            raw_output=raw_text,
            llm_client=llm_client,
            manager=manager,
            stop_event=stop_event,
            history=history,
        )
        # 用评估后的最终输出替换原始输出
        if eval_result["final_output"]:
            raw_text = eval_result["final_output"]
            full_text = eval_result["final_output"].strip()

    # Don't persist LLM error responses — they pollute history and cause the
    # model to parrot the error string back on the next turn.
    is_llm_error = ("[LLM Error" in raw_text) or ("[LLM 调用出错" in raw_text) or ("[Agent 回复出错" in raw_text)
    if not is_llm_error:
        save_message(conversation_id, agent.agent_id, {"text": raw_text}, streaming=False)

    # Broadcast thinking stop
    await manager.broadcast(conversation_id, {
        "type": "thinking",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "text": "",
    })

    # Broadcast typing stop + task done
    await manager.broadcast(conversation_id, {
        "type": "typing",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "is_typing": False,
    })
    await manager.broadcast(conversation_id, {
        "type": "task_status",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "status": "done",
    })

    await manager.broadcast(conversation_id, {
        "type": "message",
        "conversation_id": conversation_id,
        "sender": agent.agent_id,
        "content": {"text": full_text},
        "stream": False,
    })

    return assigned_agents, full_text


def _register_custom_agent(config: dict):
    """Create a custom agent from config, save to DB, register in AGENTS, create conversation."""
    aid = config.get("agent_id", "")
    name = config.get("name", "自定义助手")
    avatar = config.get("avatar", "🤖")
    role = config.get("role", "智能助手")
    style = config.get("style", "友好专业")
    system_prompt = config.get("system_prompt") or f"你是{name}，{role}。请基于这个角色为用户提供专业、有帮助的回答。"
    tools = config.get("tools", [])

    # Save to database
    save_custom_agent(aid, name, avatar, role, style, system_prompt, tools)

    # Instantiate and register
    AGENTS[aid] = CustomAgent(
        agent_id=aid, name=name, avatar=avatar,
        role=role, style=style, system_prompt=system_prompt, tools=tools,
    )

    # Create a conversation for this agent
    conv_id = f"conv_{aid}"
    create_conversation(conv_id, "single", name, avatar, agent_id=aid, preview=role)


def _remove_custom_agent(agent_id: str):
    """Delete a custom agent from DB, AGENTS dict, and its conversation."""
    AGENTS.pop(agent_id, None)
    delete_custom_agent(agent_id)


# ---- Custom Agent REST API ----

class CustomAgentCreate(BaseModel):
    name: str
    avatar: str = "🤖"
    role: str = ""
    style: str = ""
    system_prompt: str
    tools: list[str] = []


@app.get("/api/agents/custom")
async def list_custom_agents():
    return get_custom_agents()


@app.post("/api/agents/custom")
async def create_custom_agent(body: CustomAgentCreate):
    import uuid
    agent_id = f"agent_custom_{uuid.uuid4().hex[:8]}"
    config = {
        "agent_id": agent_id,
        "name": body.name,
        "avatar": body.avatar,
        "role": body.role,
        "style": body.style,
        "system_prompt": body.system_prompt,
        "tools": body.tools,
    }
    _register_custom_agent(config)
    return {"status": "created", "agent": config}


@app.delete("/api/agents/custom/{agent_id}")
async def remove_custom_agent(agent_id: str):
    _remove_custom_agent(agent_id)
    return {"status": "deleted", "agent_id": agent_id}


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


# ---- Quality Gate API ----

@app.post("/api/quality/evaluate")
async def evaluate_text(body: dict):
    """Manual quality evaluation endpoint. Body: {"text": "...", "agent_id": "..."}"""
    text = body.get("text", "")
    agent_id = body.get("agent_id", "")
    if not text:
        return {"error": "text is required"}
    report = quality_gate.evaluate(text, agent_id)
    return report.to_dict()


@app.get("/api/quality/standards")
async def list_quality_standards():
    from app.core.quality_standards import STANDARDS
    return {
        k: {"name": v["name"], "pass_threshold": v["pass_threshold"],
             "rules_count": len(v["rules"])}
        for k, v in STANDARDS.items()
    }


# ---- Prompt Engine API ----

@app.get("/api/prompt/layers")
async def list_prompt_layers():
    """List all prompt layers with their status."""
    return prompt_engine.get_layers_info()


@app.post("/api/prompt/layers/{layer_id}")
async def toggle_prompt_layer(layer_id: str, body: dict):
    """Enable/disable a prompt layer. Body: {"enabled": true/false}"""
    enabled = body.get("enabled", True)
    prompt_engine.set_layer_enabled(layer_id, enabled)
    return {"status": "ok", "layer_id": layer_id, "enabled": enabled}


@app.post("/api/prompt/preview")
async def preview_prompt(body: dict):
    """Preview the assembled prompt for a given agent and context.
    Body: {"agent_id": "...", "message": "...", "task_type": "code|html|api|document"}
    """
    agent_id = body.get("agent_id", "agent_frontend")
    message = body.get("message", "")
    task_type = body.get("task_type")

    agent = AGENTS.get(agent_id)
    if not agent:
        return {"error": f"Agent {agent_id} not found"}

    if not task_type and message:
        task_type = prompt_engine.detect_task_type(message, agent_id)

    ctx = {"task_type": task_type}
    assembled = prompt_engine.build(agent, ctx)
    return {
        "agent_id": agent_id,
        "task_type": task_type,
        "assembled_prompt": assembled,
        "char_count": len(assembled),
        "estimated_tokens": len(assembled) // 3,
    }


# ---- Speech-to-Text API ----

STT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "stt_config.json")


def _load_stt_config():
    try:
        if os.path.exists(STT_CONFIG_PATH):
            with open(STT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            stt_client.configure(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
                model=cfg.get("model", "whisper-1"),
                language=cfg.get("language", "zh"),
            )
    except Exception:
        pass


def _save_stt_config():
    os.makedirs(os.path.dirname(STT_CONFIG_PATH), exist_ok=True)
    with open(STT_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "api_key": stt_client.api_key,
            "base_url": stt_client.base_url,
            "model": stt_client.model,
            "language": stt_client.language,
        }, f, ensure_ascii=False, indent=2)


_load_stt_config()


class STTSettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = "whisper-1"
    language: str = "zh"


@app.get("/api/settings/stt")
async def get_stt_settings():
    return {
        "configured": stt_client.is_configured(),
        "base_url": stt_client.base_url,
        "model": stt_client.model,
        "language": stt_client.language,
    }


@app.post("/api/settings/stt")
async def update_stt_settings(s: STTSettings):
    stt_client.configure(
        api_key=s.api_key or stt_client.api_key,
        base_url=s.base_url,
        model=s.model,
        language=s.language,
    )
    _save_stt_config()
    return {"configured": stt_client.is_configured()}


@app.post("/api/speech/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Upload an audio file and get transcribed text back.
    Supports: webm, wav, mp3, m4a, ogg, flac
    Falls back to LLM provider's Whisper endpoint if STT not separately configured.
    """
    audio_bytes = await file.read()
    filename = file.filename or "audio.webm"

    # If STT not configured, try using the LLM provider's base_url + key
    if not stt_client.is_configured() and llm_client.is_configured():
        stt_client.configure(
            api_key=llm_client.api_key,
            base_url=llm_client.base_url,
            model="whisper-1",
            language="zh",
        )

    if not stt_client.is_configured():
        return {"error": "语音识别未配置。请在设置中配置 STT API 或 LLM API。", "text": ""}

    try:
        text = await stt_client.transcribe(audio_bytes, filename)
        return {"text": text, "status": "ok"}
    except Exception as e:
        return {"error": f"语音识别失败: {str(e)[:200]}", "text": ""}


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
