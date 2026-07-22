"""Tests for deployment cancellation admission and worker finalization."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.main import cancel_deployment
from app.services.deployment_queue import DeploymentJob, deployment_queue
from app.workers import deployment_worker


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


@pytest.mark.asyncio
async def test_worker_does_not_execute_job_owned_by_another_worker(monkeypatch):
    job = DeploymentJob(
        id="a" * 32,
        conversation_id="tenant__api-client__conv__demo",
        user_id="api-client",
        target="web",
    )
    monkeypatch.setattr(
        deployment_worker.deployment_queue,
        "claim_execution",
        AsyncMock(return_value=False),
    )
    pipeline = AsyncMock()
    monkeypatch.setattr(deployment_worker, "run_deployment_pipeline", pipeline)

    await deployment_worker.process_job("1-0", job)

    pipeline.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_leaves_message_pending_after_execution_lease_loss(monkeypatch):
    job = DeploymentJob(
        id="b" * 32,
        conversation_id="tenant__api-client__conv__demo",
        user_id="api-client",
        target="web",
        snapshot_id="c" * 40,
    )
    lease_checked = asyncio.Event()

    async def lose_lease(_job):
        lease_checked.set()
        return False

    async def run_pipeline(*_args, cancelled, **_kwargs):
        await lease_checked.wait()
        await cancelled()

    monkeypatch.setattr(
        deployment_worker.deployment_queue,
        "claim_execution",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        deployment_worker.deployment_queue,
        "heartbeat_execution",
        lose_lease,
    )
    monkeypatch.setattr(
        deployment_worker.deployment_queue,
        "release_execution",
        AsyncMock(),
    )
    monkeypatch.setattr(
        deployment_worker.deployment_queue,
        "get",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(
        deployment_worker.deployment_queue,
        "is_cancel_requested",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        deployment_worker.deployment_queue,
        "update_progress",
        AsyncMock(return_value=job),
    )
    acknowledge = AsyncMock()
    monkeypatch.setattr(deployment_worker.deployment_queue, "acknowledge", acknowledge)
    monkeypatch.setattr(deployment_worker, "_broadcast", AsyncMock())
    monkeypatch.setattr(deployment_worker, "run_deployment_pipeline", run_pipeline)

    await deployment_worker.process_job("2-0", job)

    acknowledge.assert_not_awaited()
    deployment_worker.deployment_queue.release_execution.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_cancel_queued_job_keeps_lock_until_worker_finalizes(monkeypatch):
    job = DeploymentJob(
        id="c" * 32,
        conversation_id="tenant__api-client__conv__demo",
        user_id="api-client",
        target="apk",
    )
    get_job = AsyncMock(return_value=job)
    request_cancel = AsyncMock(return_value=job)
    release_lock = AsyncMock()
    monkeypatch.setattr(deployment_queue, "get", get_job)
    monkeypatch.setattr(deployment_queue, "request_cancel", request_cancel)
    monkeypatch.setattr(deployment_queue, "release_lock", release_lock)

    response = await cancel_deployment(job.id, _request())

    assert response == {"status": "cancellation_requested", "job_id": job.id}
    request_cancel.assert_awaited_once_with(job)
    release_lock.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_running_job_keeps_lock_until_worker_stops(monkeypatch):
    job = DeploymentJob(
        id="e" * 32,
        conversation_id="tenant__api-client__conv__demo",
        user_id="api-client",
        target="apk",
        status="running",
    )
    monkeypatch.setattr(deployment_queue, "get", AsyncMock(return_value=job))
    request_cancel = AsyncMock(return_value=job)
    release_lock = AsyncMock()
    monkeypatch.setattr(deployment_queue, "request_cancel", request_cancel)
    monkeypatch.setattr(deployment_queue, "release_lock", release_lock)

    response = await cancel_deployment(job.id, _request())

    assert response["status"] == "cancellation_requested"
    request_cancel.assert_awaited_once_with(job)
    release_lock.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_finalizes_job_cancelled_while_queued(monkeypatch):
    job = DeploymentJob(
        id="d" * 32,
        conversation_id="tenant__api-client__conv__demo",
        user_id="api-client",
        target="api",
    )
    update_progress = AsyncMock()

    async def persist_progress(target, **changes):
        target.status = changes["status"]
        target.log = changes["message"]
        return target

    update_progress.side_effect = persist_progress
    monkeypatch.setattr(deployment_worker.deployment_queue, "claim_execution", AsyncMock(return_value=True))
    monkeypatch.setattr(deployment_worker.deployment_queue, "heartbeat_execution", AsyncMock(return_value=True))
    monkeypatch.setattr(deployment_worker.deployment_queue, "release_execution", AsyncMock())
    monkeypatch.setattr(deployment_worker.deployment_queue, "get", AsyncMock(return_value=job))
    monkeypatch.setattr(deployment_worker.deployment_queue, "is_cancel_requested", AsyncMock(return_value=True))
    monkeypatch.setattr(deployment_worker.deployment_queue, "update_progress", update_progress)
    monkeypatch.setattr(deployment_worker.deployment_queue, "acknowledge", AsyncMock())
    monkeypatch.setattr(deployment_worker.deployment_queue, "release_lock", AsyncMock())
    monkeypatch.setattr(deployment_worker.deployment_queue, "clear_cancel", AsyncMock())
    broadcast = AsyncMock()
    monkeypatch.setattr(deployment_worker, "_broadcast", broadcast)
    run_pipeline = AsyncMock()
    monkeypatch.setattr(deployment_worker, "run_deployment_pipeline", run_pipeline)

    await deployment_worker.process_job("1-0", job)

    assert job.status == "cancelled"
    run_pipeline.assert_not_awaited()
    broadcast.assert_awaited_once_with(job, "cancelled", "任务在排队期间被用户取消")
    deployment_worker.deployment_queue.acknowledge.assert_awaited_once_with("1-0")
    deployment_worker.deployment_queue.release_lock.assert_awaited_once_with(job)
    deployment_worker.deployment_queue.clear_cancel.assert_awaited_once_with(job.id)
