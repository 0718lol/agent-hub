"""AgentHub API — FastAPI application factory.

This module is responsible for:
- App initialization, lifespan, and middleware
- WebSocket endpoint and agent orchestration flow
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

from app.core.logging_config import setup_logging, get_logger, RequestIdMiddleware
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
AGENTS = agent_registry._agents
_stop_events: dict[str, asyncio.Event] = {}

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


_graph_builders = {}


def _build_group_chat_graph(conversation_id: str, text: str, trace: Any, stop_event: asyncio.Event) -> Any:
    from app.core.state_graph import StateGraph
    
    graph = StateGraph()
    
    # 1. Define Node execution wrappers
    async def run_pm(state: dict) -> dict:
        pm = AGENTS["agent_pm"]
        step = trace.add_step(pm.agent_id, pm.name)
        
        feedback = state.get("agent_pm_feedback", "")
        effective_prompt = text
        if feedback:
            effective_prompt = f"{text}\n\n🔄 人工审核反馈意见，请针对以下意见修改刚才的代码/结果：\n{feedback}"
        
        assigned, pm_res = await _stream_agent_reply(
            conversation_id, pm, effective_prompt, stop_event
        )
        step.finish(status="success", tokens=len(pm_res) // 3)
        metrics.record_agent_result(pm.agent_id, 80, step.duration_ms, step.tokens_used)
        return {
            "pm_response": pm_res,
            "assigned_agents": assigned,
            "agent_pm_feedback": ""
        }
        
    async def run_designer(state: dict) -> dict:
        designer = AGENTS["agent_designer"]
        step = trace.add_step(designer.agent_id, designer.name)
        
        feedback = state.get("agent_designer_feedback", "")
        effective_prompt = text
        if feedback:
            effective_prompt = f"{text}\n\n🔄 人工审核反馈意见，请针对以下意见修改刚才的代码/结果：\n{feedback}"
        
        _, res = await _stream_agent_reply(
            conversation_id, designer, effective_prompt, stop_event, context=state.get("pm_response", "")
        )
        step.finish(status="success", tokens=len(res) // 3)
        metrics.record_agent_result(designer.agent_id, 75, step.duration_ms, step.tokens_used)
        return {"designer_response": res, "agent_designer_feedback": ""}

    async def run_frontend(state: dict) -> dict:
        frontend = AGENTS["agent_frontend"]
        step = trace.add_step(frontend.agent_id, frontend.name)
        
        feedback = state.get("agent_frontend_feedback", "")
        effective_prompt = text
        if feedback:
            effective_prompt = f"{text}\n\n🔄 人工审核反馈意见，请针对以下意见修改刚才的代码/结果：\n{feedback}"
        
        _, res = await _stream_agent_reply(
            conversation_id, frontend, effective_prompt, stop_event, context=state.get("pm_response", "")
        )
        step.finish(status="success", tokens=len(res) // 3)
        metrics.record_agent_result(frontend.agent_id, 75, step.duration_ms, step.tokens_used)
        return {"frontend_response": res, "agent_frontend_feedback": ""}

    async def run_backend(state: dict) -> dict:
        backend = AGENTS["agent_backend"]
        step = trace.add_step(backend.agent_id, backend.name)
        
        feedback = state.get("agent_backend_feedback", "")
        effective_prompt = text
        if feedback:
            effective_prompt = f"{text}\n\n🔄 人工审核反馈意见，请针对以下意见修改刚才的代码/结果：\n{feedback}"
        
        _, res = await _stream_agent_reply(
            conversation_id, backend, effective_prompt, stop_event, context=state.get("pm_response", "")
        )
        step.finish(status="success", tokens=len(res) // 3)
        metrics.record_agent_result(backend.agent_id, 75, step.duration_ms, step.tokens_used)
        return {"backend_response": res, "agent_backend_feedback": ""}

    async def run_tester(state: dict) -> dict:
        tester = AGENTS["agent_tester"]
        step = trace.add_step(tester.agent_id, tester.name)
        
        feedback = state.get("agent_tester_feedback", "")
        effective_prompt = text
        if feedback:
            effective_prompt = f"{text}\n\n🔄 人工审核反馈意见，请针对以下意见修改刚才的代码/结果：\n{feedback}"
        
        _, res = await _stream_agent_reply(
            conversation_id, tester, effective_prompt, stop_event, context=state.get("pm_response", "")
        )
        step.finish(status="success", tokens=len(res) // 3)
        metrics.record_agent_result(tester.agent_id, 75, step.duration_ms, step.tokens_used)
        return {"tester_response": res, "agent_tester_feedback": ""}

    async def run_devops(state: dict) -> dict:
        devops = AGENTS["agent_devops"]
        step = trace.add_step(devops.agent_id, devops.name)
        
        feedback = state.get("agent_devops_feedback", "")
        effective_prompt = text
        if feedback:
            effective_prompt = f"{text}\n\n🔄 人工审核反馈意见，请针对以下意见修改刚才的代码/结果：\n{feedback}"
        
        _, res = await _stream_agent_reply(
            conversation_id, devops, effective_prompt, stop_event, context=state.get("pm_response", "")
        )
        step.finish(status="success", tokens=len(res) // 3)
        metrics.record_agent_result(devops.agent_id, 75, step.duration_ms, step.tokens_used)
        return {"devops_response": res, "agent_devops_feedback": ""}

    # 2. Add nodes to graph
    graph.add_node("agent_pm", run_pm)
    graph.add_node("agent_designer", run_designer)
    graph.add_node("agent_frontend", run_frontend)
    graph.add_node("agent_backend", run_backend)
    graph.add_node("agent_tester", run_tester)
    graph.add_node("agent_devops", run_devops)

    # 3. Add edges and conditional routing rules using select_next_speaker LLM Coordinator
    SPEAKER_SELECTION_SYSTEM_PROMPT = """你是一个智能体群聊协调器 (Group Chat Coordinator)。
