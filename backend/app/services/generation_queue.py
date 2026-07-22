"""Redis Streams-backed persistent interactive generation queue."""

import json
import socket
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.core.concurrency import generation_admission
from app.core.config import settings
from app.core.redis import redis_manager

GROUP = "generation-workers"
WORKER_HEARTBEAT_KEY = "agenthub:generation:worker:heartbeat"


class GenerationQueueUnavailable(RuntimeError):
    pass


class GenerationAlreadyQueued(RuntimeError):
    pass


@dataclass
class GenerationJob:
    id: str
    conversation_id: str
    user_id: str
    text: str
    target_agent: str = ""
    status: str = "queued"
    attempts: int = 0
    created_at: str = ""
    updated_at: str = ""
    error: str = ""

    def __post_init__(self):
        now = datetime.now(UTC).isoformat()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now


class GenerationQueue:
    def __init__(self):
        self.stream = settings.generation_queue
        self.consumer = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._group_ready = False

    @staticmethod
    def _status_key(job_id: str) -> str:
        return f"agenthub:generation:job:{job_id}"

    @staticmethod
    def _conversation_key(conversation_id: str) -> str:
        return f"agenthub:generation:current:{conversation_id}"

    @staticmethod
    def _cancel_key(job_id: str) -> str:
        return f"agenthub:generation:job-cancel:{job_id}"

    @staticmethod
    def _execution_key(job_id: str) -> str:
        return f"agenthub:generation:execution:{job_id}"

    async def _call(self, operation: str, awaitable):
        try:
            return await awaitable
        except GenerationQueueUnavailable:
            raise
        except Exception as exc:
            if "NOGROUP" in str(exc):
                self._group_ready = False
            redis_manager.mark_unavailable(exc, f"generation queue {operation}")
            raise GenerationQueueUnavailable(
                f"生成队列{operation}失败，请稍后重试"
            ) from exc

    async def ensure_available(self):
        if not await redis_manager.check_connection():
            raise GenerationQueueUnavailable("Redis 不可用，无法启动持久化生成任务")
        client = redis_manager.get_client()
        if self._group_ready:
            return client
        try:
            await client.xgroup_create(self.stream, GROUP, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                redis_manager.mark_unavailable(exc, "generation queue initialization")
                raise GenerationQueueUnavailable("无法初始化生成任务队列") from exc
        self._group_ready = True
        return client

    async def enqueue(
        self,
        conversation_id: str,
        user_id: str,
        text: str,
        target_agent: str | None = None,
    ) -> GenerationJob:
        client = await self.ensure_available()
        if not await self._call("读取 Worker 心跳", client.get(WORKER_HEARTBEAT_KEY)):
            raise GenerationQueueUnavailable(
                "生成 Worker 未运行，请启动 generation-worker 服务"
            )
        job = GenerationJob(
            id=uuid.uuid4().hex,
            conversation_id=conversation_id,
            user_id=user_id,
            text=text,
            target_agent=target_agent or "",
        )
        locked = await self._call(
            "获取会话锁",
            client.set(
                self._conversation_key(conversation_id),
                job.id,
                nx=True,
                ex=settings.generation_status_ttl,
            ),
        )
        if not locked:
            raise GenerationAlreadyQueued("当前会话已有生成任务正在排队或运行")
        payload = json.dumps(asdict(job), ensure_ascii=False)
        try:
            await self._call(
                "保存任务状态",
                client.set(
                    self._status_key(job.id),
                    payload,
                    ex=settings.generation_status_ttl,
                ),
            )
            await self._call(
                "写入任务",
                client.xadd(self.stream, {"payload": payload}),
            )
        except GenerationQueueUnavailable:
            try:
                await client.delete(self._conversation_key(conversation_id))
            except Exception:
                pass
            raise
        await generation_admission.set_status(
            conversation_id,
            "queued",
            user_id=user_id,
            job_id=job.id,
            started_at=int(datetime.now(UTC).timestamp()),
        )
        return job

    async def get(self, job_id: str) -> GenerationJob | None:
        client = await self.ensure_available()
        raw = await self._call("读取任务状态", client.get(self._status_key(job_id)))
        return GenerationJob(**json.loads(raw)) if raw else None

    async def update(self, job: GenerationJob, **changes) -> GenerationJob:
        client = await self.ensure_available()
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(UTC).isoformat()
        await self._call(
            "更新任务状态",
            client.set(
                self._status_key(job.id),
                json.dumps(asdict(job), ensure_ascii=False),
                ex=settings.generation_status_ttl,
            ),
        )
        current_job_id = await self._call(
            "核对当前任务",
            client.get(self._conversation_key(job.conversation_id)),
        )
        if current_job_id == job.id:
            await generation_admission.set_status(
                job.conversation_id,
                job.status,
                user_id=job.user_id,
                job_id=job.id,
                attempts=job.attempts,
                reason=job.error,
            )
        return job

    async def heartbeat(self) -> None:
        client = await self.ensure_available()
        await self._call(
            "写入 Worker 心跳",
            client.set(WORKER_HEARTBEAT_KEY, self.consumer, ex=15),
        )

    async def worker_available(self) -> bool:
        """Check liveness without refreshing or otherwise forging the heartbeat."""
        client = await self.ensure_available()
        return bool(
            await self._call(
                "读取 Worker 心跳",
                client.get(WORKER_HEARTBEAT_KEY),
            )
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
        return message_id, GenerationJob(**json.loads(fields["payload"]))

    async def reclaim_stale(self):
        client = await self.ensure_available()
        response = await self._call(
            "回收超时任务",
            client.xautoclaim(
                self.stream,
                GROUP,
                self.consumer,
                settings.generation_reclaim_idle_ms,
                "0-0",
                count=1,
            ),
        )
        entries = response[1] if len(response) > 1 else []
        if not entries:
            return None
        message_id, fields = entries[0]
        return message_id, GenerationJob(**json.loads(fields["payload"]))

    async def claim_execution(self, job: GenerationJob) -> bool:
        client = await self.ensure_available()
        return bool(await self._call(
            "获取执行租约",
            client.set(
                self._execution_key(job.id),
                self.consumer,
                nx=True,
                ex=max(30, settings.generation_lease_ttl),
            ),
        ))

    async def heartbeat_execution(self, job: GenerationJob) -> bool:
        client = await self.ensure_available()
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('expire', KEYS[1], ARGV[2])
        end
        return 0
        """
        return bool(await self._call(
            "续期执行租约",
            client.eval(
                script,
                1,
                self._execution_key(job.id),
                self.consumer,
                max(30, settings.generation_lease_ttl),
            ),
        ))

    async def release_execution(self, job: GenerationJob) -> None:
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

    async def request_cancel_by_conversation(self, conversation_id: str) -> bool:
        client = await self.ensure_available()
        job_id = await self._call(
            "读取当前任务", client.get(self._conversation_key(conversation_id))
        )
        if not job_id:
            return False
        await self._call(
            "写入取消状态",
            client.set(
                self._cancel_key(job_id),
                "1",
                ex=settings.generation_status_ttl,
            ),
        )
        job = await self.get(job_id)
        if job:
            await self.update(job, status="cancelling")
        return True

    async def is_cancel_requested(self, job_id: str) -> bool:
        client = await self.ensure_available()
        return bool(await self._call(
            "读取取消状态", client.get(self._cancel_key(job_id))
        ))

    async def retry(self, message_id: str, job: GenerationJob, error: str) -> None:
        client = await self.ensure_available()
        job.attempts += 1
        job.status = "queued"
        job.error = str(error)[:2_000]
        job.updated_at = datetime.now(UTC).isoformat()
        payload = json.dumps(asdict(job), ensure_ascii=False)
        await self._call(
            "保存重试状态",
            client.set(
                self._status_key(job.id),
                payload,
                ex=settings.generation_status_ttl,
            ),
        )
        await self._call(
            "重新写入任务",
            client.xadd(self.stream, {"payload": payload}),
        )
        await self._call(
            "确认原任务", client.xack(self.stream, GROUP, message_id)
        )
        await self._call("清理原任务", client.xdel(self.stream, message_id))
        await generation_admission.set_status(
            job.conversation_id,
            "queued",
            user_id=job.user_id,
            job_id=job.id,
            attempts=job.attempts,
            reason=job.error,
        )

    async def finalize(
        self,
        message_id: str,
        job: GenerationJob,
        status: str,
        error: str = "",
    ) -> None:
        client = await self.ensure_available()
        await self.update(job, status=status, error=str(error)[:2_000])
        await self._call("确认任务", client.xack(self.stream, GROUP, message_id))
        await self._call("清理任务", client.xdel(self.stream, message_id))
        release_script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        await self._call(
            "释放会话锁",
            client.eval(
                release_script,
                1,
                self._conversation_key(job.conversation_id),
                job.id,
            ),
        )
        await self._call(
            "清除取消状态", client.delete(self._cancel_key(job.id))
        )


generation_queue = GenerationQueue()
