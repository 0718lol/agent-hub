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
    """自部署 Agent 通用适配器 — 支持 OpenCode、Dify 及任意 HTTP 服务。"""

    name = "本地 Agent"
    adapter_type = "self_deployed"
    description = "自部署 Agent — OpenCode/Dify/自定义 HTTP 服务"

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self.api_url = config.api_url  # 内网 URL
        self.api_key = config.api_key
        self.platform = config.extra.get("platform", "opencode")
        self.user_id = config.extra.get("user_id", "agenthub_user")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_url:
            return False, "未配置服务地址"
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

        endpoint = self._get_endpoint()
        # 默认启用 TLS 验证；本地服务可在 extra 中设置 skip_tls=true 跳过
        skip_tls = self.config.extra.get("skip_tls", False)
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout, verify=not skip_tls) as client:
                async with client.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        error_body = ""
                        async for chunk in resp.aiter_bytes():
                            error_body += chunk.decode(errors="ignore")
                        yield f"[自部署 Agent 错误: HTTP {resp.status_code}: {error_body[:200]}]"
                        return

                    current_event_type = ""
                    async for line in resp.aiter_lines():
                        # 兼容 event: 行格式
                        if line.startswith("event:"):
                            current_event_type = line[6:].strip()
                            continue
                        if line.startswith("data:"):
                            data_str = line[5:].lstrip()
                        elif line.startswith("data: "):
                            data_str = line[6:].strip()
                        else:
                            continue
                        if data_str in ("[DONE]", '"[DONE]"'):
                            break

                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = current_event_type or event.get("type", "")
                        current_event_type = ""
                        text = self._parse_event(event, event_type)
                        if text:
                            yield text

        except httpx.ConnectError as e:
            print(f"[LOCAL-DEBUG] ConnectError: {e}")
            yield f"\n[无法连接到自部署 Agent: {self.api_url}]"
        except httpx.TimeoutException:
            print("[LOCAL-DEBUG] Timeout")
            yield "\n[自部署 Agent 超时，请稍后重试]"
        except Exception as e:
            print(f"[LOCAL-DEBUG] Exception: {type(e).__name__}: {e}")
            yield f"\n[自部署 Agent 错误: {str(e)[:200]}]"

    def _build_headers(self) -> dict:
        """构建请求头。"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_endpoint(self) -> str:
        """获取 API 端点 URL。"""
        base = self.api_url.rstrip("/")
        suffix_map = {
            "dify": "/v1/chat-messages",
            "langflow": "/api/v1/run",
            "flowise": "/api/v1/prediction",
            "opencode": "/v1/chat/completions",
        }
        suffix = suffix_map.get(self.platform, "")
        if suffix and not base.endswith(suffix):
            return base + suffix
        return base

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
        elif self.platform == "opencode":
            # OpenAI 兼容格式（OpenCode、vLLM、Ollama 等）
            messages = []
            if history:
                for msg in history[-20:]:
                    role = msg.get("role") or msg.get("sender", "user")
                    role = "assistant" if role == "assistant" else "user"
                    raw_content = msg.get("content", "")
                    if isinstance(raw_content, dict):
                        content = raw_content.get("text", str(raw_content))
                    elif isinstance(raw_content, str):
                        content = raw_content
                    else:
                        content = str(raw_content) if raw_content else ""
                    if content and content.strip():
                        messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": message})
            return {
                "model": self.config.model or "default",
                "messages": messages,
                "stream": True,
            }
        else:
            # 通用格式：用户自定义
            return {
                "message": message,
                "conversation_id": conversation_id or "",
                "stream": True,
            }

    def _parse_event(self, event: dict, event_type: str = "") -> str:
        """解析 SSE 事件，提取文本。"""
        if self.platform == "dify":
            et = event_type or event.get("event", "")
            if et in ("agent_message", "message"):
                return event.get("answer", "")
        elif self.platform == "langflow":
            et = event_type or event.get("event", "")
            if et == "end":
                return event.get("outputs", {}).get("message", "")
        elif self.platform == "flowise":
            return event.get("data", "")
        elif self.platform == "opencode":
            # OpenAI 兼容格式：choices[0].delta.content
            choices = event.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content") or ""
                if content:
                    return content
            # 兼容 OpenCode 自定义事件格式
            if event_type == "message.text" or event.get("type") == "message.text":
                return event.get("text") or event.get("content") or ""
            if event_type == "message.delta":
                return event.get("delta", {}).get("text") or event.get("text") or ""
        else:
            # 通用：尝试多种字段
            return (event.get("text") or event.get("answer") or event.get("content")
                    or event.get("delta", {}).get("content")
                    or event.get("message", {}).get("content")
                    or event.get("data", {}).get("content") or "")
        return ""


class DifyAdapter(SelfDeployedAdapter):
    """Dify 专用适配器（继承通用适配器，增加 Dify 特定功能）。"""

    name = "Dify Agent"
    description = "Dify 自部署 Agent — 开源 LLMOps 平台"

    def __init__(self, config: AdapterConfig):
        config.extra = config.extra or {}
        config.extra["platform"] = "dify"
        super().__init__(config)