根据当前的对话历史和各个候选智能体 (Agents) 的角色描述，判断下一个最适合发言的智能体是谁。

候选智能体列表：
{candidates_info}

规则：
1. 只能从上面的候选智能体 ID 中选择一个，或者输出 "END" 表示对话已圆满结束（所有开发/部署任务均已妥善完成，没有遗留问题）。
2. 请只输出下一个发言的智能体 ID（例如 "agent_frontend"）或 "END"，不要附带任何其他解释、标点或 markdown 格式。
3. 必须客观分析当前对话进度。如果当前步骤是 PM 分工且需要前端开发，下一步通常是 `agent_frontend`；如果刚才已经完成了编码，下一步通常是 `agent_tester` 运行测试；若测试完毕没有问题，则是 `agent_devops` 部署。如果所有规划的任务都已经完成，输出 "END"。
"""

    async def select_next_speaker(state: dict) -> str:
        import logging
        sg_logger = logging.getLogger("state_graph")
        
        assigned = state.get("assigned_agents", [])
        candidates = assigned if assigned else ["agent_designer", "agent_frontend", "agent_backend", "agent_tester", "agent_devops"]
        
        # Filter out completed nodes to ensure progress along the DAG
        remaining_candidates = [c for c in candidates if c not in state.get("completed_nodes", [])]
        
        if not remaining_candidates:
            return "END"
            
        # 💡 [Heuristic Lightweight Router Intercept (0 Latency, 0 Token Cost)]
        rule_speaker = None
        
        # Rule A: Single Choice
        if len(remaining_candidates) == 1:
            rule_speaker = remaining_candidates[0]
            sg_logger.info(f"[Speaker Selection] Heuristic rule A triggered: only one candidate remaining. Selected '{rule_speaker}'")
        
        # Rule B: Linear SDLC Waterfall Inference
        else:
            completed = state.get("completed_nodes", [])
            last_completed = completed[-1] if completed else None
            
            if last_completed == "agent_pm":
                if "agent_designer" in remaining_candidates:
                    rule_speaker = "agent_designer"
                elif "agent_frontend" in remaining_candidates:
                    rule_speaker = "agent_frontend"
                elif "agent_backend" in remaining_candidates:
                    rule_speaker = "agent_backend"
            elif last_completed == "agent_designer":
                if "agent_frontend" in remaining_candidates:
                    rule_speaker = "agent_frontend"
                elif "agent_backend" in remaining_candidates:
                    rule_speaker = "agent_backend"
            elif last_completed in ("agent_frontend", "agent_backend"):
                frontend_done = "agent_frontend" in completed or "agent_frontend" not in remaining_candidates
                backend_done = "agent_backend" in completed or "agent_backend" not in remaining_candidates
                if frontend_done and backend_done:
                    if "agent_tester" in remaining_candidates:
                        rule_speaker = "agent_tester"
                else:
                    other = "agent_backend" if last_completed == "agent_frontend" else "agent_frontend"
                    if other in remaining_candidates:
                        rule_speaker = other
            elif last_completed == "agent_tester":
                if "agent_devops" in remaining_candidates:
                    rule_speaker = "agent_devops"
            elif last_completed == "agent_devops":
                rule_speaker = "END"
                
            if rule_speaker:
                sg_logger.info(f"[Speaker Selection] Heuristic rule B triggered: SDLC waterfall transition. Selected '{rule_speaker}'")
        
        if rule_speaker:
            return rule_speaker

        # Fallback to LLM Coordinator for non-deterministic branching
        sg_logger.info("[Speaker Selection] Non-deterministic state branching. Dispatching LLM Coordinator...")
        
        # Build candidates_info string
        candidates_info = ""
        for cid in remaining_candidates:
            if cid in AGENTS:
                candidates_info += f"- ID: {cid}\n  Name: {AGENTS[cid].name}\n  Description: {AGENTS[cid].description}\n\n"
                
        if not candidates_info.strip():
            return "END"
            
        # Get last few messages to analyze conversation context
        history = get_messages(conversation_id, limit=6)
        history_text = ""
        for m in history:
             sender_name = m.get("sender", "unknown")
             content = m.get("content", {})
             text_content = content.get("text", "")
             # Strip code blocks to keep text concise and save tokens
             text_content = re.sub(r'```[\s\S]*?```', '[Generated Code Block]', text_content)
             history_text += f"{sender_name}: {text_content[:400]}\n\n"
             
        user_prompt = f"--- 对话历史 ---\n{history_text}\n\n请决定下一个最适合发言的智能体。"
        system_prompt = SPEAKER_SELECTION_SYSTEM_PROMPT.format(candidates_info=candidates_info)
        
        selected = ""
        try:
            async for chunk in llm_client.chat_stream([{"role": "user", "content": user_prompt}], system=system_prompt):
                selected += chunk
            selected = selected.strip().strip("'\"`").strip()
            sg_logger.info(f"[Speaker Selection] LLM selected speaker: '{selected}'")
        except Exception as e:
            sg_logger.error(f"[Speaker Selection] Error calling LLM router: {e}")
            selected = ""
            
        if selected in remaining_candidates:
            return selected
        elif selected == "END":
            return "END"
        else:
            fallback = remaining_candidates[0]
            sg_logger.info(f"[Speaker Selection] Invalid/unknown speaker '{selected}', falling back to '{fallback}'")
            return fallback

    graph.add_conditional_edge("agent_pm", select_next_speaker)
    graph.add_conditional_edge("agent_designer", select_next_speaker)
    graph.add_conditional_edge("agent_frontend", select_next_speaker)
    graph.add_conditional_edge("agent_backend", select_next_speaker)
    graph.add_conditional_edge("agent_tester", select_next_speaker)
    graph.add_edge("agent_devops", "END")

    # 3.5 Register Statechart Transition Guards (Guards & Fallbacks)
    graph.add_guard(
        "agent_devops",
        lambda state: "agent_tester" in state.get("completed_nodes", []),
        error_fallback_node="agent_tester"
    )
    graph.add_guard(
        "agent_tester",
        lambda state: any(n in state.get("completed_nodes", []) for n in ["agent_frontend", "agent_backend"]),
        error_fallback_node="agent_frontend"
    )
    
    return graph


async def resume_graph_from_checkpoint(conversation_id: str, action: str):
    """Restore state from persistent DB and resume suspended graph execution."""
    import uuid as _uuid
    import asyncio
    from app.core.database import get_pending_hil_checkpoint, resolve_hil_checkpoint, save_message
    from app.core.websocket import manager
    
    checkpoint = get_pending_hil_checkpoint(conversation_id)
    if not checkpoint:
        print(f"[Checkpointer Recovery] No pending HIL checkpoint found for conversation {conversation_id}", flush=True)
        return
        
    # Mark resolved in database
    resolve_hil_checkpoint(conversation_id, action)
    
    current_node = checkpoint["current_node"]
    next_node = checkpoint["next_node"]
    state_data = checkpoint["state_data"]
    original_prompt = checkpoint["original_prompt"]
    
    # Broadcast HIL recovery notice
    await manager.broadcast(conversation_id, {
        "type": "message",
        "conversation_id": conversation_id,
        "sender": "system",
        "content": {"text": f"🔄 检测到服务器重启。正在从检查点恢复流程并执行审核决策: **{action}**..."},
        "stream": False,
    })
    
    # Setup starting node and update state data based on action
    start_node = None
    if action.lower() in ("approve", "yes", "y") or any(action.lower() == opt["label"].lower() and opt["recommended"] for opt in checkpoint.get("options", [])):
        # Approved: proceed to next node
        if next_node == "END":
            # Flow finished
            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": "system",
                "content": {"text": "✅ 审核通过。流程圆满结束！"},
                "stream": False,
            })
            await manager.broadcast(conversation_id, {
                "type": "generating",
                "conversation_id": conversation_id,
                "is_generating": False,
            })
            return
        start_node = next_node
    elif action.lower() in ("terminate", "end", "stop"):
        # Terminated
        await manager.broadcast(conversation_id, {
            "type": "message",
            "conversation_id": conversation_id,
            "sender": "system",
            "content": {"text": "🛑 审核不通过，流程已终止。"},
            "stream": False,
        })
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })
        return
    else:
        # Revision Feedback
        feedback = action
        current_agent_name = current_node.replace("agent_", "").upper()
        
        # Save and broadcast user feedback message to the chat
        feedback_msg = f"🔄 [HIL 反馈] 针对 {current_agent_name} 的修改意见：\n{feedback}"
        save_message(conversation_id, "user", {"text": feedback_msg}, streaming=False)
        await manager.broadcast(conversation_id, {
            "type": "message",
            "conversation_id": conversation_id,
            "sender": "user",
            "content": {"text": feedback_msg},
            "stream": False,
        })
        
        # Set next_node back to current_node to re-run, and record feedback
        state_data[f"{current_node}_feedback"] = feedback
        if current_node in state_data.get("completed_nodes", []):
            state_data["completed_nodes"].remove(current_node)
        start_node = current_node

    # Run execution in background task
    stop_event = asyncio.Event()
    _stop_events[conversation_id] = stop_event
    
    trace = metrics.start_trace(
        task_id=str(_uuid.uuid4())[:8],
        conversation_id=conversation_id,
        user_input=original_prompt,
    )
    
    try:
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": True,
        })
        
        if conversation_id in _graph_builders:
            graph = _graph_builders[conversation_id](conversation_id, original_prompt, trace, stop_event)
        else:
            graph = _build_group_chat_graph(conversation_id, original_prompt, trace, stop_event)
        await graph.run(state_data, conversation_id, stop_event, start_node=start_node)
    finally:
        trace.finish()
        _stop_events.pop(conversation_id, None)
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })


async def _run_user_message_flow(conversation_id: str, text: str, target_agent: str | None):
    """Background generation flow for a plain user message (group or auto-routed)."""
    import uuid as _uuid
    stop_event = asyncio.Event()
    _stop_events[conversation_id] = stop_event

    # Start trace
    trace = metrics.start_trace(
        task_id=str(_uuid.uuid4())[:8],
        conversation_id=conversation_id,
        user_input=text,
    )

    try:
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": True,
        })

        # ---- Harness 拦截：复杂任务进入辩论沙盒 ----
        intercepted = await try_intercept_with_harness(
            conversation_id, text, llm_client, manager
        )
        if intercepted:
            return

        # User may have stopped during harness — skip downstream agents
        if stop_event.is_set():
            return

        is_group = not target_agent
        if is_group and not stop_event.is_set():
            graph = _build_group_chat_graph(conversation_id, text, trace, stop_event)
            # 4. Run StateGraph orchestration passing the original prompt for recovery resilience
            await graph.run({"original_prompt": text}, conversation_id, stop_event)
    finally:
        trace.finish()
        _stop_events.pop(conversation_id, None)
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })


async def _stream_agent_reply(conversation_id: str, agent, user_text: str, stop_event: asyncio.Event = None, context: str = "") -> tuple[list[str], str]:
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
                    print(f"[STOP] breaking stream loop for agent={agent.agent_id}", flush=True)
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
                    code_match = re.search(r'```(\w*)\s*\n?(.*?)```', buffer, re.DOTALL)
                    if not code_match:
                        break
                    lang = code_match.group(1) or "html"
                    code = code_match.group(2).strip()
                    
                    # 自动拦截代码并注册为交付物 Artifact（异步线程存储，保障高吞吐）
                    from app.core.database import save_artifact
                    await asyncio.to_thread(save_artifact, conversation_id, agent.agent_id, lang, code)

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

        # 将质检评分和沙盒运行状态自动绑定并反写回刚才匹配的所有交付件 Artifacts 中
        try:
            report_data = eval_result.get("report") or {}
            sandbox_data = report_data.get("sandbox_run") or {}
            sandbox_status = "skipped"
            sandbox_output = None
            if sandbox_data:
                sandbox_status = "success" if sandbox_data.get("status") == "success" else "failed"
                sandbox_output = sandbox_data.get("stderr") or sandbox_data.get("stdout")

            from app.core.database import update_latest_artifact_quality
            await asyncio.to_thread(
                update_latest_artifact_quality,
                conversation_id,
                agent.agent_id,
                eval_result.get("total_score", 100),
                sandbox_status,
                sandbox_output
            )
        except Exception as e_art:
            logger.error(f"Error updating artifact quality metrics: {e_art}")

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

def _remove_custom_agent(agent_id: str):
    """Delete a custom agent from DB, AGENTS dict, and its conversation."""
    AGENTS.pop(agent_id, None)
    delete_custom_agent(agent_id)


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


