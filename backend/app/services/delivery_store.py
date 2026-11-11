"""Immutable deployment inputs and durable receipts shared by API and workers."""

import hashlib
import io
import json
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from sqlmodel import Session, select

import app.core._engine as engine_module
from app.core.crud.artifacts import get_artifact
from app.core.crud.utils import db_write_transaction
from app.core.models import DeliveryRecord, DeliverySnapshot


def _manifest(archive: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        return {
            info.filename: hashlib.sha256(bundle.read(info)).hexdigest()
            for info in bundle.infolist()
            if not info.is_dir()
        }


@db_write_transaction
def freeze_delivery(conversation_id: str, user_id: str, artifact_id: int | None = None) -> str:
    from app.services.deployment import DeploymentError, build_project_archive, get_workspace_path

    artifact = get_artifact(artifact_id, user_id) if artifact_id else None
    if artifact_id and (not artifact or artifact["conversation_id"] != conversation_id):
        raise DeploymentError("Artifact not found in this conversation")
    if artifact:
        # A selected artifact is an explicit single-file delivery. Multi-file
        # projects freeze the complete workspace via the snapshot path below.
        name = "index.html" if artifact["language"].lower() in {"html", "htm"} else artifact["name"]
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name:
            raise DeploymentError("Invalid artifact filename")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(name, artifact["code"])
        archive = buffer.getvalue()
    else:
        archive = build_project_archive(get_workspace_path(conversation_id))
    manifest = json.dumps(_manifest(archive), sort_keys=True, separators=(",", ":"))
    snapshot = DeliverySnapshot(
        id=uuid.uuid4().hex,
        user_id=user_id,
        conversation_id=conversation_id,
        artifact_id=artifact_id,
        content_hash=hashlib.sha256(manifest.encode()).hexdigest(),
        manifest=manifest,
        archive=archive,
    )
    with Session(engine_module.engine) as session:
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)
        return snapshot.id


def read_snapshot(snapshot_id: str, user_id: str, conversation_id: str) -> dict:
    from app.services.deployment import DeploymentError

    with Session(engine_module.engine) as session:
        snapshot = session.get(DeliverySnapshot, snapshot_id)
        if not snapshot or snapshot.user_id != user_id or snapshot.conversation_id != conversation_id:
            raise DeploymentError("Delivery snapshot not found")
        return snapshot.model_dump()


@contextmanager
def materialize_snapshot(snapshot_id: str, user_id: str, conversation_id: str):
    from app.services.deployment import MAX_DEPLOY_BYTES, MAX_DEPLOY_FILES, DeploymentError

    snapshot = read_snapshot(snapshot_id, user_id, conversation_id)
    manifest = json.loads(snapshot["manifest"])
    if (
        hashlib.sha256(snapshot["manifest"].encode()).hexdigest() != snapshot["content_hash"]
        or _manifest(snapshot["archive"]) != manifest
    ):
        raise DeploymentError("Delivery snapshot integrity check failed")
    with tempfile.TemporaryDirectory(prefix="agenthub-delivery-") as directory:
        root = Path(directory)
        with zipfile.ZipFile(io.BytesIO(snapshot["archive"])) as bundle:
            infos = bundle.infolist()
            if len(infos) > MAX_DEPLOY_FILES or sum(i.file_size for i in infos) > MAX_DEPLOY_BYTES:
                raise DeploymentError("Delivery snapshot exceeds size limit")
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                    raise DeploymentError("Invalid snapshot path")
                dest = root.joinpath(*path.parts)
                if info.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(bundle.read(info))
                    mode = (info.external_attr >> 16) & 0o777
                    if mode:
                        dest.chmod(mode)
        yield root


@db_write_transaction
def discard_unused_snapshot(snapshot_id: str):
    """Clean up rejected submissions without removing inputs used by retries."""
    with Session(engine_module.engine) as session:
        records = session.exec(select(DeliveryRecord)).all()
        if any(json.loads(row.payload).get("snapshot_id") == snapshot_id for row in records):
            return
        snapshot = session.get(DeliverySnapshot, snapshot_id)
        if snapshot:
            session.delete(snapshot)
            session.commit()


@db_write_transaction
def persist_job(job):
    with Session(engine_module.engine) as session:
        record = session.get(DeliveryRecord, job.id)
        if record is None:
            record = DeliveryRecord(
                id=job.id,
                user_id=job.user_id,
                conversation_id=job.conversation_id,
                created_at=job.created_at,
                payload="",
            )
        record.payload = json.dumps(asdict(job), ensure_ascii=False)
        session.add(record)
        session.commit()


def read_job(job_id: str):
    with Session(engine_module.engine) as session:
        record = session.get(DeliveryRecord, job_id)
        return json.loads(record.payload) if record else None


def list_jobs(user_id: str, limit: int):
    with Session(engine_module.engine) as session:
        rows = session.exec(
            select(DeliveryRecord)
            .where(DeliveryRecord.user_id == user_id)
            .where(~DeliveryRecord.id.startswith("handoff:"))
            .order_by(DeliveryRecord.created_at.desc())
            .limit(limit)
        ).all()
        return [json.loads(row.payload) for row in rows if not row.id.startswith("handoff:")]


@db_write_transaction
def delete_job(job_id: str):
    with Session(engine_module.engine) as session:
        record = session.get(DeliveryRecord, job_id)
        if record:
            snapshot_id = json.loads(record.payload).get("snapshot_id")
            session.delete(record)
            session.flush()
            # Retries share their original snapshot, so delete it only after the
            # final receipt referencing it has been removed.
            if snapshot_id:
                others = session.exec(select(DeliveryRecord)).all()
                if not any(json.loads(other.payload).get("snapshot_id") == snapshot_id for other in others):
                    snapshot = session.get(DeliverySnapshot, snapshot_id)
                    if snapshot:
                        session.delete(snapshot)
            session.commit()
