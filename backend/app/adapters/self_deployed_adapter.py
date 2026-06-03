"""Self-Deployed Agent Adapter — 自部署 Agent 通用 HTTP 适配器。

适用于 Dify、LangFlow、Flowise、FastGPT 等自部署 Agent 平台。
通过统一的 HTTP API 格式调用，平台差异通过配置文件处理。

Dify 为默认实现，其他平台通过继承并重写 _build_body / _parse_event 即可接入。
"""

import json
import logging
import httpx
from typing import AsyncGenerator

from app.adapters.base import AgentAdapter, AdapterConfig

logger = logging.getLogger("self_deployed_adapter")


class SelfDeployedAdapter(AgentAdapter):
    """自部署 Agent 通用适配器 — 默认支持 Dify。"""

    name = "自部署 Agent"
    adapter_type = "self_deployed"
    description = "自部署 Agent (Dify/LangFlow/Flowise 等)"

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self.api_url = config.api_url  # 内网 URL
        self.api_key = config.api_key
        self.platform = config.extra.get("platform", "dify")
        self.user_id = config.extra.get("user_id", "agenthub_user")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_url:
            return False, "未配置自部署 Agent URL"
        return True, ""

    async def stream_reply(
        self,
        message: str,
        history: list[dict] = None,
        system_prompt: str = "",
        tools: list[dict] = None,
        conversation_id: str = None,
    ) -> AsyncGenerator[str, None]:
        """调用自部署 Agent API 流式回复。"""

        valid, err = self.validate_config()
        if not valid:
            yield f"[自部署 Agent 错误: {err}]"
            return

        headers = self._build_headers()
        body = self._build_body(message, history, conversation_id)

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST",
                    self._get_endpoint(),
                    headers=headers,
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        error_body = ""
                        async for chunk in resp.aiter_bytes():
                            error_body += chunk.decode(errors="ignore")
                        yield f"[自部署 Agent 错误: HTTP {resp.status_code}: {error_body[:200]}]"
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

                        text = self._parse_event(event)
                        if text:
                            yield text

        except httpx.ConnectError:
            yield f"\n[无法连接到自部署 Agent: {self.api_url}]"
        except httpx.TimeoutException:
            yield "\n[自部署 Agent 超时，请稍后重试]"
        except Exception as e:
            yield f"\n[自部署 Agent 错误: {str(e)[:200]}]"

    def _build_headers(self) -> dict:
        """构建请求头。"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_endpoint(self) -> str:
        """获取 API 端点 URL。"""
        if self.platform == "dify":
            return f"{self.api_url}/v1/chat-messages"
        elif self.platform == "langflow":
            return f"{self.api_url}/api/v1/run"
        elif self.platform == "flowise":
            return f"{self.api_url}/api/v1/prediction"
        else:
            return f"{self.api_url}/v1/chat-messages"

    def _build_body(self, message: str, history: list[dict], conversation_id: str) -> dict:
        """构建请求体（按平台区分）。"""
        if self.platform == "dify":
            return {
                "inputs": {},
                "query": message,
                "response_mode": "streaming",
                "conversation_id": conversation_id or "",
                "user": self.user_id,
            }
        elif self.platform == "langflow":
            return {
                "input_value": message,
                "output_type": "chat",
                "input_type": "chat",
                "stream": True,
            }
        elif self.platform == "flowise":
            return {
                "question": message,
                "streaming": True,
            }
        else:
            # 通用格式
            return {
                "message": message,
                "conversation_id": conversation_id or "",
                "stream": True,
            }

    def _parse_event(self, event: dict) -> str:
        """解析 SSE 事件，提取文本。"""
        if self.platform == "dify":
            event_type = event.get("event", "")
            if event_type == "agent_message":
                return event.get("answer", "")
            elif event_type == "message":
                return event.get("answer", "")
        elif self.platform == "langflow":
            event_type = event.get("event", "")
            if event_type == "end":
                return event.get("outputs", {}).get("message", "")
        elif self.platform == "flowise":
            return event.get("data", "")
        else:
            # 通用：尝试提取 text/answer/content
            return event.get("text") or event.get("answer") or event.get("content") or ""
        return ""


class DifyAdapter(SelfDeployedAdapter):
    """Dify 专用适配器（继承通用适配器，增加 Dify 特定功能）。"""

    name = "Dify Agent"
    description = "Dify 自部署 Agent — 开源 LLMOps 平台"

    def __init__(self, config: AdapterConfig):
        config.extra = config.extra or {}
        config.extra["platform"] = "dify"
        super().__init__(config)
