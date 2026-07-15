"""Tests for persistent deployment queue state and admission locks."""

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

    async def eval(self, _script, _count, key, expected):
        if self.values.get(key) == expected:
            self.values.pop(key, None)
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
async def test_cancel_request_is_visible_until_worker_clears_it(queue):
    instance, _redis = queue
    job = await instance.enqueue("tenant__u__conv__c", "u", "api")

    await instance.request_cancel(job)
    saved = await instance.get(job.id)

    assert saved.cancel_requested is True
    assert await instance.is_cancel_requested(job.id) is True

    await instance.clear_cancel(job.id)
    assert await instance.is_cancel_requested(job.id) is False
