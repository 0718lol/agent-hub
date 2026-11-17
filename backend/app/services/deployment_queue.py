"""Redis Streams-backed persistent deployment queue."""

import asyncio
import json
import socket
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.core.redis import redis_manager

GROUP = "deployment-workers"
WORKER_HEARTBEAT_KEY = "agenthub:deployment:worker:heartbeat"


class DeploymentQueueUnavailable(RuntimeError):
    pass


class DeploymentAlreadyQueued(RuntimeError):
    pass


@dataclass
class DeploymentJob:
    id: str
    conversation_id: str
    user_id: str
    target: str
    tenant_id: str = ""
    action: str = "deploy"
    source_job_id: str = ""
    options: dict | None = None
    status: str = "queued"
    attempts: int = 0
    created_at: str = ""
    updated_at: str = ""
    log: str = ""
    url: str = ""
    result_type: str = ""
    provider: str = ""
    published: bool = False
    lifecycle: str = "active"
    stage: str = "queued"
    progress: int = 5
    log_entries: list[dict] | None = None
    cancel_requested: bool = False

    def __post_init__(self):
        now = datetime.now(UTC).isoformat()
        self.tenant_id = self.tenant_id or self.user_id
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now
        self.options = self.options or {}
        self.log_entries = self.log_entries or []

    def public_dict(self, *, include_logs: bool = True) -> dict:
        data = asdict(self)
        data.pop("options", None)
        if not include_logs:
            data.pop("log_entries", None)
        return data


async def _mirror_job_to_sql(job: DeploymentJob) -> None:
    try:
        from app.core.crud.deployments import sync_deployment_record

        await asyncio.to_thread(sync_deployment_record, asdict(job))
    except Exception:
        pass


async def _delete_job_from_sql(job_id: str) -> None:
    try:
        from app.core.crud.deployments import delete_deployment_record

        await asyncio.to_thread(delete_deployment_record, job_id)
    except Exception:
        pass


