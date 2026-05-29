import json
import httpx
import time
import asyncio
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

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
        optimized = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                content = cls.compress_single_message(content)
            optimized.append({"role": role, "content": content})

        total_len = sum(len(msg.get("content", "")) for msg in optimized if isinstance(msg.get("content"), str))
        if total_len <= max_total_chars:
            return optimized

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
    """Distributed circuit breaker state machine for LLM providers backed by Redis, with safe in-memory fallback."""

    def __init__(self, name: str, threshold: int = 3, cooldown: float = 30.0):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.failed_attempts = 0
        self.last_state_change = time.time()
        self._lock = asyncio.Lock()

    async def _get_state_from_redis(self):
        """Retrieve the circuit breaker state from Redis with in-memory fallback."""
        from app.core.redis import redis_manager
        
        if await redis_manager.check_connection():
            try:
                client = redis_manager.get_client()
                data = await client.hgetall(f"agenthub:cb:{self.name}")
                if data:
                    state = data.get("state", "CLOSED")
                    failed_attempts = int(data.get("failed_attempts", "0"))
                    last_state_change = float(data.get("last_state_change", str(time.time())))
                    return state, failed_attempts, last_state_change
            except Exception as e:
                logger.warning(f"Failed to get CB state from Redis for {self.name}: {e}")
                redis_manager._is_connected = False
        
        # Fallback to local variables
        return self.state, self.failed_attempts, self.last_state_change

    async def _set_state_to_redis(self, state: str, failed_attempts: int, last_state_change: float):
        """Save the circuit breaker state to Redis and local memory."""
        # Always update local memory first (for consistency and fallback)
        self.state = state
        self.failed_attempts = failed_attempts
        self.last_state_change = last_state_change
        
        from app.core.redis import redis_manager
        if await redis_manager.check_connection():
            try:
                client = redis_manager.get_client()
                await client.hset(
                    f"agenthub:cb:{self.name}",
                    mapping={
                        "state": state,
                        "failed_attempts": str(failed_attempts),
                        "last_state_change": str(last_state_change)
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to set CB state to Redis for {self.name}: {e}")
                redis_manager._is_connected = False

    async def record_success(self):
        async with self._lock:
            state, failed_attempts, last_state_change = await self._get_state_from_redis()
            if state != "CLOSED":
                logger.info(f"CircuitBreaker [{self.name}] recovered! {state} -> CLOSED")
            await self._set_state_to_redis("CLOSED", 0, time.time())

    async def record_failure(self):
        async with self._lock:
            state, failed_attempts, last_state_change = await self._get_state_from_redis()
            failed_attempts += 1
            new_state = state
            new_last_state_change = last_state_change
            if failed_attempts >= self.threshold and state != "OPEN":
                new_state = "OPEN"
                new_last_state_change = time.time()
                logger.warning(f"CircuitBreaker [{self.name}] TRIPPED! {state} -> OPEN due to {failed_attempts} failures")
            await self._set_state_to_redis(new_state, failed_attempts, new_last_state_change)

    async def allow_request(self) -> bool:
        async with self._lock:
            state, failed_attempts, last_state_change = await self._get_state_from_redis()
            now = time.time()
            if state == "OPEN":
                if now - last_state_change > self.cooldown:
                    logger.info(f"CircuitBreaker [{self.name}] cooldown expired. OPEN -> HALF-OPEN (testing canary)")
                    await self._set_state_to_redis("HALF-OPEN", failed_attempts, now)
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

    async def execute_with_retry(self, client_instance, stream_func, messages: list[dict], system: str, enabled_tools: list[str] = None) -> AsyncGenerator[str, None]:
        provider = client_instance.provider
        model = client_instance.model
        breaker = self.get_breaker(provider)

        # Access active step context variable to start LLM span
        from app.core.metrics import active_step_var
        step = active_step_var.get()
        span = None
        if step:
            span = step.start_span(
                name=f"llm_{provider}_{model}",
                span_type="llm",
                input_data={"messages": messages, "system": system, "enabled_tools": enabled_tools}
            )

        output_chunks = []

        # 1. Check Circuit Breaker
        if not await breaker.allow_request():
            if provider != "ollama" and client_instance.is_ollama_active():
                failover_notice = "⚠️ [主模型服务连接已熔断，已自动降级 Failover 路由至本地 Ollama，当前状态: OPEN]\n\n"
                output_chunks.append(failover_notice)
                yield failover_notice
                
                try:
                    ollama_gen = client_instance._openai_stream_fallback_ollama(messages, system, enabled_tools)
                except TypeError:
                    ollama_gen = client_instance._openai_stream_fallback_ollama(messages, system)
                
                async for chunk in ollama_gen:
                    output_chunks.append(chunk)
                    yield chunk
                
                if span:
                    generated_text = "".join(output_chunks)
                    span.finish(
                        output_data=generated_text,
                        status="success",
                        metadata={"model": "qwen2.5-coder", "provider": "ollama", "failover": True, "tokens_approx": len(generated_text) // 3}
                    )
                return
            else:
                err_notice = f"❌ [LLM 服务已熔断 (OPEN)。请在 30 秒冷却期后再试，或切换本地 Ollama 模型。]"
                yield err_notice
                if span:
                    span.finish(output_data=err_notice, status="error", metadata={"error": "CircuitBreakerOpenException"})
                return

        # 2. Execute call with Exponential Backoff
        max_retries = 3
        backoffs = [1.5, 3.0, 6.0]

        for attempt in range(max_retries):
            try:
                try:
                    gen = stream_func(messages, system, enabled_tools)
                except TypeError:
                    gen = stream_func(messages, system)
                first_chunk = None

                try:
                    first_chunk = await gen.__anext__()
                except StopAsyncIteration:
                    await breaker.record_success()
                    if span:
                        span.finish(output_data="", status="success", metadata={"model": model, "provider": provider})
                    return
                except Exception as e:
                    raise e

                await breaker.record_success()
                output_chunks.append(first_chunk)
                yield first_chunk

                async for chunk in gen:
                    output_chunks.append(chunk)
                    yield chunk
                
                # Successful end of LLM stream span logging
                if span:
                    generated_text = "".join(output_chunks)
                    span.finish(
                        output_data=generated_text,
                        status="success",
                        metadata={"model": model, "provider": provider, "tokens_approx": len(generated_text) // 3}
                    )
                break

            except Exception as e:
                logger.error(f"LLM attempt {attempt + 1} failed for {provider}: {type(e).__name__}: {e}")

                retriable = True
                if isinstance(e, LLMAPIError):
                    if e.status_code != 429 and e.status_code < 500:
                        retriable = False

                if not retriable:
                    await breaker.record_failure()
                    err_msg = f"\n[LLM 终端错误 (不可重试): {str(e)}]"
                    output_chunks.append(err_msg)
                    yield err_msg
                    if span:
                        generated_text = "".join(output_chunks)
                        span.finish(
                            output_data=generated_text,
                            status="error",
                            metadata={"error": type(e).__name__, "model": model, "provider": provider}
                        )
                    return

                if attempt == max_retries - 1:
                    await breaker.record_failure()
                    err_msg = f"\n[LLM 故障已触发熔断保护: {type(e).__name__}: {str(e)[:150]}]"
                    output_chunks.append(err_msg)
                    yield err_msg

                    if provider != "ollama" and client_instance.is_ollama_active():
                        failover_msg = "\n\n⚠️ [主模型重试失败已触发熔断，自动降级至本地 Ollama 运行...]\n\n"
                        output_chunks.append(failover_msg)
                        yield failover_msg
                        
                        try:
                            ollama_gen = client_instance._openai_stream_fallback_ollama(messages, system, enabled_tools)
                        except TypeError:
                            ollama_gen = client_instance._openai_stream_fallback_ollama(messages, system)
                        
                        async for chunk in ollama_gen:
                            output_chunks.append(chunk)
                            yield chunk
                    
                    if span:
                        generated_text = "".join(output_chunks)
                        span.finish(
                            output_data=generated_text,
                            status="error",
                            metadata={"error": type(e).__name__, "model": model, "provider": provider}
                        )
                    return

                sleep_time = backoffs[attempt]
                jitter_msg = f"\n[LLM 连接出现抖动 ({type(e).__name__})，正在进行第 {attempt + 1} 次后台指数退避重试，等待 {sleep_time}s...]\n"
                output_chunks.append(jitter_msg)
                yield jitter_msg
                await asyncio.sleep(sleep_time)


resilience_manager = ResilienceManager()


class LLMClient:
    """Unified LLM client supporting standard OpenAI Native Function Calling with delta conversion streams."""

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
        return True

    async def _openai_stream_fallback_ollama(self, messages: list[dict], system: str, enabled_tools: list[str] = None) -> AsyncGenerator[str, None]:
        original_provider = self.provider
        original_base_url = self.base_url
        original_model = self.model
        original_api_key = self.api_key

        self.provider = "ollama"
        self.base_url = "http://127.0.0.1:11434/v1"
        self.model = "qwen2.5-coder"
        self.api_key = "ollama"

        try:
            async for chunk in self._openai_stream(messages, system, enabled_tools):
                yield chunk
        except Exception as e:
            yield f"\n[Ollama 本地降级重定向调用失败: {type(e).__name__}: {str(e)[:150]}]"
        finally:
            self.provider = original_provider
            self.base_url = original_base_url
            self.model = original_model
            self.api_key = original_api_key

    async def chat_stream(self, messages: list[dict], system: str = "", enabled_tools: list[str] = None) -> AsyncGenerator[str, None]:
        optimized_messages = ContextOptimizer.optimize_messages(messages)

        try:
            if self.provider == "opencode":
                async for chunk in resilience_manager.execute_with_retry(self, self._opencode_stream, optimized_messages, system, enabled_tools):
                    yield chunk
            elif self.provider == "claude_code":
                async for chunk in resilience_manager.execute_with_retry(self, self._claude_code_stream, optimized_messages, system, enabled_tools):
                    yield chunk
            elif self.provider == "anthropic":
                async for chunk in resilience_manager.execute_with_retry(self, self._anthropic_stream, optimized_messages, system, enabled_tools):
                    yield chunk
            elif self.provider == "ollama":
                if not self.base_url:
                    self.base_url = "http://127.0.0.1:11434/v1"
                async for chunk in resilience_manager.execute_with_retry(self, self._openai_stream, optimized_messages, system, enabled_tools):
                    yield chunk
            else:
                async for chunk in resilience_manager.execute_with_retry(self, self._openai_stream, optimized_messages, system, enabled_tools):
                    yield chunk
        except Exception as e:
            yield f"\n[LLM 调用出错: {type(e).__name__}: {str(e)[:200]}]"

    def _get_api_tools(self, enabled_tools: list[str] = None) -> list[dict]:
        """Convert AgentTools dynamically into standard API tools definition format."""
        try:
            from app.tools.registry import TOOL_REGISTRY
            api_tools = []
            for name, tool in TOOL_REGISTRY.items():
                if not tool.enabled:
                    continue
                if enabled_tools is not None and name not in enabled_tools:
                    continue
                
                api_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters or {"type": "object", "properties": {}}
                    }
                })
            return api_tools
        except Exception:
            return []

    async def _openai_stream(self, messages: list[dict], system: str, enabled_tools: list[str] = None) -> AsyncGenerator[str, None]:
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

        # 🚀 Phase 3: Seamless standard Native Tool Calling conversion
        api_tools = self._get_api_tools(enabled_tools)
        if api_tools and self.provider != "ollama": # Local Ollama bypasses standard tools in simple modes
            payload["tools"] = api_tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }

        active_tool_calls: Dict[int, Dict[str, Any]] = {}

        try:
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
                            
                            # 1. Dispatch text chunk directly
                            if content:
                                yield content

                            # 2. Check and translate API tool calls stream into Legacy [tool_call] tags dynamically
                            api_calls = delta.get("tool_calls", [])
                            if api_calls:
                                for call in api_calls:
                                    index = call.get("index", 0)
                                    func = call.get("function", {})
                                    name = func.get("name", "")
                                    args_chunk = func.get("arguments", "")

                                    if index not in active_tool_calls:
                                        # New tool call starts in stream!
                                        active_tool_calls[index] = {"name": name, "arguments": ""}
                                        # Instant bridge notification
                                        yield f'[tool_call:{name}]'

                                    # Accumulate arguments
                                    if args_chunk:
                                        active_tool_calls[index]["arguments"] += args_chunk
                                        yield args_chunk

                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        finally:
            # 3. Ensure proper tag enclosure at the end of generator stream safely
            for index, call_info in active_tool_calls.items():
                yield '[/tool_call]'
            active_tool_calls.clear()

    async def _anthropic_stream(self, messages: list[dict], system: str, enabled_tools: list[str] = None) -> AsyncGenerator[str, None]:
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

        # 🚀 Phase 3: Seamless Anthropic Native Tools injection
        api_tools = self._get_api_tools(enabled_tools)
        if api_tools:
            # Convert JSON Schema parameters for Anthropic Native tools specification
            anthropic_tools = []
            for tool in api_tools:
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func["description"],
                    "input_schema": func["parameters"]
                })
            payload["tools"] = anthropic_tools

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json; charset=utf-8",
        }

        active_tool_calls: Dict[int, Dict[str, Any]] = {}

        try:
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
                            event_type = event.get("type")
                            
                            # 1. Text chunk delta
                            if event_type == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        yield text
                                elif delta.get("type") == "input_json_delta":
                                    index = event.get("index", 0)
                                    partial_json = delta.get("partial_json", "")
                                    if index in active_tool_calls and partial_json:
                                        active_tool_calls[index]["arguments"] += partial_json
                                        yield partial_json

                            # 2. Tool call start
                            elif event_type == "content_block_start":
                                block = event.get("content_block", {})
                                if block.get("type") == "tool_use":
                                    index = event.get("index", 0)
                                    name = block.get("name", "")
                                    active_tool_calls[index] = {"name": name, "arguments": ""}
                                    yield f'[tool_call:{name}]'

                        except (json.JSONDecodeError, KeyError):
                            continue
        finally:
            for index, call_info in active_tool_calls.items():
                yield '[/tool_call]'
            active_tool_calls.clear()

    async def _claude_code_stream(self, messages: list[dict], system: str, enabled_tools: list[str] = None) -> AsyncGenerator[str, None]:
        from app.core.claude_code_client import claude_code_stream
        async for chunk in claude_code_stream(
            messages=messages,
            system=system,
            api_key=self.api_key,
            model=self.model,
        ):
            yield chunk

    async def _opencode_stream(self, messages: list[dict], system: str, enabled_tools: list[str] = None) -> AsyncGenerator[str, None]:
        from app.core.opencode_client import opencode_stream
        async for chunk in opencode_stream(
            messages=messages,
            system=system,
        ):
            yield chunk


llm_client = LLMClient()


def _sanitize_for_anthropic(messages: list[dict]) -> list[dict]:
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
