import asyncio
import json
import logging
import uuid

from app.agents.backend_agent import BackendAgent
from app.agents.base import BaseAgent
from app.agents.browser_agent import BrowserAgent
from app.agents.builder import AgentBuilderAgent
from app.agents.code_reviewer import CodeReviewerAgent
from app.agents.custom import CustomAgent
from app.agents.debug_agent import DebugAgent
from app.agents.designer import DesignerAgent
from app.agents.devops import DevopsAgent
from app.agents.frontend import FrontendAgent
from app.agents.pm import PMAgent
from app.agents.tester import TesterAgent
from app.core.async_wrappers import async_create_conversation, async_delete_custom_agent, async_save_custom_agent
from app.core.crud import get_custom_agents
from app.core.tenancy import scope_conversation_id

logger = logging.getLogger("agent_registry")

class AgentRegistry:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._agents: dict[str, BaseAgent] = {
            "agent_pm": PMAgent(),
            "agent_frontend": FrontendAgent(),
            "agent_backend": BackendAgent(),
            "agent_tester": TesterAgent(),
            "agent_devops": DevopsAgent(),
            "agent_designer": DesignerAgent(),
            "agent_builder": AgentBuilderAgent(),
            "agent_browser": BrowserAgent(),
            "agent_reviewer": CodeReviewerAgent(),
            "agent_debugger": DebugAgent(),
        }
        self._builtin_agent_ids = frozenset(self._agents)
        self._agent_owners: dict[str, str] = {}
        self._agents["agent_pm"].description = "规划需求与分工的PM智能体"
        self._agents["agent_frontend"].description = "开发 React 前端组件的智能体"
        self._agents["agent_backend"].description = "编写 Python 后端 API 的智能体"
        self._agents["agent_tester"].description = "编写与执行 pytest 测试的智能体"
        self._agents["agent_devops"].description = "配置 Docker 容器和部署的智能体"
        self._agents["agent_designer"].description = "提供 UI/UX 设计及样式美化建议的智能体"
        self._agents["agent_builder"].description = "协助用户创建并注册自定义智能体的助手"
        self._agents["agent_browser"].description = "查阅文档、搜索解决方案、验证网页效果"
        self._agents["agent_reviewer"].description = "审查代码质量、安全性、性能"
        self._agents["agent_debugger"].description = "自动分析代码错误并提供最小化修复"

        self.load_custom_agents_sync()

    def _set_custom_agent(self, config: dict) -> None:
        aid = config["agent_id"]
        db_tools = config.get("tools", [])
        if isinstance(db_tools, str):
            try:
                tools = json.loads(db_tools)
            except ValueError:
                tools = []
        else:
            tools = db_tools
        agent = CustomAgent(
            agent_id=aid,
            name=config["name"],
            avatar=config["avatar"],
            role=config["role"],
            style=config["style"],
            system_prompt=config["system_prompt"],
            tools=tools,
        )
        agent.description = f"自定义角色: {config.get('role', '智能助手')}"
        self._agents[aid] = agent
        self._agent_owners[aid] = config.get("user_id", "legacy")

    def _refresh_user_agents_sync(self, user_id: str) -> None:
        rows = get_custom_agents(user_id)
        current_ids = {row["agent_id"] for row in rows}
        for agent_id, owner in list(self._agent_owners.items()):
            if owner == user_id and agent_id not in current_ids:
                self._agents.pop(agent_id, None)
                self._agent_owners.pop(agent_id, None)
        for row in rows:
            self._set_custom_agent(row)

    def load_custom_agents_sync(self):
        try:
            for ca in get_custom_agents():
                aid = ca["agent_id"]
                if aid not in self._agents:
                    self._set_custom_agent(ca)
        except Exception as e:
            logger.error(f"Error loading custom agents: {e}")

    async def get_agent(self, agent_id: str, user_id: str | None = None) -> BaseAgent | None:
        async with self._lock:
            if user_id:
                await asyncio.to_thread(self._refresh_user_agents_sync, user_id)
            agent = self._agents.get(agent_id)
            if agent_id in self._builtin_agent_ids:
                return agent
            if user_id and self._agent_owners.get(agent_id) == user_id:
                return agent
            return None

    def get_agent_dict(self, user_id: str | None = None) -> dict[str, BaseAgent]:
        """Return agents dict synchronously (for get_agents() compatibility)."""
        if user_id is None:
            return self._agents
        self._refresh_user_agents_sync(user_id)
        return {
            agent_id: agent
            for agent_id, agent in self._agents.items()
            if agent_id in self._builtin_agent_ids or self._agent_owners.get(agent_id) == user_id
        }

    async def get_all_agents(self, user_id: str | None = None) -> dict[str, BaseAgent]:
        async with self._lock:
            return dict(self.get_agent_dict(user_id))

    async def register_custom_agent(self, config: dict, user_id: str = "legacy"):
        async with self._lock:
            aid = config.get("agent_id") or f"agent_custom_{uuid.uuid4().hex[:12]}"
            existing_owner = self._agent_owners.get(aid)
            if existing_owner and existing_owner != user_id:
                raise PermissionError("Custom agent belongs to another tenant")
            name = config.get("name", "自定义助手")
            avatar = config.get("avatar", "🤖")
            role = config.get("role", "智能助手")
            style = config.get("style", "友好专业")
            system_prompt = config.get("system_prompt") or f"你是{name}，{role}。请基于这个角色为用户提供专业、有帮助的回答。"
            tools = config.get("tools", [])

            await async_save_custom_agent(
                aid, name, avatar, role, style, system_prompt, tools, user_id
            )

            self._agents[aid] = CustomAgent(
                agent_id=aid, name=name, avatar=avatar,
                role=role, style=style, system_prompt=system_prompt, tools=tools,
            )
            self._agents[aid].description = f"自定义角色: {role}"
            self._agent_owners[aid] = user_id

            public_conv_id = f"conv_{aid}"
            conv_id = (
                scope_conversation_id(user_id, public_conv_id)
                if user_id != "legacy"
                else public_conv_id
            )
            await async_create_conversation(conv_id, "single", name, avatar, agent_id=aid, preview=role)
            return aid

    async def unregister_custom_agent(self, agent_id: str, user_id: str = "legacy") -> bool:
        async with self._lock:
            if self._agent_owners.get(agent_id) != user_id:
                return False
            deleted = await async_delete_custom_agent(agent_id, user_id)
            if not deleted:
                return False
            self._agents.pop(agent_id, None)
            self._agent_owners.pop(agent_id, None)
            return True

agent_registry = AgentRegistry()
