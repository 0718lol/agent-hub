"""Agent orchestration — WebSocket message handling, group chat graph,
streaming agent replies, and checkpoint recovery.

Extracted from main.py to keep the app factory focused on HTTP routes
and middleware while this module owns the real-time agent coordination logic.
"""
import asyncio
import json
import logging
import re
import uuid
from typing import Any

from app.core.database import (
    async_get_messages_cached,
    async_save_message_cached,
    get_messages,
    get_pending_hil_checkpoint,
    resolve_hil_checkpoint,
    save_artifact,
    save_message,
    update_latest_artifact_quality,
)
from app.core.llm_client import llm_client
from app.core.metrics import metrics
from app.core.output_validator import get_retry_prompt, validate_output
from app.core.quality_gate import quality_gate
from app.core.quality_retry import evaluate_and_retry
from app.core.websocket import manager
from app.services.agent_registry import agent_registry

logger = logging.getLogger("agent_orchestrator")

# Shared state: stop events per conversation
_stop_events: dict[str, asyncio.Event] = {}

def parse_create_agent_tag(buffer: str) -> tuple[dict | None, str]:
    """Parse a [create_agent:{json}] tag from the buffer.

    Returns:
        (agent_config, remaining_buffer) if a valid tag is found and JSON parses.
        (None, original_buffer) if no complete valid tag is found.

    Handles:
        - Normal JSON payloads
        - JSON with ``}`` characters inside string values
        - JSON with escaped quotes ``\"``
        - Incomplete tags (returns None, original buffer)
        - Nested JSON objects
        - Empty JSON ``{}``
    """
    # 1. Try regex first (simple cases)
    ca_match = re.search(r'\[create_agent:(.*?)\]', buffer, re.DOTALL)
    if ca_match:
        try:
            agent_config = json.loads(ca_match.group(1))
            remaining = buffer[:ca_match.start()] + buffer[ca_match.end():]
            return agent_config, remaining
        except (json.JSONDecodeError, Exception):
            pass

    # 2. String-aware bracket-counting parser (handles nested JSON)
    tag_start = buffer.find('[create_agent:')
    if tag_start == -1:
        return None, buffer
    json_start = tag_start + len('[create_agent:')
    bracket_depth = 0
    json_end = -1
    in_string = False
    escape_next = False
    for idx in range(json_start, len(buffer)):
        ch = buffer[idx]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            if in_string:
                escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            bracket_depth += 1
        elif ch == '}':
            bracket_depth -= 1
            if bracket_depth == 0:
                json_end = idx + 1
                break
    if json_end != -1 and json_end < len(buffer) and buffer[json_end] == ']':
        try:
            agent_config = json.loads(buffer[json_start:json_end])
            remaining = buffer[:tag_start] + buffer[json_end + 1:]
            return agent_config, remaining
        except (json.JSONDecodeError, Exception):
            pass

    return None, buffer


def get_agents() -> dict:
    """Return the current agent registry dict (direct reference, not a copy)."""
    return agent_registry._agents
# ============================================================
# Custom Agent helpers
# ============================================================

async def _remove_custom_agent(agent_id: str):
    """Delete a custom agent via the concurrency-safe agent registry."""
    await agent_registry.unregister_custom_agent(agent_id)


# ============================================================
# Output validation — format checks, anti-pattern detection
# ============================================================

# Question patterns that break the demo flow
QUESTION_PATTERNS = [
    (r'[^。\n]*[？?]\s*$', "ends with question"),
    (r'你想[^，。\n]*[？?]', "direct question to user"),
    (r'请问[^，。\n]*[？?]', "polite question to user"),
    (r'需要[^，。\n]*确认[^，。\n]*[？?]', "confirmation request"),
    (r'你希望[^，。\n]*[？?]', "preference question"),
    (r'是否需要[^，。\n]*[？?]', "yes/no question"),
    (r'能告诉我[^，。\n]*[？?]', "information request"),
    (r'有什么[^，。\n]*需求[^，。\n]*[？?]', "requirement question"),
]

# Expected format rules per agent type
FORMAT_RULES = {
    "agent_frontend": {
        "required_any": ["```html", "```jsx", "```vue", "```css", "<!DOCTYPE", "<html"],
        "min_length": 100,
    },
    "agent_backend": {
        "required_any": ["```python", "```sql", "```yaml", "```json", "```bash",
                         "```dockerfile", "def ", "import ", "class ", "CREATE TABLE"],
        "min_length": 80,
    },
    "agent_tester": {
        "required_any": ["```python", "def test_", "import pytest", "assert "],
        "min_length": 50,
    },
    "agent_devops": {
        "required_any": ["```bash", "```dockerfile", "```yaml", "docker", "Dockerfile"],
        "min_length": 30,
    },
    "agent_pm": {
        "required_any": ["[assign:"],
        "min_length": 20,
    },
    "agent_builder": {
        "required_any": ["{"],
        "min_length": 20,
    },
}

