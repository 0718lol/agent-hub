import asyncio
import base64
import json
import logging
import mimetypes
import os
import re
from collections.abc import AsyncGenerator

from app.core.llm_client import llm_client
from app.core.prompt_engine import prompt_engine

logger = logging.getLogger("base_agent")

# Maximum characters for conversation history context (~4000 tokens ≈ 12000 chars)
_MAX_HISTORY_CHARS = 12000
# Maximum tool call rounds per reply (prevent infinite loops)
_MAX_TOOL_ROUNDS = 5
_MAX_TOOLS_PER_ROUND = 8
_MAX_IMAGE_ATTACHMENT_BYTES = 4 * 1024 * 1024

_WORKSPACE_SCOPED_TOOLS = frozenset({
    "file_read",
    "file_write",
    "file_list",
    "browser_action",
    "workspace_capture_screenshot",
    "safe_python_executor",
    "file_view_windowed",
    "file_edit_line",
    "file_patch_block",
    "run_stateful_command",
    "e2b_python_interpreter",
    "git_commit",
    "git_push",
    "create_pr",
    "user_interaction_judge",
})


def _resolve_owned_upload_path(stored_name: str, conversation_id: str | None) -> str | None:
    if not stored_name or ".." in stored_name or "/" in stored_name or "\\" in stored_name:
        return None
    from app.core.file_storage import UPLOAD_DIR, FileStorageManager
    from app.core.tenancy import conversation_user_id, current_tenant_id

    owner = conversation_user_id(conversation_id or "") or current_tenant_id()
    if owner:
        allowed = stored_name.startswith(f"tenantfile__{owner}__") or (
            owner == "api-client" and not stored_name.startswith("tenantfile__")
        )
        if not allowed:
            return None
    elif stored_name.startswith("tenantfile__"):
        return None

    if not FileStorageManager.exists(stored_name):
        return None
    abs_path = os.path.realpath(FileStorageManager.get_absolute_path(stored_name))
    real_upload = os.path.realpath(UPLOAD_DIR)
    if os.path.commonpath([real_upload, abs_path]) != real_upload:
        return None
    return abs_path


def _enrich_user_content(
    message: str,
    attachments: list | None,
    conversation_id: str | None = None,
) -> str | list[dict]:
    if not attachments:
        return message
    text_blocks: list[str] = []
    image_blocks: list[dict] = []
    for att in attachments[:10]:
        if not isinstance(att, dict):
            continue
        orig_name = str(att.get("original_name") or att.get("name") or "attachment")[:120]
        stored_name = str(att.get("stored_name") or "").strip()
        if not stored_name and isinstance(att.get("url"), str) and att["url"].startswith("/uploads/"):
            stored_name = att["url"].removeprefix("/uploads/").strip()

        is_image = bool(att.get("is_image")) or str(att.get("content_type") or "").startswith("image/")
        if is_image and stored_name:
            path = _resolve_owned_upload_path(stored_name, conversation_id)
            if path and os.path.getsize(path) <= _MAX_IMAGE_ATTACHMENT_BYTES:
                mime = str(att.get("content_type") or mimetypes.guess_type(path)[0] or "image/png")
                if not mime.startswith("image/"):
                    mime = "image/png"
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                image_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
                text_blocks.append(f"[已附图片: {orig_name}]")
            continue

        extracted = str(att.get("extracted_text") or "").strip()
        if not extracted and stored_name:
            path = _resolve_owned_upload_path(stored_name, conversation_id)
            if path and os.path.getsize(path) <= 512 * 1024:
                with open(path, "rb") as f:
                    raw = f.read(16_384)
                if b"\x00" not in raw[:2048]:
                    extracted = raw.decode("utf-8", errors="replace").strip()
        if extracted:
            text_blocks.append(f"[附件: {orig_name}]\n{extracted[:4000]}")
        else:
            text_blocks.append(f"[附件: {orig_name} (二进制文件)]")

    combined_text = message
    if text_blocks:
        combined_text = (message + "\n\n" + "\n\n".join(text_blocks)).strip()
    if image_blocks:
        return [{"type": "text", "text": combined_text}, *image_blocks]
    return combined_text


