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

        update_cron_task_status(task_id, "running")
        logger.info(f"Triggering background autonomous agent {agent_id} for cron job {task_id}...")

        try:
            from app.main import AGENTS, _stream_agent_reply

            agent = AGENTS.get(agent_id)
            if not agent:
                raise ValueError(f"Agent '{agent_id}' is not loaded in current server agents dictionary.")

            stop_event = asyncio.Event()

            assigned_agents, full_text = await _stream_agent_reply(
                conversation_id=conversation_id,
                agent=agent,
                user_text=task_prompt,
                stop_event=stop_event
            )

            logger.info(f"Background cron job {task_id} successfully completed autonomous run.")

        except Exception as e:
            logger.error(f"Error running background cron job {task_id}: {e}")
            from app.core.database import save_message
            save_message(
                conversation_id,
                agent_id,
                {"text": f"\u26a0\ufe0f [\u540e\u53f0\u81ea\u6cbb\u8fd0\u884c\u5f02\u5e38]: {type(e).__name__}: {str(e)[:200]}"},
                streaming=False
            )

        finally:
            now = datetime.utcnow()
            last_run_str = now.strftime("%Y-%m-%d %H:%M:%S")
            next_run_str = (now + timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M:%S")
            update_cron_task_run_time(task_id, last_run_str, next_run_str, "active")


daemon_scheduler = DaemonScheduler()
