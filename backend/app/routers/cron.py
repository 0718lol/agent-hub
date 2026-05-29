import asyncio
import uuid
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.core.database import (
    get_cron_tasks, save_cron_task, update_cron_task_status, delete_cron_task
)

router = APIRouter(tags=["cron"])


class CronTaskCreate(BaseModel):
    conversation_id: str
    agent_id: str
    task_prompt: str
    interval_seconds: int


@router.get("/cron")
async def list_cron_tasks(conversation_id: Optional[str] = None):
    return get_cron_tasks(conversation_id)


@router.post("/cron")
async def create_cron_task_endpoint(body: CronTaskCreate):
    task_id = f"cron_{uuid.uuid4().hex[:8]}"
    save_cron_task(
        task_id=task_id,
        conversation_id=body.conversation_id,
        agent_id=body.agent_id,
        task_prompt=body.task_prompt,
        interval_seconds=body.interval_seconds,
        status="active"
    )
    return {"status": "created", "task_id": task_id}


@router.post("/cron/{task_id}/toggle")
async def toggle_cron_task(task_id: str, status: str):
    if status not in ("active", "paused"):
        return {"status": "error", "message": "无效的任务状态"}
    update_cron_task_status(task_id, status)
    return {"status": "ok", "message": f"任务状态已更新为 {status}"}


@router.post("/cron/{task_id}/run")
async def run_cron_task_now(task_id: str):
    tasks = get_cron_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"status": "error", "message": "自治任务未找到"}

    from app.services.daemon_scheduler import daemon_scheduler
    from app.main import create_tracked_task
    
    # 采用 Wac 强引用控制器进行 Task 运行，消除 GC 夭折隐患
    create_tracked_task(
        daemon_scheduler._run_task(task),
        name=f"manual_cron_{task_id}"
    )
    return {"status": "ok", "message": "已手动触发后台自治作业运行！"}


@router.delete("/cron/{task_id}")
async def delete_cron_task_endpoint(task_id: str):
    delete_cron_task(task_id)
    return {"status": "ok", "message": "离线自治任务已成功删除！"}
