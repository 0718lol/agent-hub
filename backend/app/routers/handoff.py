"""Import personal-ai-os project briefs and export reviewed execution receipts."""
from __future__ import annotations

import asyncio
import hashlib
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

import app.core._engine as engine_module
from app.core.crud.artifacts import get_artifacts
from app.core.crud.utils import db_write_transaction
from app.core.models import Conversation, DeliveryRecord, Message
from app.core.runtime_mode import require_workbench_mode
from app.core.tenancy import request_user_id, scope_conversation_id
from app.core.workspace import validate_local_workspace_path

router = APIRouter(tags=["handoff"])

TASK_FORMAT = "personal-ai-os.task.v1"
RECEIPT_FORMAT = "agent-hub.receipt.v1"


class Evidence(BaseModel):
    kind: str = Field(max_length=30)
    id: str = Field(max_length=200)
    title: str = Field(max_length=500)
    text: str = Field(max_length=2000)
    chunk_id: int | None = None
    page_start: int | None = None
    page_end: int | None = None


class ProjectBrief(BaseModel):
    id: str = Field(max_length=128)
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=10000)


class TaskBrief(BaseModel):
    format: str
    handoff_id: str = Field(pattern=r"^[a-fA-F0-9-]{36}$")
    project: ProjectBrief
    evidence: list[Evidence] = Field(default_factory=list, max_length=40)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspace_path: str | None = Field(default=None, max_length=1024)
    create_workspace: bool = False


def import_task_brief_sync(
    payload: TaskBrief,
    user: str,
) -> dict:
    if payload.format != TASK_FORMAT:
        raise HTTPException(status_code=422, detail="不支持的任务包格式（需为 personal-ai-os.task.v1）")
    evidence = [e.model_dump(exclude_unset=True) for e in payload.evidence]
    fingerprint = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if fingerprint != payload.evidence_hash:
        raise HTTPException(status_code=422, detail="证据指纹（evidence_hash）校验不匹配")

    resolved_ws: str | None = None
    if payload.workspace_path and payload.workspace_path.strip():
        require_workbench_mode()
        try:
            resolved_ws = str(
                validate_local_workspace_path(
                    payload.workspace_path, create=payload.create_workspace
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    public_id = "handoff-" + payload.handoff_id
    scoped = scope_conversation_id(user, public_id)
    return _store_task(payload, user, public_id, scoped, evidence, resolved_ws)


@db_write_transaction
def _store_task(
    payload: TaskBrief,
    user: str,
    public_id: str,
    scoped: str,
    evidence: list[dict],
    resolved_ws: str | None,
) -> dict:
    lines = [
        f"项目名称：{payload.project.name}",
        f"项目目标：{payload.project.goal or '（未填写）'}",
        "",
        "以下为从知序（personal-ai-os）导入的项目背景、笔记、待办与已审记忆证据：",
    ]
    for i, item in enumerate(evidence, 1):
        lines.extend(["", f"[{i}] {item['title']} · {item['kind']}:{item['id']}", item["text"]])
    with Session(engine_module.engine) as session:
        origin = session.get(DeliveryRecord, "handoff:" + scoped)
        existing_conv = session.get(Conversation, scoped)
        if existing_conv:
            if not origin or json.loads(origin.payload).get("evidence_hash") != payload.evidence_hash:
                raise HTTPException(status_code=409, detail="该任务 ID 已存在但证据指纹不一致")
            if resolved_ws and existing_conv.workspace_path != resolved_ws:
                existing_conv.workspace_path = resolved_ws
                session.add(existing_conv)
                session.commit()
            return {
                "conversation_id": public_id,
                "project_id": payload.project.id,
                "workspace_path": existing_conv.workspace_path or "",
                "already_imported": True,
            }

        session.add(
            Conversation(
                id=scoped,
                type="single",
                name=payload.project.name,
                avatar="📂",
                agent_id="agent_pm",
                goal_objective=payload.project.goal or payload.project.name,
                goal_stage="planning",
                goal_next_action="核对知序导入材料，拆解实现方案",
                workspace_path=resolved_ws,
                source_project_id=payload.project.id,
            )
        )
        session.flush()
        session.add(
            Message(
                conversation_id=scoped,
                sender="user",
                content=json.dumps({"text": "\n".join(lines)}, ensure_ascii=False),
            )
        )
        session.add(
            DeliveryRecord(
                id="handoff:" + scoped,
                user_id=user,
                conversation_id=scoped,
                payload=json.dumps(
                    {
                        "handoff_id": payload.handoff_id,
                        "project_id": payload.project.id,
                        "project_name": payload.project.name,
                        "evidence_hash": payload.evidence_hash,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        session.commit()
    return {
        "conversation_id": public_id,
        "project_id": payload.project.id,
        "workspace_path": resolved_ws or "",
        "already_imported": False,
    }


def build_receipt_sync(user: str, conversation_id: str) -> tuple[dict, str]:
    """Build agent-hub.receipt.v1 payload and return (receipt_dict, source_project_id)."""
    try:
        scoped = scope_conversation_id(user, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with Session(engine_module.engine) as session:
        origin = session.get(DeliveryRecord, "handoff:" + scoped)
        conv = session.get(Conversation, scoped)
        if not origin or not conv:
            raise HTTPException(status_code=404, detail="当前会话尚未关联知序（personal-ai-os）导出的项目任务")
        metadata = json.loads(origin.payload)
        objective = conv.goal_objective or conv.name
        source_project_id = str(metadata.get("project_id") or conv.source_project_id or "")
        records = session.exec(
            select(DeliveryRecord)
            .where(DeliveryRecord.user_id == user, DeliveryRecord.conversation_id == scoped)
            .order_by(DeliveryRecord.created_at.desc())
        ).all()
        deployments = []
        for record in records:
            job = json.loads(record.payload)
            if job.get("action") == "deploy":
                deployments.append(
                    {k: job.get(k) for k in ("id", "status", "target", "input_hash", "artifact_id", "url")}
                )

    artifacts = get_artifacts(scoped, 20)
    receipt = {
        "format": RECEIPT_FORMAT,
        "handoff_id": metadata["handoff_id"],
        "evidence_hash": metadata["evidence_hash"],
        "conversation_id": conversation_id,
        "objective": objective,
        "artifacts": [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "version": a.get("version") or 1,
                "content_hash": a.get("content_hash") or "",
                "sandbox_status": a.get("sandbox_status") or "untested",
                "sandbox_output": a.get("sandbox_output") or "",
            }
            for a in artifacts
        ],
        "deployments": deployments[:5],
    }
    return receipt, source_project_id


@router.post("/handoffs", status_code=201)
async def import_task(payload: TaskBrief, request: Request):
    user = request_user_id(request)
    return await asyncio.to_thread(import_task_brief_sync, payload, user)


@router.get("/handoffs/{conversation_id}/receipt")
async def export_receipt(conversation_id: str, request: Request):
    user = request_user_id(request)
    receipt, _project_id = await asyncio.to_thread(build_receipt_sync, user, conversation_id)
    return receipt
