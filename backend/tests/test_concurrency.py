"""Generation admission control regression tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.concurrency import GenerationAdmissionController


@pytest.fixture(autouse=True)
def offline_redis(monkeypatch):
    monkeypatch.setattr(
        "app.core.redis.redis_manager.check_connection",
        AsyncMock(return_value=False),
    )


@pytest.mark.asyncio
async def test_same_conversation_cannot_generate_twice():
    controller = GenerationAdmissionController(max_per_user=2)
    assert (await controller.acquire("user", "conv-1"))[0]
    accepted, reason = await controller.acquire("user", "conv-1")
    assert not accepted
    assert "正在生成" in reason
    await controller.release("user", "conv-1")
    assert (await controller.acquire("user", "conv-1"))[0]


@pytest.mark.asyncio
async def test_per_user_limit_does_not_block_another_user():
    controller = GenerationAdmissionController(max_per_user=2)
    assert (await controller.acquire("user-a", "a-1"))[0]
    assert (await controller.acquire("user-a", "a-2"))[0]
    assert not (await controller.acquire("user-a", "a-3"))[0]
    assert (await controller.acquire("user-b", "b-1"))[0]


@pytest.mark.asyncio
async def test_cancellation_and_terminal_status_survive_local_reconnect():
    controller = GenerationAdmissionController(max_per_user=1)
    assert (await controller.acquire("user-a", "conv-a"))[0]
    assert (await controller.get_status("conv-a"))["state"] == "running"

    await controller.request_cancel("conv-a")
    assert await controller.cancel_requested("conv-a")
    await controller.release("user-a", "conv-a", status="cancelled")

    assert not await controller.cancel_requested("conv-a")
    assert (await controller.get_status("conv-a"))["state"] == "cancelled"


@pytest.mark.asyncio
async def test_expired_distributed_lease_marks_generation_interrupted(monkeypatch):
    class StaleRedis:
        def __init__(self):
            self.status = {"state": "running"}

        async def hgetall(self, key):
            del key
            return dict(self.status)

        async def exists(self, key):
            del key
            return 0

        async def hset(self, key, mapping):
            del key
            self.status = dict(mapping)

        async def expire(self, key, ttl):
            del key, ttl

    client = StaleRedis()
    monkeypatch.setattr(
        "app.core.redis.redis_manager.check_connection",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr("app.core.redis.redis_manager.get_client", lambda: client)
    controller = GenerationAdmissionController(max_per_user=1)

    status = await controller.get_status("conv-stale")

    assert status["state"] == "interrupted"
    assert "lease expired" in status["reason"]


@pytest.mark.asyncio
async def test_redis_command_failure_falls_back_without_raising_in_development(monkeypatch):
    from app.core.config import settings
    from app.core.redis import redis_manager

    class BrokenRedis:
        def __getattr__(self, name):
            async def fail(*args, **kwargs):
                del args, kwargs
                raise ConnectionError(f"{name} failed")

            return fail

    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(redis_manager, "check_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(redis_manager, "get_client", lambda: BrokenRedis())
    monkeypatch.setattr(redis_manager, "mark_unavailable", MagicMock())
    controller = GenerationAdmissionController(max_per_user=1)

    accepted, reason = await controller.acquire("user-a", "conv-a")
    assert accepted and reason is None
    await controller.request_cancel("conv-a")
    assert await controller.cancel_requested("conv-a")
    assert (await controller.get_status("conv-a"))["state"] == "running"
    await controller.release("user-a", "conv-a", status="cancelled")
    assert (await controller.get_status("conv-a"))["state"] == "cancelled"
    assert redis_manager.mark_unavailable.call_count >= 4


@pytest.mark.asyncio
async def test_production_rejects_generation_when_coordination_is_offline(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "debug", False)
    controller = GenerationAdmissionController(max_per_user=1)

    accepted, reason = await controller.acquire("user-a", "conv-a")

    assert not accepted
    assert "协调服务" in reason
