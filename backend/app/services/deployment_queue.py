"""Redis Streams-backed persistent deployment queue."""

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
    action: str = "deploy"
    source_job_id: str = ""
    snapshot_id: str = ""
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


class DeploymentQueue:
    def __init__(self):
        self.stream = settings.deployment_queue
        self.consumer = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._group_ready = False

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
    def _execution_key(job_id: str) -> str:
        return f"agenthub:deployment:execution:{job_id}"

    @staticmethod
    def _user_index(user_id: str) -> str:
        return f"agenthub:deployments:user:{user_id}"

    @staticmethod
    def _global_index() -> str:
        return "agenthub:deployments:all"

    async def _call(self, operation: str, awaitable):
        try:
            return await awaitable
        except DeploymentQueueUnavailable:
            raise
        except Exception as exc:
            if "NOGROUP" in str(exc):
                self._group_ready = False
            redis_manager.mark_unavailable(exc, f"deployment queue {operation}")
            raise DeploymentQueueUnavailable(
                f"发布队列{operation}失败，请稍后重试"
            ) from exc

    async def ensure_available(self):
        if not await redis_manager.check_connection():
            raise DeploymentQueueUnavailable(
                "Redis 不可用，无法安全启动持久化发布任务；请先启动 Redis 和构建 Worker"
            )
        client = redis_manager.get_client()
        if self._group_ready:
            return client
        try:
            await client.xgroup_create(self.stream, GROUP, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                redis_manager.mark_unavailable(exc, "deployment queue initialization")
                raise DeploymentQueueUnavailable("无法初始化发布任务队列") from exc
        self._group_ready = True
        return client

    async def enqueue(
        self,
        conversation_id: str,
        user_id: str,
        target: str,
        *,
        action: str = "deploy",
        source_job_id: str = "",
        snapshot_id: str = "",
        options: dict | None = None,
    ) -> DeploymentJob:
        client = await self.ensure_available()
        if not await self._call("读取 Worker 心跳", client.get(WORKER_HEARTBEAT_KEY)):
            raise DeploymentQueueUnavailable("构建 Worker 未运行，请启动 deployment-worker 服务")
        job = DeploymentJob(
            id=uuid.uuid4().hex,
            conversation_id=conversation_id,
            user_id=user_id,
            target=target,
            action=action,
            source_job_id=source_job_id,
            snapshot_id=snapshot_id,
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
        locked = await self._call(
            "获取项目锁",
            client.set(
                self._lock_key(conversation_id),
                job.id,
                nx=True,
                ex=2 * 60 * 60,
            ),
        )
        if not locked:
            raise DeploymentAlreadyQueued("该项目已有构建任务正在排队或运行")
        payload = json.dumps(asdict(job), ensure_ascii=False)
        try:
            await self._call(
                "保存任务状态",
                client.set(
                    self._status_key(job.id),
                    payload,
                    ex=settings.deployment_status_ttl,
                ),
            )
            await self._call(
                "写入任务",
                client.xadd(
                    self.stream,
                    {"payload": payload},
                    maxlen=10_000,
                    approximate=True,
                ),
            )
            score = datetime.fromisoformat(job.created_at).timestamp()
            await self._call(
                "更新用户索引",
                client.zadd(self._user_index(user_id), {job.id: score}),
            )
            await self._call(
                "更新全局索引",
                client.zadd(self._global_index(), {job.id: score}),
            )
        except DeploymentQueueUnavailable:
            try:
                await client.delete(self._lock_key(conversation_id))
            except Exception:
                pass
            raise
        return job

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[DeploymentJob]:
        client = await self.ensure_available()
        ids = await self._call(
            "读取用户索引",
            client.zrevrange(self._user_index(user_id), 0, max(0, limit - 1)),
        )
        if not ids:
            return []
        values = await self._call(
            "读取任务状态",
            client.mget([self._status_key(job_id) for job_id in ids]),
        )
        jobs = [DeploymentJob(**json.loads(raw)) for raw in values if raw]
        return [job for job in jobs if job.action == "deploy"]

    async def indexed_job_ids(self) -> list[str]:
        client = await self.ensure_available()
        return await self._call(
            "读取全局索引", client.zrange(self._global_index(), 0, -1)
        )

    async def remove_history(self, job: DeploymentJob) -> None:
        client = await self.ensure_available()
        await self._call("删除任务状态", client.delete(self._status_key(job.id)))
        await self._call(
            "删除用户索引",
            client.zrem(self._user_index(job.user_id), job.id),
        )
        await self._call(
            "删除全局索引", client.zrem(self._global_index(), job.id)
        )

    async def heartbeat(self) -> None:
        client = await self.ensure_available()
        await self._call(
            "写入 Worker 心跳",
            client.set(WORKER_HEARTBEAT_KEY, self.consumer, ex=15),
        )

    async def get(self, job_id: str) -> DeploymentJob | None:
        client = await self.ensure_available()
        raw = await self._call("读取任务状态", client.get(self._status_key(job_id)))
        if not raw:
            return None
        job = DeploymentJob(**json.loads(raw))
        job.cancel_requested = bool(
            await self._call("读取取消状态", client.get(self._cancel_key(job_id)))
        )
        return job

    async def update(self, job: DeploymentJob, **changes) -> DeploymentJob:
        client = await self.ensure_available()
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(UTC).isoformat()
        await self._call(
            "更新任务状态",
            client.set(
                self._status_key(job.id),
                json.dumps(asdict(job), ensure_ascii=False),
                ex=settings.deployment_status_ttl,
            ),
        )
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
        messages = await self._call(
            "领取任务",
            client.xreadgroup(
                GROUP, self.consumer, {self.stream: ">"}, count=1, block=block_ms
            ),
        )
        if not messages:
            return None
        _stream, entries = messages[0]
        message_id, fields = entries[0]
        return message_id, DeploymentJob(**json.loads(fields["payload"]))

    async def reclaim_stale(self, min_idle_ms: int | None = None):
        client = await self.ensure_available()
        min_idle_ms = min_idle_ms or settings.deployment_reclaim_idle_ms
        response = await self._call(
            "回收超时任务",
            client.xautoclaim(
                self.stream, GROUP, self.consumer, min_idle_ms, "0-0", count=1
            ),
        )
        entries = response[1] if len(response) > 1 else []
        if not entries:
            return None
        message_id, fields = entries[0]
        return message_id, DeploymentJob(**json.loads(fields["payload"]))

    async def claim_execution(self, job: DeploymentJob) -> bool:
        client = await self.ensure_available()
        return bool(await self._call(
            "获取执行租约",
            client.set(
                self._execution_key(job.id),
                self.consumer,
                nx=True,
                ex=max(30, settings.deployment_lease_ttl),
            ),
        ))

    async def heartbeat_execution(self, job: DeploymentJob) -> bool:
        client = await self.ensure_available()
        script = """
        if redis.call('get', KEYS[1]) ~= ARGV[1] then
            return 0
        end
        if redis.call('get', KEYS[2]) ~= ARGV[3] then
            return 0
        end
        redis.call('expire', KEYS[1], ARGV[2])
        redis.call('expire', KEYS[2], ARGV[4])
        return 1
        """
        return bool(await self._call(
            "续期执行租约",
            client.eval(
                script,
                2,
                self._execution_key(job.id),
                self._lock_key(job.conversation_id),
                self.consumer,
                max(30, settings.deployment_lease_ttl),
                job.id,
                2 * 60 * 60,
            ),
        ))

    async def release_execution(self, job: DeploymentJob) -> None:
        client = await self.ensure_available()
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        await self._call(
            "释放执行租约",
            client.eval(
                script, 1, self._execution_key(job.id), self.consumer
            ),
        )

    async def acknowledge(self, message_id: str) -> None:
        client = await self.ensure_available()
        await self._call("确认任务", client.xack(self.stream, GROUP, message_id))

    async def release_lock(self, job: DeploymentJob) -> None:
        client = await self.ensure_available()
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        await self._call(
            "释放项目锁",
            client.eval(script, 1, self._lock_key(job.conversation_id), job.id),
        )

    async def request_cancel(self, job: DeploymentJob) -> DeploymentJob:
        client = await self.ensure_available()
        await self._call(
            "写入取消状态",
            client.set(
                self._cancel_key(job.id),
                "1",
                ex=settings.deployment_status_ttl,
            ),
        )
        job.cancel_requested = True
        return job

    async def is_cancel_requested(self, job_id: str) -> bool:
        client = await self.ensure_available()
        return bool(
            await self._call("读取取消状态", client.get(self._cancel_key(job_id)))
        )

    async def clear_cancel(self, job_id: str) -> None:
        client = await self.ensure_available()
        await self._call("清除取消状态", client.delete(self._cancel_key(job_id)))

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
        await self._call(
            "保存重试状态",
            client.set(
                self._status_key(job.id),
                payload,
                ex=settings.deployment_status_ttl,
            ),
        )
        await self._call(
            "重新写入任务",
            client.xadd(
                self.stream,
                {"payload": payload},
                maxlen=10_000,
                approximate=True,
            ),
        )
        await self._call(
            "确认原任务", client.xack(self.stream, GROUP, message_id)
        )


deployment_queue = DeploymentQueue()
