"""Small compare-and-set leases used for cross-instance coordination."""

import logging
import secrets

from app.core.redis import redis_manager

logger = logging.getLogger("redis_lease")

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class RedisLease:
    """A Redis lease that can only be renewed or released by its owner."""

    def __init__(self, key: str, ttl_seconds: int):
        self.key = key
        self.ttl_seconds = max(5, int(ttl_seconds))
        self.token = secrets.token_urlsafe(24)
        self.acquired = False

    async def acquire(self) -> bool:
        if not await redis_manager.check_connection():
            return False
        try:
            client = redis_manager.get_client()
            self.acquired = bool(
                await client.set(self.key, self.token, nx=True, ex=self.ttl_seconds)
            )
        except Exception as exc:
            redis_manager.mark_unavailable(exc, "lease acquire")
            self.acquired = False
        return self.acquired

    async def renew(self) -> bool:
        if not self.acquired or not await redis_manager.check_connection():
            self.acquired = False
            return False
        try:
            client = redis_manager.get_client()
            renewed = bool(
                await client.eval(
                    _RENEW_SCRIPT,
                    1,
                    self.key,
                    self.token,
                    self.ttl_seconds,
                )
            )
        except Exception as exc:
            redis_manager.mark_unavailable(exc, "lease renewal")
            renewed = False
        self.acquired = renewed
        return renewed

    async def release(self) -> None:
        if not self.acquired:
            return
        try:
            client = redis_manager.get_client()
            await client.eval(_RELEASE_SCRIPT, 1, self.key, self.token)
        except Exception as exc:
            redis_manager.mark_unavailable(exc, "lease release")
            logger.warning("Could not release Redis lease %s; it will expire: %s", self.key, exc)
        finally:
            self.acquired = False
