"""Generation worker scheduling regression tests."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services.generation_queue import GenerationJob
from app.workers import generation_worker


@pytest.mark.asyncio
async def test_worker_processes_jobs_concurrently(monkeypatch):
    stop_event = asyncio.Event()
    release_jobs = asyncio.Event()
    both_started = asyncio.Event()
    started: set[str] = set()
    jobs = [
        ("1-0", GenerationJob("job-1", "conversation-1", "user-1", "first")),
        ("2-0", GenerationJob("job-2", "conversation-2", "user-2", "second")),
    ]

    class FakeQueue:
        consumer = "test-worker"

        async def heartbeat(self):
            return None

        async def reclaim_stale(self):
            return None

        async def read(self):
            if jobs:
                return jobs.pop(0)
            await stop_event.wait()
            return None

    async def fake_process(_message_id, job):
        started.add(job.id)
        if len(started) == 2:
            both_started.set()
        await release_jobs.wait()

    monkeypatch.setattr(settings, "generation_worker_concurrency", 2)
    monkeypatch.setattr(generation_worker, "generation_queue", FakeQueue())
    monkeypatch.setattr(generation_worker, "process_job", fake_process)
    monkeypatch.setattr(generation_worker, "_load_saved_adapters", lambda: None)
    monkeypatch.setattr(generation_worker.redis_manager, "close", AsyncMock())

    worker = asyncio.create_task(generation_worker.run_worker(stop_event))
    await asyncio.wait_for(both_started.wait(), timeout=1)
    assert started == {"job-1", "job-2"}

    release_jobs.set()
    stop_event.set()
    await asyncio.wait_for(worker, timeout=1)