# Valid agent IDs for [assign:] tags
VALID_AGENT_IDS = {
    "agent_frontend", "agent_backend", "agent_tester",
    "agent_devops", "agent_designer", "agent_builder",
}

# Format instructions for retry prompts
FORMAT_INSTRUCTIONS = {
    "agent_frontend": (
        "你必须输出完整可运行的代码。根据任务选择合适格式：\n"
        "- 页面/游戏 → ```html 代码块，以 <!DOCTYPE html> 开头\n"
        "- React 组件 → ```jsx 代码块\n"
        "- 样式 → ```css 代码块\n"
        "不要问用户任何问题，直接实现。"
    ),
    "agent_backend": (
        "你必须输出完整可运行的代码。根据任务选择合适格式：\n"
        "- API/接口 → ```python 代码块（FastAPI）\n"
        "- 数据库 → ```sql 代码块\n"
        "- 配置 → ```yaml 代码块\n"
        "不要问用户任何问题，直接实现。"
    ),
    "agent_pm": (
        "你必须输出任务分配标签。\n"
        "在回复末尾添加 [assign:agent_frontend] [assign:agent_backend] 等标签。\n"
        "不要问用户任何问题，直接拆解任务。"
    ),
    "agent_tester": (
        "你必须输出测试代码。\n"
        "用 ```python 代码块包裹，包含 def test_ 开头的测试函数。"
    ),
    "agent_devops": (
        "你必须输出部署配置。\n"
        "用 ```bash 或 ```yaml 或 ```dockerfile 代码块包裹。"
    ),
}


def detect_questions(text: str) -> str | None:
    """Detect question patterns that would break the demo flow."""
    # Exclude [ask_user:...] tags
    clean = re.sub(r'\[ask_user:.*?\]', '', text, flags=re.DOTALL)
    # Exclude code blocks
    clean = re.sub(r'```.*?```', '', clean, flags=re.DOTALL)
    # Exclude quoted text
    clean = re.sub(r'"[^"]*[？?]"', '', clean)
    clean = re.sub(r"'[^']*[？?]'", '', clean)
    for pattern, reason in QUESTION_PATTERNS:
        if re.search(pattern, clean):
            return reason
    return None


def check_format_compliance(text: str, agent_id: str) -> tuple[bool, str]:
    """Check if output matches expected format for the agent type."""
    rules = FORMAT_RULES.get(agent_id)
    if not rules:
        return True, "no rules"
    if len(text.strip()) < rules["min_length"]:
        return False, f"output too short ({len(text.strip())} < {rules['min_length']})"
    if not any(r in text for r in rules["required_any"]):
        return False, f"missing expected content for {agent_id}"
    return True, "passed"


def check_tag_format(text: str, agent_id: str) -> tuple[bool, str]:
    """Check tag format correctness."""
    if agent_id == "agent_pm":
        tags = re.findall(r'\[assign:(\w+)\]', text)
        if not tags:
            return False, "PM must output [assign:agent_xxx] tags"
        for tag in tags:
            if tag not in VALID_AGENT_IDS:
                return False, f"invalid agent_id in [assign:{tag}]"
    return True, "passed"


def validate_agent_output(text: str, agent_id: str) -> tuple[bool, str]:
    """Full output validation. Returns (passed, reason)."""
    # Skip validation for error responses
    error_indicators = ["[LLM Error", "[LLM 调用出错", "[Agent 回复出错", "出错", "Error"]
    if any(indicator in text for indicator in error_indicators):
        return True, "error response skipped"
    # 1. Anti-pattern detection (questions)
    q = detect_questions(text)
    if q:
        return False, f"anti-pattern: {q}"
    # 2. Format compliance
    ok, reason = check_format_compliance(text, agent_id)
    if not ok:
        return False, f"format: {reason}"
    # 3. Tag format
    ok, reason = check_tag_format(text, agent_id)
    if not ok:
        return False, f"tag: {reason}"
    return True, "passed"


# ============================================================
# Error detection for browser auto-routing
# ============================================================

# Error patterns that can be fixed by looking up documentation
ERROR_PATTERNS = [
    (r'ModuleNotFoundError.*No module named .(\w+).', 'import_error'),
    (r'ImportError.*cannot import name .(\w+).', 'import_error'),
    (r'AttributeError.*has no attribute .(\w+).', 'attribute_error'),
    (r'TypeError.*unexpected keyword argument .(\w+).', 'type_error'),
    (r'TypeError.*takes (\d+) positional arguments', 'type_error'),
    (r'NameError.*name .(\w+). is not defined', 'name_error'),
    (r'HTTP (\d{3}).*Not Found', 'api_error'),
    (r'HTTP 422.*Validation', 'api_error'),
]


