import asyncio
import logging
from datetime import datetime, timedelta
from app.core.database import get_due_cron_tasks, update_cron_task_run_time, update_cron_task_status

logger = logging.getLogger("daemon_scheduler")

class DaemonScheduler:
    """
    Always-on Offline Daemon Scheduler.
    Runs a non-blocking asynchronous polling loop in the background of the FastAPI application.
    Orchestrates periodic autonomous AI tasks, supporting stdio MCP tools and sandboxed Git checkpoints.
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
                # SQLite-compatible UTC datetime format
                now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                due_tasks = get_due_cron_tasks(now_str)

                for task in due_tasks:
                    # Spawn task non-blockingly
                    asyncio.create_task(self._run_task(task))

            except Exception as e:
                logger.error(f"Daemon Scheduler poll loop error: {e}")

            # Poll every 5 seconds for responsive task execution
            await asyncio.sleep(5)

    async def _run_task(self, task: dict):
        task_id = task["id"]
        conversation_id = task["conversation_id"]
        agent_id = task["agent_id"]
        task_prompt = task["task_prompt"]
        interval = task["interval_seconds"]

        # Prevent re-entry by marking task as running
        update_cron_task_status(task_id, "running")
        logger.info(f"Triggering background autonomous agent {agent_id} for cron job {task_id}...")

        try:
            # Dynamically import to prevent circular references at startup
            from app.main import AGENTS, _stream_agent_reply

            agent = AGENTS.get(agent_id)
            if not agent:
                raise ValueError(f"Agent '{agent_id}' is not loaded in current server agents dictionary.")

            # Create stop event
            stop_event = asyncio.Event()

            # Execute agent reply. This automatically invokes StreamPipeline (purging tags, streaming tool execution logging),
            # runs standard stdio MCP tools under isolated sandbox, saves the final message to messages DB,
            # and automatically git-commits any sandbox changes under versioning checkpoints!
            assigned_agents, full_text = await _stream_agent_reply(
                conversation_id=conversation_id,
                agent=agent,
                user_text=task_prompt,
                stop_event=stop_event
            )

            logger.info(f"Background cron job {task_id} successfully completed autonomous run.")

        except Exception as e:
            logger.error(f"Error running background cron job {task_id}: {e}")
            # Log failure to message history so user can see it when online
            from app.core.database import save_message
            save_message(
                conversation_id,
                agent_id,
                {"text": f"⚠️ [后台自治运行异常]: {type(e).__name__}: {str(e)[:200]}"},
                streaming=False
            )

        finally:
            # Recalculate next run schedule
            now = datetime.utcnow()
            last_run_str = now.strftime("%Y-%m-%d %H:%M:%S")
            next_run_str = (now + timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M:%S")

            update_cron_task_run_time(task_id, last_run_str, next_run_str, "active")


daemon_scheduler = DaemonScheduler()
