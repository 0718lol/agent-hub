"""
Deployment Record CRUD operations.

Persists tenant-indexed deployment job metadata in SQL so deployment history,
auditability, and handoff receipts survive Redis cache TTL expiration.
"""
from datetime import UTC, datetime

from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import DeploymentRecord
from app.core.tenancy import infer_tenant_id


@db_write_transaction
def sync_deployment_record(job_dict: dict) -> dict:
    job_id = str(job_dict.get("id") or "").strip()
    if not job_id:
        raise ValueError("Deployment job id is required")
    conversation_id = str(job_dict.get("conversation_id") or "")
    user_id = str(job_dict.get("user_id") or "local")
    tenant_id = infer_tenant_id(
        conversation_id,
        str(job_dict.get("tenant_id") or user_id or ""),
    )
    now = datetime.now(UTC).isoformat()
    with Session(_engine_mod.engine) as session:
        existing = session.get(DeploymentRecord, job_id)
        if existing is None:
            record = DeploymentRecord(
                id=job_id,
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                target=str(job_dict.get("target") or "web"),
                action=str(job_dict.get("action") or "deploy"),
                source_job_id=str(job_dict.get("source_job_id") or ""),
                status=str(job_dict.get("status") or "queued"),
                stage=str(job_dict.get("stage") or "queued"),
                progress=int(job_dict.get("progress") or 0),
                url=str(job_dict.get("url") or ""),
                result_type=str(job_dict.get("result_type") or ""),
                provider=str(job_dict.get("provider") or ""),
                published=bool(job_dict.get("published", False)),
                lifecycle=str(job_dict.get("lifecycle") or "active"),
                log=str(job_dict.get("log") or "")[:4000],
                created_at=str(job_dict.get("created_at") or now),
                updated_at=str(job_dict.get("updated_at") or now),
            )
            session.add(record)
        else:
            existing.tenant_id = tenant_id
            existing.user_id = user_id
            existing.conversation_id = conversation_id or existing.conversation_id
            existing.target = str(job_dict.get("target") or existing.target)
            existing.action = str(job_dict.get("action") or existing.action)
            existing.source_job_id = str(job_dict.get("source_job_id") or existing.source_job_id)
            existing.status = str(job_dict.get("status") or existing.status)
            existing.stage = str(job_dict.get("stage") or existing.stage)
            existing.progress = int(job_dict.get("progress", existing.progress))
            existing.url = str(job_dict.get("url") or existing.url)
            existing.result_type = str(job_dict.get("result_type") or existing.result_type)
            existing.provider = str(job_dict.get("provider") or existing.provider)
            existing.published = bool(job_dict.get("published", existing.published))
            existing.lifecycle = str(job_dict.get("lifecycle") or existing.lifecycle)
            existing.log = str(job_dict.get("log") or existing.log)[:4000]
            existing.updated_at = str(job_dict.get("updated_at") or now)
            record = existing
            session.add(record)
        session.commit()
        session.refresh(record)
        return record.model_dump()


def get_deployment_record(job_id: str, tenant_id: str | None = None) -> dict | None:
    with Session(_engine_mod.engine) as session:
        record = session.get(DeploymentRecord, job_id)
        if record is None:
            return None
        if tenant_id is not None and record.tenant_id != tenant_id:
            return None
        return record.model_dump()


def list_deployment_records(
    tenant_id: str,
    conversation_id: str | None = None,
    limit: int = 50,
    action: str | None = "deploy",
) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(DeploymentRecord).where(DeploymentRecord.tenant_id == tenant_id)
        if conversation_id:
            statement = statement.where(DeploymentRecord.conversation_id == conversation_id)
        if action:
            statement = statement.where(DeploymentRecord.action == action)
        statement = statement.order_by(DeploymentRecord.created_at.desc()).limit(limit)
        return [row.model_dump() for row in session.exec(statement).all()]


@db_write_transaction
def delete_deployment_record(job_id: str) -> bool:
    with Session(_engine_mod.engine) as session:
        record = session.get(DeploymentRecord, job_id)
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True
