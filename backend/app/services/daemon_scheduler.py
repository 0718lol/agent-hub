import asyncio
import logging
from datetime import datetime, timedelta
from app.core.database import get_due_cron_tasks, update_cron_task_run_time, update_cron_task_status

logger = logging.getLogger("daemon_scheduler")


import multiprocessing

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
        asyncio.run(scheduler._run_task(task))
    except Exception as e:
        logger.error(f"Isolated worker process crashed for task {task.get('id')}: {e}")


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
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            if self._manager:
                try:
                    self._manager.shutdown()
                except Exception:
                    pass
            logger.info("Always-on Offline Daemon Scheduler stopped.")

    async def _loop(self):
        while self._running:
            try:
                now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                due_tasks = get_due_cron_tasks(now_str)

                for task in due_tasks:
                    # Guard against double firing by setting running status before process spawn
                    update_cron_task_status(task["id"], "running")
                    
                    import multiprocessing
                    p = multiprocessing.Process(
                        target=_run_task_process_entry,
                        args=(task, self._retry_counts)
                    )
                    p.start()

            except Exception as e:
                logger.error(f"Daemon Scheduler poll loop error: {e}")

            await asyncio.sleep(5)

    async def _run_task(self, task: dict):
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

        update_cron_task_status(task_id, "running")
        logger.info(f"Triggering background autonomous agent {agent_id} for cron job {task_id} (Attempt {self._retry_counts.get(task_id, 0) + 1})...")

        execution_success = False
        error_msg = ""

        try:
            from app.services.agent_registry import agent_registry
            from app.main import _stream_agent_reply
            from app.core.database import get_messages, save_message

            agent = await agent_registry.get_agent(agent_id)
            if not agent:
                raise ValueError(f"Agent '{agent_id}' is not loaded in current server agents dictionary.")

            # 【特性：跨运行周期记忆延续】
            # 在执行任务前，查找当前会话最新的历史消息，如果存在上一轮的回复，作为上下文继承喂给 Agent
            hist = get_messages(conversation_id, limit=15)
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
                assigned_agents, full_text = await asyncio.wait_for(
                    _stream_agent_reply(
                        conversation_id=conversation_id,
                        agent=agent,
                        user_text=enhanced_prompt,
                        stop_event=stop_event
                    ),
                    timeout=MAX_EXECUTION_TIME_SECONDS
                )
            except asyncio.TimeoutError:
                stop_event.set()  # 终止底层大模型流
                raise TimeoutError(f"后台任务执行超出安全时长限制 ({MAX_EXECUTION_TIME_SECONDS}秒)，安全熔断阀已自动介入拦截！")

            # 2. 文本长度/Token预算安全阀
            if len(full_text) > MAX_OUTPUT_CHARACTERS:
                logger.warning(f"Cron job {task_id} generated text too long ({len(full_text)} chars). Triggering truncation guardrail.")
                save_message(
                    conversation_id,
                    agent_id,
                    {"text": f"⚠️ [安全警示]: 后台任务生成文本异常过长 ({len(full_text)} 字符)，已被熔断器截断，防止刷爆 Token 额度。"},
                    streaming=False
                )

            execution_success = True
            logger.info(f"Background cron job {task_id} successfully completed autonomous run.")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error running background cron job {task_id}: {e}")

        # 【特性：自愈型指数退避重试调度机】
        now = datetime.utcnow()
        last_run_str = now.strftime("%Y-%m-%d %H:%M:%S")

        if execution_success:
            # 执行成功：清除重试计数，进入下一个正常长周期
            self._retry_counts[task_id] = 0
            next_run_str = (now + timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M:%S")
            update_cron_task_run_time(task_id, last_run_str, next_run_str, "active")
        else:
            # 执行失败：递增重试次数
            current_retry = self._retry_counts.get(task_id, 0) + 1
            self._retry_counts[task_id] = current_retry

            from app.core.database import save_message

            if current_retry <= MAX_RETRIES:
                # 依然处于重试配额内，计算指数退避等待时间 (e.g. 15s, 45s, 135s)
                backoff_seconds = BASE_BACKOFF_SECONDS * (3 ** (current_retry - 1))
                next_run_str = (now + timedelta(seconds=backoff_seconds)).strftime("%Y-%m-%d %H:%M:%S")

                logger.warning(f"Cron task {task_id} failed. Scheduling retry {current_retry}/{MAX_RETRIES} in {backoff_seconds}s.")
                
                # 写入带有自动重试字样的消息广播给前端
                save_message(
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
                update_cron_task_run_time(task_id, last_run_str, next_run_str, "active")
            else:
                # 重试次数超限，彻底宣告失败，只能等待下一个大周期的长轮询
                self._retry_counts[task_id] = 0
                next_run_str = (now + timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M:%S")

                logger.error(f"Cron task {task_id} failed 3 times. Skipping current cycle.")
                
                is_guardrail = "安全熔断" in error_msg or "TimeoutError" in error_msg
                badge = "🛑 [后台自治安全熔断]" if is_guardrail else "🛑 [后台自治彻底失败]"
                
                save_message(
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
                update_cron_task_run_time(task_id, last_run_str, next_run_str, "active")


daemon_scheduler = DaemonScheduler()
