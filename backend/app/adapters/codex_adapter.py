"""Codex Adapter — OpenAI Assistants API。

将 Codex (OpenAI Assistants) 作为外部 Agent 接入，支持：
- 流式回复 (SSE)
- 原生 function calling
- 内置 code_interpreter 和 file_search
- 多轮工具循环
"""

import json
import logging
import httpx
from typing import AsyncGenerator

from app.adapters.base import AgentAdapter, AdapterConfig
from app.adapters.tool_converter import (
    get_project_tools, to_openai_tools,
    parse_openai_tool_calls, execute_tool,
)

logger = logging.getLogger("codex_adapter")

OPENAI_ASSISTANTS_URL = "https://api.openai.com/v1"
MAX_TOOL_ROUNDS = 5


class CodexAdapter(AgentAdapter):
    """Codex 适配器 — 调用 OpenAI Assistants API。"""

    name = "Codex"
    adapter_type = "codex"
    description = "OpenAI Assistants API — 代码生成 Agent，支持代码解释器和文件搜索"

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self.api_url = config.api_url or OPENAI_ASSISTANTS_URL
        self.api_key = config.api_key
        self.model = config.model or "gpt-4o"
        self._assistant_id = config.extra.get("assistant_id")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "未配置 OpenAI API Key"
        return True, ""

    async def stream_reply(
        self,
        message: str,
        history: list[dict] = None,
        system_prompt: str = "",
        tools: list[dict] = None,
        conversation_id: str = None,
    ) -> AsyncGenerator[str, None]:
        """通过 OpenAI Assistants API 流式回复。"""

        valid, err = self.validate_config()
        if not valid:
            yield f"[Codex 适配器错误: {err}]"
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2",
        }

        try:
            # 1. 创建或复用 Assistant
            assistant_id = self._assistant_id or await self._get_or_create_assistant(headers, system_prompt, tools)

            # 2. 创建 Thread
            thread_id = await self._create_thread(headers)

            # 3. 添加历史消息
            if history:
                for msg in history[-10:]:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if content and role in ("user", "assistant"):
                        await self._add_message(headers, thread_id, role, content)

            # 4. 添加用户消息
            await self._add_message(headers, thread_id, "user", message)

            # 5. 创建 Run 并流式读取
            async for chunk in self._stream_run(headers, thread_id, assistant_id, tools, conversation_id):
                yield chunk

        except Exception as e:
            yield f"\n[Codex API 错误: {str(e)[:200]}]"

    async def _get_or_create_assistant(self, headers: dict, system_prompt: str, tools: list[dict]) -> str:
        """获取或创建 Assistant。"""
        if self._assistant_id:
            return self._assistant_id

        # 构建 tools 定义
        assistant_tools = [{"type": "code_interpreter"}, {"type": "file_search"}]
        if tools:
            assistant_tools.extend(to_openai_tools(tools))
        else:
            project_tools = get_project_tools()
            if project_tools:
                assistant_tools.extend(to_openai_tools(project_tools))

        body = {
            "name": f"AgentHub Codex ({self.model})",
            "instructions": system_prompt or "You are a helpful coding assistant.",
            "model": self.model,
            "tools": assistant_tools,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.api_url}/assistants", headers=headers, json=body)
            if resp.status_code != 200:
                raise Exception(f"Create assistant failed: {resp.status_code} {resp.text[:200]}")
            data = resp.json()
            self._assistant_id = data["id"]
            return self._assistant_id

    async def _create_thread(self, headers: dict) -> str:
        """创建 Thread。"""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.api_url}/threads", headers=headers, json={})
            if resp.status_code != 200:
                raise Exception(f"Create thread failed: {resp.status_code}")
            return resp.json()["id"]

    async def _add_message(self, headers: dict, thread_id: str, role: str, content: str):
        """向 Thread 添加消息。"""
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"{self.api_url}/threads/{thread_id}/messages",
                headers=headers,
                json={"role": role, "content": content},
            )

    async def _stream_run(
        self,
        headers: dict,
        thread_id: str,
        assistant_id: str,
        tools: list[dict],
        conversation_id: str,
    ) -> AsyncGenerator[str, None]:
        """创建 Run 并流式读取事件。"""

        body = {
            "assistant_id": assistant_id,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.api_url}/threads/{thread_id}/runs",
                headers=headers,
                json=body,
            ) as resp:
                if resp.status_code != 200:
                    error_body = ""
                    async for chunk in resp.aiter_bytes():
                        error_body += chunk.decode(errors="ignore")
                    raise Exception(f"Run failed: HTTP {resp.status_code}: {error_body[:300]}")

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

                    event_type = event.get("object", "")

                    # 文本增量
                    if event_type == "thread.message.delta":
                        delta = event.get("delta", {})
                        content_list = delta.get("content", [])
                        for c in content_list:
                            if c.get("type") == "text":
                                yield c.get("text", {}).get("value", "")

                    # 工具调用（function call）
                    elif event_type == "thread.run.requires_action":
                        run = event.get("run", {})
                        required = run.get("required_action", {})
                        if required.get("type") == "submit_tool_outputs":
                            tool_calls = required.get("submit_tool_outputs", {}).get("tool_outputs", [])
                            outputs = []
                            for tc in tool_calls:
                                func = tc.get("function", {})
                                tool_name = func.get("name", "")
                                tool_args = func.get("arguments", "{}")
                                try:
                                    params = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
                                except json.JSONDecodeError:
                                    params = {}

                                if conversation_id:
                                    params.setdefault("conversation_id", conversation_id)

                                logger.info(f"Codex calling tool: {tool_name}({params})")
                                result = await execute_tool(tool_name, params)
                                result_text = json.dumps(
                                    result.get("data") if result.get("success") else {"error": result.get("error")},
                                    ensure_ascii=False, default=str,
                                )[:5000]

                                outputs.append({
                                    "tool_call_id": tc.get("id", ""),
                                    "output": result_text,
                                })
                                yield f"\n\n> 🔧 **工具调用**: `{tool_name}`\n"

                            # 提交工具结果
                            run_id = run.get("id", "")
                            await client.post(
                                f"{self.api_url}/threads/{thread_id}/runs/{run_id}/submit_tool_outputs",
                                headers=headers,
                                json={"tool_outputs": outputs},
                            )
