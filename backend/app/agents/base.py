import asyncio
import json
import random
import logging
from typing import AsyncGenerator

from app.core.llm_client import llm_client
from app.core.prompt_engine import prompt_engine

logger = logging.getLogger("base_agent")

# Maximum characters for conversation history context (~4000 tokens ≈ 12000 chars)
_MAX_HISTORY_CHARS = 12000
# Maximum tool call rounds per reply (prevent infinite loops)
_MAX_TOOL_ROUNDS = 5


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

    async def stream_reply(self, message: str, context: list = None,
                           history: list = None, attachments: list = None,
                           conversation_id: str = "") -> AsyncGenerator[str, None]:
        if llm_client.is_configured() and self.system_prompt:
            if conversation_id:
                from app.core.event_stream import event_stream_manager, MessageEvent
                stream = event_stream_manager.get_stream(conversation_id)
                has_user_prompt = any(isinstance(ev, MessageEvent) and ev.sender == "user" and ev.content == message for ev in stream)
                if not has_user_prompt:
                    event_stream_manager.append_event(conversation_id, MessageEvent(sender="user", content=message))
                messages = event_stream_manager.compile_to_messages(conversation_id)
            else:
                messages = self._build_messages(message, context, history, attachments)

            # Structured layered prompt injection
            task_type = prompt_engine.detect_task_type(message, self.agent_id)
            prompt_context = {"task_type": task_type, "conversation_id": conversation_id}
            full_prompt = prompt_engine.build(self, prompt_context)

            # Inject tool descriptions into system prompt
            tools_prompt = self._get_tools_prompt()
            if tools_prompt:
                full_prompt = full_prompt + tools_prompt

            # Stream with tool call interception loop
            round_count = 0
            while True:
                accumulated = ""
                async for chunk in llm_client.chat_stream(messages, full_prompt):
                    accumulated += chunk
                    yield chunk

                # Check if output contains tool_call tags
                from app.tools.registry import parse_tool_calls, execute_tool_call
                tool_calls = parse_tool_calls(accumulated)

                if conversation_id:
                    from app.core.event_stream import event_stream_manager, ThoughtEvent, ActionCallEvent
                    if tool_calls:
                        tool_name, params, start_pos, end_pos = tool_calls[0]
                        thought_text = accumulated[:start_pos]
                        if thought_text.strip():
                            event_stream_manager.append_event(conversation_id, ThoughtEvent(agent_id=self.agent_id, content=thought_text))
                        event_stream_manager.append_event(conversation_id, ActionCallEvent(tool_name=tool_name, params=params))
                    else:
                        event_stream_manager.append_event(conversation_id, ThoughtEvent(agent_id=self.agent_id, content=accumulated))

                if not tool_calls or round_count >= _MAX_TOOL_ROUNDS:
                    break  # No tool calls or max rounds reached

                round_count += 1
                # Execute the first tool call found
                tool_name, params, start_pos, end_pos = tool_calls[0]

                # Inject conversation_id for ACI and file/browser tools
                if tool_name in ("file_read", "file_write", "file_list", "browser_action", "file_view_windowed", "file_edit_line", "run_stateful_command", "e2b_python_interpreter") and conversation_id:
                    params.setdefault("conversation_id", conversation_id)

                logger.info(f"Agent '{self.agent_id}' calling tool: {tool_name}({params})")
                result = await execute_tool_call(tool_name, params)

                # Format tool result for display
                result_text = self._format_tool_result(tool_name, result)
                yield f"\n\n> 🔧 **工具调用**: `{tool_name}`\n{result_text}\n\n"

                # Add assistant output + tool result to messages for next round
                if conversation_id:
                    from app.core.event_stream import event_stream_manager, ObservationEvent
                    obs_output = result.data if result.success else result.error
                    obs_images = result.data.get("images", []) if (result.success and isinstance(result.data, dict)) else []
                    event_stream_manager.append_event(
                        conversation_id,
                        ObservationEvent(tool_name=tool_name, success=result.success, output=obs_output, images=obs_images)
                    )
                    messages = event_stream_manager.compile_to_messages(conversation_id)
                else:
                    messages.append({"role": "assistant", "content": accumulated})
                    messages.append({"role": "user", "content": f"[工具结果: {tool_name}]\n{json.dumps(result.data if result.success else {'error': result.error}, ensure_ascii=False, indent=2)}\n\n请基于以上工具结果继续回复用户。"})
        else:
            reply = self._generate_reply(message, context)
            for char in reply:
                delay = random.uniform(0.04, 0.10)
                await asyncio.sleep(delay)
                yield char

    def _get_tools_prompt(self) -> str:
        """Get tools prompt block for this agent."""
        try:
            from app.tools.registry import get_tools_prompt
            return get_tools_prompt(self.enabled_tools)
        except Exception:
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
            return f"> **有状态命令执行输出**:\n> ```\n" + "\n".join(f"> {line}" for line in output.split("\n")) + "\n> ```"
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

    def _build_messages(self, message: str, context: list = None,
                        history: list = None, attachments: list = None) -> list[dict]:
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

        # RAG 知识库检索注入
        rag_context = ""
        try:
            from app.core.rag_engine import rag_engine
            rag_context = rag_engine.build_context_prompt(message)
            if rag_context:
                logger.debug(f"RAG: injecting context for query '{message[:50]}...'")
        except Exception as e:
            logger.debug(f"RAG: skipped ({e})")

        # 附件文件内容注入：将 extracted_text 追加到用户消息中
        enhanced_message = message
        if attachments:
            file_contexts = []
            for att in attachments:
                extracted = att.get("extracted_text", "")
                if extracted:
                    file_contexts.append(
                        f"[文件: {att.get('original_name', 'unknown')}]\n{extracted[:2000]}"
                    )
            if file_contexts:
                enhanced_message = message + "\n\n" + "\n\n".join(file_contexts)

        # 将 RAG 上下文作为 system 级参考，插在用户消息前
        if rag_context:
            messages.append({"role": "user", "content": rag_context})
            messages.append({"role": "assistant", "content": "好的，我已了解参考资料，请继续提问。"})

        messages.append({"role": "user", "content": enhanced_message})
        return messages

    def _generate_reply(self, message: str, context: list = None) -> str:
        return f"[{self.name}] 收到你的消息了！"

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "avatar": self.avatar,
            "role": self.role,
            "style": self.style,
        }
