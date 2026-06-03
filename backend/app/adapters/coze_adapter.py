"""Coze Adapter — Coze Bot API。

将 Coze Bot 作为外部 Agent 接入，支持：
- 流式回复
- 对话管理
- Coze 内置插件和工具
"""

import json
import logging
import httpx
from typing import AsyncGenerator

from app.adapters.base import AgentAdapter, AdapterConfig

logger = logging.getLogger("coze_adapter")

COZE_API_URL = "https://api.coze.cn"  # 中国区


class CozeAdapter(AgentAdapter):
    """Coze 适配器 — 调用 Coze Bot API。"""

    name = "Coze"
    adapter_type = "coze"
    description = "Coze 智能体 — 字节跳动 Agent 平台，支持插件和工作流"

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self.api_url = config.api_url or COZE_API_URL
        self.api_key = config.api_key
        self.bot_id = config.extra.get("bot_id", "")
        self.user_id = config.extra.get("user_id", "agenthub_user")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "未配置 Coze API Key"
        if not self.bot_id:
            return False, "未配置 Coze Bot ID"
        return True, ""

    async def stream_reply(
        self,
        message: str,
        history: list[dict] = None,
        system_prompt: str = "",
        tools: list[dict] = None,
        conversation_id: str = None,
    ) -> AsyncGenerator[str, None]:
        """调用 Coze Chat API 流式回复。"""

        valid, err = self.validate_config()
        if not valid:
            yield f"[Coze 适配器错误: {err}]"
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "additional_messages": [
                {"role": "user", "content": message, "content_type": "text"}
            ],
            "stream": True,
            "auto_save_history": True,
        }

        # Coze 使用 conversation_id 管理会话
        if conversation_id:
            body["conversation_id"] = conversation_id

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.api_url}/v3/chat",
                    headers=headers,
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        error_body = ""
                        async for chunk in resp.aiter_bytes():
                            error_body += chunk.decode(errors="ignore")
                        yield f"[Coze API 错误: HTTP {resp.status_code}: {error_body[:200]}]"
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type", "")

                        # 文本消息增量
                        if event_type == "conversation.message.delta":
                            msg = event.get("delta", {})
                            if msg.get("type") == "answer":
                                yield msg.get("content", "")

                        # 工具调用
                        elif event_type == "conversation.chat.requires_action":
                            # Coze 工具调用由平台内部处理，通常不需要用户提交结果
                            pass

                        # 错误
                        elif event_type == "conversation.chat.failed":
                            error = event.get("last_error", {})
                            yield f"\n[Coze 错误: {error.get('msg', '未知错误')}]"

        except httpx.TimeoutException:
            yield "\n[Coze API 超时，请稍后重试]"
        except Exception as e:
            yield f"\n[Coze API 错误: {str(e)[:200]}]"
