import json
import httpx
from typing import AsyncGenerator


class LLMClient:
    """Unified LLM client supporting OpenAI-compatible, Anthropic, Claude Code SDK, and OpenCode formats."""

    def __init__(self):
        self.provider: str = "openai"
        self.api_key: str = ""
        self.base_url: str = ""
        self.model: str = ""
        self.temperature: float = 0.5
        self.max_tokens: int = 8192

    def configure(self, provider: str, api_key: str, base_url: str, model: str,
                  temperature: float = None, max_tokens: int = None):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        if temperature is not None:
            self.temperature = temperature
        if max_tokens is not None:
            self.max_tokens = max_tokens

    def is_configured(self) -> bool:
        if self.provider == "opencode":
            return True
        if self.provider == "claude_code":
            return bool(self.api_key)
        if self.provider == "ollama":
            return bool(self.model)
        return bool(self.api_key and self.base_url and self.model)

    async def chat_stream(self, messages: list[dict], system: str = "", route_override=None,
                          tools: list = None, tool_calls_out: list = None) -> AsyncGenerator[str, None]:
        client_to_use = self
        if route_override:
            client_to_use = LLMClient()
            client_to_use.configure(
                provider=route_override.provider,
                api_key=route_override.api_key,
                base_url=route_override.base_url,
                model=route_override.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

        try:
            if client_to_use.provider == "opencode":
                async for chunk in client_to_use._opencode_stream(messages, system):
                    yield chunk
            elif client_to_use.provider == "claude_code":
                async for chunk in client_to_use._claude_code_stream(messages, system):
                    yield chunk
            elif client_to_use.provider == "anthropic":
                async for chunk in client_to_use._anthropic_stream(messages, system):
                    yield chunk
            elif client_to_use.provider == "ollama":
                if not client_to_use.base_url:
                    client_to_use.base_url = "http://127.0.0.1:11434/v1"
                async for chunk in client_to_use._openai_stream(messages, system, tools, tool_calls_out):
                    yield chunk
            else:
                async for chunk in client_to_use._openai_stream(messages, system, tools, tool_calls_out):
                    yield chunk
        except Exception as e:
            yield f"\n[LLM 调用出错: {type(e).__name__}: {str(e)[:200]}]"

    async def _openai_stream(self, messages: list[dict], system: str,
                             tools: list = None, tool_calls_out: list = None) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/chat/completions"
        if not url.startswith("http"):
            url = f"https://{url}"

        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": payload_messages,
            "stream": True,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        if tools:
            formatted_tools = []
            for t in tools:
                formatted_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t.get("inputSchema", t.get("schema", {"type": "object", "properties": {}}))
                    }
                })
            payload["tools"] = formatted_tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield f"[LLM Error {resp.status_code}: {body.decode('utf-8', errors='replace')[:300]}]"
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        
                        # Handle streaming tool calls
                        tool_calls = delta.get("tool_calls", [])
                        if tool_calls and tool_calls_out is not None:
                            for tc in tool_calls:
                                idx = tc.get("index", 0)
                                while len(tool_calls_out) <= idx:
                                    tool_calls_out.append({"id": "", "name": "", "arguments": ""})
                                tc_out = tool_calls_out[idx]
                                if "id" in tc:
                                    tc_out["id"] = tc["id"]
                                if "function" in tc:
                                    fn = tc["function"]
                                    if "name" in fn:
                                        tc_out["name"] = fn["name"]
                                    if "arguments" in fn:
                                        tc_out["arguments"] += fn["arguments"]

                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def _anthropic_stream(self, messages: list[dict], system: str) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/messages"
        if not url.startswith("http"):
            url = f"https://{url}"

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "stream": True,
            "temperature": self.temperature,
        }
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json; charset=utf-8",
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield f"[LLM Error {resp.status_code}: {body.decode('utf-8', errors='replace')[:300]}]"
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        continue


    async def _claude_code_stream(self, messages: list[dict], system: str) -> AsyncGenerator[str, None]:
        from app.core.claude_code_client import claude_code_stream
        async for chunk in claude_code_stream(
            messages=messages,
            system=system,
            api_key=self.api_key,
            model=self.model,
        ):
            yield chunk

    async def _opencode_stream(self, messages: list[dict], system: str) -> AsyncGenerator[str, None]:
        from app.core.opencode_client import opencode_stream
        async for chunk in opencode_stream(
            messages=messages,
            system=system,
        ):
            yield chunk


llm_client = LLMClient()
