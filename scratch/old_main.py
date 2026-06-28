import json
import os
import re
import uuid
import asyncio
from pydantic import BaseModel
from typing import Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
)


_BACKGROUND_TASKS: set[asyncio.Task] = set()

def create_tracked_task(coro, name: str = None) -> asyncio.Task:
    """鍒涘缓骞跺己寮曠敤涓€涓悗鍙?asyncio 浠诲姟锛岄槻姝㈣ GC 鍨冨溇鍥炴敹鍣ㄧ绉橀攢姣?""
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


# get_hil_settings imported from app.core.config_persistence

# _save_hil_settings replaced by save_hil_settings from config_persistence

from app.agents.pm import PMAgent
from app.agents.frontend import FrontendAgent
from app.agents.backend_agent import BackendAgent
from app.agents.tester import TesterAgent
from app.agents.devops import DevopsAgent
from app.agents.designer import DesignerAgent
from app.agents.builder import AgentBuilderAgent
from app.agents.custom import CustomAgent, AVAILABLE_TOOLS
import app.tools  # noqa: F401 鈥?trigger auto-registration of runtime tools

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run background autonomous daemon
    from app.services.daemon_scheduler import daemon_scheduler
    daemon_scheduler.start()
    
    yield
    
    # Shutdown: Clean resources and stop background tasks
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

# ---- 鏂囦欢涓婁紶鐩綍 ----
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 鍏ㄥ眬 API 閴存潈 / 鏈湴 Localhost 闃茬伀澧欎腑闂翠欢 ----
from fastapi import Request, status
from fastapi.responses import JSONResponse

@app.middleware("http")
async def api_security_middleware(request: Request, call_next):
    path = request.url.path
    # 璞佸厤 Swagger UI 鏂囨。銆佸叕鍏遍潤鎬佽祫婧愬拰 Webhook 鍥炶皟鎺ュ彛鐨勫畨鍏ㄧ瓥鐣?    if path in ("/", "/docs", "/openapi.json", "/redoc", "/api/health") or path.startswith("/api/webhook/callback/") or path.startswith("/uploads/"):
        return await call_next(request)

    # 浠呴拡瀵逛互 /api 寮€澶寸殑鍐呴儴 API 璺敱杩涜闃叉姢
    if not path.startswith("/api"):
        return await call_next(request)

    # 1. 鑻ラ厤缃簡澶栭儴閴存潈瀵嗛挜 AGENTHUB_API_SECRET锛屽紑鍚己鍒?Bearer Token 鏍￠獙
    if settings.api_secret:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Unauthorized: Missing or invalid Authorization header"}
            )
        token = auth_header.split(" ", 1)[1]
        if token != settings.api_secret:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Unauthorized: Invalid API secret token"}
            )
    else:
        # 2. 鑻ユ湭閰嶇疆澶栭儴閴存潈瀵嗛挜锛岄粯璁ゅ紑鍚湰鍦?Localhost 绾墿鐞嗙幆鍥為槻鐏锛屾嫆缁濆眬鍩熺綉鎴栧叕缃戝閮ㄨ闂?        client_host = request.client.host if request.client else None
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": f"Forbidden: Access from external IP '{client_host}' is blocked. To enable, configure AGENTHUB_API_SECRET in the environment."}
            )

    return await call_next(request)


from app.services.agent_registry import agent_registry
AGENTS = agent_registry._agents

# Stop events per conversation 鈥?set to cancel ongoing generation
_stop_events: dict[str, asyncio.Event] = {}

app.include_router(agents_router.router, prefix="/api")
app.include_router(uploads_router.router)
app.include_router(settings_router.router, prefix="/api")
app.include_router(cron_router.router, prefix="/api")
app.include_router(workflows_router.router, prefix="/api")
app.include_router(mcp_router.router, prefix="/api")

init_db()




def _load_llm_config():
    load_llm_config(llm_client, settings)


def _save_llm_config():
    save_llm_config(llm_client, settings)


_load_llm_config()




@app.get("/")
async def root():
    return {"name": "AgentHub API", "version": "1.0.0", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "agents": list(AGENTS.keys())}


# ---- MULTI-CHANNEL WEBHOOK CALLBACK ENDPOINTS ----
from fastapi import Request, HTTPException

@app.post("/api/webhook/callback/slack")
async def slack_webhook_callback(request: Request):
    """Slack interactive actions callback endpoint."""
    try:
        # 1. Fetch headers and body bytes for cryptographic signature verification
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")
        body_bytes = await request.body()
        
        # 2. Verify Slack signature using configured Signing Secret
        signing_secret = os.environ.get("AGENTHUB_SLACK_SIGNING_SECRET")
        if signing_secret:
            if not timestamp or not signature:
                raise HTTPException(status_code=401, detail="Missing Slack verification headers")
            
            from app.services.webhook_gateway import verify_slack_signature
            if not verify_slack_signature(signing_secret, body_bytes, timestamp, signature):
                raise HTTPException(status_code=403, detail="Invalid Slack signature")
        else:
            raise HTTPException(status_code=503, detail="Slack webhook not configured. Set AGENTHUB_SLACK_SIGNING_SECRET to enable.")

        # 3. Parse payload from form-data URL encoded string or direct JSON
        import urllib.parse
        body_str = body_bytes.decode('utf-8')
        payload = None
        
        if body_str.startswith("payload="):
            parsed = urllib.parse.parse_qs(body_str)
            payload_str = parsed.get("payload", [None])[0]
            if payload_str:
                payload = json.loads(payload_str)
        
        if not payload:
            try:
                payload = json.loads(body_str)
            except json.JSONDecodeError:
                pass
                
        if not payload:
            return {"success": False, "error": "Invalid form-data or JSON payload"}
            
        from app.services.webhook_gateway import webhook_gateway
        res = await webhook_gateway.handle_slack_callback(payload)
        return res
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/webhook/callback/telegram")
async def telegram_webhook_callback(request: Request):
    """Telegram inline keyboard button click callback endpoint."""
    try:
        # 1. Fetch token and verify source authentication
        received_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        secret_token = os.environ.get("AGENTHUB_TELEGRAM_SECRET_TOKEN")
        
        if secret_token:
            if not received_token:
                raise HTTPException(status_code=401, detail="Missing Telegram verification token")
            
            from app.services.webhook_gateway import verify_telegram_secret_token
            if not verify_telegram_secret_token(secret_token, received_token):
                raise HTTPException(status_code=403, detail="Invalid Telegram secret token")
        else:
            raise HTTPException(status_code=503, detail="Telegram webhook not configured. Set AGENTHUB_TELEGRAM_SECRET_TOKEN to enable.")

        payload = await request.json()
        from app.services.webhook_gateway import webhook_gateway
        res = await webhook_gateway.handle_telegram_callback(payload)
        return res
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/conversations")
async def list_conversations():
    return get_conversations()


@app.get("/api/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, limit: int = 100):
    return get_messages(conversation_id, limit)


@app.delete("/api/conversations/{conversation_id}/messages")
async def delete_messages(conversation_id: str):
    clear_messages(conversation_id)
    return {"status": "cleared"}


@app.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    # ---- WebSocket IP/Token 閴存潈 ----
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

            # Handle stop generation 鈥?must be processed without blocking on
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

            # Handle harness verdict (user瑁佸喅鎸囦护)
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
            effective_prompt = f"{text}\n\n馃攧 浜哄伐瀹℃牳鍙嶉鎰忚锛岃閽堝浠ヤ笅鎰忚淇敼鍒氭墠鐨勪唬鐮?缁撴灉锛歕n{feedback}"
        
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
            effective_prompt = f"{text}\n\n馃攧 浜哄伐瀹℃牳鍙嶉鎰忚锛岃閽堝浠ヤ笅鎰忚淇敼鍒氭墠鐨勪唬鐮?缁撴灉锛歕n{feedback}"
        
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
            effective_prompt = f"{text}\n\n馃攧 浜哄伐瀹℃牳鍙嶉鎰忚锛岃閽堝浠ヤ笅鎰忚淇敼鍒氭墠鐨勪唬鐮?缁撴灉锛歕n{feedback}"
        
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
            effective_prompt = f"{text}\n\n馃攧 浜哄伐瀹℃牳鍙嶉鎰忚锛岃閽堝浠ヤ笅鎰忚淇敼鍒氭墠鐨勪唬鐮?缁撴灉锛歕n{feedback}"
        
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
            effective_prompt = f"{text}\n\n馃攧 浜哄伐瀹℃牳鍙嶉鎰忚锛岃閽堝浠ヤ笅鎰忚淇敼鍒氭墠鐨勪唬鐮?缁撴灉锛歕n{feedback}"
        
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
            effective_prompt = f"{text}\n\n馃攧 浜哄伐瀹℃牳鍙嶉鎰忚锛岃閽堝浠ヤ笅鎰忚淇敼鍒氭墠鐨勪唬鐮?缁撴灉锛歕n{feedback}"
        
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
    SPEAKER_SELECTION_SYSTEM_PROMPT = """浣犳槸涓€涓櫤鑳戒綋缇よ亰鍗忚皟鍣?(Group Chat Coordinator)銆?鏍规嵁褰撳墠鐨勫璇濆巻鍙插拰鍚勪釜鍊欓€夋櫤鑳戒綋 (Agents) 鐨勮鑹叉弿杩帮紝鍒ゆ柇涓嬩竴涓渶閫傚悎鍙戣█鐨勬櫤鑳戒綋鏄皝銆?
