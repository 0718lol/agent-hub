"""Coze Adapter — Coze Bot API。

将 Coze Bot 作为外部 Agent 接入，支持：
- 流式回复
- 对话管理
- Coze 内置插件和工具
"""

import json
import logging
from typing import AsyncGenerator

import httpx

from app.adapters.base import AdapterConfig, AgentAdapter

logger = logging.getLogger("coze_adapter")

COZE_API_URL = "https://api.coze.cn"  # 中国区


class CozeAdapter(AgentAdapter):
    """Coze 适配器 — 调用 Coze Bot API。"""

    name = "Coze"
    adapter_type = "coze"
    description = "Coze 智能体 — 字节跳动 Agent 平台，支持插件和工作流"

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        base = (config.api_url or COZE_API_URL).rstrip("/")
        if not base.endswith("/v3/chat"):
            base = base + "/v3/chat"
        self.api_url = base
        self.api_key = (config.api_key or "").strip()
        self.bot_id = config.extra.get("bot_id", "")
        self.user_id = config.extra.get("user_id", "agenthub_user")
        # 存储 AgentHub conversation_id → Coze conversation_id 的映射
        self._conv_map: dict[str, str] = {}

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

        # 构建消息列表，传入历史上下文
        additional_messages = []
        if history:
            for msg in history[-20:]:
                role = msg.get("role") or msg.get("sender", "user")
                if role == "assistant":
                    msg_type = "answer"
                else:
                    role = "user"
                    msg_type = "question"
                raw_content = msg.get("content", "")
                if isinstance(raw_content, dict):
                    content = raw_content.get("text", str(raw_content))
                elif isinstance(raw_content, str):
                    content = raw_content
                else:
                    content = str(raw_content) if raw_content else ""
                if content and content.strip():
                    additional_messages.append({
                        "role": role,
                        "content": content,
                        "content_type": "text",
                        "type": msg_type,
                    })
        additional_messages.append({
            "role": "user",
            "content": message,
            "content_type": "text",
            "type": "question",
        })

        body = {
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "additional_messages": additional_messages,
            "stream": True,
            "auto_save_history": True,
            "parameters": {},
        }

        # 传入 Coze 侧的 conversation_id 以延续对话
        if conversation_id and conversation_id in self._conv_map:
            body["conversation_id"] = self._conv_map[conversation_id]

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST",
                    self.api_url,
                    headers=headers,
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        error_body = ""
                        async for chunk in resp.aiter_bytes():
                            error_body += chunk.decode(errors="ignore")
                        yield f"[Coze API 错误: HTTP {resp.status_code}: {error_body[:200]}]"
                        return

                    current_event_type = ""
                    async for line in resp.aiter_lines():
                        # Coze SSE 格式：event:xxx 在前一行，data:xxx 在后一行
                        if line.startswith("event:"):
                            current_event_type = line[6:].strip()
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == '"[DONE]"' or data_str == "[DONE]":
                            break

                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        # 优先用 event: 行的类型，回退到 JSON 内的 type
                        event_type = current_event_type or event.get("type", "")
                        current_event_type = ""

                        # 捕获 Coze 侧的 conversation_id（可能在多个事件中返回）
                        coze_conv_id = event.get("conversation_id", "")
                        if coze_conv_id and conversation_id and conversation_id not in self._conv_map:
                            self._conv_map[conversation_id] = coze_conv_id

                        # 文本消息增量（流式模式）
                        if event_type == "conversation.message.delta":
                            msg = event.get("delta", {})
                            if msg.get("type") in ("answer", "follow_up"):
                                content = msg.get("content", "")
                                if content:
                                    yield content

                        # 完整消息（非流式或 completed 事件）
                        elif event_type == "conversation.message.completed":
                            msg_type = event.get("type", "")
                            if msg_type in ("answer", "follow_up"):
                                content = event.get("content", "")
                                if content:
                                    yield content

                        # 工具调用
                        elif event_type == "conversation.chat.requires_action":
                            pass

                        # 错误
                        elif event_type == "conversation.chat.failed":
                            error = event.get("last_error", {})
                            yield f"\n[Coze 错误: {error.get('msg', '未知错误')}]"

        except httpx.TimeoutException:
            yield "\n[Coze API 超时，请稍后重试]"
        except Exception as e:
            logger.warning(f"Coze API error: {e}")
            yield f"\n[Coze API 错误: {str(e)[:200]}]"
