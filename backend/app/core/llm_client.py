import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

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
        """
        Compresses a single message by:
        1. Filtering console progress bars and heavy verbose logs (like npm, webpack, vite progress counters, and warnings).
        2. Folding extremely long code bodies (if content contains code blocks with > 100 lines).
        3. Falling back to head/tail truncation if the content is still too long.
        """
        if not isinstance(content, str) or not content:
            return content

        import re

        # Step 1: Filter console progress bars, webpack/vite verbose progress indicators
        # Filter e.g. "99% progress...", "[15:30:10] ...", or npm percentages
        content = re.sub(r'(?i)(\b\d+%\s+(?:progress|building|compile|webpack|vite|rollup|node_modules).*|\[\d{2}:\d{2}:\d{2}\].*(?:progress|building|compile|webpack|vite|rollup).*)', '', content)
        # Filter npm warnings and general warnings to reduce log bloat
        content = re.sub(r'(?i)(Warning:.*|npm WARN.*)\n', '', content)

        # Step 2: AST/Outline-based semantic code folding for extremely long code blocks (> 100 lines)
        # Identify fenced code blocks like ```python ... ``` or ```javascript ... ```
        code_blocks = re.findall(r'(```(\w*)\n(.*?)```)', content, re.DOTALL)
        for _full_block, _lang, code in code_blocks:
            lines = code.split("\n")
            if len(lines) > 100:
                # We perform an outline fold: keeping imports, class definitions, and def (function) signatures,
                # but folding long inner function bodies.
                folded_lines = []
                folded_count = 0
                in_class_or_def = False

                for idx, line in enumerate(lines):
                    stripped = line.strip()
                    # We keep header elements (first 10 lines, last 10 lines) and class/def/import signatures
                    if (idx < 10 or idx > len(lines) - 10 or
                        stripped.startswith("import ") or
                        stripped.startswith("from ") or
                        stripped.startswith("class ") or
                        stripped.startswith("def ") or
                        stripped.startswith("function ") or
                        stripped.startswith("export ")):
                        if in_class_or_def and folded_count > 0:
                            folded_lines.append(f"    # [... 中段 {folded_count} 行实现被折叠以节省 Token ...]")
                            folded_count = 0
                        folded_lines.append(line)
                        in_class_or_def = stripped.startswith("class ") or stripped.startswith("def ") or stripped.startswith("function ")
                    else:
                        if in_class_or_def:
                            folded_count += 1
                        else:
                            folded_lines.append(line)

                if folded_count > 0:
                    folded_lines.append(f"    # [... 中段 {folded_count} 行实现被折叠以节省 Token ...]")

                folded_code = "\n".join(folded_lines)
                content = content.replace(code, folded_code)

        # Step 3: Default Head/Tail truncation preserving critical tracebacks/exceptions/errors
        if len(content) <= max_chars:
            return content

        # Search for Traceback or Error block
        error_pattern = r'(Traceback\s*\(most\s+recent\s+call\s+last\):.*|Exception:.*|Error:.*|RuntimeError:.*|TypeError:.*|ValueError:.*|SyntaxError:.*|NameError:.*|KeyError:.*|AttributeError:.*)'
        error_match = re.search(error_pattern, content, re.IGNORECASE | re.DOTALL)
        error_block = ""
        if error_match:
            # Extract up to 1200 characters from the error start
            error_block = error_match.group(0)[:1200]

        keep = max_chars // 6
        head = content[:keep * 2]
        tail = content[-keep * 2:]

        if error_block:
            # We construct a message structure with the error block injected
            num_pruned = len(content) - len(head) - len(tail) - len(error_block)
            return (
                f"{head}\n\n"
                f"[... ⚠️ 此处已自动压缩中段 {num_pruned} 字符以节省 Token ...]\n\n"
                f"【拦截并抽取的关键报错/堆栈片段】:\n{error_block}\n\n"
                f"{tail}"
            )
        else:
            # Fallback to standard head/tail truncation
            keep_standard = max_chars // 4
            head_std = content[:keep_standard * 2]
            tail_std = content[-keep_standard * 2:]
            num_pruned = len(content) - 4 * keep_standard
            return (
                f"{head_std}\n\n"
                f"[... ⚠️ 此处已自动压缩中段 {num_pruned} 字符以节省 Token，防止上下文溢出 ...]\n\n"
                f"{tail_std}"
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
            state, _failed_attempts, _last_state_change = await self._get_state_from_redis()
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



def get_backup_provider_config(primary_provider: str) -> dict | None:
    """Scans settings or environment variables for fallback cloud credentials."""
    import os

    from app.core.config import settings

    # Define potential backups
    if primary_provider in ("openai", "opencode"):
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            return {
                "provider": "anthropic",
                "api_key": anthropic_key,
                "base_url": "https://api.anthropic.com/v1",
                "model": "claude-3-haiku-20240307"
            }
    elif primary_provider in ("anthropic", "claude_code"):
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_key and settings.llm_provider == "openai" and settings.llm_api_key:
            from app.core.config import deobfuscate_key
            openai_key = deobfuscate_key(settings.llm_api_key)

        if openai_key:
            return {
                "provider": "openai",
                "api_key": openai_key,
                "base_url": settings.llm_base_url or "https://api.openai.com/v1",
                "model": "gpt-4o-mini"
            }
    return None


class ResilienceManager:
    """Handles automatic retries, backoff, and circuit breaking/failover for LLM calls."""

    def __init__(self):
        self.breakers = {}

    def get_breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self.breakers:
            self.breakers[provider] = CircuitBreaker(provider)
        return self.breakers[provider]

    async def execute_failover(self, client_instance, messages: list[dict], system: str,
                               enabled_tools: list[str] | None = None,
                               response_format: dict | None = None) -> AsyncGenerator[str, None]:
        provider = client_instance.provider
        backup_cfg = get_backup_provider_config(provider)

        # Tier 2: Backup Cloud Model (e.g. OpenAI GPT-4o-mini if Claude fails)
        if backup_cfg:
            backup_provider = backup_cfg["provider"]
            backup_breaker = self.get_breaker(backup_provider)
            if await backup_breaker.allow_request():
                failover_notice = f"⚠️ [主模型服务连接已熔断，已自动降级 Failover 路由至备份云服务 {backup_provider} ({backup_cfg['model']})]\n\n"
                yield failover_notice

                backup_success = False
                try:
                    output_chunks = []
                    try:
                        backup_gen = client_instance._stream_fallback_provider(
                            backup_cfg, messages, system, enabled_tools, response_format
                        )
                    except TypeError:
                        backup_gen = client_instance._stream_fallback_provider(
                            backup_cfg, messages, system, enabled_tools
                        )
                    async for chunk in backup_gen:
                        if not chunk.startswith("\n[云端备份提供商"):
                            backup_success = True
                        output_chunks.append(chunk)
                        yield chunk

                    if backup_success:
                        await backup_breaker.record_success()
                    else:
                        await backup_breaker.record_failure()
                except Exception as e:
                    await backup_breaker.record_failure()
                    yield f"\n[云端备份提供商 {backup_provider} 降级执行异常: {type(e).__name__}: {str(e)[:150]}]"

                if backup_success:
                    return

        # Tier 3: Local Ollama Model
        if provider != "ollama" and client_instance.is_ollama_active():
            failover_notice = "⚠️ [主模型与备份云服务均已熔断/未配置，已自动降级至本地 Ollama 运行...]\n\n"
            yield failover_notice

            try:
                ollama_gen = client_instance._openai_stream_fallback_ollama(
                    messages, system, enabled_tools, response_format
                )
            except TypeError:
                ollama_gen = client_instance._openai_stream_fallback_ollama(messages, system)

            async for chunk in ollama_gen:
                yield chunk
        else:
            yield "❌ [所有 LLM 服务（主模型、备份云服务、本地 Ollama）均不可用或已被熔断。请在冷却期过后重试。]"

    async def execute_with_retry(self, client_instance, stream_func, messages: list[dict], system: str,
                                 enabled_tools: list[str] | None = None,
                                 response_format: dict | None = None) -> AsyncGenerator[str, None]:
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
            async for chunk in self.execute_failover(
                client_instance, messages, system, enabled_tools, response_format
            ):
                output_chunks.append(chunk)
                yield chunk

            if span:
                generated_text = "".join(output_chunks)
                span.finish(
                    output_data=generated_text,
                    status="success",
                    metadata={"failover": True, "tokens_approx": len(generated_text) // 3}
                )
            return

        # 2. Execute call with Exponential Backoff
        max_retries = 3
        backoffs = [1.5, 3.0, 6.0]

        for attempt in range(max_retries):
            try:
                try:
                    gen = stream_func(messages, system, enabled_tools, response_format)
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
                if isinstance(e, LLMAPIError) and e.status_code != 429 and e.status_code < 500:
                    retriable = False

                if not retriable:
                    await breaker.record_failure()
                    err_msg = f"\n[LLM 终端错误 (不可重试): {e!s}]"
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

                    async for chunk in self.execute_failover(
                        client_instance, messages, system, enabled_tools, response_format
                    ):
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
        self.thinking_enabled: bool | None = None
        self.thinking_mode: str = "auto"

    def configure(self, provider: str, api_key: str, base_url: str, model: str,
                  temperature: float | None = None, max_tokens: int | None = None,
                  thinking_enabled: bool | None = None,
                  thinking_mode: str | None = None):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        if temperature is not None:
            self.temperature = temperature
        if max_tokens is not None:
            self.max_tokens = max_tokens
        if thinking_mode in ("auto", "enabled", "disabled"):
            self.thinking_mode = thinking_mode
            self.thinking_enabled = {
                "enabled": True,
                "disabled": False,
            }.get(thinking_mode, thinking_enabled)
        elif thinking_enabled is not None:
            self.thinking_enabled = thinking_enabled
            self.thinking_mode = "enabled" if thinking_enabled else "disabled"
        else:
            self.thinking_enabled = None
            self.thinking_mode = "auto"

    def is_configured(self) -> bool:
        if self.provider == "opencode":
            return True
        if self.provider == "claude_code":
            return bool(self.api_key)
        if self.provider == "ollama":
            return bool(self.model)
        return bool(self.api_key and self.base_url and self.model)

    def is_ollama_active(self) -> bool:
        """Check if local Ollama service is running."""
        import socket
        try:
            with socket.create_connection(("127.0.0.1", 11434), timeout=0.5):
                return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False

    async def _openai_stream_fallback_ollama(self, messages: list[dict], system: str,
                                             enabled_tools: list[str] | None = None,
                                             response_format: dict | None = None) -> AsyncGenerator[str, None]:
        original_provider = self.provider
        original_base_url = self.base_url
        original_model = self.model
        original_api_key = self.api_key

        self.provider = "ollama"
        self.base_url = "http://127.0.0.1:11434/v1"
        self.model = "qwen2.5-coder:7b"
        self.api_key = "ollama"

        try:
            async for chunk in self._openai_stream(
                messages, system, enabled_tools, response_format
            ):
                yield chunk
        except Exception as e:
            yield f"\n[Ollama 本地降级重定向调用失败: {type(e).__name__}: {str(e)[:150]}]"
        finally:
            self.provider = original_provider
            self.base_url = original_base_url
            self.model = original_model
            self.api_key = original_api_key

    async def _stream_fallback_provider(self, backup_config: dict, messages: list[dict], system: str,
                                        enabled_tools: list[str] | None = None,
                                        response_format: dict | None = None) -> AsyncGenerator[str, None]:
        original_provider = self.provider
        original_base_url = self.base_url
        original_model = self.model
        original_api_key = self.api_key
        original_temp = self.temperature
        original_tokens = self.max_tokens

        self.provider = backup_config["provider"]
        self.base_url = backup_config["base_url"]
        self.model = backup_config["model"]
        self.api_key = backup_config["api_key"]

        try:
            # Dynamically route stream based on fallback provider
            if self.provider == "anthropic":
                async for chunk in self._anthropic_stream(
                    messages, system, enabled_tools, response_format
                ):
                    yield chunk
            else:
                async for chunk in self._openai_stream(
                    messages, system, enabled_tools, response_format
                ):
                    yield chunk
        except Exception as e:
            yield f"\n[云端备份提供商 {self.provider} 降级调用失败: {type(e).__name__}: {str(e)[:150]}]"
        finally:
            self.provider = original_provider
            self.base_url = original_base_url
            self.model = original_model
            self.api_key = original_api_key
            self.temperature = original_temp
            self.max_tokens = original_tokens

    async def chat_stream(self, messages: list[dict], system: str = "",
                          enabled_tools: list[str] | None = None,
                          response_format: dict | None = None) -> AsyncGenerator[str, None]:
        optimized_messages = ContextOptimizer.optimize_messages(messages)

        try:
            if self.provider == "opencode":
                async for chunk in resilience_manager.execute_with_retry(
                    self, self._opencode_stream, optimized_messages, system,
                    enabled_tools, response_format
                ):
                    yield chunk
            elif self.provider == "claude_code":
                async for chunk in resilience_manager.execute_with_retry(
                    self, self._claude_code_stream, optimized_messages, system,
                    enabled_tools, response_format
                ):
                    yield chunk
            elif self.provider == "anthropic":
                async for chunk in resilience_manager.execute_with_retry(
                    self, self._anthropic_stream, optimized_messages, system,
                    enabled_tools, response_format
                ):
                    yield chunk
            elif self.provider == "ollama":
                if not self.base_url:
                    self.base_url = "http://127.0.0.1:11434/v1"
                async for chunk in resilience_manager.execute_with_retry(
                    self, self._openai_stream, optimized_messages, system,
                    enabled_tools, response_format
                ):
                    yield chunk
            else:
                async for chunk in resilience_manager.execute_with_retry(
                    self, self._openai_stream, optimized_messages, system,
                    enabled_tools, response_format
                ):
                    yield chunk
        except Exception as e:
            yield f"\n[LLM 调用出错: {type(e).__name__}: {str(e)[:200]}]"

    def _get_api_tools(self, enabled_tools: list[str] | None = None) -> list[dict]:
        """Convert AgentTools dynamically into standard API tools definition format."""
        try:
            from app.tools.registry import get_tool, is_tool_enabled, list_tools
            api_tools = []
            for item in list_tools():
                name = item["name"]
                tool = get_tool(name)
                if tool is None or not is_tool_enabled(name, tool):
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

    async def _openai_stream(self, messages: list[dict], system: str,
                             enabled_tools: list[str] | None = None,
                             response_format: dict | None = None) -> AsyncGenerator[str, None]:
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
        if response_format:
            payload["response_format"] = response_format

        # DeepSeek V4 exposes thinking as an OpenAI-compatible request option.
        # Keep it provider-specific so other OpenAI-compatible APIs are unchanged.
        if self.thinking_mode in ("enabled", "disabled"):
            payload["thinking"] = {"type": self.thinking_mode}
        elif "deepseek" in self.model.lower() or "api.deepseek.com" in self.base_url.lower():
            thinking_enabled = self.thinking_enabled
            if thinking_enabled is None and "deepseek-v4-flash" in self.model.lower():
                thinking_enabled = False
            if thinking_enabled is not None:
                payload["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}

        # 🚀 Phase 3: Seamless standard Native Tool Calling conversion
        api_tools = self._get_api_tools(enabled_tools)
        if api_tools and self.provider != "ollama": # Local Ollama bypasses standard tools in simple modes
            payload["tools"] = api_tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }

        active_tool_calls: dict[int, dict[str, Any]] = {}

        try:
            async with httpx.AsyncClient(timeout=180.0) as client, client.stream("POST", url, json=payload, headers=headers) as resp:
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
            for _index, _call_info in active_tool_calls.items():
                yield '[/tool_call]'
            active_tool_calls.clear()

    async def _anthropic_stream(self, messages: list[dict], system: str,
                                enabled_tools: list[str] | None = None,
                                response_format: dict | None = None) -> AsyncGenerator[str, None]:
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

        active_tool_calls: dict[int, dict[str, Any]] = {}

        try:
            async with httpx.AsyncClient(timeout=180.0) as client, client.stream("POST", url, json=payload, headers=headers) as resp:
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
            for _index, _call_info in active_tool_calls.items():
                yield '[/tool_call]'
            active_tool_calls.clear()

    async def _claude_code_stream(self, messages: list[dict], system: str,
                                  enabled_tools: list[str] | None = None,
                                  response_format: dict | None = None) -> AsyncGenerator[str, None]:
        from app.core.claude_code_client import claude_code_stream
        async for chunk in claude_code_stream(
            messages=messages,
            system=system,
            api_key=self.api_key,
            model=self.model,
        ):
            yield chunk

    async def _opencode_stream(self, messages: list[dict], system: str,
                               enabled_tools: list[str] | None = None,
                               response_format: dict | None = None) -> AsyncGenerator[str, None]:
        from app.core.opencode_client import opencode_stream
        async for chunk in opencode_stream(
            messages=messages,
            system=system,
        ):
            yield chunk


class TenantAwareLLMClient:
    """Dispatch LLM operations to an isolated client for the active tenant."""

    def __init__(self):
        self._default = LLMClient()
        self._clients: dict[str, LLMClient] = {}

    def _client(self) -> LLMClient:
        from app.core.tenancy import current_tenant_id

        tenant_id = current_tenant_id()
        if not tenant_id:
            return self._default
        existing = self._clients.get(tenant_id)
        if existing is not None:
            return existing

        from app.core.config import deobfuscate_key, settings
        from app.core.tenant_config import get_tenant_json

        config = get_tenant_json(tenant_id, "llm", {}, encrypted=True) or {}
        client = LLMClient()
        inherited = self._default
        client.configure(
            provider=config.get("provider") or inherited.provider or settings.llm_provider,
            api_key=deobfuscate_key(config.get("api_key", "")) or inherited.api_key or settings.llm_api_key,
            base_url=config.get("base_url") or inherited.base_url or settings.llm_base_url,
            model=config.get("model") or inherited.model or settings.llm_model,
            temperature=config.get("temperature", inherited.temperature),
            max_tokens=config.get("max_tokens", inherited.max_tokens),
            thinking_enabled=config.get("thinking_enabled", inherited.thinking_enabled),
            thinking_mode=config.get("thinking_mode", inherited.thinking_mode),
        )
        self._clients[tenant_id] = client
        return client

    def __getattr__(self, name):
        return getattr(self._client(), name)

    def evict(self, tenant_id: str) -> None:
        self._clients.pop(tenant_id, None)


llm_client = TenantAwareLLMClient()


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
