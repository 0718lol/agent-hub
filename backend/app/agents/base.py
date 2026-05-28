import asyncio
import json
import random
from typing import AsyncGenerator

from app.core.llm_client import llm_client
from app.core.prompt_engine import prompt_engine

# Maximum characters for conversation history context (~4000 tokens ≈ 12000 chars)
_MAX_HISTORY_CHARS = 12000


class BaseAgent:
    agent_id: str = ""
    name: str = ""
    avatar: str = ""
    role: str = ""
    style: str = ""
    system_prompt: str = ""

    async def stream_reply(self, message: str, context: list = None,
                           history: list = None) -> AsyncGenerator[str, None]:
        if llm_client.is_configured() and self.system_prompt:
            messages = self._build_messages(message, context, history)
            # Structured layered prompt injection
            task_type = prompt_engine.detect_task_type(message, self.agent_id)
            prompt_context = {"task_type": task_type}
            conv_id = None
            if history and len(history) > 0:
                conv_id = history[0].get("conversation_id")
            if conv_id:
                prompt_context["conversation_id"] = conv_id
            full_prompt = prompt_engine.build(self, prompt_context)
            
            # Fetch dynamic route
            from app.core.router import smart_router
            route = smart_router.get_route_for_agent(self.agent_id)
            
            # Stream beautiful route indicator to user
            yield f"\n[thinking]🤖 智能路由调度: 正在调用 {route.model} ({route.provider}) 执行任务...[/thinking]\n"
            
            # Load active MCP tools from manager
            from app.core.mcp_client import mcp_manager
            mcp_tools = await mcp_manager.get_all_tools()
            
            tool_calls_out = []
            async for chunk in llm_client.chat_stream(
                messages, full_prompt, route_override=route, tools=mcp_tools, tool_calls_out=tool_calls_out
            ):
                yield chunk
                
            # Process tool calls in a recursive loop
            while tool_calls_out:
                active_calls = list(tool_calls_out)
                tool_calls_out.clear()
                
                for tc in active_calls:
                    tc_id = tc.get("id")
                    tc_name = tc.get("name")
                    tc_args_str = tc.get("arguments", "{}")
                    
                    if not tc_name:
                        continue
                    
                    try:
                        tc_args = json.loads(tc_args_str) if tc_args_str.strip() else {}
                    except Exception:
                        tc_args = {}
                        
                    # Stream execution trace bubble
                    yield f"\n[tool_execution]🔌 MCP 工具调用: 正在请求 {tc_name}，参数：{tc_args_str}...[/tool_execution]\n"
                    
                    # Execute tool through manager
                    result = await mcp_manager.execute_tool(tc_name, tc_args, conversation_id=conv_id)
                    
                    is_error = result.get("isError", False)
                    result_content = result.get("content", [])
                    result_text = result_content[0].get("text", "") if result_content else "无返回结果"
                    
                    status_icon = "❌" if is_error else "✅"
                    yield f"\n[tool_execution]{status_icon} MCP 执行结果: {result_text[:400]}...[/tool_execution]\n"
                    
                    # Inject tool interaction into conversation history
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc_id or f"call_{tc_name}",
                                "type": "function",
                                "function": {
                                    "name": tc_name,
                                    "arguments": tc_args_str
                                }
                            }
                        ]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id or f"call_{tc_name}",
                        "name": tc_name,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
                    
                # Invoke LLM again with injected tool history context
                yield f"\n[thinking]🤖 路由调度 (多轮推理中): 正在调用 {route.model}...[/thinking]\n"
                async for chunk in llm_client.chat_stream(
                    messages, full_prompt, route_override=route, tools=mcp_tools, tool_calls_out=tool_calls_out
                ):
                    yield chunk
        else:
            reply = self._generate_reply(message, context)
            for char in reply:
                delay = random.uniform(0.02, 0.06)
                await asyncio.sleep(delay)
                yield char

    def _build_messages(self, message: str, context: list = None,
                        history: list = None) -> list[dict]:
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

        messages.append({"role": "user", "content": message})
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