鍊欓€夋櫤鑳戒綋鍒楄〃锛?{candidates_info}

瑙勫垯锛?1. 鍙兘浠庝笂闈㈢殑鍊欓€夋櫤鑳戒綋 ID 涓€夋嫨涓€涓紝鎴栬€呰緭鍑?"END" 琛ㄧず瀵硅瘽宸插渾婊＄粨鏉燂紙鎵€鏈夊紑鍙?閮ㄧ讲浠诲姟鍧囧凡濡ュ杽瀹屾垚锛屾病鏈夐仐鐣欓棶棰橈級銆?2. 璇峰彧杈撳嚭涓嬩竴涓彂瑷€鐨勬櫤鑳戒綋 ID锛堜緥濡?"agent_frontend"锛夋垨 "END"锛屼笉瑕侀檮甯︿换浣曞叾浠栬В閲娿€佹爣鐐规垨 markdown 鏍煎紡銆?3. 蹇呴』瀹㈣鍒嗘瀽褰撳墠瀵硅瘽杩涘害銆傚鏋滃綋鍓嶆楠ゆ槸 PM 鍒嗗伐涓旈渶瑕佸墠绔紑鍙戯紝涓嬩竴姝ラ€氬父鏄?`agent_frontend`锛涘鏋滃垰鎵嶅凡缁忓畬鎴愪簡缂栫爜锛屼笅涓€姝ラ€氬父鏄?`agent_tester` 杩愯娴嬭瘯锛涜嫢娴嬭瘯瀹屾瘯娌℃湁闂锛屽垯鏄?`agent_devops` 閮ㄧ讲銆傚鏋滄墍鏈夎鍒掔殑浠诲姟閮藉凡缁忓畬鎴愶紝杈撳嚭 "END"銆?"""

    async def select_next_speaker(state: dict) -> str:
        import logging
        sg_logger = logging.getLogger("state_graph")
        
        assigned = state.get("assigned_agents", [])
        candidates = assigned if assigned else ["agent_designer", "agent_frontend", "agent_backend", "agent_tester", "agent_devops"]
        
        # Filter out completed nodes to ensure progress along the DAG
        remaining_candidates = [c for c in candidates if c not in state.get("completed_nodes", [])]
        
        if not remaining_candidates:
            return "END"
            
        # 馃挕 [Heuristic Lightweight Router Intercept (0 Latency, 0 Token Cost)]
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
             
        user_prompt = f"--- 瀵硅瘽鍘嗗彶 ---\n{history_text}\n\n璇峰喅瀹氫笅涓€涓渶閫傚悎鍙戣█鐨勬櫤鑳戒綋銆?
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
        "content": {"text": f"馃攧 妫€娴嬪埌鏈嶅姟鍣ㄩ噸鍚€傛鍦ㄤ粠妫€鏌ョ偣鎭㈠娴佺▼骞舵墽琛屽鏍稿喅绛? **{action}**..."},
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
                "content": {"text": "鉁?瀹℃牳閫氳繃銆傛祦绋嬪渾婊＄粨鏉燂紒"},
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
            "content": {"text": "馃洃 瀹℃牳涓嶉€氳繃锛屾祦绋嬪凡缁堟銆?},
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
        feedback_msg = f"馃攧 [HIL 鍙嶉] 閽堝 {current_agent_name} 鐨勪慨鏀规剰瑙侊細\n{feedback}"
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

        # ---- Harness 鎷︽埅锛氬鏉備换鍔¤繘鍏ヨ京璁烘矙鐩?----
        intercepted = await try_intercept_with_harness(
            conversation_id, text, llm_client, manager
        )
        if intercepted:
            return

        # User may have stopped during harness 鈥?skip downstream agents
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
        effective_text = f"PM 鐨勪换鍔℃媶瑙ｏ細\n{context}\n\n鐢ㄦ埛鍘熷闇€姹傦細{user_text}"

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
                "content": {"text": f"鈿?姝ｅ湪骞惰鐢熸垚 {quality_gate.best_of_n} 涓€欓€夋柟妗堬紝鎷╀紭杈撳嚭..."},
                "stream": True,
            })

            async def _on_progress(idx, status):
                await manager.broadcast(conversation_id, {
                    "type": "message",
                    "conversation_id": conversation_id,
                    "sender": agent.agent_id,
                    "content": {"text": f"馃弳 {status}"},
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
                # Don't strip [options:...], [clarify:...], [ask_user:...] 鈥?let frontend handle them

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
                    
                    # 鑷姩鎷︽埅浠ｇ爜骞舵敞鍐屼负浜や粯鐗?Artifact锛堝紓姝ョ嚎绋嬪瓨鍌紝淇濋殰楂樺悶鍚愶級
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
                # 鑺傛祦鎺у埗锛氭渶蹇瘡 80ms 骞挎挱涓€娆★紝閬垮厤鍒峰睆
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
                    full_text = "锛堝凡鐢熸垚浠ｇ爜锛岃鏌ョ湅鍙充晶闈㈡澘锛?

    except Exception as e:
        err_msg = f"[Agent 鍥炲鍑洪敊: {type(e).__name__}: {str(e)[:200]}]"
        if not full_text:
            full_text = err_msg
        else:
            full_text += f"\n[鍑洪敊: {str(e)[:100]}]"
        raw_text += f"\n{err_msg}"

    stopped = stop_event and stop_event.is_set()

    if not full_text:
        full_text = "锛堝凡鍋滄鐢熸垚锛? if stopped else "锛堝凡鐢熸垚浠ｇ爜锛岃鏌ョ湅鍙充晶闈㈡澘锛?

    if not raw_text:
        raw_text = full_text

    # ---- 鑷姩鍙嶆€濅笌閲嶈瘯 (Self-Reflection & Retry) ----
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
        # 鐢ㄨ瘎浼板悗鐨勬渶缁堣緭鍑烘浛鎹㈠師濮嬭緭鍑?        if eval_result["final_output"]:
            raw_text = eval_result["final_output"]
            full_text = eval_result["final_output"].strip()

        # 灏嗚川妫€璇勫垎鍜屾矙鐩掕繍琛岀姸鎬佽嚜鍔ㄧ粦瀹氬苟鍙嶅啓鍥炲垰鎵嶅尮閰嶇殑鎵€鏈変氦浠樹欢 Artifacts 涓?        try:
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

    # Don't persist LLM error responses 鈥?they pollute history and cause the
    # model to parrot the error string back on the next turn.
    is_llm_error = ("[LLM Error" in raw_text) or ("[LLM 璋冪敤鍑洪敊" in raw_text) or ("[Agent 鍥炲鍑洪敊" in raw_text)
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


# ---- File Upload API ----

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    # 鐢熸垚鍞竴鏂囦欢鍚嶏紝淇濈暀鍘熷鎵╁睍鍚?    ext = os.path.splitext(file.filename or "")[1]
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


# ---- Quality Gate API ----

class QualityGateSettings(BaseModel):
    enabled: bool = True
    max_retries: int = 1
    use_llm_judge: bool = False
    best_of_n: int = 1  # 1=disabled, 3=generate 3 candidates pick best


@app.get("/api/settings/quality")
async def get_quality_settings():
    return {
        "enabled": quality_gate.enabled,
        "max_retries": quality_gate.max_retries,
        "use_llm_judge": quality_gate.use_llm_judge,
        "best_of_n": quality_gate.best_of_n,
    }


@app.post("/api/settings/quality")
async def update_quality_settings(s: QualityGateSettings):
    quality_gate.enabled = s.enabled
    quality_gate.max_retries = s.max_retries
    quality_gate.use_llm_judge = s.use_llm_judge
    quality_gate.best_of_n = s.best_of_n
    return {"status": "ok", "best_of_n": quality_gate.best_of_n}


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
            api_key = cfg.get("api_key", "")
            api_key = deobfuscate_key(api_key)
            stt_client.configure(
                api_key=api_key,
                base_url=cfg.get("base_url", ""),
                model=cfg.get("model", "whisper-1"),
                language=cfg.get("language", "zh"),
            )
    except Exception:
        pass


def _save_stt_config():
    os.makedirs(os.path.dirname(STT_CONFIG_PATH), exist_ok=True)
    obfuscated_api_key = obfuscate_key(stt_client.api_key)
    with open(STT_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "api_key": obfuscated_api_key,
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
        return {"error": "璇煶璇嗗埆鏈厤缃€傝鍦ㄨ缃腑閰嶇疆 STT API 鎴?LLM API銆?, "text": ""}

    try:
        text = await stt_client.transcribe(audio_bytes, filename)
        return {"text": text, "status": "ok"}
    except Exception as e:
        return {"error": f"璇煶璇嗗埆澶辫触: {str(e)[:200]}", "text": ""}


# ---- Code Sandbox API ----

class CodeRunRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 10
    stdin: str = ""


@app.post("/api/sandbox/run")
async def sandbox_run(req: CodeRunRequest):
    """Execute code in a sandboxed subprocess and return results."""
    result = await execute_code(
        code=req.code,
        language=req.language,
        timeout=min(req.timeout, 30),  # cap at 30s
        stdin_data=req.stdin,
    )
    # Record metrics
    metrics.record_sandbox(req.language, result.status, result.duration_ms)
    return result.to_dict()


class CodeHealRequest(BaseModel):
    code: str
    language: str
    error_output: str

@app.post("/api/sandbox/heal")
async def sandbox_heal(req: CodeHealRequest):
    """Ask backend agent to heal broken code."""
    from app.core.llm_client import llm_client
    
    prompt = f"""浣犳槸涓€涓笓闂ㄤ慨澶嶄唬鐮佹姤閿欑殑 AI 涓撳銆?鐢ㄦ埛杩愯浜嗕竴娈?{req.language} 浠ｇ爜锛屼絾鏄け璐ヤ簡銆?璇峰垎鏋愭姤閿欏師鍥狅紝骞跺彧杈撳嚭淇鍚庣殑瀹屾暣鍙繍琛屼唬鐮併€?涓嶈浠讳綍澶氫綑鐨勮В閲婏紝蹇呴』鍖呭惈鍦?```{req.language} ... ``` 浠ｇ爜鍧椾腑銆?
