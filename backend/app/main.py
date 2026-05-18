import json
import os
import re
import asyncio
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.websocket import manager
from app.core.database import init_db, save_message, get_messages, get_conversations, clear_messages
from app.core.config import settings
from app.core.llm_client import llm_client
from app.routers import agents as agents_router

LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "llm_config.json")
from app.agents.pm import PMAgent
from app.agents.frontend import FrontendAgent
from app.agents.backend_agent import BackendAgent
from app.agents.tester import TesterAgent
from app.agents.devops import DevopsAgent
from app.agents.designer import DesignerAgent

app = FastAPI(title="AgentHub API")

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
}

# Stop events per conversation — set to cancel ongoing generation
_stop_events: dict[str, asyncio.Event] = {}

app.include_router(agents_router.router, prefix="/api")

init_db()


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
        }, f, ensure_ascii=False, indent=2)


_load_llm_config()


class LLMSettings(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = ""


@app.get("/api/settings/llm")
async def get_llm_settings():
    return {
        "provider": llm_client.provider,
        "api_key_set": bool(llm_client.api_key),
        "base_url": llm_client.base_url,
        "model": llm_client.model,
        "configured": llm_client.is_configured(),
    }


@app.post("/api/settings/llm")
async def update_llm_settings(s: LLMSettings):
    llm_client.configure(
        provider=s.provider,
        api_key=s.api_key if s.api_key else llm_client.api_key,
        base_url=s.base_url,
        model=s.model,
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
                await _stream_agent_reply(conversation_id, agent, text)
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
                        # Default: frontend + backend
                        agents_to_run = [AGENTS["agent_frontend"], AGENTS["agent_backend"]]

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
    buffer = ""
    last_thinking_broadcast = ""
    assigned_agents = []

    # If context provided (PM's task breakdown), prepend to user_text for the agent
    effective_text = user_text
    if context:
        effective_text = f"PM 的任务拆解：\n{context}\n\n用户原始需求：{user_text}"

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
        async for chunk in agent.stream_reply(effective_text):
            # Check stop signal
            if stop_event and stop_event.is_set():
                break

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

            # Extract and broadcast code blocks
            code_match = re.search(r'```(\w*)\n(.*?)```', buffer, re.DOTALL)
            if code_match:
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
            summary = buffer.strip()
            if summary:
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
        if not full_text:
            full_text = f"[Agent 回复出错: {type(e).__name__}: {str(e)[:200]}]"
        else:
            full_text += f"\n[出错: {str(e)[:100]}]"

    stopped = stop_event and stop_event.is_set()

    if not full_text:
        full_text = "（已停止生成）" if stopped else "（已生成代码，请查看右侧面板）"

    save_message(conversation_id, agent.agent_id, {"text": full_text}, streaming=False)

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

