"""Redis 缓存抽象层 — 统一的缓存读写接口，带内存回退与优雅降级。

所有缓存操作静默失败，Redis 不可用时自动降级为内存缓存或直查数据库，
绝不影响主业务流程。

使用方式：
    from app.core.cache import cache

    # 写入缓存
    await cache.set_json("key", {"data": "value"}, ttl=60)

    # 读取缓存
    data = await cache.get_json("key")

    # 删除缓存
    await cache.delete("key")

    # 批量失效（按前缀）
    await cache.delete_pattern("msg:conv_123:*")
"""
import json
import time
import logging
from typing import Optional, Any

logger = logging.getLogger("redis_cache")


class _MemoryFallback:
    """简易内存 LRU 缓存，Redis 不可用时的降级方案。
    仅用于单进程内缓存热数据，不跨进程共享。
    """

    def __init__(self, max_size: int = 512):
        self._store: dict[str, tuple[str, float]] = {}  # key -> (value, expire_at)
        self._max_size = max_size

    def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expire_at = entry
        if expire_at and time.time() > expire_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl: int = 60):
        # 简单淘汰：超过上限时清空过期项
        if len(self._store) >= self._max_size:
            now = time.time()
            self._store = {k: v for k, v in self._store.items() if v[1] == 0 or v[1] > now}
            if len(self._store) >= self._max_size:
                self._store.clear()
        expire_at = time.time() + ttl if ttl > 0 else 0
        self._store[key] = (value, expire_at)

    def delete(self, key: str):
        self._store.pop(key, None)

    def delete_pattern(self, pattern: str):
        """简单前缀匹配删除，仅支持 'prefix*' 格式。"""
        prefix = pattern.rstrip("*")
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            self._store.pop(k, None)


class RedisCache:
    """Redis 缓存层，带内存回退和优雅降级。

    设计原则：
    - 读 miss 时返回 None，调用方负责回源查 DB
    - 写操作静默失败，不影响主流程
    - Redis 不可用时自动降级到内存缓存
    """

    def __init__(self):
        self._memory = _MemoryFallback()

    def _get_redis(self):
        """延迟导入 redis_manager，避免循环依赖。"""
        from app.core.redis import redis_manager
        return redis_manager

    async def get(self, key: str) -> Optional[str]:
        """读取缓存，Redis 不可用时回退到内存缓存。"""
        rm = self._get_redis()
        if await rm.check_connection():
            try:
                client = rm.get_client()
                value = await client.get(key)
                if value is not None:
                    return value
                return None
            except Exception as e:
                logger.debug(f"Redis GET 失败 [{key}]: {e}，降级到内存缓存")
                rm._is_connected = False

        # 内存缓存回退
        return self._memory.get(key)

    async def set(self, key: str, value: str, ttl: int = 60):
        """写入缓存，同时更新内存缓存作为降级备份。"""
        # 始终更新内存缓存（保证降级可用）
        self._memory.set(key, value, ttl)

        rm = self._get_redis()
        if await rm.check_connection():
            try:
                client = rm.get_client()
                if ttl > 0:
                    await client.set(key, value, ex=ttl)
                else:
                    await client.set(key, value)
            except Exception as e:
                logger.debug(f"Redis SET 失败 [{key}]: {e}")
                rm._is_connected = False

    async def delete(self, key: str):
        """删除单个缓存键。"""
        self._memory.delete(key)

        rm = self._get_redis()
        if await rm.check_connection():
            try:
                client = rm.get_client()
                await client.delete(key)
            except Exception as e:
                logger.debug(f"Redis DEL 失败 [{key}]: {e}")
                rm._is_connected = False

    async def delete_pattern(self, pattern: str):
        """按模式批量删除缓存键。

        Redis 使用 SCAN + 匹配，内存缓存使用前缀匹配。
        """
        self._memory.delete_pattern(pattern)

        rm = self._get_redis()
        if await rm.check_connection():
            try:
                client = rm.get_client()
                # 使用 SCAN 迭代删除，避免 KEYS 阻塞
                cursor = 0
                while True:
                    cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
                    if keys:
                        await client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.debug(f"Redis DEL_PATTERN 失败 [{pattern}]: {e}")
                rm._is_connected = False

    async def get_json(self, key: str) -> Optional[Any]:
        """读取 JSON 缓存，自动反序列化。"""
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # 缓存数据损坏，删除之
            await self.delete(key)
            return None

    async def set_json(self, key: str, value: Any, ttl: int = 60):
        """写入 JSON 缓存，自动序列化。"""
        try:
            raw = json.dumps(value, ensure_ascii=False)
            await self.set(key, raw, ttl)
        except (TypeError, ValueError) as e:
            logger.debug(f"JSON 序列化失败 [{key}]: {e}")


# 全局单例
cache = RedisCache()