### 鍘熷浠ｇ爜
```{req.language}
{req.code}
```

### 鎶ラ敊淇℃伅
```text
{req.error_output}
```
"""
    
    response = ""
    # 璋冪敤 LLM 鐢熸垚淇浠ｇ爜
    async for chunk in llm_client.chat_stream([{"role": "user", "content": prompt}], system="浣犲彧鑳借緭鍑轰慨澶嶅悗鐨勪唬鐮佸潡銆?):
        response += chunk
        
    import re
    # 鎻愬彇浠ｇ爜鍧?    match = re.search(r"```[a-zA-Z]*\n(.*?)```", response, re.DOTALL)
    healed_code = match.group(1).strip() if match else response.strip()
    
    return {"healed_code": healed_code}


# ---- Artifacts API ----

@app.get("/api/artifacts")
async def list_artifacts(conversation_id: str = None, limit: int = 50):
    """List generated code artifacts from SQLite DB."""
    from app.core.database import get_artifacts
    artifacts = await asyncio.to_thread(get_artifacts, conversation_id, limit)
    return artifacts


# ---- Metrics / Dashboard API ----

@app.get("/api/metrics")
async def get_metrics():
    """Get all metrics for the evaluation dashboard."""
    return metrics.get_dashboard_data()


@app.get("/api/metrics/traces")
async def get_traces(limit: int = 20):
    """Get recent execution traces."""
    traces = metrics.traces[-limit:]
    return [t.to_dict() for t in traces]


# ---- Benchmark API ----

@app.get("/api/benchmark/cases")
async def list_benchmark_cases():
    """List available benchmark test cases."""
    return [{"id": c.id, "name": c.name, "agent_id": c.agent_id, "category": c.category} for c in BENCHMARK_CASES]


@app.post("/api/benchmark/run")
async def start_benchmark():
    """Start a benchmark run (async). Poll /api/benchmark/status for progress."""
    current = get_current_run()
    if current and current.status == "running":
        return {"error": "宸叉湁 benchmark 姝ｅ湪杩愯", "run_id": current.run_id}

    async def _run():
        await run_benchmark(
            agents=AGENTS,
            quality_gate=quality_gate,
        )

    create_tracked_task(_run(), name="benchmark_run")
    return {"status": "started", "message": "Benchmark 宸插惎鍔紝璇疯疆璇?/api/benchmark/status"}


@app.get("/api/benchmark/status")
async def benchmark_status():
    """Get current benchmark run status and results."""
    current = get_current_run()
    if not current:
        return {"status": "idle", "message": "娌℃湁姝ｅ湪杩愯鐨?benchmark"}
    return current.to_dict()


@app.post("/api/deploy/{conversation_id}")
async def deploy_project(conversation_id: str):
    create_tracked_task(_simulate_deploy(conversation_id), name=f"deploy_{conversation_id}")
    return {"status": "started"}


async def _simulate_deploy(conversation_id: str):
    logs = [
        "馃殌 姝ｅ湪鍒濆鍖栦簯閮ㄧ讲娌欑洅鐜...",
        "馃摝 妫€鏌ュ伐浣滅洰褰曞苟鎷夊彇鏈€鏂颁緷璧栧寘...",
        "馃И 杩愯鑷姩鍖栧啋鐑熸祴璇?(Tester Agent 楠岃瘉閫氳繃)...",
        "馃惓 鏋勫缓鐢熶骇鐜 Docker 瀹瑰櫒闀滃儚...",
        "馃惓 姝ｅ湪鍚戣繙绔暅鍍忎粨搴撴帹閫侀暅鍍?agenthub/app:latest...",
        "鈽革笍 Kubernetes 璧勬簮璋冨害涓庡仴搴风姸鎬佹鏌?..",
        "馃寧 鍩熷悕瑙ｆ瀽涓?SSL 璇佷功(Let's Encrypt) 鑷姩閰嶇疆...",
        "馃帀 涓€閿儴缃叉垚鍔燂紒闈欐€佽祫婧愪笌 API 鏈嶅姟鍧囧凡涓婄嚎銆?
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
        "content": {"text": f"鉁?鎶ュ憡锛侀」鐩凡鎴愬姛涓€閿儴缃蹭笂绾匡紒\n\n馃實 绾夸笂璁块棶鍦板潃锛歿url}\n鈿狅笍 鐢熶骇闆嗙兢杩愯骞崇ǔ锛孲SL 璇佷功閰嶇疆姝ｇ‘锛孋DN 鍒嗗彂宸插叏鐞冪敓鏁堬紒"},
        "stream": False
    })


# ---- Background Autonomous Tasks REST API ----



# ---- Knowledge Base (RAG) REST API ----

@app.get("/api/knowledge")
async def list_knowledge_docs():
    from app.core.database import get_knowledge_docs
    from app.core.rag_engine import rag_engine
    docs = get_knowledge_docs()
    stats = rag_engine.get_stats()
    return {"status": "ok", "docs": docs, "stats": stats}


@app.post("/api/knowledge/upload")
async def upload_knowledge_doc(file: UploadFile = File(...)):
    from app.core.document_parser import DocumentParser
    from app.core.rag_engine import rag_engine
    from app.core.database import save_knowledge_doc

    if not DocumentParser.is_supported(file.filename):
        return {"status": "error", "message": f"涓嶆敮鎸佺殑鏂囦欢绫诲瀷: {file.filename}"}

    doc_id = f"kb_{uuid.uuid4().hex[:8]}"
    content = await file.read()

    # 淇濆瓨鏂囦欢鍒扮鐩?    kb_dir = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge")
    os.makedirs(kb_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    stored_path = os.path.join(kb_dir, f"{doc_id}{ext}")
    with open(stored_path, "wb") as f:
        f.write(content)

    # 鎻愬彇鏂囨湰
    text = DocumentParser.extract_text(stored_path, file.content_type or "")
    if not text:
        os.remove(stored_path)
        return {"status": "error", "message": "鏃犳硶浠庢枃浠朵腑鎻愬彇鏂囨湰鍐呭"}

    # 鍒嗗潡鍐欏叆鍚戦噺搴?    chunk_count = rag_engine.add_document(doc_id, text, metadata={
        "source": "upload",
        "filename": file.filename,
    })

    # 璁板綍鍒?SQLite
    save_knowledge_doc(
        doc_id=doc_id,
        filename=file.filename,
        file_path=stored_path,
        content_type=file.content_type or "",
        chunk_count=chunk_count,
        char_count=len(text),
    )

    return {
        "status": "ok",
        "doc_id": doc_id,
        "filename": file.filename,
        "chunk_count": chunk_count,
        "char_count": len(text),
        "message": f"鏂囨。宸插叆搴擄紝鐢熸垚 {chunk_count} 涓煡璇嗗潡",
    }


@app.delete("/api/knowledge/{doc_id}")
async def delete_knowledge_doc_endpoint(doc_id: str):
    from app.core.rag_engine import rag_engine
    from app.core.database import delete_knowledge_doc, get_knowledge_docs

    # 鍒犻櫎鍚戦噺搴撲腑鐨勫垎鍧?    rag_engine.remove_document(doc_id)

    # 鍒犻櫎鐗╃悊鏂囦欢
    docs = get_knowledge_docs()
    doc = next((d for d in docs if d["id"] == doc_id), None)
    if doc and doc.get("file_path") and os.path.isfile(doc["file_path"]):
        os.remove(doc["file_path"])

    # 鍒犻櫎鏁版嵁搴撹褰?    delete_knowledge_doc(doc_id)
    return {"status": "ok", "message": "鐭ヨ瘑鏂囨。宸插垹闄?}


@app.post("/api/knowledge/query")
async def query_knowledge(body: dict):
    from app.core.rag_engine import rag_engine
    query = body.get("query", "")
    top_k = body.get("top_k", 5)
    if not query.strip():
        return {"status": "error", "message": "鏌ヨ鍐呭涓嶈兘涓虹┖"}

    hits = rag_engine.query(query, top_k=top_k)
    return {"status": "ok", "results": hits}


# ---- Langflow Workflow Serialization & Compiler REST APIs ----

@app.get("/api/workflow/export/{conversation_id}")
async def export_workflow(conversation_id: str):
    """Export current workflow configuration, custom agents, and settings as JSON."""
    hil = get_hil_settings()
    custom_agents_data = []
    for ca in get_custom_agents():
        custom_agents_data.append(ca)
        
    workflow_data = {
        "conversation_id": conversation_id,
        "llm": {
            "provider": llm_client.provider,
            "base_url": llm_client.base_url,
            "model": llm_client.model,
            "temperature": llm_client.temperature,
            "max_tokens": llm_client.max_tokens,
        },
        "hil": hil,
        "custom_agents": custom_agents_data
    }
    return workflow_data


@app.post("/api/workflow/import")
async def import_workflow(body: dict):
    """Import and reconstruct workflow custom agents and settings from JSON config."""
    custom_agents = body.get("custom_agents", [])
    imported_count = 0
    for ca in custom_agents:
        aid = ca.get("agent_id")
        if aid:
            await agent_registry.register_custom_agent(ca)
            imported_count += 1
            
    hil = body.get("hil")
    if hil:
        save_hil_settings(hil)
        
    llm = body.get("llm")
    if llm:
        llm_client.configure(
            provider=llm.get("provider", "openai"),
            api_key=llm_client.api_key, # preserve current api key
            base_url=llm.get("base_url", ""),
            model=llm.get("model", ""),
            temperature=llm.get("temperature"),
            max_tokens=llm.get("max_tokens"),
        )
        _save_llm_config()
        
    return {"status": "ok", "imported_agents_count": imported_count}


@app.post("/api/workflow/compile/{conversation_id}")
async def compile_workflow(conversation_id: str):
    """Compile visually designed multi-agent team and guards into a standalone, 0-dependency Python script."""
    # Serialize agents data
    agents_str_dict = {}
    for aid, agent in AGENTS.items():
        agents_str_dict[aid] = {
            "name": agent.name,
            "avatar": agent.avatar,
            "role": agent.role,
            "style": agent.style,
            "system_prompt": agent.system_prompt,
            "description": agent.description
        }
        
    hil = get_hil_settings()
    
    # Standalone code template
    code_content = f"""# -*- coding: utf-8 -*-
