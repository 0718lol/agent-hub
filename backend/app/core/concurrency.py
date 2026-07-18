"""Cross-instance admission and cancellation for interactive generation."""

import asyncio
import hashlib
import logging
import secrets
import time
from collections import Counter

from app.core.config import settings
from app.core.redis import redis_manager

logger = logging.getLogger("generation_admission")

_ACQUIRE_SCRIPT = """
if redis.call('exists', KEYS[1]) == 1 then
  return 1
end
redis.call('zremrangebyscore', KEYS[2], '-inf', ARGV[1])
if redis.call('zcard', KEYS[2]) >= tonumber(ARGV[2]) then
  return 2
end
redis.call('set', KEYS[1], ARGV[3], 'EX', ARGV[4])
redis.call('zadd', KEYS[2], tonumber(ARGV[1]) + tonumber(ARGV[4]), ARGV[5])
redis.call('expire', KEYS[2], ARGV[4])
redis.call('del', KEYS[3])
redis.call('hset', KEYS[4],
  'state', 'running',
  'user_id', ARGV[6],
  'started_at', ARGV[1],
  'updated_at', ARGV[1])
redis.call('expire', KEYS[4], ARGV[7])
return 0
"""

_HEARTBEAT_SCRIPT = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then
  return 0
end
redis.call('expire', KEYS[1], ARGV[2])
redis.call('zadd', KEYS[2], tonumber(ARGV[3]) + tonumber(ARGV[2]), ARGV[4])
redis.call('expire', KEYS[2], ARGV[2])
redis.call('hset', KEYS[3], 'updated_at', ARGV[3])
redis.call('expire', KEYS[3], ARGV[5])
return 1
"""

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then
  return 0
end
redis.call('del', KEYS[1])
redis.call('zrem', KEYS[2], ARGV[2])
redis.call('del', KEYS[3])
redis.call('hset', KEYS[4], 'state', ARGV[3], 'updated_at', ARGV[4])
redis.call('expire', KEYS[4], ARGV[5])
return 1
"""


