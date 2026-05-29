import asyncio
import json
import logging
from typing import Dict, Any, List
from app.agents.base import BaseAgent
from app.core.database import get_custom_agents, save_custom_agent, delete_custom_agent, create_conversation
from app.agents.pm import PMAgent
from app.agents.frontend import FrontendAgent
from app.agents.backend_agent import BackendAgent
from app.agents.tester import TesterAgent
from app.agents.devops import DevopsAgent
from app.agents.designer import DesignerAgent
from app.agents.builder import AgentBuilderAgent
from app.agents.custom import CustomAgent

logger = logging.getLogger("agent_registry")

class AgentRegistry:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._agents: Dict[str, BaseAgent] = {
            "agent_pm": PMAgent(),
            "agent_frontend": FrontendAgent(),
            "agent_backend": BackendAgent(),
            "agent_tester": TesterAgent(),
            "agent_devops": DevopsAgent(),
            "agent_designer": DesignerAgent(),
            "agent_builder": AgentBuilderAgent(),
        }
        self._agents["agent_pm"].description = "规划需求与分工的PM智能体"
        self._agents["agent_frontend"].description = "开发 React 前端组件的智能体"
        self._agents["agent_backend"].description = "编写 Python 后端 API 的智能体"
        self._agents["agent_tester"].description = "编写与执行 pytest 测试的智能体"
        self._agents["agent_devops"].description = "配置 Docker 容器和部署的智能体"
        self._agents["agent_designer"].description = "提供 UI/UX 设计及样式美化建议的智能体"
        self._agents["agent_builder"].description = "协助用户创建并注册自定义智能体的助手"

        self.load_custom_agents_sync()

    def load_custom_agents_sync(self):
        try:
            for ca in get_custom_agents():
                aid = ca["agent_id"]
                if aid not in self._agents:
                    # Resolve tools from database string
                    db_tools = ca.get("tools", [])
                    if isinstance(db_tools, str):
                        try:
                            tools_list = json.loads(db_tools)
                        except Exception:
                            tools_list = []
                    else:
                        tools_list = db_tools

                    self._agents[aid] = CustomAgent(
                        agent_id=aid,
                        name=ca["name"],
                        avatar=ca["avatar"],
                        role=ca["role"],
                        style=ca["style"],
                        system_prompt=ca["system_prompt"],
                        tools=tools_list,
                    )
                    self._agents[aid].description = f"自定义角色: {ca.get('role', '智能助手')}"
        except Exception as e:
            logger.error(f"Error loading custom agents: {e}")

    async def get_agent(self, agent_id: str) -> BaseAgent:
        async with self._lock:
            return self._agents.get(agent_id)

    async def get_all_agents(self) -> Dict[str, BaseAgent]:
        async with self._lock:
            return dict(self._agents)

    async def register_custom_agent(self, config: dict):
        async with self._lock:
            aid = config.get("agent_id", "")
            name = config.get("name", "自定义助手")
            avatar = config.get("avatar", "🤖")
            role = config.get("role", "智能助手")
            style = config.get("style", "友好专业")
            system_prompt = config.get("system_prompt") or f"你是{name}，{role}。请基于这个角色为用户提供专业、有帮助的回答。"
            tools = config.get("tools", [])

            save_custom_agent(aid, name, avatar, role, style, system_prompt, tools)

            self._agents[aid] = CustomAgent(
                agent_id=aid, name=name, avatar=avatar,
                role=role, style=style, system_prompt=system_prompt, tools=tools,
            )
            self._agents[aid].description = f"自定义角色: {role}"

            conv_id = f"conv_{aid}"
            create_conversation(conv_id, "single", name, avatar, agent_id=aid, preview=role)

    async def unregister_custom_agent(self, agent_id: str):
        async with self._lock:
            self._agents.pop(agent_id, None)
            delete_custom_agent(agent_id)

agent_registry = AgentRegistry()