\"\"\"
Generated Standalone StateGraph Agent Team - Compiler Plan L
Powered by AgentHub Visual-to-Code Compiler
\"\"\"

import asyncio
import json
import os
import re
import sys
import logging
import argparse
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("exported_team")

# ---- EMBEDDED STATEGRAPH ENGINE ----
class StateGraph:
    def __init__(self):
        self.nodes = {{}}
        self.edges = {{}}
        self.conditional_edges = {{}}
        self.guards = {{}}
        
    def add_node(self, name, func):
        self.nodes[name] = func
        
    def add_edge(self, from_node, to_node):
        self.edges[from_node] = to_node
        
    def add_conditional_edge(self, from_node, router_func):
        self.conditional_edges[from_node] = router_func

    def add_guard(self, node_name, guard_func, error_fallback_node=None):
        if node_name not in self.guards:
            self.guards[node_name] = []
        self.guards[node_name].append((guard_func, error_fallback_node))
        
    async def run(self, initial_state, human_input_mode="NEVER", cooldown_steps=2):
        state = initial_state.copy()
        state.setdefault("completed_nodes", [])
        current_node = "agent_pm"
        
        print("\\n=== [StateGraph] Starting Standalone Execution ===")
        
        while current_node and current_node != "END":
            print(f"\\n馃煝 [StateGraph] Active Node: {{current_node.upper()}}")
            
            # Execute Node
            node_func = self.nodes.get(current_node)
            if not node_func:
                break
                
            if isinstance(node_func, StateGraph):
                update = await node_func.run(state, human_input_mode, cooldown_steps)
            else:
                update = await node_func(state)
                
            if update and isinstance(update, dict):
                state.update(update)
            if current_node not in state["completed_nodes"]:
                state["completed_nodes"].append(current_node)
                
            # Resolve Next Node
            next_node = None
            if current_node in self.conditional_edges:
                router = self.conditional_edges[current_node]
                if asyncio.iscoroutinefunction(router):
                    next_node = await router(state)
                else:
                    res = router(state)
                    if asyncio.iscoroutine(res):
                        next_node = await res
                    else:
                        next_node = res
            elif current_node in self.edges:
                next_node = self.edges[current_node]
                
            # Transition Guards Check
            if next_node and next_node != "END" and next_node in self.guards:
                failed_fallback = None
                for guard, fallback in self.guards[next_node]:
                    if not guard(state):
                        failed_fallback = fallback or "agent_pm"
                        break
                if failed_fallback:
                    print(f"\\n鈿狅笍 [鐘舵€佸畧鍗己鎷︽埅] 鏅鸿兘浣?{{next_node.upper()}} 鏈弧瓒冲噯鍏ュ墠缃潯浠讹紒")
                    print(f"馃攧 宸插畨鍏ㄨ嚜鍔ㄩ噸瀹氬悜鑷崇籂鍋忚妭鐐?{{failed_fallback.upper()}}銆?)
                    next_node = failed_fallback
                    
            # Human-in-the-loop Intercept Check
            if next_node and (human_input_mode == "ALWAYS" or (human_input_mode == "COOLDOWN" and len(state.get("completed_nodes", [])) % cooldown_steps == 0)):
                next_desc = next_node.upper() if next_node != "END" else "缁撴潫娴佺▼ (END)"
                print(f"\\n鈴?[HIL 鎷︽埅] 鏅鸿兘浣?{{current_node.upper()}} 杩愯瀹屾瘯銆傛槸鍚︽壒鍑嗗叾缁撴灉骞舵帹杩涜嚦 {{next_desc}}锛?)
                print("  1. Approve (鎵瑰噯骞舵帹杩?")
                print("  2. Terminate (缁堟娴佺▼)")
                print("  3. Feedback (杈撳叆淇敼鎰忚)")
                
                choice = input("璇烽€夋嫨 (1-3): ").strip()
                if choice == "2":
                    next_node = "END"
                elif choice == "3" or choice not in ("1", "2"):
                    feedback = input("璇疯緭鍏ヤ綘鐨勪慨鏀规剰瑙? ").strip() if choice == "3" else choice
                    print(f"馃攧 [HIL 鍙嶉] 娉ㄥ叆淇敼鎰忚锛岄噸璺?{{current_node.upper()}}...")
                    state[f"{{current_node}}_feedback"] = feedback
                    next_node = current_node
                    if current_node in state["completed_nodes"]:
                        state["completed_nodes"].remove(current_node)
                        
            current_node = next_node
            
        print("\\n=== [StateGraph] Finished Standalone Execution ===\\n")
        return state


# ---- EXPORTED CONFIGURATION ----
AGENTS = {json.dumps(agents_str_dict, ensure_ascii=False, indent=4)}
LLM_CONFIG = {{
    "provider": "{llm_client.provider}",
    "base_url": "{llm_client.base_url}",
    "model": "{llm_client.model}",
    "api_key": "{llm_client.api_key if llm_client.api_key else ''}"
}}

# ---- STANDALONE LLM CHAT CLIENT ----
class StandaloneLLMClient:
    async def chat_stream(self, messages, system=""):
        url = LLM_CONFIG["base_url"] or "https://api.openai.com/v1"
        key = LLM_CONFIG["api_key"]
        
        headers = {{
            "Authorization": f"Bearer {{key}}",
            "Content-Type": "application/json"
        }}
        
        payload_messages = []
        if system:
            payload_messages.append({{"role": "system", "content": system}})
        payload_messages.extend(messages)
        
        payload = {{
            "model": LLM_CONFIG["model"] or "gpt-4o",
            "messages": payload_messages,
            "stream": True
        }}
        
        target_url = url.rstrip("/") + "/chat/completions"
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", target_url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        yield f"\\n[LLM API Error {{response.status_code}}]\\n"
                        return
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                text = chunk["choices"][0]["delta"].get("content", "")
                                if text:
                                    yield text
                            except Exception:
                                pass
        except Exception as e:
            yield f"\\n[API Call Exception: {{e}}]\\n"

standalone_llm = StandaloneLLMClient()

# ---- RUNNER HELPERS ----
async def stream_agent_reply(agent_id, user_text, context=""):
    agent = AGENTS[agent_id]
    print(f"馃 **{{agent['name']}}** ({{agent['role']}}) 姝ｅ湪鎬濊€?..")
    
    messages = []
    if context:
        messages.append({{"role": "user", "content": f"PM 浠诲姟鎷嗚В锛歕\n{{context}}\\n\\n闇€姹傦細{{user_text}}"}} )
    else:
        messages.append({{"role": "user", "content": user_text}})
        
    full_prompt = agent["system_prompt"]
    
    full_response = ""
    async for chunk in standalone_llm.chat_stream(messages, system=full_prompt):
        sys.stdout.write(chunk)
        sys.stdout.flush()
        full_response += chunk
    print()
    
    assigned_agents = []
    for match in re.finditer(r'\\[assign:(\\w+)\\]', full_response):
        assigned_agents.append(match.group(1))
        
    return assigned_agents, full_response


# ---- STANDALONE DAG RUN DEFINITION ----
async def main_flow(task_text, human_input_mode, cooldown_steps):
    graph = StateGraph()
    
    async def run_pm(state):
        feedback = state.get("agent_pm_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n馃攧 浜哄伐鍙嶉锛歕\n{{feedback}}"
        assigned, pm_res = await stream_agent_reply("agent_pm", prompt)
        return {{"pm_response": pm_res, "assigned_agents": assigned, "agent_pm_feedback": ""}}
        
    async def run_designer(state):
        feedback = state.get("agent_designer_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n馃攧 浜哄伐鍙嶉锛歕\n{{feedback}}"
        _, res = await stream_agent_reply("agent_designer", prompt, context=state.get("pm_response", ""))
        return {{"designer_response": res, "agent_designer_feedback": ""}}

    async def run_frontend(state):
        feedback = state.get("agent_frontend_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n馃攧 浜哄伐鍙嶉锛歕\n{{feedback}}"
        _, res = await stream_agent_reply("agent_frontend", prompt, context=state.get("pm_response", ""))
        return {{"frontend_response": res, "agent_frontend_feedback": ""}}

    async def run_backend(state):
        feedback = state.get("agent_backend_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n馃攧 浜哄伐鍙嶉锛歕\n{{feedback}}"
        _, res = await stream_agent_reply("agent_backend", prompt, context=state.get("pm_response", ""))
        return {{"backend_response": res, "agent_backend_feedback": ""}}

    async def run_tester(state):
        feedback = state.get("agent_tester_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n馃攧 浜哄伐鍙嶉锛歕\n{{feedback}}"
        _, res = await stream_agent_reply("agent_tester", prompt, context=state.get("pm_response", ""))
        return {{"tester_response": res, "agent_tester_feedback": ""}}

    async def run_devops(state):
        feedback = state.get("agent_devops_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n馃攧 浜哄伐鍙嶉锛歕\n{{feedback}}"
        _, res = await stream_agent_reply("agent_devops", prompt, context=state.get("pm_response", ""))
        return {{"devops_response": res, "agent_devops_feedback": ""}}

    graph.add_node("agent_pm", run_pm)
    graph.add_node("agent_designer", run_designer)
    graph.add_node("agent_frontend", run_frontend)
    graph.add_node("agent_backend", run_backend)
    graph.add_node("agent_tester", run_tester)
    graph.add_node("agent_devops", run_devops)

    async def select_next_speaker(state):
        assigned = state.get("assigned_agents", [])
        candidates = assigned if assigned else ["agent_designer", "agent_frontend", "agent_backend", "agent_tester", "agent_devops"]
        remaining = [c for c in candidates if c not in state.get("completed_nodes", [])]
        
        if not remaining:
            return "END"
            
        # 馃挕 [Heuristic Lightweight Router Intercept (0 Latency, 0 Token Cost)]
        rule_speaker = None
        
        # Rule A: Single Choice
        if len(remaining) == 1:
            rule_speaker = remaining[0]
            print(f"\\n馃挕 [Heuristic Speaker Selection] Rule A: only one candidate remaining -> Selected '{{rule_speaker}}'")
            
        # Rule B: Linear SDLC Waterfall Inference
        else:
            completed = state.get("completed_nodes", [])
            last_completed = completed[-1] if completed else None
            
            if last_completed == "agent_pm":
                if "agent_designer" in remaining:
                    rule_speaker = "agent_designer"
                elif "agent_frontend" in remaining:
                    rule_speaker = "agent_frontend"
                elif "agent_backend" in remaining:
                    rule_speaker = "agent_backend"
            elif last_completed == "agent_designer":
                if "agent_frontend" in remaining:
                    rule_speaker = "agent_frontend"
                elif "agent_backend" in remaining:
                    rule_speaker = "agent_backend"
            elif last_completed in ("agent_frontend", "agent_backend"):
                frontend_done = "agent_frontend" in completed or "agent_frontend" not in remaining
                backend_done = "agent_backend" in completed or "agent_backend" not in remaining
                if frontend_done and backend_done:
                    if "agent_tester" in remaining:
                        rule_speaker = "agent_tester"
                else:
                    other = "agent_backend" if last_completed == "agent_frontend" else "agent_frontend"
                    if other in remaining:
                        rule_speaker = other
            elif last_completed == "agent_tester":
                if "agent_devops" in remaining:
                    rule_speaker = "agent_devops"
            elif last_completed == "agent_devops":
                rule_speaker = "END"
                
            if rule_speaker:
                print(f"\\n馃挕 [Heuristic Speaker Selection] Rule B: SDLC Waterfall Inference -> Selected '{{rule_speaker}}'")
                
        if rule_speaker:
            return rule_speaker

        print("\\n馃 [Speaker Selection] Non-deterministic state branching. Dispatching LLM Coordinator...")
        
        candidates_info = ""
        for cid in remaining:
            if cid in AGENTS:
                candidates_info += f"- ID: {{cid}}\\n  Name: {{AGENTS[cid]['name']}}\\n  Description: {{AGENTS[cid]['description']}}\\n\\n"
                
        system_prompt = f\"\"\"浣犳槸涓€涓櫤鑳戒綋缇よ亰鍗忚皟鍣?(Group Chat Coordinator)銆?鏍规嵁褰撳墠鐨勫璇濆巻鍙插拰鍚勪釜鍊欓€夋櫤鑳戒綋 (Agents) 鐨勮鑹叉弿杩帮紝鍒ゆ柇涓嬩竴涓渶閫傚悎鍙戣█鐨勬櫤鑳戒綋鏄皝銆?
鍊欓€夋櫤鑳戒綋鍒楄〃锛?{{candidates_info}}

瑙勫垯锛?1. 鍙兘浠庝笂闈㈢殑鍊欓€夋櫤鑳戒綋 ID 涓€夋嫨涓€涓紝鎴栬€呰緭鍑?"END" 琛ㄧず瀵硅瘽宸插渾婊＄粨鏉燂紙鎵€鏈夊紑鍙?閮ㄧ讲浠诲姟鍧囧凡濡ュ杽瀹屾垚锛屾病鏈夐仐鐣欓棶棰橈級銆?2. 璇峰彧杈撳嚭涓嬩竴涓彂瑷€鐨勬櫤鑳戒綋 ID锛堜緥濡?"agent_frontend"锛夋垨 "END"锛屼笉瑕侀檮甯︿换浣曞叾浠栬В閲娿€佹爣鐐规垨 markdown 鏍煎紡銆?3. 蹇呴』瀹㈣鍒嗘瀽褰撳墠瀵硅瘽杩涘害銆?\"\"\"
        user_prompt = f"璇峰喅瀹氫笅涓€涓渶閫傚悎鍙戣█鐨勬櫤鑳戒綋銆?
        
        selected = ""
        try:
            async for chunk in standalone_llm.chat_stream([{{"role": "user", "content": user_prompt}}], system=system_prompt):
                selected += chunk
            selected = selected.strip().strip("'\\"`").strip()
        except Exception:
            selected = ""
            
        if selected in remaining:
            return selected
        elif selected == "END":
            return "END"
        else:
            return remaining[0]

    graph.add_conditional_edge("agent_pm", select_next_speaker)
    graph.add_conditional_edge("agent_designer", select_next_speaker)
    graph.add_conditional_edge("agent_frontend", select_next_speaker)
    graph.add_conditional_edge("agent_backend", select_next_speaker)
    graph.add_conditional_edge("agent_tester", select_next_speaker)
    graph.add_edge("agent_devops", "END")

    graph.add_guard("agent_devops", lambda s: "agent_tester" in s.get("completed_nodes", []), "agent_tester")
    graph.add_guard("agent_tester", lambda s: any(n in s.get("completed_nodes", []) for n in ["agent_frontend", "agent_backend"]), "agent_frontend")

    await graph.run({{}}, human_input_mode=human_input_mode, cooldown_steps=cooldown_steps)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Exported Standalone Agent Team")
    parser.add_argument("--task", type=str, required=True, help="Task prompt for the agent team")
    parser.add_argument("--hil", type=str, default="{hil.get('human_input_mode', 'NEVER')}", choices=["NEVER", "ALWAYS", "COOLDOWN"], help="Human-in-the-loop mode")
    parser.add_argument("--cooldown", type=int, default={hil.get('cooldown_steps', 2)}, help="Cooldown steps for HIL")
    
    args = parser.parse_args()
    
    asyncio.run(main_flow(args.task, args.hil, args.cooldown))
"""
    return {"status": "ok", "filename": "exported_team.py", "code": code_content}