class DeploymentQueue:
    def __init__(self):
        self.stream = settings.deployment_queue
        self.consumer = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _status_key(job_id: str) -> str:
        return f"agenthub:deployment:status:{job_id}"

    @staticmethod
    def _lock_key(conversation_id: str) -> str:
        return f"agenthub:deployment:lock:{conversation_id}"

    @staticmethod
    def _cancel_key(job_id: str) -> str:
        return f"agenthub:deployment:cancel:{job_id}"

    @staticmethod
    def _user_index(user_id: str) -> str:
        return f"agenthub:deployments:user:{user_id}"

    @staticmethod
    def _global_index() -> str:
        return "agenthub:deployments:all"

    async def ensure_available(self):
        if not await redis_manager.check_connection():
            raise DeploymentQueueUnavailable("Redis 不可用，无法安全启动持久化发布任务")
        client = redis_manager.get_client()
        try:
            await client.xgroup_create(self.stream, GROUP, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise DeploymentQueueUnavailable("无法初始化发布任务队列") from exc
        return client

    async def enqueue(
        self,
        conversation_id: str,
        user_id: str,
        target: str,
        *,
        action: str = "deploy",
        source_job_id: str = "",
        options: dict | None = None,
    ) -> DeploymentJob:
        client = await self.ensure_available()
        if not await client.get(WORKER_HEARTBEAT_KEY):
            raise DeploymentQueueUnavailable("构建 Worker 未运行，请启动 deployment-worker 服务")
        job = DeploymentJob(
            id=uuid.uuid4().hex,
            conversation_id=conversation_id,
            user_id=user_id,
            target=target,
            action=action,
            source_job_id=source_job_id,
            options=options,
            log="任务已进入持久化队列",
            log_entries=[{
                "timestamp": datetime.now(UTC).isoformat(),
                "stage": "queued",
                "level": "info",
                "message": "任务已进入持久化队列，等待构建 Worker。",
                "progress": 5,
            }],
        )
        locked = await client.set(self._lock_key(conversation_id), job.id, nx=True, ex=2 * 60 * 60)
        if not locked:
            raise DeploymentAlreadyQueued("该项目已有构建任务正在排队或运行")
        payload = json.dumps(asdict(job), ensure_ascii=False)
        try:
            await client.set(self._status_key(job.id), payload, ex=settings.deployment_status_ttl)
            await client.xadd(self.stream, {"payload": payload}, maxlen=10_000, approximate=True)
            score = datetime.fromisoformat(job.created_at).timestamp()
            await client.zadd(self._user_index(user_id), {job.id: score})
            await client.zadd(self._global_index(), {job.id: score})
        except Exception:
            await client.delete(self._lock_key(conversation_id))
            raise
        await _mirror_job_to_sql(job)
        return job

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 50,
        conversation_id: str | None = None,
    ) -> list[DeploymentJob]:
        client = await self.ensure_available()
        ids = await client.zrevrange(self._user_index(user_id), 0, max(0, limit - 1))
        jobs: list[DeploymentJob] = []
        seen_ids: set[str] = set()
        if ids:
            values = await client.mget([self._status_key(job_id) for job_id in ids])
            for raw in values:
                if not raw:
                    continue
                job = DeploymentJob(**json.loads(raw))
                if job.action != "deploy":
                    continue
                if conversation_id and job.conversation_id != conversation_id:
                    continue
                seen_ids.add(job.id)
                jobs.append(job)
        if len(jobs) < limit:
            try:
                from app.core.crud.deployments import list_deployment_records

                sql_rows = await asyncio.to_thread(
                    list_deployment_records,
                    user_id,
                    conversation_id,
                    limit,
                    "deploy",
                )
                for row in sql_rows:
                    if row["id"] in seen_ids:
                        continue
                    jobs.append(
                        DeploymentJob(
                            id=row["id"],
                            conversation_id=row["conversation_id"],
                            user_id=row["user_id"],
                            tenant_id=row["tenant_id"],
                            target=row["target"],
                            action=row["action"],
                            source_job_id=row["source_job_id"],
                            status=row["status"],
                            stage=row["stage"],
                            progress=row["progress"],
                            url=row["url"],
                            result_type=row["result_type"],
                            provider=row["provider"],
                            published=row["published"],
                            lifecycle=row["lifecycle"],
                            log=row["log"],
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                        )
                    )
                    if len(jobs) >= limit:
                        break
            except Exception:
                pass
        return jobs[:limit]

    async def indexed_job_ids(self) -> list[str]:
        client = await self.ensure_available()
        return await client.zrange(self._global_index(), 0, -1)

    async def remove_history(self, job: DeploymentJob) -> None:
        client = await self.ensure_available()
        await client.delete(self._status_key(job.id))
        await client.zrem(self._user_index(job.user_id), job.id)
        await client.zrem(self._global_index(), job.id)
        await _delete_job_from_sql(job.id)

    async def heartbeat(self) -> None:
        client = await self.ensure_available()
        await client.set(WORKER_HEARTBEAT_KEY, self.consumer, ex=15)

    async def get(self, job_id: str) -> DeploymentJob | None:
        client = await self.ensure_available()
        raw = await client.get(self._status_key(job_id))
        if not raw:
            return None
        job = DeploymentJob(**json.loads(raw))
        job.cancel_requested = bool(await client.get(self._cancel_key(job_id)))
        return job

    async def update(self, job: DeploymentJob, **changes) -> DeploymentJob:
        client = await self.ensure_available()
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(UTC).isoformat()
        await client.set(
            self._status_key(job.id),
            json.dumps(asdict(job), ensure_ascii=False),
            ex=settings.deployment_status_ttl,
        )
        await _mirror_job_to_sql(job)
        return job

    async def update_progress(
        self,
        job: DeploymentJob,
        *,
        stage: str,
        progress: int,
        message: str,
        level: str = "info",
        status: str = "running",
    ) -> DeploymentJob:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "stage": stage,
            "level": level,
            "message": str(message)[:4_000],
            "progress": min(max(int(progress), 0), 100),
        }
        entries = [*(job.log_entries or []), entry][-300:]
        return await self.update(
            job,
            status=status,
            stage=stage,
            progress=entry["progress"],
            log=entry["message"],
            log_entries=entries,
        )

    async def read(self, block_ms: int = 5_000):
        client = await self.ensure_available()
        messages = await client.xreadgroup(
            GROUP, self.consumer, {self.stream: ">"}, count=1, block=block_ms
        )
        if not messages:
            return None
        _stream, entries = messages[0]
        message_id, fields = entries[0]
        return message_id, DeploymentJob(**json.loads(fields["payload"]))

    async def reclaim_stale(self, min_idle_ms: int = 15 * 60_000):
        client = await self.ensure_available()
        response = await client.xautoclaim(
            self.stream, GROUP, self.consumer, min_idle_ms, "0-0", count=1
        )
        entries = response[1] if len(response) > 1 else []
        if not entries:
            return None
        message_id, fields = entries[0]
        return message_id, DeploymentJob(**json.loads(fields["payload"]))

    async def acknowledge(self, message_id: str) -> None:
        client = await self.ensure_available()
        await client.xack(self.stream, GROUP, message_id)

    async def release_lock(self, job: DeploymentJob) -> None:
        client = await self.ensure_available()
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        await client.eval(script, 1, self._lock_key(job.conversation_id), job.id)

    async def request_cancel(self, job: DeploymentJob) -> DeploymentJob:
        client = await self.ensure_available()
        await client.set(
            self._cancel_key(job.id),
            "1",
            ex=settings.deployment_status_ttl,
        )
        job.cancel_requested = True
        return job

    async def is_cancel_requested(self, job_id: str) -> bool:
        client = await self.ensure_available()
        return bool(await client.get(self._cancel_key(job_id)))

    async def clear_cancel(self, job_id: str) -> None:
        client = await self.ensure_available()
        await client.delete(self._cancel_key(job_id))

    async def retry(self, message_id: str, job: DeploymentJob) -> None:
        client = await self.ensure_available()
        job.attempts += 1
        job.status = "queued"
        job.cancel_requested = False
        job.stage = "queued"
        job.progress = 5
        job.log = "任务重新进入队列，等待自动重试"
        job.log_entries = [*(job.log_entries or []), {
            "timestamp": datetime.now(UTC).isoformat(),
            "stage": "queued",
            "level": "warning",
            "message": job.log,
            "progress": 5,
        }][-300:]
        job.updated_at = datetime.now(UTC).isoformat()
        payload = json.dumps(asdict(job), ensure_ascii=False)
        await client.set(self._status_key(job.id), payload, ex=settings.deployment_status_ttl)
        await client.xadd(self.stream, {"payload": payload}, maxlen=10_000, approximate=True)
        await client.xack(self.stream, GROUP, message_id)
        await _mirror_job_to_sql(job)


deployment_queue = DeploymentQueue()
