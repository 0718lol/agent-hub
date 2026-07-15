"""In-process task admission control for interactive generation workloads."""

import asyncio
from collections import Counter


class GenerationAdmissionController:
    def __init__(self, max_per_user: int = 2):
        self.max_per_user = max_per_user
        self._active_conversations: set[str] = set()
        self._active_users: Counter[str] = Counter()
        self._lock = asyncio.Lock()

    async def acquire(self, user_id: str, conversation_id: str) -> tuple[bool, str | None]:
        async with self._lock:
            if conversation_id in self._active_conversations:
                return False, "当前会话正在生成，请等待完成或点击停止。"
            if self._active_users[user_id] >= self.max_per_user:
                return False, f"每位用户最多同时运行 {self.max_per_user} 个生成任务。"
            self._active_conversations.add(conversation_id)
            self._active_users[user_id] += 1
            return True, None

    async def release(self, user_id: str, conversation_id: str) -> None:
        async with self._lock:
            self._active_conversations.discard(conversation_id)
            if self._active_users[user_id] > 1:
                self._active_users[user_id] -= 1
            else:
                self._active_users.pop(user_id, None)

    def reset(self) -> None:
        self._active_conversations.clear()
        self._active_users.clear()


generation_admission = GenerationAdmissionController()
