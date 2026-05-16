from fastapi import APIRouter

router = APIRouter(tags=["agents"])

AGENTS_META = [
    {"agent_id": "agent_pm", "name": "PM 小助手", "avatar": "📋", "role": "产品经理", "style": "条理清晰，爱用数字列表"},
    {"agent_id": "agent_frontend", "name": "前端工程师", "avatar": "🎨", "role": "前端开发", "style": "活泼，爱用 emoji"},
    {"agent_id": "agent_backend", "name": "后端工程师", "avatar": "⚙️", "role": "后端开发", "style": "严谨务实"},
    {"agent_id": "agent_tester", "name": "测试工程师", "avatar": "🧪", "role": "测试", "style": "爱挑毛病"},
    {"agent_id": "agent_devops", "name": "运维工程师", "avatar": "🚀", "role": "运维部署", "style": "谨慎带警告"},
    {"agent_id": "agent_designer", "name": "设计顾问", "avatar": "🎯", "role": "UI/UX 设计", "style": "审美感强"},
]


@router.get("/agents")
async def list_agents():
    return AGENTS_META


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    for agent in AGENTS_META:
        if agent["agent_id"] == agent_id:
            return agent
    return {"error": "Agent not found"}, 404
