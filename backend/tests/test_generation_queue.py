"""Persistent generation queue regression tests."""

from unittest.mock import AsyncMock

import pytest

from app.core.concurrency import generation_admission
from app.services.generation_queue import (
    WORKER_HEARTBEAT_KEY,
    GenerationAlreadyQueued,
    GenerationQueue,
    GenerationQueueUnavailable,
)


class FakeRedis:
    def __init__(self):
        self.values = {WORKER_HEARTBEAT_KEY: "worker-1"}
        self.entries = []

    async def set(self, key, value, ex=None, nx=False):
        del ex
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

    async def xdel(self, *_args):
        return 1

    async def eval(self, _script, _count, key, *args):
        expected = args[0]
        if self.values.get(key) == expected:
            self.values.pop(key, None)
            return 1
        return 0


@pytest.fixture
def queue(monkeypatch):
    instance = GenerationQueue()
    redis = FakeRedis()

    async def available():
        return redis

    monkeypatch.setattr(instance, "ensure_available", available)
    monkeypatch.setattr(generation_admission, "set_status", AsyncMock())
    return instance, redis


@pytest.mark.asyncio
async def test_enqueue_persists_prompt_and_queue_state(queue):
    instance, redis = queue

    job = await instance.enqueue(
        "tenant__u__conv__c",
        "u",
        "生成一个待办应用",
        "agent_frontend",
    )

    saved = await instance.get(job.id)
    assert saved == job
    assert saved.text == "生成一个待办应用"
    assert redis.entries[0][0] == instance.stream
    status_call = generation_admission.set_status.await_args
    assert status_call.args == (job.conversation_id, "queued")
    assert status_call.kwargs["user_id"] == "u"
    assert status_call.kwargs["job_id"] == job.id
    assert isinstance(status_call.kwargs["started_at"], int)


@pytest.mark.asyncio
async def test_only_one_generation_job_per_conversation(queue):
    instance, _redis = queue
    await instance.enqueue("tenant__u__conv__c", "u", "first")

    with pytest.raises(GenerationAlreadyQueued):
        await instance.enqueue("tenant__u__conv__c", "u", "second")


@pytest.mark.asyncio
async def test_enqueue_requires_live_worker(queue):
    instance, redis = queue
    redis.values.pop(WORKER_HEARTBEAT_KEY)

    with pytest.raises(GenerationQueueUnavailable, match="Worker 未运行"):
        await instance.enqueue("tenant__u__conv__c", "u", "prompt")


@pytest.mark.asyncio
async def test_cancel_and_finalize_release_conversation_lock(queue):
    instance, redis = queue
    job = await instance.enqueue("tenant__u__conv__c", "u", "prompt")

    assert await instance.request_cancel_by_conversation(job.conversation_id)
    assert await instance.is_cancel_requested(job.id)

    await instance.finalize("1-0", job, "cancelled")

    assert not await instance.is_cancel_requested(job.id)
    second = await instance.enqueue(job.conversation_id, "u", "retry later")
    assert second.id != job.id


@pytest.mark.asyncio
async def test_retry_keeps_job_identity_and_persists_attempt(queue):
    instance, redis = queue
    job = await instance.enqueue("tenant__u__conv__c", "u", "prompt")

    await instance.retry("1-0", job, "worker restarted")
    saved = await instance.get(job.id)

    assert saved.attempts == 1
    assert saved.status == "queued"
    assert saved.error == "worker restarted"
    assert len(redis.entries) == 2