class GenerationAdmissionController:
    def __init__(
        self,
        max_per_user: int | None = None,
        lease_ttl: int | None = None,
    ):
        self.max_per_user = max_per_user or settings.generation_max_per_user
        self.lease_ttl = max(15, lease_ttl or settings.generation_lease_ttl)
        self.status_ttl = 24 * 60 * 60
        self._active_conversations: set[str] = set()
        self._active_users: Counter[str] = Counter()
        self._leases: dict[str, tuple[str, str]] = {}
        self._cancelled: set[str] = set()
        self._statuses: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _conversation_key(conversation_id: str) -> str:
        digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
        return f"agenthub:generation:lease:{digest}"

    @staticmethod
    def _user_key(user_id: str) -> str:
        digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
        return f"agenthub:generation:user:{digest}"

    @classmethod
    def _cancel_key(cls, conversation_id: str) -> str:
        return cls._conversation_key(conversation_id).replace(":lease:", ":cancel:")

    @classmethod
    def _status_key(cls, conversation_id: str) -> str:
        return cls._conversation_key(conversation_id).replace(":lease:", ":status:")

    async def acquire(self, user_id: str, conversation_id: str) -> tuple[bool, str | None]:
        if await redis_manager.check_connection():
            try:
                token = secrets.token_urlsafe(24)
                now = int(time.time())
                client = redis_manager.get_client()
                result = int(await client.eval(
                    _ACQUIRE_SCRIPT,
                    4,
                    self._conversation_key(conversation_id),
                    self._user_key(user_id),
                    self._cancel_key(conversation_id),
                    self._status_key(conversation_id),
                    now,
                    self.max_per_user,
                    token,
                    self.lease_ttl,
                    conversation_id,
                    user_id,
                    self.status_ttl,
                ))
                if result == 1:
                    return False, "当前会话正在生成，请等待完成或点击停止。"
                if result == 2:
                    return False, f"每位用户最多同时运行 {self.max_per_user} 个生成任务。"
                self._leases[conversation_id] = (user_id, token)
                return True, None
            except Exception as exc:
                redis_manager.mark_unavailable(exc, "generation acquire")
                logger.warning("Generation coordination failed during acquire: %s", exc)

        if not settings.debug:
            return False, "生成协调服务暂时不可用，请稍后重试。"

        async with self._lock:
            if conversation_id in self._active_conversations:
                return False, "当前会话正在生成，请等待完成或点击停止。"
            if self._active_users[user_id] >= self.max_per_user:
                return False, f"每位用户最多同时运行 {self.max_per_user} 个生成任务。"
            self._active_conversations.add(conversation_id)
            self._active_users[user_id] += 1
            self._cancelled.discard(conversation_id)
            self._statuses[conversation_id] = {
                "state": "running",
                "user_id": user_id,
                "started_at": int(time.time()),
            }
            return True, None

    async def heartbeat(self, user_id: str, conversation_id: str) -> bool:
        lease = self._leases.get(conversation_id)
        if not lease or lease[0] != user_id:
            return conversation_id in self._active_conversations
        if not await redis_manager.check_connection():
            return False
        now = int(time.time())
        try:
            client = redis_manager.get_client()
            return bool(await client.eval(
                _HEARTBEAT_SCRIPT,
                3,
                self._conversation_key(conversation_id),
                self._user_key(user_id),
                self._status_key(conversation_id),
                lease[1],
                self.lease_ttl,
                now,
                conversation_id,
                self.status_ttl,
            ))
        except Exception as exc:
            redis_manager.mark_unavailable(exc, "generation heartbeat")
            return False

    async def release(
        self,
        user_id: str,
        conversation_id: str,
        status: str = "completed",
    ) -> None:
        lease = self._leases.pop(conversation_id, None)
        if lease and lease[0] == user_id and await redis_manager.check_connection():
            try:
                client = redis_manager.get_client()
                await client.eval(
                    _RELEASE_SCRIPT,
                    4,
                    self._conversation_key(conversation_id),
                    self._user_key(user_id),
                    self._cancel_key(conversation_id),
                    self._status_key(conversation_id),
                    lease[1],
                    conversation_id,
                    status,
                    int(time.time()),
                    self.status_ttl,
                )
                return
            except Exception as exc:
                redis_manager.mark_unavailable(exc, "generation release")
                logger.warning(
                    "Generation lease release failed; lease will expire: %s", exc
                )

        async with self._lock:
            self._active_conversations.discard(conversation_id)
            if self._active_users[user_id] > 1:
                self._active_users[user_id] -= 1
            else:
                self._active_users.pop(user_id, None)
            self._cancelled.discard(conversation_id)
            previous = self._statuses.get(conversation_id, {})
            self._statuses[conversation_id] = {
                **previous,
                "state": status,
                "updated_at": int(time.time()),
            }

    async def request_cancel(self, conversation_id: str) -> None:
        if await redis_manager.check_connection():
            try:
                client = redis_manager.get_client()
                now = int(time.time())
                await client.set(self._cancel_key(conversation_id), "1", ex=self.lease_ttl)
                await client.hset(
                    self._status_key(conversation_id),
                    mapping={"state": "cancelling", "updated_at": now},
                )
                await client.expire(self._status_key(conversation_id), self.status_ttl)
                return
            except Exception as exc:
                redis_manager.mark_unavailable(exc, "generation cancel")
        self._cancelled.add(conversation_id)

    async def cancel_requested(self, conversation_id: str) -> bool:
        if await redis_manager.check_connection():
            try:
                return bool(
                    await redis_manager.get_client().exists(
                        self._cancel_key(conversation_id)
                    )
                )
            except Exception as exc:
                redis_manager.mark_unavailable(exc, "generation cancel check")
        return conversation_id in self._cancelled

    async def get_status(self, conversation_id: str) -> dict:
        if await redis_manager.check_connection():
            try:
                client = redis_manager.get_client()
                status = await client.hgetall(self._status_key(conversation_id))
                if (
                    status.get("state") in {"running", "cancelling"}
                    and not await client.exists(self._conversation_key(conversation_id))
                ):
                    now = int(time.time())
                    status.update({
                        "state": "interrupted",
                        "updated_at": str(now),
                        "reason": "generation lease expired before completion",
                    })
                    await client.hset(self._status_key(conversation_id), mapping=status)
                    await client.expire(self._status_key(conversation_id), self.status_ttl)
                return status
            except Exception as exc:
                redis_manager.mark_unavailable(exc, "generation status")
        return dict(self._statuses.get(conversation_id, {}))

    def reset(self) -> None:
        self._active_conversations.clear()
        self._active_users.clear()
        self._leases.clear()
        self._cancelled.clear()
        self._statuses.clear()


generation_admission = GenerationAdmissionController()
