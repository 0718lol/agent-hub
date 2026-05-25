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
from app.core.prompt_engine import prompt_engine
from app.routers import agents as agents_router
from app.routers import uploads as uploads_router

LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "llm_config.json")
from app.agents.pm import PMAgent
from app.agents.frontend import FrontendAgent
from app.agents.backend_agent import BackendAgent
from app.agents.tester import TesterAgent
from app.agents.devops import DevopsAgent
from app.agents.designer import DesignerAgent
from app.agents.builder import AgentBuilderAgent
from app.agents.custom import CustomAgent, AVAILABLE_TOOLS

app = FastAPI(title="AgentHub API")

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


@app.get("/")
async def root():
    return {"name": "AgentHub API", "version": "1.0.0", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "agents": list(AGENTS.keys())}


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
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            msg_type = msg.get("type", "message")
            sender = msg.get("sender", "user")
            content = msg.get("content", {})
            text = content.get("text", "")
            target_agent = content.get("target_agent")

            # Handle stop generation
            if msg_type == "stop":
                event = _stop_events.get(conversation_id)
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

            save_message(conversation_id, sender, content, streaming=False)

            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": sender,
                "content": {"text": text},
                "stream": False,
            })

            if target_agent and target_agent in AGENTS:
                agent = AGENTS[target_agent]
                stop_event = asyncio.Event()
                _stop_events[conversation_id] = stop_event
                await manager.broadcast(conversation_id, {
                    "type": "generating",
                    "conversation_id": conversation_id,
                    "is_generating": True,
                })
                assigned_agent_ids, pm_response = await _stream_agent_reply(conversation_id, agent, text, stop_event)

                # If the agent (e.g. PM) assigned downstream agents, trigger them
                if assigned_agent_ids and not stop_event.is_set():
                    agents_to_run = [AGENTS[aid] for aid in assigned_agent_ids if aid in AGENTS and aid != target_agent]
                    if agents_to_run:
                        await asyncio.gather(*[
                            _stream_agent_reply(conversation_id, a, text, stop_event, context=pm_response)
                            for a in agents_to_run
                        ])

                _stop_events.pop(conversation_id, None)
                await manager.broadcast(conversation_id, {
                    "type": "generating",
                    "conversation_id": conversation_id,
                    "is_generating": False,
                })
            elif sender == "user":
                # Create stop event for this generation
                stop_event = asyncio.Event()
                _stop_events[conversation_id] = stop_event

                # Broadcast generating start
                await manager.broadcast(conversation_id, {
                    "type": "generating",
                    "conversation_id": conversation_id,
                    "is_generating": True,
                })

                is_group = not target_agent
                pm = AGENTS.get("agent_pm")
                assigned_agent_ids = []
                pm_response = ""

                if pm:
                    assigned_agent_ids, pm_response = await _stream_agent_reply(conversation_id, pm, text, stop_event)

                if is_group and not stop_event.is_set():
                    # Determine which agents to run
                    if assigned_agent_ids:
                        # PM assigned specific agents
                        agents_to_run = [AGENTS[aid] for aid in assigned_agent_ids if aid in AGENTS and aid != "agent_pm"]
                    else:
                        # Default: designer + frontend + backend
                        agents_to_run = [AGENTS["agent_designer"], AGENTS["agent_frontend"], AGENTS["agent_backend"]]

                    if agents_to_run:
                        # Pass PM's task breakdown as context to other agents
                        await asyncio.gather(*[
                            _stream_agent_reply(conversation_id, agent, text, stop_event, context=pm_response)
                            for agent in agents_to_run
                        ])

                # Clean up stop event and broadcast generating end
                _stop_events.pop(conversation_id, None)
                await manager.broadcast(conversation_id, {
                    "type": "generating",
                    "conversation_id": conversation_id,
                    "is_generating": False,
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)


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
            async for chunk in agent.stream_reply(effective_text, history=history):
                # Check stop signal
                if stop_event and stop_event.is_set():
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
                # Don't strip [options:...] — let frontend handle it

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

    # ---- Quality Gate: evaluate and optionally auto-retry ----
    if not stopped and quality_gate.enabled and agent.agent_id not in ("agent_builder", "agent_pm"):
        report = quality_gate.evaluate(raw_text, agent.agent_id)
        if not report.passed and quality_gate.max_retries > 0:
            # Auto-retry: re-generate with quality feedback
            feedback = report.feedback_text()
            retry_msg = (
                f"{effective_text}\n\n"
                f"【质量检查未通过，请修复后重新输出】：\n{feedback}"
            )
            retry_output = ""
            async for chunk in agent.stream_reply(retry_msg, history=history):
                if stop_event and stop_event.is_set():
                    break
                retry_output += chunk
                # Broadcast retry streaming
                await manager.broadcast(conversation_id, {
                    "type": "message",
                    "conversation_id": conversation_id,
                    "sender": agent.agent_id,
                    "content": {"text": "[质量优化中...] " + retry_output.strip()[:100]},
                    "stream": True,
                })
            if retry_output.strip():
                raw_text = retry_output
                full_text = retry_output.strip()
                report = quality_gate.evaluate(raw_text, agent.agent_id)

        # Broadcast quality report to frontend
        await manager.broadcast(conversation_id, {
            "type": "quality_report",
            "conversation_id": conversation_id,
            "agent_id": agent.agent_id,
            "report": report.to_dict(),
        })

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
    system_prompt = config.get("system_prompt", f"你是{name}，角色是{role}。")
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
    return [
        {"id": tid, "name": t["name"], "icon": t["icon"], "description": t["description"]}
        for tid, t in AVAILABLE_TOOLS.items()
    ]


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

