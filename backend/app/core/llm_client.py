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

    async def chat_stream(self, messages: list[dict], system: str = "") -> AsyncGenerator[str, None]:
        try:
            if self.provider == "opencode":
                async for chunk in self._opencode_stream(messages, system):
                    yield chunk
            elif self.provider == "claude_code":
                async for chunk in self._claude_code_stream(messages, system):
                    yield chunk
            elif self.provider == "anthropic":
                async for chunk in self._anthropic_stream(messages, system):
                    yield chunk
            elif self.provider == "ollama":
                if not self.base_url:
                    self.base_url = "http://127.0.0.1:11434/v1"
                async for chunk in self._openai_stream(messages, system):
                    yield chunk
            else:
                async for chunk in self._openai_stream(messages, system):
                    yield chunk
        except Exception as e:
            yield f"\n[LLM 调用出错: {type(e).__name__}: {str(e)[:200]}]"

    async def _openai_stream(self, messages: list[dict], system: str) -> AsyncGenerator[str, None]:
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
