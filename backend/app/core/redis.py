import time
import logging
import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool
from app.core.config import settings

logger = logging.getLogger("redis_client")


class RedisManager:
    """Manages asynchronous Redis connections with high-availability memory fallback,
    connection pool, and performance-optimized status caching.
    """

    def __init__(self):
        self.redis_url = settings.redis_url
        self._client = None
        self._pool = None
        self._is_connected = None  # None: untried, True: connected, False: offline
        self._last_probe_time = 0.0
        self._probe_ttl = 10.0  # Cache connection status for 10 seconds to avoid network latency penalty

    def _ensure_pool(self):
        """Lazy initialization of the connection pool."""
        if self._pool is None:
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
                max_connections=20,
                retry_on_timeout=True,
            )
        return self._pool

    def get_client(self):
        """Lazy initialization of the aioredis client backed by a connection pool."""
        if self._client is None:
            pool = self._ensure_pool()
            self._client = aioredis.Redis(connection_pool=pool)
        return self._client

    async def check_connection(self) -> bool:
        """Ping the Redis server with a short timeout to see if it is online.
        Caches connection status for `_probe_ttl` seconds to avoid performance degradation.
        """
        now = time.time()

        # Return cached status if TTL has not expired
        if self._is_connected is not None:
            if now - self._last_probe_time < self._probe_ttl:
                return self._is_connected

        self._last_probe_time = now
        try:
            client = self.get_client()
            await client.ping()
            if self._is_connected is not True:
                logger.info(f"Successfully connected to Redis at {self.redis_url}")
            self._is_connected = True
            return True
        except Exception as e:
            if self._is_connected is not False:
                logger.warning(
                    f"Redis connection failed at {self.redis_url}. "
                    f"Falling back to local in-memory dictionaries. Error: {e}"
                )
            self._is_connected = False
            return False

    async def close(self):
        """Close the Redis client connection pool safely."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
        if self._pool:
            try:
                await self._pool.disconnect(inuse_connections=True)
            except Exception:
                pass
            self._pool = None
        self._is_connected = None
        self._last_probe_time = 0.0

    def get_status(self) -> dict:
        """返回当前 Redis 连接状态，供健康检查端点使用。"""
        return {
            "configured": bool(self.redis_url),
            "connected": self._is_connected is True,
            "last_probe": self._last_probe_time,
            "pool_size": self._pool.max_connections if self._pool else 0,
        }


redis_manager = RedisManager()
