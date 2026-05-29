import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.database import get_custom_agents
from app.services.agent_registry import agent_registry

router = APIRouter(tags=["agents"])

AGENTS_META = [
    {"agent_id": "agent_pm", "name": "PM 小助手", "avatar": "📋", "role": "产品经理", "style": "条理清晰，爱用数字列表"},
    {"agent_id": "agent_frontend", "name": "前端工程师", "avatar": "🎨", "role": "前端开发", "style": "活泼，爱用 emoji"},
    {"agent_id": "agent_backend", "name": "后端工程师", "avatar": "⚙️", "role": "后端开发", "style": "严谨务实"},
    {"agent_id": "agent_tester", "name": "测试工程师", "avatar": "🧪", "role": "测试", "style": "爱挑毛病"},
    {"agent_id": "agent_devops", "name": "运维工程师", "avatar": "🚀", "role": "运维部署", "style": "谨慎带警告"},
    {"agent_id": "agent_designer", "name": "设计顾问", "avatar": "🎯", "role": "UI/UX 设计", "style": "审美感强"},
    {"agent_id": "agent_builder", "name": "Agent 工坊", "avatar": "🔧", "role": "Agent 创建助手", "style": "友好引导"},
]


class CustomAgentCreate(BaseModel):
    name: str
    avatar: str = "🤖"
    role: str = ""
    style: str = ""
    system_prompt: str
    tools: list[str] = []


@router.get("/agents")
async def list_agents():
    all_agents = list(AGENTS_META)
    for ca in get_custom_agents():
        # Safeguard tools parsing if returned as JSON string
        ca_tools = ca.get("tools", [])
        import json
        if isinstance(ca_tools, str):
            try:
                ca_tools = json.loads(ca_tools)
            except Exception:
                ca_tools = []
                
        all_agents.append({
            "agent_id": ca["agent_id"],
            "name": ca["name"],
            "avatar": ca["avatar"],
            "role": ca["role"],
            "style": ca["style"],
            "tools": ca_tools,
            "custom": True,
        })
    return all_agents


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    for agent in AGENTS_META:
        if agent["agent_id"] == agent_id:
            return agent
    for ca in get_custom_agents():
        if ca["agent_id"] == agent_id:
            ca_tools = ca.get("tools", [])
            import json
            if isinstance(ca_tools, str):
                try:
                    ca_tools = json.loads(ca_tools)
                except Exception:
                    ca_tools = []
            ca["tools"] = ca_tools
            return ca
    raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/agents/custom")
async def list_custom_agents():
    return get_custom_agents()


@router.post("/agents/custom")
async def create_custom_agent(body: CustomAgentCreate):
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
    # Invoke the concurrency-safe agent registry
    await agent_registry.register_custom_agent(config)
    return {"status": "created", "agent": config}


@router.delete("/agents/custom/{agent_id}")
async def delete_custom_agent_api(agent_id: str):
    # Invoke the concurrency-safe agent registry
    await agent_registry.unregister_custom_agent(agent_id)
    return {"status": "deleted"}