def detect_fixable_errors(text: str) -> list[dict]:
    """Detect errors in Agent output that could be fixed by looking up documentation."""
    errors = []
    for pattern, error_type in ERROR_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            errors.append({
                'type': error_type,
                'match': match.group(0),
                'groups': match.groups(),
            })
    return errors


def should_use_browser(text: str, agent_id: str) -> tuple[bool, str]:
    """Determine if Agent output suggests browser should be used."""
    # Don't trigger for BrowserAgent itself
    if agent_id == 'agent_browser':
        return False, 'is browser agent'
    
    errors = detect_fixable_errors(text)
    if not errors:
        return False, 'no fixable errors'
    
    # Priority: import > attribute > type > api > name
    priority = ['import_error', 'attribute_error', 'type_error', 'api_error', 'name_error']
    for error_type in priority:
        for error in errors:
            if error['type'] == error_type:
                return True, f"{error_type}: {error['match']}"
    
    return False, 'no fixable errors'


# ============================================================
# Core streaming reply
# ============================================================

async def stream_agent_reply(
    conversation_id: str, agent, user_text: str,
    stop_event: asyncio.Event | None = None, context: str = "",
) -> tuple[list[str], str]:
    """Stream agent reply. Returns (assigned_agent_ids, response_text)."""
    full_text = ""
    raw_text = ""
    buffer = ""
    last_thinking_broadcast = ""
    last_stream_broadcast = 0.0
    assigned_agents = []

    effective_text = user_text
    if context:
        effective_text = f"PM 的任务拆解：\n{context}\n\n用户原始需求：{user_text}"

    history = await async_get_messages_cached(conversation_id, limit=20)

    await manager.broadcast(conversation_id, {
        "type": "typing",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "is_typing": True,
    })
    await manager.broadcast(conversation_id, {
        "type": "task_status",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "status": "doing",
    })

    try:
        # ---- Best-of-N: parallel multi-candidate generation ----
        # 外部 Agent（AdapterAgent）走标准流式路径，不走 Best-of-N
        _is_external = hasattr(agent, 'adapter')
        if quality_gate.enabled and quality_gate.best_of_n > 1 and agent.agent_id not in ("agent_builder", "agent_pm") and not _is_external:
            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": agent.agent_id,
                "content": {"text": f"⚡ 正在并行生成 {quality_gate.best_of_n} 个候选方案，择优输出..."},
                "stream": True,
            })

            async def _on_progress(idx, status):
                await manager.broadcast(conversation_id, {
                    "type": "message",
                    "conversation_id": conversation_id,
                    "sender": agent.agent_id,
                    "content": {"text": f"🏆 {status}"},
                    "stream": True,
                })

            best_output, _best_report, candidates_summary = await quality_gate.best_of_n_generate(
                agent, effective_text,
                agent_id=agent.agent_id,
                history=history,
                on_progress=_on_progress,
            )

            raw_text = best_output
            buffer = best_output
            full_text = best_output.strip()

            await manager.broadcast(conversation_id, {
                "type": "candidates_report",
                "conversation_id": conversation_id,
                "agent_id": agent.agent_id,
                "candidates": candidates_summary,
            })

        # ---- Standard streaming mode ----
        _use_stream = _is_external or not (quality_gate.enabled and quality_gate.best_of_n > 1
                           and agent.agent_id not in ("agent_builder", "agent_pm"))
        if _use_stream:
            async for chunk in agent.stream_reply(effective_text, history=history, conversation_id=conversation_id):
                if stop_event and stop_event.is_set():
                    break

                raw_text += chunk
                buffer += chunk

                # Extract and broadcast thinking blocks
                while True:
                    think_match = re.search(r'\[thinking\](.*?)\[/thinking\]', buffer, re.DOTALL)
                    if not think_match:
                        break
                    think_text = think_match.group(1).strip()
                    if think_text and think_text != last_thinking_broadcast:
                        last_thinking_broadcast = think_text
                        await manager.broadcast(conversation_id, {
                            "type": "thinking",
                            "conversation_id": conversation_id,
                            "agent_id": agent.agent_id,
                            "text": think_text,
                        })
                    buffer = buffer[:think_match.start()] + buffer[think_match.end():]

                # Extract assign tags
                while True:
                    assign_match = re.search(r'\[assign:(\w+)\]', buffer)
                    if not assign_match:
                        break
                    agent_id = assign_match.group(1)
                    if agent_id not in assigned_agents:
                        assigned_agents.append(agent_id)
                    buffer = buffer[:assign_match.start()] + buffer[assign_match.end():]

                # Extract [create_agent:{json}] tags
                while True:
                    ca_match = re.search(r'\[create_agent:(.*?)\]', buffer, re.DOTALL)
                    parsed_ok = False
                    if ca_match:
                        try:
                            agent_config = json.loads(ca_match.group(1))
                            await agent_registry.register_custom_agent(agent_config)
                            await manager.broadcast(conversation_id, {
                                "type": "agent_created",
                                "conversation_id": conversation_id,
                                "agent": agent_config,
                            })
                            parsed_ok = True
                            buffer = buffer[:ca_match.start()] + buffer[ca_match.end():]
                        except (json.JSONDecodeError, Exception):
                            pass

                    if not parsed_ok:
                        # Fallback: string-aware bracket-counting parser to handle nested JSON
                        tag_start = buffer.find('[create_agent:')
                        if tag_start == -1:
                            break
                        json_start = tag_start + len('[create_agent:')
                        bracket_depth = 0
                        json_end = -1
                        in_string = False
                        escape_next = False
                        for idx in range(json_start, len(buffer)):
                            ch = buffer[idx]
                            if escape_next:
                                escape_next = False
                                continue
                            if ch == '\\':
                                if in_string:
                                    escape_next = True
                                continue
                            if ch == '"':
                                in_string = not in_string
                                continue
                            if in_string:
                                continue
                            if ch == '{':
                                bracket_depth += 1
                            elif ch == '}':
                                bracket_depth -= 1
                                if bracket_depth == 0:
                                    json_end = idx + 1
                                    break
                        if json_end != -1 and json_end < len(buffer) and buffer[json_end] == ']':
                            try:
                                agent_config = json.loads(buffer[json_start:json_end])
                                await agent_registry.register_custom_agent(agent_config)
                                await manager.broadcast(conversation_id, {
                                    "type": "agent_created",
                                    "conversation_id": conversation_id,
                                    "agent": agent_config,
                                })
                            except (json.JSONDecodeError, Exception):
                                pass
                            buffer = buffer[:tag_start] + buffer[json_end + 1:]
                        else:
                            break

                # Extract [delete_agent:agent_id] tags
                while True:
                    da_match = re.search(r'\[delete_agent:(agent_custom_\w+)\]', buffer)
                    if not da_match:
                        break
                    del_id = da_match.group(1)
                    await _remove_custom_agent(del_id)
                    await manager.broadcast(conversation_id, {
                        "type": "agent_deleted",
                        "conversation_id": conversation_id,
                        "agent_id": del_id,
                    })
                    buffer = buffer[:da_match.start()] + buffer[da_match.end():]

                # Extract and broadcast code blocks
                while True:
                    code_match = re.search(r'```(\w*)\s*\n?(.*?)```', buffer, re.DOTALL)
                    if not code_match:
                        break
                    lang = code_match.group(1) or "html"
                    code = code_match.group(2).strip()

                    await asyncio.to_thread(save_artifact, conversation_id, agent.agent_id, lang, code)

                    await manager.broadcast(conversation_id, {
                        "type": "code",
                        "conversation_id": conversation_id,
                        "agent_id": agent.agent_id,
                        "language": lang,
                        "code": code,
                    })
                    if lang.lower() in ("html", "htm", ""):
                        await manager.broadcast(conversation_id, {
                            "type": "preview",
                            "conversation_id": conversation_id,
                            "agent_id": agent.agent_id,
                            "html": code,
                        })
                    buffer = buffer[:code_match.start()] + buffer[code_match.end():]

                # Throttled streaming broadcast
                now = asyncio.get_running_loop().time()
                summary = buffer.strip()
                if summary and (now - last_stream_broadcast) >= 0.08:
                    last_stream_broadcast = now
                    await manager.broadcast(conversation_id, {
                        "type": "message",
                        "conversation_id": conversation_id,
                        "sender": agent.agent_id,
                        "content": {"text": summary},
                        "stream": True,
                    })

        # Final text
        full_text = buffer.strip()

        # Bare HTML fallback
        if full_text and "```" not in raw_text and re.search(
            r'<!DOCTYPE\s+html|<html[\s>]|<body[\s>]', full_text, re.IGNORECASE
        ):
            html_match = re.search(
                r'(<!DOCTYPE[\s\S]*?</html>|<html[\s\S]*?</html>|<body[\s\S]*?</body>)',
                full_text, re.IGNORECASE
            )
            if html_match:
                bare_html = html_match.group(1).strip()
                await manager.broadcast(conversation_id, {
                    "type": "code",
                    "conversation_id": conversation_id,
                    "agent_id": agent.agent_id,
                    "language": "html",
                    "code": bare_html,
                })
                await manager.broadcast(conversation_id, {
                    "type": "preview",
                    "conversation_id": conversation_id,
                    "agent_id": agent.agent_id,
                    "html": bare_html,
                })
                full_text = full_text.replace(bare_html, "").strip()
                if not full_text:
                    full_text = "（已生成代码，请查看右侧面板）"

    except Exception as e:
        err_msg = f"[Agent 回复出错: {type(e).__name__}: {str(e)[:200]}]"
        if not full_text:
            full_text = err_msg
        else:
            full_text += f"\n[出错: {str(e)[:100]}]"
        raw_text += f"\n{err_msg}"

    stopped = stop_event and stop_event.is_set()

    if not full_text:
        full_text = "（已停止生成）" if stopped else "（已生成代码，请查看右侧面板）"

    if not raw_text:
        raw_text = full_text

    # ---- Format validation layer (skip for external agents) ----
    if not stopped and not _is_external and full_text and full_text not in ("（已停止生成）", "（已生成代码，请查看右侧面板）"):
        is_valid, reason = validate_agent_output(full_text, agent.agent_id)
        if not is_valid:
            logger.warning(f"Agent {agent.agent_id} format check failed: {reason}")
            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": agent.agent_id,
                "content": {"text": f"⚠️ 输出格式不符合要求（{reason}），正在重新生成..."},
                "stream": True,
            })
            retry_prompt = (
                f"你的上一次输出不符合要求：{reason}。"
                f"请严格按照以下格式重新生成：\n"
                f"{FORMAT_INSTRUCTIONS.get(agent.agent_id, '')}"
                f"\n\n用户原始需求：{effective_text}"
            )
            retry_text = ""
            async for chunk in agent.stream_reply(retry_prompt, history=history, conversation_id=conversation_id):
                if stop_event and stop_event.is_set():
                    break
                retry_text += chunk
            if retry_text.strip():
                full_text = retry_text.strip()
                raw_text = retry_text
                # Re-validate once (no infinite loop)
                is_valid2, reason2 = validate_agent_output(full_text, agent.agent_id)
                if not is_valid2:
                    logger.warning(f"Agent {agent.agent_id} retry still invalid: {reason2}")
                    await manager.broadcast(conversation_id, {
                        "type": "message",
                        "conversation_id": conversation_id,
                        "sender": agent.agent_id,
                        "content": {"text": f"⚠️ 重试后仍不符合要求（{reason2}），已保留当前输出。"},
                        "stream": True,
                    })

    # ---- Browser auto-routing: if Agent output has fixable errors, use BrowserAgent ----
    if not stopped and not _is_external and full_text and agent.agent_id != 'agent_browser':
        should_browser, browser_reason = should_use_browser(full_text, agent.agent_id)
        if should_browser:
            logger.info(f'Agent {agent.agent_id} output has fixable error: {browser_reason}')
            await manager.broadcast(conversation_id, {
                'type': 'message',
                'conversation_id': conversation_id,
                'sender': agent.agent_id,
                'content': {'text': '⚠️ 检测到可修复错误（' + browser_reason + '），正在查文档...'},
                'stream': True,
            })
            # Get BrowserAgent
            browser_agent = get_agents().get('agent_browser')
            if browser_agent:
                # BrowserAgent looks up documentation
                doc_task = '查阅文档解决以下错误: ' + browser_reason + '. 用户需求: ' + effective_text
                doc_result = ''
                try:
                    async for chunk in browser_agent.stream_reply(doc_task, history=history, conversation_id=conversation_id):
                        doc_result += chunk
                except Exception as e:
                    logger.warning(f'BrowserAgent failed: {e}')

                if doc_result.strip():
                    # Retry original agent with documentation context
                    doc_summary = doc_result[:3000]
                    nl = chr(10)
                    prefix = chr(26681) + chr(25454) + chr(25991) + chr(26723) + ": "
                    suffix = nl + nl + chr(35831) + chr(20462) + chr(27491) + chr(20197) + chr(19979) + chr(20195) + chr(30721) + chr(20013) + chr(30340) + chr(38169) + chr(35823) + chr(12290) + chr(29992) + chr(25143) + chr(38656) + chr(27714) + ": "
                    retry_prompt = prefix + doc_summary + suffix + effective_text
                    retry_text = ''
                    async for chunk in agent.stream_reply(retry_prompt, history=history, conversation_id=conversation_id):
                        if stop_event and stop_event.is_set():
                            break
                        retry_text += chunk
                    if retry_text.strip():
                        full_text = retry_text.strip()
                        raw_text = retry_text

    # ---- Auto self-reflection & retry (skip for external agents) ----
    if not stopped and agent.agent_id not in ("agent_builder", "agent_pm") and not _is_external:
        eval_result = await evaluate_and_retry(
            conversation_id=conversation_id,
            agent=agent,
            task=effective_text,
            raw_output=raw_text,
            llm_client=llm_client,
            manager=manager,
            stop_event=stop_event,
            history=history,
        )
        if eval_result["final_output"]:
            raw_text = eval_result["final_output"]
            full_text = eval_result["final_output"].strip()

        try:
            report_data = eval_result.get("report") or {}
            sandbox_data = report_data.get("sandbox_run") or {}
            sandbox_status = "skipped"
            sandbox_output = None
            if sandbox_data:
                sandbox_status = "success" if sandbox_data.get("status") == "success" else "failed"
                sandbox_output = sandbox_data.get("stderr") or sandbox_data.get("stdout")

            await asyncio.to_thread(
                update_latest_artifact_quality,
                conversation_id,
                agent.agent_id,
                eval_result.get("total_score", 100),
                sandbox_status,
                sandbox_output,
            )
        except Exception as e_art:
            logger.error(f"Error updating artifact quality metrics: {e_art}")

    # Don't persist LLM error responses
    is_llm_error = ("[LLM Error" in raw_text) or ("[LLM 调用出错" in raw_text) or ("[Agent 回复出错" in raw_text)
    if not is_llm_error:
        await async_save_message_cached(conversation_id, agent.agent_id, {"text": raw_text}, streaming=False)

    # Broadcast thinking/typing stop + task done
    await manager.broadcast(conversation_id, {
        "type": "thinking",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "text": "",
    })
    await manager.broadcast(conversation_id, {
        "type": "typing",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "is_typing": False,
    })
    await manager.broadcast(conversation_id, {
        "type": "task_status",
        "conversation_id": conversation_id,
        "agent_id": agent.agent_id,
        "status": "done",
    })
    await manager.broadcast(conversation_id, {
        "type": "message",
        "conversation_id": conversation_id,
        "sender": agent.agent_id,
        "content": {"text": full_text},
        "stream": False,
    })

    return assigned_agents, full_text


