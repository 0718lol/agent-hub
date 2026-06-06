"""Claude Adapter — Anthropic Messages API + tool_use。

将 Claude 作为外部 Agent 接入，支持：
- 流式回复 (SSE)
- 原生工具调用 (tool_use)
- 多轮工具循环（自动执行工具并继续对话）
- 项目工具自动注入
"""

import json
import logging
import httpx
from typing import AsyncGenerator

from app.adapters.base import AgentAdapter, AdapterConfig
from app.adapters.tool_converter import (
    get_project_tools, to_claude_tools,
    parse_claude_tool_use, execute_tool,
    supports_tool_calling,
)

logger = logging.getLogger("claude_adapter")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOOL_ROUNDS = 5


class ClaudeAdapter(AgentAdapter):
    """Claude 适配器 — 调用 Anthropic Messages API。"""

    name = "Claude Code"
    adapter_type = "claude"
    description = "Anthropic Claude — 最强代码 Agent，支持原生工具调用"

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        base = config.api_url or ""
        if base:
            # 用户提供的是 base_url，自动拼接 /v1/messages
            base = base.rstrip("/")
            if not base.endswith("/v1/messages"):
                base = base + "/v1/messages"
            self.api_url = base
        else:
            self.api_url = ANTHROPIC_API_URL
        self.api_key = (config.api_key or "").strip()
        self.model = config.model or "claude-sonnet-4-20250514"

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "未配置 Anthropic API Key"
        return True, ""

    async def stream_reply(
        self,
        message: str,
        history: list[dict] = None,
        system_prompt: str = "",
        tools: list[dict] = None,
        conversation_id: str = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用 Claude API，支持工具循环。"""

        valid, err = self.validate_config()
        logger.info(f"[ClaudeAdapter] stream_reply called: valid={valid}, err={err}")
        if not valid:
            yield f"[Claude 适配器错误: {err}]"
            return

        # 构建消息
        messages = []
        if history:
            for msg in history[-20:]:
                role = msg.get("role", "user") or msg.get("sender", "user")
                if role == "user":
                    role = "user"
                elif role:
                    role = "assistant"
                raw_content = msg.get("content", "")
                # content 可能是字符串或字典，统一提取为字符串
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
        claude_tools = None
        _mode = self.config.tool_mode
        _should_use_tools = (
            _mode == "agent"
            or (_mode == "auto" and supports_tool_calling(self.model, self.api_url))
        )
        if _should_use_tools:
            if tools:
                claude_tools = to_claude_tools(tools)
            else:
                project_tools = get_project_tools()
                if project_tools:
                    claude_tools = to_claude_tools(project_tools)

        # 工具循环
        for round_num in range(MAX_TOOL_ROUNDS + 1):
            accumulated = ""
            tool_calls = []

            try:
                async for chunk in self._call_api(messages, system_prompt, claude_tools):
                    if isinstance(chunk, str):
                        accumulated += chunk
                        yield chunk
                    elif isinstance(chunk, dict):
                        # tool_use 块
                        tool_calls.append(chunk)
            except Exception as e:
                yield f"\n[Claude API 错误: {str(e)[:200]}]"
                return

            # 没有工具调用，结束
            if not tool_calls or round_num >= MAX_TOOL_ROUNDS:
                return

            # 执行工具调用
            messages.append({"role": "assistant", "content": accumulated})
            tool_results = []

            for tc in tool_calls:
                tool_name = tc["name"]
                tool_input = tc.get("input", {})
                tool_id = tc.get("id", "")

                logger.info(f"Claude calling tool: {tool_name}({tool_input})")

                # 注入 conversation_id
                if conversation_id:
                    tool_input.setdefault("conversation_id", conversation_id)

                result = await execute_tool(tool_name, tool_input)

                # 格式化结果给 Claude
                result_text = json.dumps(
                    result.get("data") if result.get("success") else {"error": result.get("error")},
                    ensure_ascii=False,
                    default=str,
                )[:5000]

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_text,
                })

                # 给用户显示工具调用结果
                yield f"\n\n> 🔧 **工具调用**: `{tool_name}`\n"

            # 把工具结果作为 user 消息发回
            messages.append({"role": "user", "content": tool_results})

    async def _call_api(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict] = None,
    ):
        """调用 Anthropic Messages API，流式返回。

        Yields:
            str: 文本片段
            dict: tool_use 块 {"id": "...", "name": "...", "input": {...}}
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        body = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages,
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream("POST", self.api_url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    error_body = ""
                    async for chunk in resp.aiter_bytes():
                        error_body += chunk.decode(errors="ignore")
                    raise Exception(f"HTTP {resp.status_code}: {error_body[:300]}")

                current_tool = None
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

                    if event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            current_tool = {
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "input": "",
                            }
                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")
                        elif delta.get("type") == "input_json_delta":
                            if current_tool is not None:
                                current_tool["input"] += delta.get("partial_json", "")
                    elif event_type == "content_block_stop":
                        if current_tool is not None:
                            try:
                                input_data = json.loads(current_tool["input"]) if current_tool["input"] else {}
                            except json.JSONDecodeError:
                                input_data = {}
                            yield {
                                "id": current_tool["id"],
                                "name": current_tool["name"],
                                "input": input_data,
                            }
                            current_tool = None
