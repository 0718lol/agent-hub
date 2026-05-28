import json
import httpx
import time
import asyncio
import logging
from typing import AsyncGenerator

logger = logging.getLogger("llm_client")


class LLMAPIError(Exception):
    """Custom exception raised when LLM API returns non-200 response."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"LLM API Error {status_code}: {message}")


class ContextOptimizer:
    """Helper to optimize and prune LLM input messages to save tokens."""

    @staticmethod
    def compress_single_message(content: str, max_chars: int = 6000) -> str:
        """Truncate the middle of extremely long messages (e.g. from tool outputs or raw files)
        while preserving the head and tail context.
        """
        if not isinstance(content, str) or len(content) <= max_chars:
            return content

        # Keep 1500 chars from start and 1500 chars from end
        keep = 1500
        head = content[:keep]
        tail = content[-keep:]
        num_pruned = len(content) - 2 * keep

        return (
            f"{head}\n\n"
            f"[... ⚠️ 此处已自动压缩中段 {num_pruned} 字符以节省 Token，防止上下文溢出 ...]\n\n"
            f"{tail}"
        )

    @classmethod
    def optimize_messages(cls, messages: list[dict], max_total_chars: int = 30000) -> list[dict]:
        """Scan messages to compress individual large ones, and compress deep conversation history
        if total character length exceeds max_total_chars.
        """
        # 1. Compress individual large messages
        optimized = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                content = cls.compress_single_message(content)
            optimized.append({"role": role, "content": content})

        # 2. Check total character length
        total_len = sum(len(msg.get("content", "")) for msg in optimized if isinstance(msg.get("content"), str))
        if total_len <= max_total_chars:
            return optimized

        # If too long, perform history compaction:
        # Keep System Prompt, RAG context, and last 3 turns (6 messages) completely intact.
        keep_last_count = 6
        if len(optimized) <= keep_last_count:
            return optimized

        history_to_compress = optimized[:-keep_last_count]
        recent_messages = optimized[-keep_last_count:]

        compressed_history = []
        for msg in history_to_compress:
            role = msg.get("role")
            content = msg.get("content", "")

            if not isinstance(content, str):
                compressed_history.append(msg)
                continue

            # Compress older tool results or large older responses
            if role == "user" and ("[工具结果" in content or "[工具结果:" in content):
                lines = content.split("\n")
                header = lines[0] if lines else "[工具结果]"
                compressed_history.append({
                    "role": role,
                    "content": f"{header}\n[... 此处已自动清除较早的历史工具执行大文本以节省 Token ...]"
                })
            elif role == "assistant" and len(content) > 1000:
                compressed_history.append({
                    "role": role,
                    "content": content[:300] + "\n[... 此处已自动截断较早的历史回复内容以节省 Token ...]"
                })
            else:
                compressed_history.append(msg)

        return compressed_history + recent_messages


class CircuitBreaker:
    """Thread-safe in-memory circuit breaker state machine for LLM providers."""

    def __init__(self, name: str, threshold: int = 3, cooldown: float = 30.0):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.failed_attempts = 0
        self.last_state_change = time.time()
        self._lock = asyncio.Lock()

    async def record_success(self):
        async with self._lock:
            if self.state != "CLOSED":
                logger.info(f"CircuitBreaker [{self.name}] recovered! {self.state} -> CLOSED")
            self.state = "CLOSED"
            self.failed_attempts = 0
            self.last_state_change = time.time()

    async def record_failure(self):
        async with self._lock:
            self.failed_attempts += 1
            if self.failed_attempts >= self.threshold and self.state != "OPEN":
                self.state = "OPEN"
                self.last_state_change = time.time()
                logger.warning(f"CircuitBreaker [{self.name}] TRIPPED! CLOSED -> OPEN due to {self.failed_attempts} failures")

    async def allow_request(self) -> bool:
        async with self._lock:
            now = time.time()
            if self.state == "OPEN":
                if now - self.last_state_change > self.cooldown:
                    self.state = "HALF-OPEN"
                    self.last_state_change = now
                    logger.info(f"CircuitBreaker [{self.name}] cooldown expired. OPEN -> HALF-OPEN (testing canary)")
                    return True
                return False
            return True


class ResilienceManager:
    """Handles automatic retries, backoff, and circuit breaking/failover for LLM calls."""

    def __init__(self):
        self.breakers = {}

    def get_breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self.breakers:
            self.breakers[provider] = CircuitBreaker(provider)
        return self.breakers[provider]

    async def execute_with_retry(self, client_instance, stream_func, messages: list[dict], system: str) -> AsyncGenerator[str, None]:
        provider = client_instance.provider
        breaker = self.get_breaker(provider)

        # 1. Check Circuit Breaker
        if not await breaker.allow_request():
            if provider != "ollama" and client_instance.is_ollama_active():
                yield "⚠️ [主模型服务连接已熔断，已自动降级 Failover 路由至本地 Ollama，当前状态: OPEN]\n\n"
                async for chunk in client_instance._openai_stream_fallback_ollama(messages, system):
                    yield chunk
                return
            else:
                yield f"❌ [LLM 服务已熔断 (OPEN)。请在 30 秒冷却期后再试，或切换本地 Ollama 模型。]"
                return

        # 2. Execute call with Exponential Backoff
        max_retries = 3
        backoffs = [1.5, 3.0, 6.0]

        for attempt in range(max_retries):
            try:
                gen = stream_func(messages, system)
                first_chunk = None

                try:
                    # Peek at the first chunk to catch connection/HTTP status errors early
                    first_chunk = await gen.__anext__()
                except StopAsyncIteration:
                    await breaker.record_success()
                    return
                except Exception as e:
                    raise e

                # Got first chunk successfully! Record success and stream out
                await breaker.record_success()
                yield first_chunk

                async for chunk in gen:
                    yield chunk
                break  # Completed successfully

            except Exception as e:
                logger.error(f"LLM attempt {attempt + 1} failed for {provider}: {type(e).__name__}: {e}")

                # Determine if retriable
                retriable = True
                if isinstance(e, LLMAPIError):
                    # Only retry on 429 (rate limit) or 5xx (server error)
                    if e.status_code != 429 and e.status_code < 500:
                        retriable = False

                if not retriable:
                    await breaker.record_failure()
                    yield f"\n[LLM 终端错误 (不可重试): {str(e)}]"
                    return

                if attempt == max_retries - 1:
                    await breaker.record_failure()
                    yield f"\n[LLM 故障已触发熔断保护: {type(e).__name__}: {str(e)[:150]}]"

                    # Failover to local Ollama if available
                    if provider != "ollama" and client_instance.is_ollama_active():
                        yield "\n\n⚠️ [主模型重试失败已触发熔断，自动降级至本地 Ollama 运行...]\n\n"
                        async for chunk in client_instance._openai_stream_fallback_ollama(messages, system):
                            yield chunk
                    return

                sleep_time = backoffs[attempt]
                yield f"\n[LLM 连接出现抖动 ({type(e).__name__})，正在进行第 {attempt + 1} 次后台指数退避重试，等待 {sleep_time}s...]\n"
                await asyncio.sleep(sleep_time)


resilience_manager = ResilienceManager()


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

    def is_ollama_active(self) -> bool:
        """Returns True if local Ollama is active or available for failover."""
        return True

    async def _openai_stream_fallback_ollama(self, messages: list[dict], system: str) -> AsyncGenerator[str, None]:
        """Stream helper to fall back to a local Ollama instance without losing state."""
        original_provider = self.provider
        original_base_url = self.base_url
        original_model = self.model
        original_api_key = self.api_key

        self.provider = "ollama"
        self.base_url = "http://127.0.0.1:11434/v1"
        self.model = "qwen2.5-coder"  # Popular robust local developer model
        self.api_key = "ollama"

        try:
            async for chunk in self._openai_stream(messages, system):
                yield chunk
        except Exception as e:
            yield f"\n[Ollama 本地降级重定向调用失败: {type(e).__name__}: {str(e)[:150]}]"
        finally:
            self.provider = original_provider
            self.base_url = original_base_url
            self.model = original_model
            self.api_key = original_api_key

    async def chat_stream(self, messages: list[dict], system: str = "") -> AsyncGenerator[str, None]:
        # Perform Context Pruning and Token Optimization first!
        optimized_messages = ContextOptimizer.optimize_messages(messages)

        try:
            if self.provider == "opencode":
                async for chunk in resilience_manager.execute_with_retry(self, self._opencode_stream, optimized_messages, system):
                    yield chunk
            elif self.provider == "claude_code":
                async for chunk in resilience_manager.execute_with_retry(self, self._claude_code_stream, optimized_messages, system):
                    yield chunk
            elif self.provider == "anthropic":
                async for chunk in resilience_manager.execute_with_retry(self, self._anthropic_stream, optimized_messages, system):
                    yield chunk
            elif self.provider == "ollama":
                if not self.base_url:
                    self.base_url = "http://127.0.0.1:11434/v1"
                async for chunk in resilience_manager.execute_with_retry(self, self._openai_stream, optimized_messages, system):
                    yield chunk
            else:
                async for chunk in resilience_manager.execute_with_retry(self, self._openai_stream, optimized_messages, system):
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
                    err_msg = body.decode('utf-8', errors='replace')[:300]
                    raise LLMAPIError(resp.status_code, err_msg)

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

        sanitized = _sanitize_for_anthropic(messages)
        if not sanitized:
            raise ValueError("消息为空或无 user 消息，无法调用 Anthropic API")

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": sanitized,
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
                    err_msg = body.decode('utf-8', errors='replace')[:300]
                    raise LLMAPIError(resp.status_code, err_msg)

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


def _sanitize_for_anthropic(messages: list[dict]) -> list[dict]:
    """Anthropic 要求 messages 以 user 开头且 user/assistant 交替。
    合并相邻同 role 的消息，丢弃开头的 assistant 消息。"""
    cleaned: list[dict] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if not content or role not in ("user", "assistant"):
            continue
        if cleaned and cleaned[-1]["role"] == role:
            cleaned[-1]["content"] = f"{cleaned[-1]['content']}\n\n{content}"
        else:
            cleaned.append({"role": role, "content": content})
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)
    return cleaned
