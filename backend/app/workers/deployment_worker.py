"""Persistent deployment worker. Run with: python -m app.workers.deployment_worker"""

import asyncio
import contextlib
import json
import logging
import signal
import time
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.file_storage import FileStorageManager
from app.core.redis import redis_manager
from app.core.websocket import manager
from app.services.deployment import (
    DeploymentCancelled,
    DeploymentError,
    DeploymentResult,
    run_deployment_pipeline,
)
from app.services.deployment_queue import (
    DeploymentJob,
    DeploymentQueueUnavailable,
    deployment_queue,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deployment_worker")


class DeploymentExecutionLeaseLost(DeploymentCancelled):
    """The worker no longer owns this deployment's external side effects."""


async def _broadcast(job: DeploymentJob, status: str, log: str, **extra) -> None:
    await manager.broadcast(job.conversation_id, {
        "type": "deploy_status",
        "conversation_id": job.conversation_id,
        "status": status,
        "log": log,
        "job_id": job.id,
        "stage": job.stage,
        "progress": job.progress,
        **extra,
    })


async def _register_runtime(job: DeploymentJob, result: DeploymentResult) -> None:
    if not result.runtime_url:
        return
    client = redis_manager.get_client()
    mapping_key = f"agenthub:published:{job.id}"
    conversation_key = f"agenthub:published:conversation:{job.conversation_id}"
    current_job_key = f"agenthub:published:current:{job.conversation_id}"
    previous_job_id = await client.get(current_job_key)
    mapping = json.dumps({
        "runtime_url": result.runtime_url,
        "container_name": result.container_name,
        "conversation_id": job.conversation_id,
        "user_id": job.user_id,
    })
    await client.set(mapping_key, mapping)
    await client.set(conversation_key, result.container_name)
    await client.set(current_job_key, job.id)
    if previous_job_id and previous_job_id != job.id:
        previous = await deployment_queue.get(previous_job_id)
        if previous:
            await deployment_queue.update(previous, lifecycle="superseded")


async def _register_artifact(job: DeploymentJob, result: DeploymentResult) -> str:
    """Return a capability URL for a tenant-owned build artifact."""
    if not result.url.startswith("/uploads/"):
        return result.url
    file_id = Path(result.url).name
    if not file_id.startswith(f"tenantfile__{job.user_id}__"):
        raise DeploymentError("构建产物不属于当前用户，已拒绝发布")
    if not FileStorageManager.exists(file_id):
        raise DeploymentError("构建产物不存在，无法创建分享链接")
    mapping = json.dumps({
        "file_id": file_id,
        "conversation_id": job.conversation_id,
        "user_id": job.user_id,
    })
    await redis_manager.get_client().set(
        f"agenthub:published-artifact:{job.id}",
        mapping,
        ex=settings.deployment_status_ttl,
    )
    return f"/published-artifacts/{job.id}"


async def _run_lifecycle_action(job: DeploymentJob) -> DeploymentResult:
    from app.services.deployment import _container_exists, _run_docker_command
    source = await deployment_queue.get(job.source_job_id)
    if not source or source.user_id != job.user_id:
        raise DeploymentError("找不到可操作的历史发布记录")
    client = redis_manager.get_client()
    mapping_key = f"agenthub:published:{source.id}"
    raw = await client.get(mapping_key)
    if not raw:
        raise DeploymentError("该 API 发布实例已经被清理")
    mapping = json.loads(raw)
    container_name = mapping.get("container_name", "")
    if job.action == "offline":
        if container_name and await _container_exists(container_name):
            await _run_docker_command(["docker", "stop", container_name], 30, "下线 API")
        current_key = f"agenthub:published:current:{source.conversation_id}"
        if await client.get(current_key) == source.id:
            await client.delete(current_key)
            await client.delete(f"agenthub:published:conversation:{source.conversation_id}")
        await deployment_queue.update(source, lifecycle="offline")
        return DeploymentResult(
            url=source.url, provider="docker-runtime", target="api",
            result_type="action", published=False,
        )
    if not container_name or not await _container_exists(container_name):
        raise DeploymentError("历史 API 容器已被清理，无法回滚")
    await _run_docker_command(["docker", "start", container_name], 30, "恢复历史 API 容器")
    await client.set(f"agenthub:published:conversation:{source.conversation_id}", container_name)
    current_key = f"agenthub:published:current:{source.conversation_id}"
    previous_job_id = await client.get(current_key)
    if previous_job_id and previous_job_id != source.id:
        previous = await deployment_queue.get(previous_job_id)
        if previous:
            await deployment_queue.update(previous, lifecycle="superseded")
    await client.set(current_key, source.id)
    await deployment_queue.update(source, lifecycle="active")
    return DeploymentResult(
        url=source.url, provider="docker-runtime", target="api",
        result_type="site", published=True,
    )


async def _remove_deployment(job: DeploymentJob) -> None:
    from app.services.deployment import _container_exists, _run_docker_command
    client = redis_manager.get_client()
    raw = await client.get(f"agenthub:published:{job.id}")
    if raw:
        container_name = json.loads(raw).get("container_name", "")
        if container_name and await _container_exists(container_name):
            await _run_docker_command(["docker", "rm", "-f", container_name], 30, "清理过期容器")
        await client.delete(f"agenthub:published:{job.id}")
        current_key = f"agenthub:published:current:{job.conversation_id}"
        if await client.get(current_key) == job.id:
            await client.delete(current_key)
            await client.delete(f"agenthub:published:conversation:{job.conversation_id}")
        try:
            await _run_docker_command(
                ["docker", "image", "rm", "-f", f"agenthub-generated-api:{job.id[:16]}"],
                30,
                "清理过期 API 镜像",
            )
        except DeploymentError:
            pass
    artifact_key = f"agenthub:published-artifact:{job.id}"
    artifact_raw = await client.get(artifact_key)
    file_id = ""
    if artifact_raw:
        file_id = json.loads(artifact_raw).get("file_id", "")
        await client.delete(artifact_key)
    elif job.url.startswith("/uploads/"):
        file_id = Path(job.url).name
    if file_id.startswith(f"tenantfile__{job.user_id}__"):
        FileStorageManager.delete(file_id)
    await deployment_queue.remove_history(job)


async def cleanup_deployments(user_id: str | None = None) -> int:
    jobs = []
    for job_id in await deployment_queue.indexed_job_ids():
        job = await deployment_queue.get(job_id)
        if job and job.action == "deploy" and (not user_id or job.user_id == user_id):
            jobs.append(job)
    jobs.sort(key=lambda item: item.created_at, reverse=True)
    cutoff = time.time() - settings.deployment_retention_days * 24 * 60 * 60
    per_user = {}
    remove = []
    for job in jobs:
        bucket = per_user.setdefault(job.user_id, [])
        bucket.append(job)
        created = datetime.fromisoformat(job.created_at).timestamp()
        if created < cutoff or len(bucket) > settings.deployment_max_per_user:
            remove.append(job)
    for job in remove:
        await _remove_deployment(job)
    return len(remove)


async def _cleanup_cancelled_result(job: DeploymentJob, result: DeploymentResult) -> None:
    if result.container_name:
        from app.services.deployment import _container_exists, _run_docker_command
        if await _container_exists(result.container_name):
            await _run_docker_command(
                ["docker", "rm", "-f", result.container_name],
                30,
                "清理已取消的 API 容器",
            )
    if result.url.startswith("/uploads/"):
        file_id = Path(result.url).name
        if file_id.startswith(f"tenantfile__{job.user_id}__"):
            FileStorageManager.delete(file_id)


async def _execution_heartbeat(
    job: DeploymentJob,
    stop_event: asyncio.Event,
    lease_lost: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            renewed = await deployment_queue.heartbeat_execution(job)
        except DeploymentQueueUnavailable:
            renewed = False
        if not renewed:
            logger.error("Deployment execution lease was lost: %s", job.id)
            lease_lost.set()
            return
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=max(5, settings.deployment_lease_ttl // 3),
            )
        except asyncio.TimeoutError:
            pass


async def process_job(message_id: str, job: DeploymentJob) -> None:
    if not await deployment_queue.claim_execution(job):
        return
    heartbeat_stop = asyncio.Event()
    lease_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _execution_heartbeat(job, heartbeat_stop, lease_lost),
        name=f"deployment_job_heartbeat_{job.id}",
    )

    async def cancelled() -> bool:
        if lease_lost.is_set():
            raise DeploymentExecutionLeaseLost(
                "发布任务执行租约已失效，当前 Worker 已停止构建"
            )
        try:
            return await deployment_queue.is_cancel_requested(job.id)
        except DeploymentQueueUnavailable:
            return False

    async def progress(stage: str, message: str, percent: int) -> None:
        await deployment_queue.update_progress(
            job,
            stage=stage,
            progress=percent,
            message=message,
        )
        await _broadcast(job, "running", message)

    terminal = False
    try:
        saved_job = await deployment_queue.get(job.id)
        if saved_job is not None:
            job = saved_job
        if job.status in {"success", "failed", "cancelled"}:
            terminal = True
            return
        if await cancelled():
            raise DeploymentCancelled("任务在排队期间被用户取消")
        await deployment_queue.update_progress(
            job,
            stage="generate",
            progress=12,
            message="构建 Worker 已领取任务，正在读取生成项目。",
        )
        await _broadcast(job, "running", "构建 Worker 已领取任务，开始执行隔离流水线...")
        if job.action in {"rollback", "offline"}:
            result = await _run_lifecycle_action(job)
        elif job.action == "cleanup":
            removed = await cleanup_deployments(job.user_id)
            result = DeploymentResult(
                url="", provider="cleanup", target="maintenance",
                result_type="action", published=True,
            )
            await progress("complete", f"清理完成，共删除 {removed} 条过期发布记录及关联资源。", 100)
        else:
            result = await run_deployment_pipeline(
                job.conversation_id,
                user_id=job.user_id,
                target=job.target,
                token=settings.netlify_token,
                site_id=settings.netlify_site_id,
                progress=progress,
                deployment_id=job.id,
                snapshot_id=job.snapshot_id,
                options=job.options,
                cancelled=cancelled,
            )
        async def ensure_result_is_owned() -> None:
            try:
                was_cancelled = await cancelled()
            except DeploymentExecutionLeaseLost:
                await _cleanup_cancelled_result(job, result)
                raise
            if was_cancelled:
                await _cleanup_cancelled_result(job, result)
                raise DeploymentCancelled("构建已被用户取消")

        await ensure_result_is_owned()
        await _register_runtime(job, result)
        public_url = await _register_artifact(job, result)
        await ensure_result_is_owned()
        if job.action == "cleanup":
            log = "过期资源清理完成"
        elif job.action == "offline":
            log = "API 已下线"
        elif job.action == "rollback":
            log = "历史版本已恢复"
        else:
            log = "发布成功" if result.result_type in {"site", "miniprogram"} else "构建产物已就绪"
        await deployment_queue.complete(
            job,
            message=log,
            url=public_url,
            result_type=result.result_type,
            provider=result.provider,
            published=result.published,
        )
        terminal = True
        try:
            await _broadcast(
                job,
                "success",
                f"{log}：{public_url}",
                url=public_url,
                target=result.target,
                provider=result.provider,
                result_type=result.result_type,
                published=result.published,
            )
        except Exception:
            logger.exception("Failed to broadcast completed deployment %s", job.id)
    except DeploymentExecutionLeaseLost as exc:
        logger.warning("%s: %s", exc, job.id)
    except DeploymentCancelled as exc:
        await deployment_queue.update_progress(
            job,
            stage=job.stage,
            progress=job.progress,
            message=str(exc),
            level="warning",
            status="cancelled",
        )
        await _broadcast(job, "cancelled", str(exc))
        terminal = True
    except DeploymentError as exc:
        await deployment_queue.update_progress(
            job,
            stage=job.stage,
            progress=job.progress,
            message=str(exc),
            level="error",
            status="failed",
        )
        await _broadcast(job, "failed", str(exc))
        terminal = True
    except Exception as exc:
        logger.exception("Unexpected deployment failure for %s", job.id)
        if job.attempts < 2:
            await deployment_queue.retry(message_id, job)
            await _broadcast(job, "running", f"Worker 异常，任务将在队列中自动重试：{exc}")
        else:
            await deployment_queue.update_progress(
                job,
                stage=job.stage,
                progress=job.progress,
                message="Worker 连续失败，已停止重试",
                level="error",
                status="failed",
            )
            await _broadcast(job, "failed", "Worker 连续失败，已停止重试")
            terminal = True
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        with contextlib.suppress(DeploymentQueueUnavailable):
            await deployment_queue.release_execution(job)
        if terminal:
            try:
                await deployment_queue.acknowledge(message_id)
                await deployment_queue.release_lock(job)
                await deployment_queue.clear_cancel(job.id)
            except Exception:
                logger.exception("Failed to finalize terminal deployment %s", job.id)


async def _heartbeat_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await deployment_queue.heartbeat()
        except DeploymentQueueUnavailable:
            pass
        await asyncio.sleep(5)


async def _cleanup_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await cleanup_deployments()
        except Exception:
            logger.exception("Scheduled deployment cleanup failed")
        await asyncio.sleep(60 * 60)


async def run_worker(stop_event: asyncio.Event | None = None) -> None:
    settings.validate_deployment_worker_security()
    stop_event = stop_event or asyncio.Event()
    logger.info("Deployment worker %s starting", deployment_queue.consumer)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(stop_event))
    cleanup_task = asyncio.create_task(_cleanup_loop(stop_event))
    try:
        while not stop_event.is_set():
            try:
                item = await deployment_queue.reclaim_stale()
                if item is None:
                    item = await deployment_queue.read()
                if item:
                    await process_job(*item)
            except DeploymentQueueUnavailable as exc:
                logger.warning("%s; retrying", exc)
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker loop failed; retrying")
                await asyncio.sleep(3)
    finally:
        heartbeat_task.cancel()
        cleanup_task.cancel()
        await asyncio.gather(heartbeat_task, cleanup_task, return_exceptions=True)
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
