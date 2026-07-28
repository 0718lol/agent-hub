import asyncio
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.async_wrappers import (
    async_delete_cron_task,
    async_get_cron_tasks,
    async_save_cron_task,
    async_update_cron_task_status,
)
from app.core.database import claim_cron_task
from app.core.tenancy import belongs_to_user, public_conversation_id, request_user_id, scope_conversation_id

router = APIRouter(tags=["cron"])


class CronTaskCreate(BaseModel):
    conversation_id: str
    agent_id: str
    task_prompt: str
    interval_seconds: int


@router.get("/cron")
async def list_cron_tasks(request: Request, conversation_id: str | None = None):
    user_id = request_user_id(request)
    scoped_id = scope_conversation_id(user_id, conversation_id) if conversation_id else None
    tasks = await async_get_cron_tasks(scoped_id)
    return [{**task, "conversation_id": public_conversation_id(task["conversation_id"])} for task in tasks if belongs_to_user(task["conversation_id"], user_id)]


@router.post("/cron")
async def create_cron_task_endpoint(body: CronTaskCreate, request: Request):
    task_id = f"cron_{uuid.uuid4().hex[:8]}"
    await async_save_cron_task(
        task_id=task_id,
        conversation_id=scope_conversation_id(request_user_id(request), body.conversation_id),
        agent_id=body.agent_id,
        task_prompt=body.task_prompt,
        interval_seconds=body.interval_seconds,
        status="active"
    )
    return {"status": "created", "task_id": task_id}


@router.post("/cron/{task_id}/toggle")
async def toggle_cron_task(task_id: str, status: str, request: Request):
    if status not in ("active", "paused"):
        return {"status": "error", "message": "无效的任务状态"}
    tasks = await async_get_cron_tasks()
    task = next((t for t in tasks if t["id"] == task_id and belongs_to_user(t["conversation_id"], request_user_id(request))), None)
    if not task:
        return {"status": "error", "message": "自治任务未找到"}
    await async_update_cron_task_status(task_id, status)
    return {"status": "ok", "message": f"任务状态已更新为 {status}"}


@router.post("/cron/{task_id}/run")
async def run_cron_task_now(task_id: str, request: Request):
    tasks = await async_get_cron_tasks()
    task = next((t for t in tasks if t["id"] == task_id and belongs_to_user(t["conversation_id"], request_user_id(request))), None)
    if not task:
        return {"status": "error", "message": "自治任务未找到"}
    if not await asyncio.to_thread(claim_cron_task, task_id, True):
        return {"status": "busy", "message": "任务正在运行，请勿重复触发"}

    from app.routers.ws import create_tracked_task
    from app.services.daemon_scheduler import daemon_scheduler

    # 采用 Wac 强引用控制器进行 Task 运行，消除 GC 夭折隐患
    create_tracked_task(
        daemon_scheduler._run_task(task, claimed=True),
        name=f"manual_cron_{task_id}"
    )
    return {"status": "ok", "message": "已手动触发后台自治作业运行！"}


@router.delete("/cron/{task_id}")
async def delete_cron_task_endpoint(task_id: str, request: Request):
    tasks = await async_get_cron_tasks()
    task = next((t for t in tasks if t["id"] == task_id and belongs_to_user(t["conversation_id"], request_user_id(request))), None)
    if not task:
        return {"status": "error", "message": "自治任务未找到"}
    await async_delete_cron_task(task_id)
    return {"status": "ok", "message": "离线自治任务已成功删除！"}
