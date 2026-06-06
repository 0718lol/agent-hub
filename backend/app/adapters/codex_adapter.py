"""Codex Adapter — OpenAI 兼容 Chat Completions API。

将 Codex 作为外部 Agent 接入，支持：
- 流式回复 (SSE)
- 原生 function calling
- 多轮工具循环（自动执行工具并继续对话）
- 兼容 DeepSeek、Qwen 等国产模型
"""

import json
import logging
import httpx
from typing import AsyncGenerator

from app.adapters.base import AgentAdapter, AdapterConfig
from app.adapters.tool_converter import (
    get_project_tools, to_openai_tools,
    parse_openai_tool_calls, execute_tool,
    supports_tool_calling,
)

logger = logging.getLogger("codex_adapter")

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
MAX_TOOL_ROUNDS = 5


class CodexAdapter(AgentAdapter):
    """Codex 适配器 — 调用 OpenAI 兼容 Chat Completions API。"""

    name = "Codex"
    adapter_type = "codex"
    description = "OpenAI 兼容 API — 代码生成 Agent（支持 DeepSeek/Qwen 等国产模型）"

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        base = config.api_url or ""
        if base:
            base = base.rstrip("/")
            if not base.endswith("/chat/completions"):
                base = base + "/chat/completions"
            self.api_url = base
        else:
            self.api_url = OPENAI_CHAT_URL
        self.api_key = (config.api_key or "").strip()
        self.model = config.model or "deepseek-v4-pro"

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "未配置 API Key"
        return True, ""

    async def stream_reply(
        self,
        message: str,
        history: list[dict] = None,
        system_prompt: str = "",
        tools: list[dict] = None,
        conversation_id: str = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用 Chat Completions API，支持工具循环。"""

        valid, err = self.validate_config()
        if not valid:
            yield f"[Codex 适配器错误: {err}]"
            return

        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if history:
            for msg in history[-20:]:
                role = msg.get("role") or msg.get("sender", "user")
                if role not in ("user", "assistant"):
                    role = "user" if role == "user" else "assistant"
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

        # 获取工具定义 — 根据 tool_mode 决定是否注入
        openai_tools = None
        _mode = self.config.tool_mode
        _should_use_tools = (
            _mode == "agent"
            or (_mode == "auto" and supports_tool_calling(self.model, self.api_url))
        )
        if _should_use_tools:
            if tools:
                openai_tools = to_openai_tools(tools)
            else:
                project_tools = get_project_tools()
                if project_tools:
                    openai_tools = to_openai_tools(project_tools)

        # 工具循环
        for round_num in range(MAX_TOOL_ROUNDS + 1):
            accumulated = ""
            tool_calls_raw = []

            try:
                async for chunk in self._call_api(messages, openai_tools):
                    if isinstance(chunk, str):
                        accumulated += chunk
                        yield chunk
                    elif isinstance(chunk, list):
                        tool_calls_raw = chunk
            except Exception as e:
                yield f"\n[Codex API 错误: {str(e)[:200]}]"
                return

            # 没有工具调用，结束
            if not tool_calls_raw or round_num >= MAX_TOOL_ROUNDS:
                return

            # 执行工具调用
            messages.append({"role": "assistant", "content": accumulated or None, "tool_calls": tool_calls_raw})
            for tc in tool_calls_raw:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                tool_args_str = func.get("arguments", "{}")
                try:
                    tool_params = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                except json.JSONDecodeError:
                    tool_params = {}

                if conversation_id:
                    tool_params.setdefault("conversation_id", conversation_id)

                logger.info(f"Codex calling tool: {tool_name}({tool_params})")
                result = await execute_tool(tool_name, tool_params)
                result_text = json.dumps(
                    result.get("data") if result.get("success") else {"error": result.get("error")},
                    ensure_ascii=False, default=str,
                )[:5000]

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result_text,
                })

                yield f"\n\n> 🔧 **工具调用**: `{tool_name}`\n"

    async def _call_api(self, messages: list, tools: list = None):
        """调用 OpenAI 兼容 Chat Completions API。

        Yields:
            str: 文本片段
            list: tool_calls 数组（当模型请求调用工具时）
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream("POST", self.api_url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    error_body = ""
                    async for chunk in resp.aiter_bytes():
                        error_body += chunk.decode(errors="ignore")
                    raise Exception(f"HTTP {resp.status_code}: {error_body[:300]}")

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

                    choices = event.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    # 文本内容
                    content = delta.get("content")
                    if content:
                        yield content

                    # 工具调用
                    tool_calls = delta.get("tool_calls")
                    if tool_calls:
                        yield tool_calls
