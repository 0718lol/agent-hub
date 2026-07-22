"""Tests for persistent deployment queue state and admission locks."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.deployment_queue import (
    WORKER_HEARTBEAT_KEY,
    DeploymentAlreadyQueued,
    DeploymentQueue,
    DeploymentQueueUnavailable,
)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.entries = []
        self.zsets = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)

    async def xadd(self, stream, fields, **_kwargs):
        message_id = f"{len(self.entries) + 1}-0"
        self.entries.append((stream, message_id, fields))
        return message_id

    async def xack(self, *_args):
        return 1

    async def zadd(self, key, values):
        self.zsets.setdefault(key, {}).update(values)

    async def zrevrange(self, key, start, end):
        values = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1], reverse=True)
        return [item[0] for item in values[start:end + 1]]

    async def zrange(self, key, start, end):
        values = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1])
        stop = None if end == -1 else end + 1
        return [item[0] for item in values[start:stop]]

    async def zrem(self, key, member):
        self.zsets.get(key, {}).pop(member, None)

    async def mget(self, keys):
        return [self.values.get(key) for key in keys]

    async def eval(self, script, count, *args):
        keys = args[:count]
        values = args[count:]
        if "xadd" in script:
            if not self.values.get(keys[0]):
                return -1
            if keys[1] in self.values:
                return 0
            self.values[keys[1]] = values[0]
            self.values[keys[2]] = values[1]
            message_id = f"{len(self.entries) + 1}-0"
            self.entries.append((keys[3], message_id, {"payload": values[1]}))
            self.zsets.setdefault(keys[4], {})[values[0]] = float(values[4])
            self.zsets.setdefault(keys[5], {})[values[0]] = float(values[4])
            return 1
        if "local project_owner" in script:
            project_owner = self.values.get(keys[1])
            if project_owner and project_owner != values[1]:
                return 0
            self.values.setdefault(keys[1], values[1])
            if keys[0] in self.values:
                return 0
            self.values[keys[0]] = values[0]
            return 1
        if "expire" in script:
            if (
                self.values.get(keys[0]) == values[0]
                and self.values.get(keys[1]) == values[2]
            ):
                return 1
            return 0
        if self.values.get(keys[0]) == values[0]:
            self.values.pop(keys[0], None)
            return 1
        return 0


@pytest.fixture
def queue(monkeypatch):
    instance = DeploymentQueue()
    redis = FakeRedis()
    redis.values[WORKER_HEARTBEAT_KEY] = "worker-1"

    async def available():
        return redis

    monkeypatch.setattr(instance, "ensure_available", available)
    return instance, redis


@pytest.mark.asyncio
async def test_enqueue_persists_status_and_stream_message(queue):
    instance, redis = queue

    job = await instance.enqueue("tenant__u__conv__c", "u", "apk")

    assert job.status == "queued"
    assert await instance.get(job.id) == job
    assert redis.entries[0][0] == instance.stream


@pytest.mark.asyncio
async def test_execution_lease_prevents_duplicate_workers(queue, monkeypatch):
    first, redis = queue
    second = DeploymentQueue()

    async def available():
        return redis

    monkeypatch.setattr(second, "ensure_available", available)
    job = await first.enqueue(
        "tenant__u__conv__c",
        "u",
        "web",
        snapshot_id="a" * 40,
    )

    assert job.snapshot_id == "a" * 40
    assert await first.claim_execution(job) is True
    assert await second.claim_execution(job) is False
    assert await first.heartbeat_execution(job) is True
    assert await second.heartbeat_execution(job) is False

    await second.release_execution(job)
    assert await second.claim_execution(job) is False
    await first.release_execution(job)
    assert await second.claim_execution(job) is True


@pytest.mark.asyncio
async def test_only_one_job_per_conversation_can_be_active(queue):
    instance, _redis = queue
    first = await instance.enqueue("tenant__u__conv__c", "u", "web")

    with pytest.raises(DeploymentAlreadyQueued):
        await instance.enqueue("tenant__u__conv__c", "u", "api")

    await instance.release_lock(first)
    second = await instance.enqueue("tenant__u__conv__c", "u", "api")
    assert second.id != first.id


@pytest.mark.asyncio
async def test_retry_is_persistent_and_keeps_same_job_id(queue):
    instance, redis = queue
    job = await instance.enqueue("tenant__u__conv__c", "u", "api")

    await instance.retry("1-0", job)
    saved = await instance.get(job.id)

    assert saved.id == job.id
    assert saved.attempts == 1
    assert saved.status == "queued"
    assert len(redis.entries) == 2


@pytest.mark.asyncio
async def test_enqueue_rejects_when_no_worker_is_alive(queue):
    instance, redis = queue
    redis.values.pop(WORKER_HEARTBEAT_KEY)

    with pytest.raises(DeploymentQueueUnavailable, match="Worker 未运行"):
        await instance.enqueue("tenant__u__conv__c", "u", "web")


@pytest.mark.asyncio
async def test_history_is_tenant_scoped_and_hides_secret_options(queue):
    instance, _redis = queue
    first = await instance.enqueue(
        "tenant__u__conv__one", "u", "apk", options={"store_password": "encrypted"}
    )
    await instance.release_lock(first)
    await instance.enqueue("tenant__other__conv__two", "other", "web")

    history = await instance.list_for_user("u")

    assert [job.id for job in history] == [first.id]
    assert "options" not in history[0].public_dict()


@pytest.mark.asyncio
async def test_progress_is_persisted_as_bounded_structured_log(queue):
    instance, _redis = queue
    job = await instance.enqueue("tenant__u__conv__c", "u", "apk")

    await instance.update_progress(
        job,
        stage="build",
        progress=52,
        message="Gradle 正在构建",
    )
    saved = await instance.get(job.id)

    assert saved.stage == "build"
    assert saved.progress == 52
    assert saved.log == "Gradle 正在构建"
    assert saved.log_entries[-1]["stage"] == "build"
    assert saved.log_entries[-1]["message"] == "Gradle 正在构建"
    assert saved.public_dict()["log_entries"][-1]["progress"] == 52


@pytest.mark.asyncio
async def test_completion_persists_status_and_result_atomically(queue):
    instance, _redis = queue
    job = await instance.enqueue("tenant__u__conv__c", "u", "web")

    await instance.complete(
        job,
        message="发布成功",
        url="/uploads/result.zip",
        result_type="download",
        provider="artifact",
        published=False,
    )
    saved = await instance.get(job.id)

    assert saved.status == "success"
    assert saved.stage == "complete"
    assert saved.progress == 100
    assert saved.url == "/uploads/result.zip"
    assert saved.provider == "artifact"
    assert saved.log_entries[-1]["message"] == "发布成功"


@pytest.mark.asyncio
async def test_execution_claim_restores_expired_project_lock(queue):
    instance, redis = queue
    job = await instance.enqueue("tenant__u__conv__c", "u", "web")
    redis.values.pop(instance._lock_key(job.conversation_id))

    assert await instance.claim_execution(job) is True
    assert redis.values[instance._lock_key(job.conversation_id)] == job.id


@pytest.mark.asyncio
async def test_cancel_request_is_visible_until_worker_clears_it(queue):
    instance, _redis = queue
    job = await instance.enqueue("tenant__u__conv__c", "u", "api")

    await instance.request_cancel(job)
    saved = await instance.get(job.id)

    assert saved.cancel_requested is True
    assert await instance.is_cancel_requested(job.id) is True

    await instance.clear_cancel(job.id)
    assert await instance.is_cancel_requested(job.id) is False


@pytest.mark.asyncio
async def test_command_failure_is_reported_as_queue_unavailable(monkeypatch):
    from app.core.redis import redis_manager

    class BrokenRedis:
        async def eval(self, *args):
            del args
            raise ConnectionError("redis disconnected")

    instance = DeploymentQueue()

    async def available():
        return BrokenRedis()

    monkeypatch.setattr(instance, "ensure_available", available)
    monkeypatch.setattr(redis_manager, "mark_unavailable", MagicMock())

    with pytest.raises(DeploymentQueueUnavailable, match="原子写入任务"):
        await instance.enqueue("tenant__u__conv__c", "u", "web")

    redis_manager.mark_unavailable.assert_called_once()


@pytest.mark.asyncio
async def test_consumer_group_initialization_is_cached(monkeypatch):
    from app.core.redis import redis_manager

    class GroupRedis:
        def __init__(self):
            self.creates = 0

        async def xgroup_create(self, *args, **kwargs):
            del args, kwargs
            self.creates += 1

    client = GroupRedis()
    instance = DeploymentQueue()
    monkeypatch.setattr(redis_manager, "check_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(redis_manager, "get_client", lambda: client)

    assert await instance.ensure_available() is client
    assert await instance.ensure_available() is client
    assert client.creates == 1
