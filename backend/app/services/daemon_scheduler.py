import asyncio
import contextlib
import hashlib
import logging
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.database import (
    claim_cron_task,
    get_cron_tasks,
    get_due_cron_tasks,
    update_cron_task_run_time,
)
from app.core.redis_lease import RedisLease

logger = logging.getLogger("daemon_scheduler")



def _run_task_process_entry(task: dict, retry_counts_dict: dict):
    """
    Subprocess entry point to run a single cron task in an isolated process,
    releasing the main FastAPI event loop from heavy LLM/reasoning tasks.
    """
    import asyncio
    import logging

    # Configure logging for the child process
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("daemon_scheduler.worker")

    from app.services.daemon_scheduler import DaemonScheduler

    scheduler = DaemonScheduler()
    # Share the manager-backed dict reference
    scheduler._retry_counts = retry_counts_dict

    try:
        asyncio.run(scheduler._run_task(task, claimed=True))
    except Exception as e:
        logger.error(f"Isolated worker process crashed for task {task.get('id')}: {e}")
        raise


class DaemonScheduler:
    """
    Always-on Offline Daemon Scheduler.
    Runs a non-blocking asynchronous polling loop in the background of the FastAPI application.
    Orchestrates periodic autonomous AI tasks even when no WebSocket clients are connected.
    """
    def __init__(self):
        self._running = False
        self._task = None
        self._manager = None
        self._retry_counts = {}  # 存储任务重试次数: {task_id: current_retry_count}
        self._leader_lease = None
        self._leader_recovered = False

    def start(self):
        if not self._running:
            self._running = True
            import multiprocessing
            try:
                self._manager = multiprocessing.Manager()
                self._retry_counts = self._manager.dict()
            except Exception as e:
                logger.error(f"Failed to initialize multiprocessing Manager: {e}. Falling back to standard dict.")
                self._manager = None
                self._retry_counts = {}
            self._task = asyncio.create_task(self._loop())
            logger.info("Always-on Offline Daemon Scheduler started successfully.")

    async def stop(self):
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            for process, task_id in getattr(self, "_child_processes", []):
                if process.is_alive():
                    process.terminate()
                    await asyncio.to_thread(process.join, 5)
                await asyncio.to_thread(
                    update_cron_task_run_time,
                    task_id,
                    now_str,
                    now_str,
                    "active",
                )
            self._child_processes = []
            if self._manager:
                try:
                    self._manager.shutdown()
                except Exception as e:
                    logger.warning(f"Failed to shutdown multiprocessing Manager: {e}")
            if self._leader_lease:
                await self._leader_lease.release()
                self._leader_lease = None
            self._leader_recovered = False
            logger.info("Always-on Offline Daemon Scheduler stopped.")

    async def _ensure_leader(self) -> bool:
        """Elect one scheduler across API replicas."""
        if self._leader_lease and self._leader_lease.acquired:
            if await self._leader_lease.renew():
                return True
            self._leader_recovered = False

        lease = RedisLease("agenthub:scheduler:leader", settings.scheduler_leader_ttl)
        if await lease.acquire():
            self._leader_lease = lease
            self._leader_recovered = False
            logger.info("This process acquired the distributed scheduler leader lease.")
            return True

        from app.core.redis import redis_manager

        if not await redis_manager.check_connection() and settings.debug:
            # Local development commonly runs one API process without Redis.
            return True
        return False

    async def _recover_after_leadership(self, now_str: str) -> None:
        if self._leader_recovered:
            return
        from app.core.crud.cron import recover_running_cron_tasks
        from app.core.redis import redis_manager

        protected = set()
        running_tasks = await asyncio.to_thread(get_cron_tasks)
        if await redis_manager.check_connection():
            client = redis_manager.get_client()
            for task in running_tasks:
                if (
                    task["status"] == "running"
                    and await client.exists(self._execution_key(task["id"]))
                ):
                    protected.add(task["id"])
        recovered = await asyncio.to_thread(recover_running_cron_tasks, now_str, protected)
        if recovered:
            logger.warning("Recovered %s cron task(s) left by the prior leader.", recovered)
        self._leader_recovered = True

    @staticmethod
    def _retry_key(task_id: str) -> str:
        digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
        return f"agenthub:scheduler:retry:{digest}"

    @staticmethod
    def _execution_key(task_id: str) -> str:
        digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
        return f"agenthub:scheduler:execution:{digest}"

    async def _get_retry_count(self, task_id: str) -> int:
        from app.core.redis import redis_manager

        if await redis_manager.check_connection():
            try:
                value = await redis_manager.get_client().get(self._retry_key(task_id))
                return int(value or 0)
            except Exception as exc:
                redis_manager.mark_unavailable(exc, "scheduler retry read")
        return int(self._retry_counts.get(task_id, 0))

    async def _set_retry_count(self, task_id: str, count: int) -> None:
        from app.core.redis import redis_manager

        if await redis_manager.check_connection():
            try:
                client = redis_manager.get_client()
                if count > 0:
                    await client.set(self._retry_key(task_id), count, ex=24 * 60 * 60)
                else:
                    await client.delete(self._retry_key(task_id))
                return
            except Exception as exc:
                redis_manager.mark_unavailable(exc, "scheduler retry write")
        self._retry_counts[task_id] = count

    async def _loop(self):
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                if not await self._ensure_leader():
                    await asyncio.sleep(5)
                    continue
                now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                await self._recover_after_leadership(now_str)
                due_tasks = await loop.run_in_executor(None, get_due_cron_tasks, now_str)

                for task in due_tasks:
                    claimed = await loop.run_in_executor(None, claim_cron_task, task["id"])
                    if not claimed:
                        continue

                    if self._manager is None:
                        # Fallback: run in-thread when multiprocessing Manager failed
                        asyncio.create_task(self._run_task(task, claimed=True))
                    else:
                        import multiprocessing
                        p = multiprocessing.Process(
                            target=_run_task_process_entry,
                            args=(task, self._retry_counts)
                        )
                        try:
                            p.start()
                        except Exception:
                            await loop.run_in_executor(
                                None,
                                update_cron_task_run_time,
                                task["id"],
                                now_str,
                                now_str,
                                "active",
                            )
                            raise
                        # Track child process for reaping to prevent zombie processes
                        if not hasattr(self, "_child_processes"):
                            self._child_processes = []
                        self._child_processes.append((p, task["id"]))

                # Reap any finished child processes to prevent zombie accumulation
                if hasattr(self, '_child_processes'):
                    still_running = []
                    for p, task_id in self._child_processes:
                        p.join(timeout=0)  # Non-blocking check
                        if p.is_alive():
                            still_running.append((p, task_id))
                        elif p.exitcode not in {0, None}:
                            failed_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                            await loop.run_in_executor(
                                None,
                                update_cron_task_run_time,
                                task_id,
                                failed_at,
                                failed_at,
                                "active",
                            )
                    self._child_processes = still_running

            except Exception as e:
                logger.error(f"Daemon Scheduler poll loop error: {e}")

            await asyncio.sleep(5)

    async def _run_task(self, task: dict, claimed: bool = False):
        task_id = task["id"]
        conversation_id = task["conversation_id"]
        agent_id = task["agent_id"]
        task_prompt = task["task_prompt"]
        interval = task["interval_seconds"]

        # 配置安全阀与重试参数 (Guardrails & Retries Config)
        MAX_EXECUTION_TIME_SECONDS = 90.0  # 单次任务最大运行时间（防死循环）
        MAX_OUTPUT_CHARACTERS = 15000     # 单次最大生成文本长度（防刷爆 Token）
        MAX_RETRIES = 3                   # 失败自愈最大重试次数
        BASE_BACKOFF_SECONDS = 15         # 基础指数退避秒数

        if not claimed and not await asyncio.to_thread(claim_cron_task, task_id, True):
            logger.info("Cron task %s is already running; duplicate trigger ignored.", task_id)
            return
        execution_lease = RedisLease(self._execution_key(task_id), 180)
        from app.core.redis import redis_manager

        redis_available = await redis_manager.check_connection()
        if redis_available and not await execution_lease.acquire():
            if await redis_manager.check_connection():
                logger.info("Cron task %s already owns a distributed execution lease.", task_id)
            else:
                logger.warning(
                    "Cron task %s lost Redis after it was claimed; returning it to the queue.",
                    task_id,
                )
                now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                await asyncio.to_thread(
                    update_cron_task_run_time,
                    task_id,
                    now_str,
                    now_str,
                    "active",
                )
            return
        if not redis_available and not settings.debug:
            logger.warning(
                "Cron task %s cannot start without distributed coordination.", task_id
            )
            now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            await asyncio.to_thread(
                update_cron_task_run_time,
                task_id,
                now_str,
                now_str,
                "active",
            )
            return
        retry_count = await self._get_retry_count(task_id)
        logger.info(f"Triggering background autonomous agent {agent_id} for cron job {task_id} (Attempt {retry_count + 1})...")

        execution_success = False
        error_msg = ""
        llm_context = None
        quality_context = None
        tool_context = None

        try:
            from app.core.database import get_messages, save_message
            from app.core.llm_client import llm_client
            from app.core.quality_gate import quality_gate
            from app.core.tenancy import conversation_user_id
            from app.core.tenant_settings import (
                get_tenant_disabled_tools,
                get_tenant_llm_client,
                get_tenant_quality_gate,
            )

            # Lazy import to avoid circular dependency
            from app.services.agent_orchestrator import stream_agent_reply as _stream_agent_reply
            from app.services.agent_registry import agent_registry
            from app.tools.registry import reset_tool_tenant, set_tool_tenant

            user_id = conversation_user_id(conversation_id) or "legacy"
            tenant_client = await asyncio.to_thread(get_tenant_llm_client, user_id)
            tenant_gate = await asyncio.to_thread(get_tenant_quality_gate, user_id)
            await asyncio.to_thread(get_tenant_disabled_tools, user_id)
            llm_context = llm_client.set_current(tenant_client)
            quality_context = quality_gate.set_current(tenant_gate)
            tool_context = set_tool_tenant(user_id)

            agent = await agent_registry.get_agent(agent_id, user_id)
            if not agent:
                raise ValueError(f"Agent '{agent_id}' is unavailable for tenant '{user_id}'.")

            # 【特性：跨运行周期记忆延续】
            # 在执行任务前，查找当前会话最新的历史消息，如果存在上一轮的回复，作为上下文继承喂给 Agent
            hist = await asyncio.to_thread(get_messages, conversation_id, 15)
            previous_run_summary = ""
            for m in reversed(hist):
                # 找到上一次该 Agent 的非系统提示/非报错的正常回复
                if m["sender"] == agent_id and isinstance(m.get("content"), dict) and m["content"].get("text"):
                    text = m["content"]["text"]
                    if "后台自治" not in text and "安全熔断" not in text and "自愈重试" not in text:
                        previous_run_summary = text
                        break

            enhanced_prompt = task_prompt
            if previous_run_summary:
                summary_excerpt = previous_run_summary[:2000]
                enhanced_prompt = (
                    f"【跨运行周期记忆延续 — 状态继承成功】\n"
                    f"你在上一次执行此定时任务时的成功输出概要如下：\n"
                    f"\"\"\"\n{summary_excerpt}\n\"\"\"\n\n"
                    f"现在已进入新一个任务执行周期。请在上述前序状态/记忆的基础上，继续完成本次任务。\n"
                    f"当前本次定时任务的要求是：{task_prompt}"
                )

            stop_event = asyncio.Event()

            # 1. 时间预算安全阀：使用 asyncio.wait_for 强制限制最大运行时间
            try:
                _assigned_agents, full_text = await asyncio.wait_for(
                    _stream_agent_reply(
                        conversation_id=conversation_id,
                        agent=agent,
                        user_text=enhanced_prompt,
                        stop_event=stop_event
                    ),
                    timeout=MAX_EXECUTION_TIME_SECONDS
                )
            except TimeoutError:
                stop_event.set()  # 终止底层大模型流
                raise TimeoutError(f"后台任务执行超出安全时长限制 ({MAX_EXECUTION_TIME_SECONDS}秒)，安全熔断阀已自动介入拦截！") from None

            # 2. 文本长度/Token预算安全阀
            if len(full_text) > MAX_OUTPUT_CHARACTERS:
                logger.warning(f"Cron job {task_id} generated text too long ({len(full_text)} chars). Triggering truncation guardrail.")
                await asyncio.to_thread(
                    save_message,
                    conversation_id,
                    agent_id,
                    {"text": f"⚠️ [安全警示]: 后台任务生成文本异常过长 ({len(full_text)} 字符)，已被熔断器截断，防止刷爆 Token 额度。"},
                    False
                )

            execution_success = True
            logger.info(f"Background cron job {task_id} successfully completed autonomous run.")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error running background cron job {task_id}: {e}")
        finally:
            if tool_context is not None:
                reset_tool_tenant(tool_context)
            if quality_context is not None:
                quality_gate.reset_current(quality_context)
            if llm_context is not None:
                llm_client.reset_current(llm_context)

        # 【特性：自愈型指数退避重试调度机】
        now = datetime.now(UTC)
        last_run_str = now.strftime("%Y-%m-%d %H:%M:%S")

        if execution_success:
            # 执行成功：清除重试计数，进入下一个正常长周期
            await self._set_retry_count(task_id, 0)
            next_run_str = (now + timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M:%S")
            await asyncio.to_thread(update_cron_task_run_time, task_id, last_run_str, next_run_str, "active")
        else:
            # 执行失败：递增重试次数
            current_retry = await self._get_retry_count(task_id) + 1
            await self._set_retry_count(task_id, current_retry)

            from app.core.database import save_message

            if current_retry <= MAX_RETRIES:
                # 依然处于重试配额内，计算指数退避等待时间 (e.g. 15s, 45s, 135s)
                backoff_seconds = BASE_BACKOFF_SECONDS * (3 ** (current_retry - 1))
                next_run_str = (now + timedelta(seconds=backoff_seconds)).strftime("%Y-%m-%d %H:%M:%S")

                logger.warning(f"Cron task {task_id} failed. Scheduling retry {current_retry}/{MAX_RETRIES} in {backoff_seconds}s.")

                # 写入带有自动重试字样的消息广播给前端
                await asyncio.to_thread(save_message,
                    conversation_id,
                    agent_id,
                    {
                        "text": (
                            f"⚠️ [后台自治异常自动重试]: 定时任务运行报错 ({error_msg[:120]}...)。\n"
                            f"已自动激活 Prefect 级自愈退避算法，正在启动第 **{current_retry}/{MAX_RETRIES}** 次重试，"
                            f"将在 **{backoff_seconds}** 秒后自动重试..."
                        )
                    },
                    streaming=False
                )
                await asyncio.to_thread(update_cron_task_run_time, task_id, last_run_str, next_run_str, "active")

            else:
                # 重试次数超限，彻底宣告失败，只能等待下一个大周期的长轮询
                await self._set_retry_count(task_id, 0)
                next_run_str = (now + timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M:%S")

                logger.error(f"Cron task {task_id} failed 3 times. Skipping current cycle.")

                is_guardrail = "安全熔断" in error_msg or "TimeoutError" in error_msg
                badge = "🛑 [后台自治安全熔断]" if is_guardrail else "🛑 [后台自治彻底失败]"

                await asyncio.to_thread(save_message,
                    conversation_id,
                    agent_id,
                    {
                        "text": (
                            f"{badge}: 经过连续 {MAX_RETRIES} 次退避自动重试自愈，任务依然报错。\n"
                            f"本次定时周期被迫跳过，已将任务重置为正常待命，等待下一长轮次调度。\n"
                            f"报错信息: {error_msg}"
                        )
                    },
                    streaming=False
                )
                await asyncio.to_thread(update_cron_task_run_time, task_id, last_run_str, next_run_str, "active")

        await execution_lease.release()


daemon_scheduler = DaemonScheduler()
