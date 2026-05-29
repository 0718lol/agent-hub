import json
import os
import re
import uuid
import asyncio
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.websocket import manager
from app.core.database import (
    init_db, save_message, get_messages, get_conversations, clear_messages,
    save_custom_agent, get_custom_agents, delete_custom_agent, create_conversation,
)
from app.core.config import settings
from app.core.llm_client import llm_client
from app.core.quality_gate import quality_gate
from app.core.quality_retry import evaluate_and_retry
from app.core.prompt_engine import prompt_engine
from app.core.speech import stt_client
from app.core.sandbox import execute_code
from app.core.metrics import metrics
from app.core.benchmark import run_benchmark, get_current_run, BENCHMARK_CASES
from app.routers import agents as agents_router
from app.routers import uploads as uploads_router

LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "llm_config.json")
HIL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "hil_config.json")

def get_hil_settings() -> dict:
    try:
        if os.path.exists(HIL_CONFIG_PATH):
            with open(HIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"human_input_mode": "NEVER", "cooldown_steps": 2}

def _save_hil_settings(settings: dict):
    try:
        os.makedirs(os.path.dirname(HIL_CONFIG_PATH), exist_ok=True)
        with open(HIL_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

from app.agents.pm import PMAgent
from app.agents.frontend import FrontendAgent
from app.agents.backend_agent import BackendAgent
from app.agents.tester import TesterAgent
from app.agents.devops import DevopsAgent
from app.agents.designer import DesignerAgent
from app.agents.builder import AgentBuilderAgent
from app.agents.custom import CustomAgent, AVAILABLE_TOOLS
import app.tools  # noqa: F401 — trigger auto-registration of runtime tools

app = FastAPI(title="AgentHub API")

@app.on_event("shutdown")
async def shutdown_event():
    from app.tools.browser_tools import browser_session_manager
    from app.core.terminal import stateful_terminal_manager
    await browser_session_manager.close_all()
    await stateful_terminal_manager.close_all()

# ---- 文件上传目录 ----
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AGENTS = {
    "agent_pm": PMAgent(),
    "agent_frontend": FrontendAgent(),
    "agent_backend": BackendAgent(),
    "agent_tester": TesterAgent(),
    "agent_devops": DevopsAgent(),
    "agent_designer": DesignerAgent(),
    "agent_builder": AgentBuilderAgent(),
}

AGENTS["agent_pm"].description = "规划需求与分工的PM智能体"
AGENTS["agent_frontend"].description = "编写前端代码和页面的前端工程师智能体"
AGENTS["agent_backend"].description = "设计 API 和数据库逻辑的后端工程师智能体"
AGENTS["agent_tester"].description = "编写测试用例和审查代码缺陷的测试工程师智能体"
AGENTS["agent_devops"].description = "进行 CI/CD、部署和运维管理的运维工程师智能体"
AGENTS["agent_designer"].description = "提供 UI/UX 体验并生成网页 SVG 原型的设计师智能体"
AGENTS["agent_builder"].description = "动态构建项目和创建新智能体的构建专家智能体"

# Stop events per conversation — set to cancel ongoing generation
_stop_events: dict[str, asyncio.Event] = {}

app.include_router(agents_router.router, prefix="/api")
app.include_router(uploads_router.router)

init_db()


def _load_custom_agents():
    """Load user-created custom agents from DB into AGENTS dict."""
    for agent_data in get_custom_agents():
        aid = agent_data["agent_id"]
        if aid not in AGENTS:
            AGENTS[aid] = CustomAgent(
                agent_id=aid,
                name=agent_data["name"],
                avatar=agent_data["avatar"],
                role=agent_data["role"],
                style=agent_data["style"],
                system_prompt=agent_data["system_prompt"],
                tools=agent_data["tools"],
            )
            AGENTS[aid].description = f"自定义角色: {agent_data.get('role', '智能助手')}"


_load_custom_agents()


def _load_llm_config():
    try:
        if os.path.exists(LLM_CONFIG_PATH):
            with open(LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            llm_client.configure(
                provider=cfg.get("provider", "openai"),
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
                model=cfg.get("model", ""),
                temperature=cfg.get("temperature"),
                max_tokens=cfg.get("max_tokens"),
            )
    except Exception:
        pass


def _save_llm_config():
    os.makedirs(os.path.dirname(LLM_CONFIG_PATH), exist_ok=True)
    with open(LLM_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "provider": llm_client.provider,
            "api_key": llm_client.api_key,
            "base_url": llm_client.base_url,
            "model": llm_client.model,
            "temperature": llm_client.temperature,
            "max_tokens": llm_client.max_tokens,
        }, f, ensure_ascii=False, indent=2)


_load_llm_config()


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


class HILSettings(BaseModel):
    human_input_mode: str = "NEVER"
    cooldown_steps: int = 2


@app.get("/api/settings/hil")
async def get_hil_settings_api():
    return get_hil_settings()


@app.post("/api/settings/hil")
async def update_hil_settings_api(s: HILSettings):
    settings = {
        "human_input_mode": s.human_input_mode,
        "cooldown_steps": s.cooldown_steps
    }
    _save_hil_settings(settings)
    return {"status": "ok", "settings": settings}


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


@app.get("/")
async def root():
    return {"name": "AgentHub API", "version": "1.0.0", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "agents": list(AGENTS.keys())}


# ---- MULTI-CHANNEL WEBHOOK CALLBACK ENDPOINTS ----
from fastapi import Request

@app.post("/api/webhook/callback/slack")
async def slack_webhook_callback(request: Request):
    """Slack interactive actions callback endpoint."""
    try:
        # Slack sends payloads as form-data URL encoded JSON string under 'payload'
        form_data = await request.form()
        payload_str = form_data.get("payload")
        
        if payload_str:
            payload = json.loads(payload_str)
        else:
            # Fallback to direct JSON in case of custom test setups
            payload = await request.json()
            
        from app.services.webhook_gateway import webhook_gateway
        res = await webhook_gateway.handle_slack_callback(payload)
        return res
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/webhook/callback/telegram")
async def telegram_webhook_callback(request: Request):
    """Telegram inline keyboard button click callback endpoint."""
    try:
        payload = await request.json()
        from app.services.webhook_gateway import webhook_gateway
        res = await webhook_gateway.handle_telegram_callback(payload)
        return res
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
            if conversation_id in _pending_interactions:
                fut = _pending_interactions[conversation_id]
                if not fut.done():
                    reply_text = text
                    if reply_text.startswith("[ask_user_reply]"):
                        reply_text = reply_text.replace("[ask_user_reply]", "").strip()
                    fut.set_result(reply_text)
                    
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
                print(f"[STOP] conv={conversation_id} event_exists={event is not None} already_set={event.is_set() if event else 'N/A'}", flush=True)
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

            # 4. Run StateGraph orchestration
            await graph.run({}, conversation_id, stop_event)
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


# ---- File Upload API ----

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    # 生成唯一文件名，保留原始扩展名
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
    
    prompt = f"""你是一个专门修复代码报错的 AI 专家。
用户运行了一段 {req.language} 代码，但是失败了。
请分析报错原因，并只输出修复后的完整可运行代码。
不要任何多余的解释，必须包含在 ```{req.language} ... ``` 代码块中。

### 原始代码
```{req.language}
{req.code}
```

### 报错信息
```text
{req.error_output}
```
"""
    
    response = ""
    # 调用 LLM 生成修复代码
    async for chunk in llm_client.chat_stream([{"role": "user", "content": prompt}], system="你只能输出修复后的代码块。"):
        response += chunk
        
    import re
    # 提取代码块
    match = re.search(r"```[a-zA-Z]*\n(.*?)```", response, re.DOTALL)
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
        return {"error": "已有 benchmark 正在运行", "run_id": current.run_id}

    async def _run():
        await run_benchmark(
            agents=AGENTS,
            quality_gate=quality_gate,
        )

    asyncio.create_task(_run())
    return {"status": "started", "message": "Benchmark 已启动，请轮询 /api/benchmark/status"}


@app.get("/api/benchmark/status")
async def benchmark_status():
    """Get current benchmark run status and results."""
    current = get_current_run()
    if not current:
        return {"status": "idle", "message": "没有正在运行的 benchmark"}
    return current.to_dict()


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


# ---- Startup / Shutdown Lifespan Hooks ----

@app.on_event("startup")
async def startup_event():
    from app.services.daemon_scheduler import daemon_scheduler
    daemon_scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    from app.services.daemon_scheduler import daemon_scheduler
    await daemon_scheduler.stop()


# ---- Background Autonomous Tasks REST API ----

class CronTaskCreate(BaseModel):
    conversation_id: str
    agent_id: str
    task_prompt: str
    interval_seconds: int


@app.get("/api/cron")
async def list_cron_tasks(conversation_id: str = None):
    from app.core.database import get_cron_tasks
    tasks = get_cron_tasks(conversation_id)
    return {"status": "ok", "tasks": tasks}


@app.post("/api/cron")
async def create_cron_task(body: CronTaskCreate):
    from datetime import datetime, timedelta
    from app.core.database import save_cron_task

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow()
    next_run = (now + timedelta(seconds=body.interval_seconds)).strftime("%Y-%m-%d %H:%M:%S")

    save_cron_task(
        task_id=task_id,
        conversation_id=body.conversation_id,
        agent_id=body.agent_id,
        task_prompt=body.task_prompt,
        interval_seconds=body.interval_seconds,
        status="active",
        last_run=None,
        next_run=next_run
    )
    return {"status": "ok", "task_id": task_id, "message": "离线自治任务创建成功！"}


@app.post("/api/cron/{task_id}/toggle")
async def toggle_cron_task(task_id: str, body: dict):
    from app.core.database import update_cron_task_status
    status = body.get("status", "active")
    if status not in ("active", "paused"):
        return {"status": "error", "message": "无效的任务状态"}
    update_cron_task_status(task_id, status)
    return {"status": "ok", "message": f"任务状态已更新为 {status}"}


@app.post("/api/cron/{task_id}/run")
async def run_cron_task_now(task_id: str):
    from app.core.database import get_cron_tasks
    tasks = get_cron_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"status": "error", "message": "自治任务未找到"}

    from app.services.daemon_scheduler import daemon_scheduler
    asyncio.create_task(daemon_scheduler._run_task(task))
    return {"status": "ok", "message": "已手动触发后台自治作业运行！"}