# ============================================================
# Targeted agent flow
# ============================================================

async def run_target_agent_flow(conversation_id: str, agent, text: str):
    """Background generation flow when user targets a specific agent."""
    logger.info(f"run_target_agent_flow: conv={conversation_id}, agent={agent.agent_id}")
    AGENTS = get_agents()
    stop_event = asyncio.Event()
    _stop_events[conversation_id] = stop_event
    try:
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": True,
        })
        assigned_agent_ids, pm_response = await stream_agent_reply(
            conversation_id, agent, text, stop_event
        )

        if assigned_agent_ids and not stop_event.is_set():
            agents_to_run = [
                AGENTS[aid] for aid in assigned_agent_ids
                if aid in AGENTS and aid != agent.agent_id
            ]
            if agents_to_run:
                await asyncio.gather(*[
                    stream_agent_reply(conversation_id, a, text, stop_event, context=pm_response)
                    for a in agents_to_run
                ], return_exceptions=True)
    finally:
        _stop_events.pop(conversation_id, None)
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })


# ============================================================
# Group chat graph builder
# ============================================================

def build_group_chat_graph(conversation_id: str, text: str, trace: Any, stop_event: asyncio.Event) -> Any:
    """Build a StateGraph for multi-agent group chat orchestration."""
    from app.core.state_graph import StateGraph
    AGENTS = get_agents()

    graph = StateGraph()

    # --- Helper to create agent node runners ---
    def _make_node(agent_key: str, response_key: str, feedback_key: str):
        async def run_node(state: dict) -> dict:
            agent = AGENTS[agent_key]
            step = trace.add_step(agent.agent_id, agent.name)

            feedback = state.get(feedback_key, "")
            effective_prompt = text
            if feedback:
                effective_prompt = f"{text}\n\n🔄 人工审核反馈意见，请针对以下意见修改刚才的代码/结果：\n{feedback}"

            _, res = await stream_agent_reply(
                conversation_id, agent, effective_prompt, stop_event,
                context=state.get("pm_response", ""),
            )
            step.finish(status="success", tokens=len(res) // 3)
            metrics.record_agent_result(agent.agent_id, 75, step.duration_ms, step.tokens_used)
            return {response_key: res, feedback_key: ""}
        return run_node

    # PM node is special — it returns assigned_agents
    async def run_pm(state: dict) -> dict:
        pm = AGENTS["agent_pm"]
        step = trace.add_step(pm.agent_id, pm.name)

        feedback = state.get("agent_pm_feedback", "")
        effective_prompt = text
        if feedback:
            effective_prompt = f"{text}\n\n🔄 人工审核反馈意见，请针对以下意见修改刚才的代码/结果：\n{feedback}"

        assigned, pm_res = await stream_agent_reply(
            conversation_id, pm, effective_prompt, stop_event
        )
        step.finish(status="success", tokens=len(pm_res) // 3)
        metrics.record_agent_result(pm.agent_id, 80, step.duration_ms, step.tokens_used)
        return {
            "pm_response": pm_res,
            "assigned_agents": assigned,
            "agent_pm_feedback": "",
        }

    # Add nodes
    graph.add_node("agent_pm", run_pm)
    graph.add_node("agent_designer", _make_node("agent_designer", "designer_response", "agent_designer_feedback"))
    graph.add_node("agent_frontend", _make_node("agent_frontend", "frontend_response", "agent_frontend_feedback"))
    graph.add_node("agent_backend", _make_node("agent_backend", "backend_response", "agent_backend_feedback"))
    graph.add_node("agent_tester", _make_node("agent_tester", "tester_response", "agent_tester_feedback"))
    graph.add_node("agent_devops", _make_node("agent_devops", "devops_response", "agent_devops_feedback"))

    # --- Speaker selection ---
    SPEAKER_SELECTION_SYSTEM_PROMPT = """你是一个智能体群聊协调器 (Group Chat Coordinator)。
根据当前的对话历史和各个候选智能体 (Agents) 的角色描述，判断下一个最适合发言的智能体是谁。

候选智能体列表：
{candidates_info}

规则：
1. 只能从上面的候选智能体列表中选择一个，或者回复 END 表示流程结束。
2. 考虑当前对话上下文，选择最需要发言的智能体。
3. 如果所有任务都已完成，回复 END。

请只回复智能体 ID（如 agent_frontend）或 END，不要回复其他内容。"""

    async def select_next_speaker(state: dict) -> str:
        sg_logger = logging.getLogger("state_graph")

        assigned = state.get("assigned_agents", [])
        candidates = assigned if assigned else ["agent_designer", "agent_frontend", "agent_backend", "agent_tester", "agent_devops"]

        remaining_candidates = [c for c in candidates if c not in state.get("completed_nodes", [])]

        if not remaining_candidates:
            return "END"

        # Heuristic routing
        rule_speaker = None

        if len(remaining_candidates) == 1:
            rule_speaker = remaining_candidates[0]
            sg_logger.info(f"[Speaker Selection] Heuristic rule A: only one candidate. Selected '{rule_speaker}'")
        else:
            completed = state.get("completed_nodes", [])
            last_completed = completed[-1] if completed else None

            if last_completed == "agent_pm":
                if "agent_designer" in remaining_candidates:
                    rule_speaker = "agent_designer"
                elif "agent_frontend" in remaining_candidates:
                    rule_speaker = "agent_frontend"
                elif "agent_backend" in remaining_candidates:
                    rule_speaker = "agent_backend"
            elif last_completed == "agent_designer":
                if "agent_frontend" in remaining_candidates:
                    rule_speaker = "agent_frontend"
                elif "agent_backend" in remaining_candidates:
                    rule_speaker = "agent_backend"
            elif last_completed in ("agent_frontend", "agent_backend"):
                frontend_done = "agent_frontend" in completed or "agent_frontend" not in remaining_candidates
                backend_done = "agent_backend" in completed or "agent_backend" not in remaining_candidates
                if frontend_done and backend_done:
                    if "agent_tester" in remaining_candidates:
                        rule_speaker = "agent_tester"
                else:
                    other = "agent_backend" if last_completed == "agent_frontend" else "agent_frontend"
                    if other in remaining_candidates:
                        rule_speaker = other
            elif last_completed == "agent_tester":
                if "agent_devops" in remaining_candidates:
                    rule_speaker = "agent_devops"
            elif last_completed == "agent_devops":
                rule_speaker = "END"

            if rule_speaker:
                sg_logger.info(f"[Speaker Selection] Heuristic rule B: SDLC waterfall. Selected '{rule_speaker}'")

        if rule_speaker:
            return rule_speaker

        # LLM fallback
        sg_logger.info("[Speaker Selection] Non-deterministic state. Dispatching LLM Coordinator...")

        candidates_info = ""
        for cid in remaining_candidates:
            if cid in AGENTS:
                candidates_info += f"- ID: {cid}\n  Name: {AGENTS[cid].name}\n  Description: {AGENTS[cid].description}\n\n"

        if not candidates_info.strip():
            return "END"

        history = await async_get_messages_cached(conversation_id, limit=6)
        history_text = ""
        for m in history:
            sender_name = m.get("sender", "unknown")
            content = m.get("content", {})
            text_content = content.get("text", "")
            text_content = re.sub(r'```[\s\S]*?```', '[Generated Code Block]', text_content)
            history_text += f"{sender_name}: {text_content[:400]}\n\n"

        user_prompt = f"--- 对话历史 ---\n{history_text}\n\n请决定下一个最适合发言的智能体。"
        system_prompt = SPEAKER_SELECTION_SYSTEM_PROMPT.format(candidates_info=candidates_info)

        selected = ""
        try:
            async for chunk in llm_client.chat_stream([{"role": "user", "content": user_prompt}], system=system_prompt):
                selected += chunk
            selected = selected.strip().strip("'\"`").strip()
            sg_logger.info(f"[Speaker Selection] LLM selected speaker: '{selected}'")
        except Exception as e:
            sg_logger.error(f"[Speaker Selection] Error calling LLM router: {e}")
            selected = ""

        if selected in remaining_candidates:
            return selected
        elif selected == "END":
            return "END"
        else:
            fallback = remaining_candidates[0]
            sg_logger.info(f"[Speaker Selection] Invalid speaker '{selected}', falling back to '{fallback}'")
            return fallback

    graph.add_conditional_edge("agent_pm", select_next_speaker)
    graph.add_conditional_edge("agent_designer", select_next_speaker)
    graph.add_conditional_edge("agent_frontend", select_next_speaker)
    graph.add_conditional_edge("agent_backend", select_next_speaker)
    graph.add_conditional_edge("agent_tester", select_next_speaker)
    graph.add_edge("agent_devops", "END")

    # Transition guards
    graph.add_guard(
        "agent_devops",
        lambda state: "agent_tester" in state.get("completed_nodes", []),
        error_fallback_node="agent_tester",
    )
    graph.add_guard(
        "agent_tester",
        lambda state: any(n in state.get("completed_nodes", []) for n in ["agent_frontend", "agent_backend"]),
        error_fallback_node="agent_frontend",
    )

    return graph


# ============================================================
# Checkpoint recovery
# ============================================================

async def resume_graph_from_checkpoint(conversation_id: str, action: str):
    """Restore state from persistent DB and resume suspended graph execution."""
    checkpoint = get_pending_hil_checkpoint(conversation_id)
    if not checkpoint:
        logger.warning(f"[Checkpointer Recovery] No pending HIL checkpoint for {conversation_id}")
        return

    resolve_hil_checkpoint(conversation_id, action)

    current_node = checkpoint["current_node"]
    next_node = checkpoint["next_node"]
    state_data = checkpoint["state_data"]
    original_prompt = checkpoint["original_prompt"]

    await manager.broadcast(conversation_id, {
        "type": "message",
        "conversation_id": conversation_id,
        "sender": "system",
        "content": {"text": f"🔄 检测到服务器重启。正在从检查点恢复流程并执行审核决策: **{action}**..."},
        "stream": False,
    })

    start_node = None
    if action.lower() in ("approve", "yes", "y") or any(
        action.lower() == opt["label"].lower() and opt["recommended"]
        for opt in checkpoint.get("options", [])
    ):
        if next_node == "END":
            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": "system",
                "content": {"text": "✅ 审核通过。流程圆满结束！"},
                "stream": False,
            })
            await manager.broadcast(conversation_id, {
                "type": "generating",
                "conversation_id": conversation_id,
                "is_generating": False,
            })
            return
        start_node = next_node
    elif action.lower() in ("terminate", "end", "stop"):
        await manager.broadcast(conversation_id, {
            "type": "message",
            "conversation_id": conversation_id,
            "sender": "system",
            "content": {"text": "🛑 审核不通过，流程已终止。"},
            "stream": False,
        })
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })
        return
    else:
        # Feedback / retry
        feedback = action
        feedback_msg = f"🔄 人工审核反馈：{feedback}\n\n正在重新生成..."
        await manager.broadcast(conversation_id, {
            "type": "message",
            "conversation_id": conversation_id,
            "sender": "user",
            "content": {"text": feedback_msg},
            "stream": False,
        })

        state_data[f"{current_node}_feedback"] = feedback
        if current_node in state_data.get("completed_nodes", []):
            state_data["completed_nodes"].remove(current_node)
        start_node = current_node

    stop_event = asyncio.Event()
    _stop_events[conversation_id] = stop_event

    trace = metrics.start_trace(
        task_id=str(uuid.uuid4())[:8],
        conversation_id=conversation_id,
        user_input=original_prompt,
    )

    try:
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": True,
        })

        graph = build_group_chat_graph(conversation_id, original_prompt, trace, stop_event)
        await graph.run(state_data, conversation_id, stop_event, start_node=start_node)
    finally:
        trace.finish()
        _stop_events.pop(conversation_id, None)
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })


# ============================================================
# User message flow (group or auto-routed)
# ============================================================

async def run_user_message_flow(conversation_id: str, text: str, target_agent: str | None):
    """Background generation flow for a plain user message (group or auto-routed)."""
    from app.routers.harness_handler import try_intercept_with_harness

    stop_event = asyncio.Event()
    _stop_events[conversation_id] = stop_event

    trace = metrics.start_trace(
        task_id=str(uuid.uuid4())[:8],
        conversation_id=conversation_id,
        user_input=text,
    )

    try:
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": True,
        })

        # Harness intercept
        intercepted = await try_intercept_with_harness(
            conversation_id, text, llm_client, manager
        )
        if intercepted:
            return

        if stop_event.is_set():
            return

        is_group = not target_agent
        if is_group and not stop_event.is_set():
            graph = build_group_chat_graph(conversation_id, text, trace, stop_event)
            await graph.run({"original_prompt": text}, conversation_id, stop_event)
    finally:
        trace.finish()
        _stop_events.pop(conversation_id, None)
        await manager.broadcast(conversation_id, {
            "type": "generating",
            "conversation_id": conversation_id,
            "is_generating": False,
        })

