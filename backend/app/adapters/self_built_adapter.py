"""Self-Built Agent Adapter — 包装现有 BaseAgent 为统一适配器接口。

将现有的 BaseAgent.stream_reply() 包装为 AgentAdapter 接口，
使其与外部 Agent 适配器使用同一套调用协议。
"""

import logging
from typing import AsyncGenerator

from app.adapters.base import AdapterConfig, AgentAdapter

logger = logging.getLogger("self_built_adapter")


class SelfBuiltAdapter(AgentAdapter):
    """自建 Agent 适配器 — 包装现有 BaseAgent。"""

    name = "自建 Agent"
    adapter_type = "self_built"
    description = "项目内置 Agent（PM、前端、后端、测试、运维、设计）"

    def __init__(self, config: AdapterConfig, agent=None):
        super().__init__(config)
        self.agent = agent  # BaseAgent 实例

    def validate_config(self) -> tuple[bool, str]:
        if not self.agent:
            return False, "未绑定 Agent 实例"
        return True, ""

    async def stream_reply(
        self,
        message: str,
        history: list[dict] = None,
        system_prompt: str = "",
        tools: list[dict] = None,
        conversation_id: str = None,
    ) -> AsyncGenerator[str, None]:
        """直接调用 BaseAgent.stream_reply()。"""

        valid, err = self.validate_config()
        if not valid:
            yield f"[自建 Agent 错误: {err}]"
            return

        try:
            async for chunk in self.agent.stream_reply(
                message,
                history=history,
                conversation_id=conversation_id,
            ):
                yield chunk
        except Exception as e:
            yield f"\n[自建 Agent 错误: {str(e)[:200]}]"
