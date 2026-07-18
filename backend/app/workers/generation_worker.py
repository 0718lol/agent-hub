"""Persistent generation worker. Run with: python -m app.workers.generation_worker"""

import asyncio
import contextlib
import logging
import signal

from app.core.concurrency import generation_admission
from app.core.config import settings
from app.core.llm_client import llm_client
from app.core.quality_gate import quality_gate
from app.core.redis import redis_manager
from app.core.tenant_settings import get_tenant_llm_client, get_tenant_quality_gate
from app.core.websocket import manager
from app.services.agent_orchestrator import (
    _stop_events,
    get_agents,
    run_target_agent_flow,
    run_user_message_flow,
)
from app.services.generation_queue import (
    GenerationJob,
    GenerationQueueUnavailable,
    generation_queue,
)
from app.services.generation_runner import run_admitted_flow
from app.tools.registry import reset_tool_tenant, set_tool_tenant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generation_worker")


async def _broadcast(job: GenerationJob, state: str, text: str = "") -> None:
    payload = {
        "type": "generating",
        "conversation_id": job.conversation_id,
        "is_generating": state in {"queued", "running", "cancelling"},
        "state": state,
        "job_id": job.id,
    }
    if text:
        payload["content"] = {"text": text}
    await manager.broadcast(job.conversation_id, payload)


async def _execute(job: GenerationJob) -> None:
    tenant_client = await asyncio.to_thread(get_tenant_llm_client, job.user_id)
    tenant_quality_gate = await asyncio.to_thread(
        get_tenant_quality_gate, job.user_id
    )
    client_token = llm_client.set_current(tenant_client)
    quality_token = quality_gate.set_current(tenant_quality_gate)
    tool_token = set_tool_tenant(job.user_id)
    try:
        agents = get_agents(job.conversation_id)
        if job.target_agent and job.target_agent in agents:
            flow = run_target_agent_flow(
                job.conversation_id,
                agents[job.target_agent],
                job.text,
            )
        else:
            flow = run_user_message_flow(
                job.conversation_id,
                job.text,
                job.target_agent or None,
            )
        await flow
    finally:
        reset_tool_tenant(tool_token)
        quality_gate.reset_current(quality_token)
        llm_client.reset_current(client_token)


async def _execution_heartbeat(job: GenerationJob, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            if not await generation_queue.heartbeat_execution(job):
                logger.error("Generation job execution lease was lost: %s", job.id)
                flow_stop = _stop_events.get(job.conversation_id)
                if flow_stop:
                    flow_stop.set()
                return
        except GenerationQueueUnavailable:
            pass
        await asyncio.sleep(max(5, generation_admission.lease_ttl // 3))


async def _wait_for_admission(job: GenerationJob) -> tuple[bool, str | None]:
    while True:
        if await generation_queue.is_cancel_requested(job.id):
            return False, "任务在等待执行资源时被用户取消"
        admitted, reason = await generation_admission.acquire(
            job.user_id, job.conversation_id
        )
        if admitted:
            return True, None
        if reason and ("正在生成" in reason or "最多同时运行" in reason):
            await asyncio.sleep(2)
            continue
        return False, reason


async def process_job(message_id: str, job: GenerationJob) -> None:
    if not await generation_queue.claim_execution(job):
        return
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _execution_heartbeat(job, heartbeat_stop),
        name=f"generation_job_heartbeat_{job.id}",
    )
    terminal = False
    try:
        saved_job = await generation_queue.get(job.id)
        if saved_job is not None:
            job = saved_job
        if job.status in {"completed", "cancelled", "failed"}:
            await generation_queue.finalize(
                message_id, job, job.status, job.error
            )
            terminal = True
            return

        if await generation_queue.is_cancel_requested(job.id):
            await generation_queue.finalize(
                message_id, job, "cancelled", "任务在排队期间被用户取消"
            )
            await _broadcast(job, "cancelled")
            terminal = True
            return

        admitted, reason = await _wait_for_admission(job)
        if not admitted:
            if await generation_queue.is_cancel_requested(job.id):
                await generation_queue.finalize(
                    message_id, job, "cancelled", reason or ""
                )
                await _broadcast(job, "cancelled")
                terminal = True
                return
            raise RuntimeError(reason or "无法获取生成执行租约")

        await generation_queue.update(job, status="running", error="")
        await _broadcast(job, "running")
        await run_admitted_flow(
            job.user_id,
            job.conversation_id,
            _execute(job),
        )
        status = (
            "cancelled"
            if await generation_queue.is_cancel_requested(job.id)
            else "completed"
        )
        await generation_queue.finalize(message_id, job, status)
        await _broadcast(job, status)
        terminal = True
    except Exception as exc:
        logger.exception("Generation job %s failed", job.id)
        if job.attempts < settings.generation_max_attempts:
            await generation_queue.retry(message_id, job, str(exc))
            await _broadcast(job, "queued", "生成 Worker 异常，任务已自动重试")
        else:
            await generation_queue.finalize(message_id, job, "failed", str(exc))
            await _broadcast(job, "failed", str(exc))
            terminal = True
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        with contextlib.suppress(GenerationQueueUnavailable):
            await generation_queue.release_execution(job)
        if not terminal:
            logger.info("Generation job %s returned to the queue", job.id)


async def _heartbeat_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await generation_queue.heartbeat()
        except GenerationQueueUnavailable:
            pass
        await asyncio.sleep(5)


async def run_worker(stop_event: asyncio.Event | None = None) -> None:
    from app.routers.adapters import load_saved_adapters

    load_saved_adapters()
    stop_event = stop_event or asyncio.Event()
    logger.info("Generation worker %s starting", generation_queue.consumer)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(stop_event))
    try:
        while not stop_event.is_set():
            try:
                item = await generation_queue.reclaim_stale()
                if item is None:
                    item = await generation_queue.read()
                if item:
                    await process_job(*item)
            except GenerationQueueUnavailable as exc:
                logger.warning("%s; retrying", exc)
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Generation worker loop failed; retrying")
                await asyncio.sleep(3)
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        await redis_manager.close()


def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for event in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(event, stop_event.set)
    try:
        loop.run_until_complete(run_worker(stop_event))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
