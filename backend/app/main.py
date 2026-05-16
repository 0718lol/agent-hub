import json
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.websocket import manager
from app.core.database import init_db, save_message, get_messages, get_conversations, clear_messages
from app.core.config import settings
from app.core.llm_client import llm_client
from app.routers import agents as agents_router
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

app.include_router(agents_router.router, prefix="/api")

init_db()

# Initialize LLM client from config
if settings.llm_api_key:
    llm_client.configure(
        provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )


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
        api_key=s.api_key,
        base_url=s.base_url,
        model=s.model,
    )
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

            sender = msg.get("sender", "user")
            content = msg.get("content", {})
            text = content.get("text", "")
            target_agent = content.get("target_agent")

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
                for agent_id, agent in AGENTS.items():
                    if agent_id == "agent_pm":
                        await _stream_agent_reply(conversation_id, agent, text)
                        break

    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)


async def _stream_agent_reply(conversation_id: str, agent, user_text: str):
    full_text = ""
    async for chunk in agent.stream_reply(user_text):
        full_text += chunk
        await manager.broadcast(conversation_id, {
            "type": "message",
            "conversation_id": conversation_id,
            "sender": agent.agent_id,
            "content": {"text": full_text},
            "stream": True,
        })

    save_message(conversation_id, agent.agent_id, {"text": full_text}, streaming=False)

    await manager.broadcast(conversation_id, {
        "type": "message",
        "conversation_id": conversation_id,
        "sender": agent.agent_id,
        "content": {"text": full_text},
        "stream": False,
    })
