"""Cross-instance scheduler coordination tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from app.core.database import (
    claim_cron_task,
    create_conversation,
    get_cron_tasks,
    save_cron_task,
    update_cron_task_status,
)


def test_cron_task_can_only_be_claimed_once():
    create_conversation("conv-cron", "single", "Cron", "", "agent_pm")
    save_cron_task(
        "cron-1",
        "conv-cron",
        "agent_pm",
        "run",
        60,
        next_run=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
    )

    assert claim_cron_task("cron-1")
    assert not claim_cron_task("cron-1")


async def test_only_one_scheduler_acquires_the_leader_lease(monkeypatch):
    from unittest.mock import AsyncMock

    from app.services import daemon_scheduler as scheduler_module

    class FakeLease:
        held = False

        def __init__(self, key, ttl_seconds):
            self.key = key
            self.ttl_seconds = ttl_seconds
            self.acquired = False

        async def acquire(self):
            if type(self).held:
                return False
            type(self).held = True
            self.acquired = True
            return True

        async def renew(self):
            return self.acquired

    monkeypatch.setattr(scheduler_module, "RedisLease", FakeLease)
    monkeypatch.setattr(
        "app.core.redis.redis_manager.check_connection",
        AsyncMock(return_value=True),
    )
    first = scheduler_module.DaemonScheduler()
    second = scheduler_module.DaemonScheduler()

    assert await first._ensure_leader()
    assert not await second._ensure_leader()


async def test_new_leader_preserves_tasks_with_live_execution_leases(monkeypatch):
    from app.services import daemon_scheduler as scheduler_module

    create_conversation("conv-recover", "single", "Cron", "", "agent_pm")
    for task_id in ("cron-live", "cron-stale"):
        save_cron_task(task_id, "conv-recover", "agent_pm", "run", 60)
        update_cron_task_status(task_id, "running")

    scheduler = scheduler_module.DaemonScheduler()
    live_key = scheduler._execution_key("cron-live")

    class LeaseRedis:
        async def exists(self, key):
            return int(key == live_key)

    monkeypatch.setattr(
        "app.core.redis.redis_manager.get_client",
        lambda: LeaseRedis(),
    )
    monkeypatch.setattr(
        "app.core.redis.redis_manager.check_connection",
        AsyncMock(return_value=True),
    )

    await scheduler._recover_after_leadership("2026-07-17 12:00:00")
    states = {task["id"]: task["status"] for task in get_cron_tasks()}

    assert states["cron-live"] == "running"
    assert states["cron-stale"] == "active"


async def test_local_scheduler_recovery_does_not_require_redis(monkeypatch):
    from app.services import daemon_scheduler as scheduler_module

    create_conversation("conv-local-recover", "single", "Cron", "", "agent_pm")
    save_cron_task("cron-local-recover", "conv-local-recover", "agent_pm", "run", 60)
    update_cron_task_status("cron-local-recover", "running")
    monkeypatch.setattr(
        "app.core.redis.redis_manager.check_connection",
        AsyncMock(return_value=False),
    )

    scheduler = scheduler_module.DaemonScheduler()
    await scheduler._recover_after_leadership("2026-07-18 12:00:00")

    state = next(
        item["status"]
        for item in get_cron_tasks()
        if item["id"] == "cron-local-recover"
    )
    assert state == "active"


async def test_redis_lease_command_failures_are_contained(monkeypatch):
    from app.core.redis import redis_manager
    from app.core.redis_lease import RedisLease

    class BrokenRedis:
        async def set(self, *args, **kwargs):
            del args, kwargs
            raise ConnectionError("redis disconnected")

        async def eval(self, *args):
            del args
            raise ConnectionError("redis disconnected")

    monkeypatch.setattr(redis_manager, "check_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(redis_manager, "get_client", lambda: BrokenRedis())
    monkeypatch.setattr(redis_manager, "mark_unavailable", MagicMock())
    lease = RedisLease("lease:test", 30)

    assert not await lease.acquire()
    lease.acquired = True
    assert not await lease.renew()
    lease.acquired = True
    await lease.release()

    assert not lease.acquired
    assert redis_manager.mark_unavailable.call_count == 3


async def test_claimed_task_returns_to_queue_when_production_redis_is_offline(monkeypatch):
    from app.core.config import settings
    from app.services import daemon_scheduler as scheduler_module

    create_conversation("conv-offline", "single", "Cron", "", "agent_pm")
    save_cron_task("cron-offline", "conv-offline", "agent_pm", "run", 60)
    update_cron_task_status("cron-offline", "running")
    task = next(item for item in get_cron_tasks() if item["id"] == "cron-offline")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(
        "app.core.redis.redis_manager.check_connection",
        AsyncMock(return_value=False),
    )

    await scheduler_module.DaemonScheduler()._run_task(task, claimed=True)

    state = next(
        item["status"] for item in get_cron_tasks() if item["id"] == "cron-offline"
    )
    assert state == "active"
