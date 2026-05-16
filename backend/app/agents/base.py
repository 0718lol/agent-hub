import asyncio
import random
from typing import AsyncGenerator


class BaseAgent:
    agent_id: str = ""
    name: str = ""
    avatar: str = ""
    role: str = ""
    style: str = ""

    async def stream_reply(self, message: str, context: list = None) -> AsyncGenerator[str, None]:
        reply = self._generate_reply(message, context)
        for char in reply:
            delay = random.uniform(0.02, 0.06)
            await asyncio.sleep(delay)
            yield char

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