@app.delete("/api/cron/{task_id}")
async def delete_cron_task_endpoint(task_id: str):
    from app.core.database import delete_cron_task
    delete_cron_task(task_id)
    return {"status": "ok", "message": "离线自治任务已成功删除！"}


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
        return {"status": "error", "message": f"不支持的文件类型: {file.filename}"}

    doc_id = f"kb_{uuid.uuid4().hex[:8]}"
    content = await file.read()

    # 保存文件到磁盘
    kb_dir = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge")
    os.makedirs(kb_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    stored_path = os.path.join(kb_dir, f"{doc_id}{ext}")
    with open(stored_path, "wb") as f:
        f.write(content)

    # 提取文本
    text = DocumentParser.extract_text(stored_path, file.content_type or "")
    if not text:
        os.remove(stored_path)
        return {"status": "error", "message": "无法从文件中提取文本内容"}

    # 分块写入向量库
    chunk_count = rag_engine.add_document(doc_id, text, metadata={
        "source": "upload",
        "filename": file.filename,
    })

    # 记录到 SQLite
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
        "message": f"文档已入库，生成 {chunk_count} 个知识块",
    }


@app.delete("/api/knowledge/{doc_id}")
async def delete_knowledge_doc_endpoint(doc_id: str):
    from app.core.rag_engine import rag_engine
    from app.core.database import delete_knowledge_doc, get_knowledge_docs

    # 删除向量库中的分块
    rag_engine.remove_document(doc_id)

    # 删除物理文件
    docs = get_knowledge_docs()
    doc = next((d for d in docs if d["id"] == doc_id), None)
    if doc and doc.get("file_path") and os.path.isfile(doc["file_path"]):
        os.remove(doc["file_path"])

    # 删除数据库记录
    delete_knowledge_doc(doc_id)
    return {"status": "ok", "message": "知识文档已删除"}


