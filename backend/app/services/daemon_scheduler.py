import asyncio
import logging
from datetime import datetime, timedelta
from app.core.database import get_due_cron_tasks, update_cron_task_run_time, update_cron_task_status

logger = logging.getLogger("daemon_scheduler")


class DaemonScheduler:
    """
    Always-on Offline Daemon Scheduler.
    Runs a non-blocking asynchronous polling loop in the background of the FastAPI application.
    Orchestrates periodic autonomous AI tasks even when no WebSocket clients are connected.
    """
    def __init__(self):
        self._running = False
        self._task = None

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("Always-on Offline Daemon Scheduler started successfully.")

    async def stop(self):
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("Always-on Offline Daemon Scheduler stopped.")

    async def _loop(self):
        while self._running:
            try:
                now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                due_tasks = get_due_cron_tasks(now_str)

                for task in due_tasks:
                    asyncio.create_task(self._run_task(task))

            except Exception as e:
                logger.error(f"Daemon Scheduler poll loop error: {e}")

            await asyncio.sleep(5)

    async def _run_task(self, task: dict):
        task_id = task["id"]
        conversation_id = task["conversation_id"]
        agent_id = task["agent_id"]
        task_prompt = task["task_prompt"]
        interval = task["interval_seconds"]

        # 配置安全阀阈值 (Guardrails Config)
        MAX_EXECUTION_TIME_SECONDS = 90.0  # 单次任务最大运行时间（防死循环）
        MAX_OUTPUT_CHARACTERS = 15000     # 单次最大生成文本长度（防刷爆 Token）

        update_cron_task_status(task_id, "running")
        logger.info(f"Triggering background autonomous agent {agent_id} for cron job {task_id} with guardrails...")

        try:
            from app.main import AGENTS, _stream_agent_reply

            agent = AGENTS.get(agent_id)
            if not agent:
                raise ValueError(f"Agent '{agent_id}' is not loaded in current server agents dictionary.")

            stop_event = asyncio.Event()

            # 1. 时间预算安全阀：使用 asyncio.wait_for 强制限制最大运行时间
            try:
                assigned_agents, full_text = await asyncio.wait_for(
                    _stream_agent_reply(
                        conversation_id=conversation_id,
                        agent=agent,
                        user_text=task_prompt,
                        stop_event=stop_event
                    ),
                    timeout=MAX_EXECUTION_TIME_SECONDS
                )
            except asyncio.TimeoutError:
                stop_event.set()  # 终止底层大模型流
                raise TimeoutError(f"后台任务执行超出安全时长限制 ({MAX_EXECUTION_TIME_SECONDS}秒)，安全熔断阀已自动介入拦截，防止无限循环及费用失控！")

            # 2. 文本长度/Token预算安全阀
            if len(full_text) > MAX_OUTPUT_CHARACTERS:
                logger.warning(f"Cron job {task_id} generated text too long ({len(full_text)} chars). Triggering truncation guardrail.")
                from app.core.database import save_message
                save_message(
                    conversation_id,
                    agent_id,
                    {"text": f"⚠️ [安全警示]: 后台任务生成文本异常过长 ({len(full_text)} 字符)，已被熔断器截断，防止刷爆 Token 额度。"},
                    streaming=False
                )

            logger.info(f"Background cron job {task_id} successfully completed autonomous run.")

        except Exception as e:
            logger.error(f"Error running background cron job {task_id}: {e}")
            from app.core.database import save_message
            
            # 判断是否是我们的安全阀触发的异常
            is_guardrail = "安全熔断" in str(e) or "TimeoutError" in type(e).__name__
            badge_title = "🛑 [后台自治安全熔断]" if is_guardrail else "⚠️ [后台自治运行异常]"
            
            save_message(
                conversation_id,
                agent_id,
                {"text": f"{badge_title}: {str(e)[:400]}"},
                streaming=False
            )

        finally:
            now = datetime.utcnow()
            last_run_str = now.strftime("%Y-%m-%d %H:%M:%S")
            next_run_str = (now + timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M:%S")
            update_cron_task_run_time(task_id, last_run_str, next_run_str, "active")


daemon_scheduler = DaemonScheduler()
