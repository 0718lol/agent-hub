import asyncio
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
            full_prompt = prompt_engine.build(self, prompt_context)
            async for chunk in llm_client.chat_stream(messages, full_prompt):
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

        # Avoid duplicating the current user message when history already includes it
        # (main.py saves the user message before fetching history, so the last entry
        # may already be the same message — appending again breaks Anthropic's
        # user/assistant alternation rule).
        if not (messages and messages[-1].get("role") == "user"
                and messages[-1].get("content") == message):
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
