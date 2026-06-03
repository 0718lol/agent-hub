"""AdapterAgent — 将适配器包装为 BaseAgent 兼容对象。

使外部 Agent 适配器可以注册到 AGENTS 字典中，
复用现有的 WebSocket 路由和消息处理逻辑，无需修改存量代码。
"""

import logging
from typing import AsyncGenerator

from app.adapters.base import AgentAdapter

logger = logging.getLogger("adapter_agent")


class AdapterAgent:
    """将 AgentAdapter 包装为 BaseAgent 兼容接口。

    实现 BaseAgent 的关键属性和方法：
    - agent_id, name, avatar, role, style, system_prompt
    - stream_reply(message, history, conversation_id)
    - to_dict()

    这样现有的 WebSocket 处理器可以无缝调用它。
    """

    def __init__(self, agent_id: str, name: str, adapter: AgentAdapter,
                 avatar: str = "🤖", role: str = "", style: str = "",
                 system_prompt: str = ""):
        self.agent_id = agent_id
        self.name = name
        self.avatar = avatar
        self.role = role or adapter.description
        self.style = style
        self.system_prompt = system_prompt
        self.adapter = adapter

    async def stream_reply(self, message: str, context=None, history=None,
                           conversation_id: str = None) -> AsyncGenerator[str, None]:
        """流式回复 — 委托给适配器。"""
        async for chunk in self.adapter.stream_reply(
            message=message,
            history=history,
            system_prompt=self.system_prompt,
            conversation_id=conversation_id,
        ):
            yield chunk

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "avatar": self.avatar,
            "role": self.role,
            "style": self.style,
            "agent_type": self.adapter.adapter_type,
            "description": self.adapter.description,
        }
