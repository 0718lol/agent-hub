import asyncio
import random
from typing import AsyncGenerator

from app.core.llm_client import llm_client


class BaseAgent:
    agent_id: str = ""
    name: str = ""
    avatar: str = ""
    role: str = ""
    style: str = ""
    system_prompt: str = ""

    async def stream_reply(self, message: str, context: list = None) -> AsyncGenerator[str, None]:
        if llm_client.is_configured() and self.system_prompt:
            messages = self._build_messages(message, context)
            async for chunk in llm_client.chat_stream(messages, self.system_prompt):
                yield chunk
        else:
            reply = self._generate_reply(message, context)
            for char in reply:
                delay = random.uniform(0.02, 0.06)
                await asyncio.sleep(delay)
                yield char

    def _build_messages(self, message: str, context: list = None) -> list[dict]:
        messages = []
        if context:
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
