import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.async_wrappers import (
    async_delete_cron_task,
    async_get_cron_tasks,
    async_save_cron_task,
    async_update_cron_task_status,
)
from app.core.crud.cron import claim_cron_task
from app.core.database import get_conversations
from app.services.agent_registry import agent_registry

router = APIRouter(tags=["cron"])
from app.core.tenancy import belongs_to_user, public_conversation_id, request_user_id, scope_conversation_id


class CronTaskCreate(BaseModel):
    conversation_id: str
    agent_id: str
    task_prompt: str = Field(min_length=1, max_length=10_000)
    interval_seconds: int = Field(ge=60, le=31_536_000)


class CronToggleRequest(BaseModel):
    status: str


@router.get("/cron")
async def list_cron_tasks(request: Request, conversation_id: str | None = None):
    user_id = request_user_id(request)
    scoped_id = scope_conversation_id(user_id, conversation_id) if conversation_id else None
    tasks = await async_get_cron_tasks(scoped_id)
    owned = [
        {**task, "conversation_id": public_conversation_id(task["conversation_id"])}
        for task in tasks if belongs_to_user(task["conversation_id"], user_id)
    ]
    return {"status": "ok", "tasks": owned}


@router.post("/cron")
async def create_cron_task_endpoint(body: CronTaskCreate, request: Request):
    tenant_id = request_user_id(request)
    scoped_conversation_id = scope_conversation_id(tenant_id, body.conversation_id)
    conversations = await asyncio.to_thread(get_conversations)
    if not any(row["id"] == scoped_conversation_id for row in conversations):
        raise HTTPException(status_code=404, detail="会话不存在")
    if await agent_registry.get_agent(body.agent_id, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    task_id = f"cron_{uuid.uuid4().hex[:8]}"
    next_run = (datetime.now(UTC) + timedelta(seconds=body.interval_seconds)).strftime("%Y-%m-%d %H:%M:%S")
    await async_save_cron_task(
        task_id=task_id,
        conversation_id=scoped_conversation_id,
        agent_id=body.agent_id,
        task_prompt=body.task_prompt,
        interval_seconds=body.interval_seconds,
        status="active",
        next_run=next_run,
    )
    return {"status": "ok", "task": {"id": task_id, **body.model_dump(), "status": "active", "next_run": next_run}}


@router.post("/cron/{task_id}/toggle")
async def toggle_cron_task(task_id: str, body: CronToggleRequest, request: Request):
    if body.status not in ("active", "paused"):
        raise HTTPException(status_code=422, detail="无效的任务状态")
    tasks = await async_get_cron_tasks()
    task = next((t for t in tasks if t["id"] == task_id and belongs_to_user(t["conversation_id"], request_user_id(request))), None)
    if not task:
        raise HTTPException(status_code=404, detail="自治任务未找到")
    await async_update_cron_task_status(task_id, body.status)
    return {"status": "ok", "task": {**task, "status": body.status}}


@router.post("/cron/{task_id}/run")
async def run_cron_task_now(task_id: str, request: Request):
    tasks = await async_get_cron_tasks()
    task = next((t for t in tasks if t["id"] == task_id and belongs_to_user(t["conversation_id"], request_user_id(request))), None)
    if not task:
        raise HTTPException(status_code=404, detail="自治任务未找到")
    if not await asyncio.to_thread(claim_cron_task, task_id, True):
        raise HTTPException(status_code=409, detail="任务正在运行，请勿重复触发")

    from app.routers.ws import create_tracked_task
    from app.services.daemon_scheduler import daemon_scheduler

    # 采用 Wac 强引用控制器进行 Task 运行，消除 GC 夭折隐患
    create_tracked_task(
        daemon_scheduler._run_task(task),
        name=f"manual_cron_{task_id}"
    )
    return {"status": "ok", "message": "已手动触发后台自治作业运行！"}


@router.delete("/cron/{task_id}")
async def delete_cron_task_endpoint(task_id: str, request: Request):
    tasks = await async_get_cron_tasks()
    task = next((t for t in tasks if t["id"] == task_id and belongs_to_user(t["conversation_id"], request_user_id(request))), None)
    if not task:
        raise HTTPException(status_code=404, detail="自治任务未找到")
    await async_delete_cron_task(task_id)
    return {"status": "ok", "message": "离线自治任务已成功删除！"}