def _without_explicit_thinking(prompt: str) -> str:
    """Remove prompt lines that request user-visible chain-of-thought tags."""
    filtered = [
        line for line in prompt.splitlines()
        if "[thinking]" not in line
        and "[/thinking]" not in line
        and "【思维过程】" not in line
        and "思考完毕后" not in line
    ]
    return "\n".join(filtered).strip() + (
        "\n\n【输出约束】当前模型已关闭思考模式。"
        "不要输出分析过程、思考标签或推理草稿，只输出最终结果。"
    )


class BaseAgent:
    agent_id: str = ""
    name: str = ""
    avatar: str = ""
    role: str = ""
    style: str = ""
    system_prompt: str = ""
    description: str = ""
    # Runtime tools enabled for this agent (None = all enabled tools)
    enabled_tools: list[str] | None = None

    async def stream_reply(
        self,
        message: str,
        context: list | None = None,
        history: list | None = None,
        conversation_id: str | None = None,
        attachments: list | None = None,
    ) -> AsyncGenerator[str, None]:
        if llm_client.is_configured() and self.system_prompt:
            enriched_user = _enrich_user_content(message, attachments, conversation_id)
            if conversation_id:
                from app.core.event_stream import MessageEvent, event_stream_manager
                stream = event_stream_manager.get_stream(conversation_id)
                event_text = enriched_user if isinstance(enriched_user, str) else message
                has_user_prompt = any(
                    isinstance(ev, MessageEvent) and ev.sender == "user" and ev.content == event_text
                    for ev in stream
                )
                if not has_user_prompt:
                    event_stream_manager.append_event(
                        conversation_id,
                        MessageEvent(sender="user", content=event_text),
                    )
                messages = event_stream_manager.compile_to_messages(conversation_id)
                if isinstance(enriched_user, list):
                    if messages and messages[-1].get("role") == "user":
                        messages[-1] = {"role": "user", "content": enriched_user}
                    else:
                        messages.append({"role": "user", "content": enriched_user})
            else:
                messages = self._build_messages(message, context, history, attachments=attachments)
            # Structured layered prompt injection
            task_type = prompt_engine.detect_task_type(message, self.agent_id)
            prompt_context = {"task_type": task_type, "conversation_id": conversation_id}
            full_prompt = prompt_engine.build(self, prompt_context)
            if llm_client.thinking_mode == "disabled":
                full_prompt = _without_explicit_thinking(full_prompt)

            # Only inject text tool schemas when provider does not receive native tools JSON schema
            if getattr(llm_client, "provider", "openai") in ("ollama", "opencode", "claude_code"):
                tools_prompt = self._get_tools_prompt()
                if tools_prompt:
                    full_prompt = full_prompt + tools_prompt

            # Stream with tool call interception loop
            round_count = 0
            while True:
                accumulated = ""
                try:
                    llm_gen = llm_client.chat_stream(messages, full_prompt, self.enabled_tools)
                except TypeError:
                    llm_gen = llm_client.chat_stream(messages, full_prompt)
                async for chunk in llm_gen:
                    accumulated += chunk
                    yield chunk

                # Check if output contains tool_call tags
                from app.tools.registry import execute_tool_call, get_tool, parse_tool_calls
                tool_calls = parse_tool_calls(accumulated)

                if conversation_id:
                    from app.core.event_stream import ActionCallEvent, ThoughtEvent, event_stream_manager
                    if tool_calls:
                        first_start = tool_calls[0][2]
                        thought_text = accumulated[:first_start]
                        if thought_text.strip():
                            event_stream_manager.append_event(
                                conversation_id,
                                ThoughtEvent(agent_id=self.agent_id, content=thought_text),
                            )
                        for t_name, t_params, _s, _e in tool_calls[:_MAX_TOOLS_PER_ROUND]:
                            event_stream_manager.append_event(
                                conversation_id,
                                ActionCallEvent(tool_name=t_name, params=t_params),
                            )
                    else:
                        event_stream_manager.append_event(
                            conversation_id,
                            ThoughtEvent(agent_id=self.agent_id, content=accumulated),
                        )

                if not tool_calls or round_count >= _MAX_TOOL_ROUNDS:
                    break  # No tool calls or max rounds reached

                round_count += 1
                observations: list[str] = []
                all_obs_images: list[str] = []

                for tool_name, params, _start_pos, _end_pos in tool_calls[:_MAX_TOOLS_PER_ROUND]:
                    if not isinstance(params, dict):
                        params = {}
                    # Mandatory tenant workspace scoping: overwrite conversation_id on any tool that accepts it
                    tool_obj = get_tool(tool_name)
                    accepts_conv = bool(
                        tool_obj
                        and "conversation_id" in (tool_obj.parameters or {}).get("properties", {})
                    )
                    if conversation_id and (tool_name in _WORKSPACE_SCOPED_TOOLS or accepts_conv):
                        params["conversation_id"] = conversation_id

                    logger.info(f"Agent '{self.agent_id}' calling tool: {tool_name}({params})")
                    result = await execute_tool_call(tool_name, params)

                    result_text = self._format_tool_result(tool_name, result)
                    yield f"\n\n> 🔧 **工具调用**: `{tool_name}`\n{result_text}\n\n"

                    obs_output = result.data if result.success else {"error": result.error}
                    obs_images: list[str] = []
                    if result.success and isinstance(result.data, dict):
                        if "images" in result.data:
                            obs_images = [img for img in result.data["images"] if img]
                        elif result.data.get("screenshot_base64"):
                            obs_images = [result.data["screenshot_base64"]]
                        elif result.data.get("screenshot"):
                            obs_images = [result.data["screenshot"]]

                    if conversation_id:
                        from app.core.event_stream import ObservationEvent, event_stream_manager
                        event_stream_manager.append_event(
                            conversation_id,
                            ObservationEvent(
                                tool_name=tool_name,
                                success=result.success,
                                output=result.data if result.success else result.error,
                                images=obs_images,
                            ),
                        )
                    observations.append(
                        f"[工具结果: {tool_name}]\n{json.dumps(obs_output, ensure_ascii=False, indent=2)}"
                    )
                    all_obs_images.extend(obs_images)

                messages.append({"role": "assistant", "content": accumulated})
                combined_observation = "\n\n".join(observations) + "\n\n请基于以上工具结果继续回复用户。"
                if all_obs_images:
                    observation_content: list[dict] = [{"type": "text", "text": combined_observation}]
                    observation_content.extend(
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}}
                        for image in all_obs_images
                    )
                    messages.append({"role": "user", "content": observation_content})
                else:
                    messages.append({"role": "user", "content": combined_observation})
        else:
            reply = self._generate_reply(message, context)
            # Mock mode should still feel streamed, but character-by-character
            # delays made code responses take minutes.
            for offset in range(0, len(reply), 32):
                await asyncio.sleep(0.005)
                yield reply[offset:offset + 32]

    def _get_tools_prompt(self) -> str:
        """Get tools prompt block for this agent."""
        try:
            from app.tools.registry import get_tools_prompt
            return get_tools_prompt(self.enabled_tools)
        except Exception as e:
            logger.warning(f"Failed to get tools prompt: {e}")
            return ""

    @staticmethod
    def _format_tool_result(tool_name: str, result) -> str:
        """Format a ToolResult for inline display in chat."""
        if not result.success:
            return f"> ❌ 错误: {result.error}"
        data = result.data
        if tool_name == "web_search" and isinstance(data, dict):
            items = data.get("results", [])
            if not items:
                return "> 未找到相关结果"
            lines = []
            for i, item in enumerate(items[:5], 1):
                lines.append(f"> {i}. **{item['title']}**\n>    {item['snippet'][:100]}")
            return "\n".join(lines)
        elif tool_name == "http_request" and isinstance(data, dict):
            status = data.get("status_code", "?")
            body = data.get("body", "")[:500]
            return f"> 状态码: {status}\n> ```\n> {body}\n> ```"
        elif tool_name == "file_read" and isinstance(data, dict):
            content = data.get("content", "")[:500]
            return f"> ```\n{content}\n> ```"
        elif tool_name == "safe_python_executor" and isinstance(data, dict):
            stdout = data.get("stdout", "")
            ret = data.get("result", None)
            lines = []
            if stdout:
                lines.append(f"> **标准输出 (stdout)**:\n> ```\n> {stdout.strip()}\n> ```")
            if ret is not None:
                lines.append(f"> **返回值 (return)**: `{ret}`")
            if not lines:
                lines.append("> (执行成功，无任何输出与返回值)")
            return "\n".join(lines)
        elif tool_name == "browser_action" and isinstance(data, dict):
            msg = data.get("message", "")
            prefix = ""
            if data.get("vision_used"):
                prefix = "> ✨ **[👁️ 视觉定位成功]** 实时激活多模态视觉定位主循环，百分比视口绝对坐标转换精确触发！\n"
            elif data.get("failover_used"):
                prefix = "> 🛡️ **[🩹 模糊匹配自愈已启动]** 视觉调用降级，自动激活 DOM 节点与自然语言局部自愈网络安全触达！\n"
            return prefix + "\n".join(f"> {line}" for line in msg.split("\n"))
        elif tool_name == "file_view_windowed" and isinstance(data, dict):
            msg = data.get("message", "")
            return "\n".join(f"> {line}" for line in msg.split("\n"))
        elif tool_name == "file_edit_line" and isinstance(data, dict):
            msg = data.get("message", "")
            return f"> {msg}"
        elif tool_name == "run_stateful_command" and isinstance(data, dict):
            output = data.get("output", "")[:1000]
            return "> **有状态命令执行输出**:\n> ```\n" + "\n".join(f"> {line}" for line in output.split("\n")) + "\n> ```"
        elif tool_name == "e2b_python_interpreter" and isinstance(data, dict):
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            images = data.get("images", [])
            lines = []
            if stdout:
                lines.append(f"> **标准输出 (stdout)**:\n> ```\n> {stdout.strip()}\n> ```")
            if stderr:
                lines.append(f"> ❌ **错误输出 (stderr)**:\n> ```\n> {stderr.strip()}\n> ```")
            if images:
                lines.append("> ✨ **[📊 E2B 代码解释器绘图成功]** 已自动拦截并捕捉科学计算可视化成果：")
                for img in images:
                    lines.append(f"> ![Generated Visualization](data:image/png;base64,{img})")
            if not lines:
                lines.append("> (执行成功，无任何文本输出)")
            return "\n".join(lines)
        elif tool_name in ("file_write", "file_list") and isinstance(data, dict):
            return f"> {json.dumps(data, ensure_ascii=False, indent=2)}"
        else:
            return f"> {json.dumps(data, ensure_ascii=False)[:500]}"

    def _build_messages(self, message: str, context: list | None = None,
                        history: list | None = None, attachments: list | None = None) -> list[dict]:
        messages = []
        total_chars = 0

        # Include conversation history (from DB) for multi-turn awareness
        if history:
            hist_messages = []
            for msg in history:
                sender = msg.get("sender", "user")
                text = msg.get("content", {}).get("text", "") if isinstance(msg.get("content"), dict) else ""
                if not text:
                    continue
                role = "user" if sender == "user" else "assistant"
                hist_messages.append({"role": role, "content": text})

            # Trim history to fit within context budget (keep most recent)
            trimmed = []
            for m in reversed(hist_messages):
                if total_chars + len(m["content"]) > _MAX_HISTORY_CHARS:
                    break
                trimmed.insert(0, m)
                total_chars += len(m["content"])
            messages.extend(trimmed)

        # Include inline context (e.g. PM breakdown passed between agents)
        if context and isinstance(context, list):
            for msg in context[-10:]:
                role = "assistant" if msg.get("sender") != "user" else "user"
                text = msg.get("content", {}).get("text", "")
                if text:
                    messages.append({"role": role, "content": text})

        # Avoid duplicating the current user message when history already includes it
        if not (messages and messages[-1].get("role") == "user"
                and messages[-1].get("content") == message and not attachments):
            enhanced_message = _enrich_user_content(message, attachments)
            if messages and messages[-1].get("role") == "user" and messages[-1].get("content") == message:
                messages[-1] = {"role": "user", "content": enhanced_message}
            else:
                messages.append({"role": "user", "content": enhanced_message})
        return messages

    def _generate_reply(self, message: str, context: list | None = None) -> str:
        return f"[{self.name}] 收到你的消息了！"

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "avatar": self.avatar,
            "role": self.role,
            "style": self.style,
        }