@app.post("/api/knowledge/query")
async def query_knowledge(body: dict):
    from app.core.rag_engine import rag_engine
    query = body.get("query", "")
    top_k = body.get("top_k", 5)
    if not query.strip():
        return {"status": "error", "message": "查询内容不能为空"}

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
            _register_custom_agent(ca)
            imported_count += 1
            
    hil = body.get("hil")
    if hil:
        _save_hil_settings(hil)
        
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
            print(f"\\n🟢 [StateGraph] Active Node: {{current_node.upper()}}")
            
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
                    print(f"\\n⚠️ [状态守卫强拦截] 智能体 {{next_node.upper()}} 未满足准入前置条件！")
                    print(f"🔄 已安全自动重定向至纠偏节点 {{failed_fallback.upper()}}。")
                    next_node = failed_fallback
                    
            # Human-in-the-loop Intercept Check
            if next_node and (human_input_mode == "ALWAYS" or (human_input_mode == "COOLDOWN" and len(state.get("completed_nodes", [])) % cooldown_steps == 0)):
                next_desc = next_node.upper() if next_node != "END" else "结束流程 (END)"
                print(f"\\n⏳ [HIL 拦截] 智能体 {{current_node.upper()}} 运行完毕。是否批准其结果并推进至 {{next_desc}}？")
                print("  1. Approve (批准并推进)")
                print("  2. Terminate (终止流程)")
                print("  3. Feedback (输入修改意见)")
                
                choice = input("请选择 (1-3): ").strip()
                if choice == "2":
                    next_node = "END"
                elif choice == "3" or choice not in ("1", "2"):
                    feedback = input("请输入你的修改意见: ").strip() if choice == "3" else choice
                    print(f"🔄 [HIL 反馈] 注入修改意见，重跑 {{current_node.upper()}}...")
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
    print(f"🤖 **{{agent['name']}}** ({{agent['role']}}) 正在思考...")
    
    messages = []
    if context:
        messages.append({{"role": "user", "content": f"PM 任务拆解：\\n{{context}}\\n\\n需求：{{user_text}}"}} )
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
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        assigned, pm_res = await stream_agent_reply("agent_pm", prompt)
        return {{"pm_response": pm_res, "assigned_agents": assigned, "agent_pm_feedback": ""}}
        
    async def run_designer(state):
        feedback = state.get("agent_designer_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_designer", prompt, context=state.get("pm_response", ""))
        return {{"designer_response": res, "agent_designer_feedback": ""}}

    async def run_frontend(state):
        feedback = state.get("agent_frontend_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_frontend", prompt, context=state.get("pm_response", ""))
        return {{"frontend_response": res, "agent_frontend_feedback": ""}}

    async def run_backend(state):
        feedback = state.get("agent_backend_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_backend", prompt, context=state.get("pm_response", ""))
        return {{"backend_response": res, "agent_backend_feedback": ""}}

    async def run_tester(state):
        feedback = state.get("agent_tester_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_tester", prompt, context=state.get("pm_response", ""))
        return {{"tester_response": res, "agent_tester_feedback": ""}}

    async def run_devops(state):
        feedback = state.get("agent_devops_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
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
            
        candidates_info = ""
        for cid in remaining:
            if cid in AGENTS:
                candidates_info += f"- ID: {{cid}}\\n  Name: {{AGENTS[cid]['name']}}\\n  Description: {{AGENTS[cid]['description']}}\\n\\n"
                
        system_prompt = f\"\"\"你是一个智能体群聊协调器 (Group Chat Coordinator)。
根据当前的对话历史和各个候选智能体 (Agents) 的角色描述，判断下一个最适合发言的智能体是谁。

候选智能体列表：
{{candidates_info}}

规则：
1. 只能从上面的候选智能体 ID 中选择一个，或者输出 "END" 表示对话已圆满结束（所有开发/部署任务均已妥善完成，没有遗留问题）。
2. 请只输出下一个发言的智能体 ID（例如 "agent_frontend"）或 "END"，不要附带任何其他解释、标点或 markdown 格式。
3. 必须客观分析当前对话进度。
\"\"\"
        user_prompt = f"请决定下一个最适合发言的智能体。"
        
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

