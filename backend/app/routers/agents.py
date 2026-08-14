import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.async_wrappers import async_get_custom_agents
from app.core.tenancy import request_user_id
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
    tools: list[str] = Field(default_factory=list)


@router.get("/agents")
async def list_agents(request: Request):
    all_agents = list(AGENTS_META)
    for ca in await async_get_custom_agents(request_user_id(request)):
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


# 必须放在 /agents/{agent_id} 前面，否则被参数化路由吞掉
@router.get("/agents/custom")
async def list_custom_agents_route(request: Request):
    return await async_get_custom_agents(request_user_id(request))


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    for agent in AGENTS_META:
        if agent["agent_id"] == agent_id:
            return agent
    for ca in await async_get_custom_agents(request_user_id(request)):
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


@router.post("/agents/custom")
async def create_custom_agent(body: CustomAgentCreate, request: Request):
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
    await agent_registry.register_custom_agent(config, request_user_id(request))
    return {"status": "created", "agent": config}


@router.put("/agents/custom/{agent_id}")
async def update_custom_agent(agent_id: str, body: CustomAgentCreate, request: Request):
    user_id = request_user_id(request)
    existing = next(
        (agent for agent in await async_get_custom_agents(user_id) if agent["agent_id"] == agent_id),
        None,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    config = {
        "agent_id": agent_id,
        "name": body.name,
        "avatar": body.avatar,
        "role": body.role,
        "style": body.style,
        "system_prompt": body.system_prompt,
        "tools": body.tools,
    }
    await agent_registry.register_custom_agent(config, user_id)
    return {"status": "ok", "agent": config}


@router.delete("/agents/custom/{agent_id}")
async def delete_custom_agent_api(agent_id: str, request: Request):
    # Invoke the concurrency-safe agent registry
    deleted = await agent_registry.unregister_custom_agent(agent_id, request_user_id(request))
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted"}

# ============================================================
# Agent Export / Import (team sharing)
# ============================================================

@router.get("/agents/custom/{agent_id}/export")
async def export_custom_agent(agent_id: str, request: Request):
    """Export a custom agent as JSON (filters sensitive data)."""
    agents = await async_get_custom_agents(request_user_id(request))
    agent = next((a for a in agents if a.get("agent_id") == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Filter sensitive fields
    export_data = {
        "version": "1.0",
        "agent": {
            "name": agent.get("name", ""),
            "avatar": agent.get("avatar", ""),
            "role": agent.get("role", ""),
            "style": agent.get("style", ""),
            "system_prompt": agent.get("system_prompt", ""),
            "tools": agent.get("tools", []),
        }
    }
    return export_data


class AgentImportRequest(BaseModel):
    version: str = "1.0"
    agent: dict


@router.post("/agents/import")
async def import_custom_agent(body: AgentImportRequest, request: Request):
    """Import a custom agent from exported JSON."""
    agent_data = body.agent
    
    # Validate required fields
    if not agent_data.get("name"):
        raise HTTPException(status_code=400, detail="Agent name is required")
    if not agent_data.get("system_prompt"):
        raise HTTPException(status_code=400, detail="Agent system_prompt is required")
    
    # Check for duplicate name
    existing = await async_get_custom_agents(request_user_id(request))
    existing_names = [a.get("name", "") for a in existing]
    original_name = agent_data["name"]
    name = original_name
    if name in existing_names:
        name = f"{name} (imported)"
        agent_data["name"] = name
    
    # Generate new agent_id
    agent_id = f"agent_imported_{uuid.uuid4().hex[:8]}"
    
    # Register the agent
    config = {
        "agent_id": agent_id,
        "name": agent_data.get("name"),
        "avatar": agent_data.get("avatar", "🤖"),
        "role": agent_data.get("role", "Imported Agent"),
        "style": agent_data.get("style", ""),
        "system_prompt": agent_data.get("system_prompt"),
        "tools": agent_data.get("tools", []),
    }
    
    await agent_registry.register_custom_agent(config, request_user_id(request))
    return {"status": "imported", "agent": config, "duplicate_renamed": name != original_name}
