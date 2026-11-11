"""Artifact authority, frozen inputs and durable receipt regressions."""

import io
import zipfile
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session

from app.core._engine import engine
from app.core.crud import create_conversation
from app.core.crud.artifacts import get_artifact, save_artifact
from app.core.models import DeliverySnapshot
from app.core.sandbox import ExecutionResult
from app.core.tenancy import scope_conversation_id
from app.services.delivery_store import freeze_delivery, materialize_snapshot, read_snapshot
from app.services.deployment import DeploymentError, run_deployment_pipeline
from app.services.deployment_queue import DeploymentJob, DeploymentQueue, DeploymentQueueUnavailable


def artifact(user="alice", code="<h1>original</h1>"):
    conv = scope_conversation_id(user, "project")
    create_conversation(conv, "single", "Project", "", "agent_frontend")
    return save_artifact(conv, "agent_frontend", "html", code, "index.html")


def test_lineage_and_ownership():
    first = artifact()
    second = save_artifact(
        first["conversation_id"], "agent_frontend", "html", "<h1>edited</h1>", "index.html", parent_id=first["id"]
    )
    assert (first["version"], second["version"], second["parent_id"]) == (1, 2, first["id"])
    assert first["content_hash"] != second["content_hash"]
    assert get_artifact(first["id"], "alice")["code"] == "<h1>original</h1>"
    assert get_artifact(first["id"], "bob") is None


@pytest.mark.asyncio
async def test_selected_version_deploys_without_current_workspace(monkeypatch):
    first = artifact()
    snapshot = freeze_delivery(first["conversation_id"], "alice", first["id"])
    save_artifact(first["conversation_id"], "agent_frontend", "html", "<h1>newer</h1>", "index.html")
    captured = []

    def save_archive(content, user, extension):
        with zipfile.ZipFile(io.BytesIO(content)) as bundle:
            captured.append(bundle.read("index.html").decode())
        return "/uploads/frozen.zip"

    monkeypatch.setattr("app.services.deployment._save_artifact", save_archive)
    await run_deployment_pipeline(
        first["conversation_id"],
        user_id="alice",
        target="web",
        token="",
        site_id="",
        progress=AsyncMock(),
        snapshot_id=snapshot,
    )
    assert captured == ["<h1>original</h1>"]


def test_project_snapshot_stays_fixed_after_workspace_changes(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<h1>frozen</h1>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "script.js").write_text("console.log(1)")
    monkeypatch.setattr("app.services.deployment.get_workspace_path", lambda conv: tmp_path)
    snapshot = freeze_delivery(scope_conversation_id("alice", "project"), "alice")
    (tmp_path / "index.html").write_text("<h1>changed while queued</h1>")
    with materialize_snapshot(snapshot, "alice", scope_conversation_id("alice", "project")) as frozen:
        assert (frozen / "index.html").read_text() == "<h1>frozen</h1>"
        assert (frozen / "assets" / "script.js").read_text() == "console.log(1)"
    with pytest.raises(DeploymentError):
        read_snapshot(snapshot, "bob", scope_conversation_id("alice", "project"))


def test_modified_snapshot_is_rejected():
    first = artifact()
    snapshot = freeze_delivery(first["conversation_id"], "alice", first["id"])
    with Session(engine) as session:
        row = session.get(DeliverySnapshot, snapshot)
        row.manifest = "{}"
        session.add(row)
        session.commit()
    with pytest.raises(DeploymentError, match="integrity"):
        with materialize_snapshot(snapshot, "alice", first["conversation_id"]):
            pass


def test_unused_snapshots_are_removed_but_retry_inputs_are_kept():
    from app.services.delivery_store import discard_unused_snapshot, persist_job

    first = artifact()
    snapshot = freeze_delivery(first["conversation_id"], "alice", first["id"])
    persist_job(DeploymentJob(id="retry", user_id="alice", conversation_id=first["conversation_id"], target="web", snapshot_id=snapshot))
    discard_unused_snapshot(snapshot)
    assert read_snapshot(snapshot, "alice", first["conversation_id"])
    unused = freeze_delivery(first["conversation_id"], "alice", first["id"])
    discard_unused_snapshot(unused)
    with pytest.raises(DeploymentError, match="not found"):
        read_snapshot(unused, "alice", first["conversation_id"])


@pytest.mark.asyncio
async def test_receipt_survives_unavailable_redis():
    from app.services.delivery_store import persist_job

    instance = DeploymentQueue()
    job = DeploymentJob(
        id="job",
        user_id="alice",
        conversation_id=scope_conversation_id("alice", "project"),
        target="web",
        status="success",
    )
    persist_job(job)
    instance.ensure_available = AsyncMock(side_effect=DeploymentQueueUnavailable("offline"))
    assert (await instance.get("job")).status == "success"
    assert [j.id for j in await instance.list_for_user("alice")] == ["job"]
    assert await instance.list_for_user("bob") == []


@pytest.mark.asyncio
async def test_edit_and_validate_reference_exact_version(monkeypatch):
    from app.routers import artifacts

    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.tenant_id = request.headers.get("x-user", "alice")
        return await call_next(request)

    app.include_router(artifacts.router, prefix="/api")
    first = artifact(code="print(1)")
    # Set the language through the normal save API.
    first = save_artifact(first["conversation_id"], "agent_frontend", "python", "print(1)", "main.py")
    execute = AsyncMock(return_value=ExecutionResult(language="python", status="success", stdout="1", exit_code=0))
    monkeypatch.setattr("app.core.sandbox.execute_code", execute)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        forbidden = await client.get("/api/artifacts/" + str(first["id"]), headers={"x-user": "bob"})
        assert forbidden.status_code == 404
        edit = await client.post(f"/api/artifacts/{first['id']}/versions", json={"code": "print(2)"})
        assert edit.status_code == 201
        second = edit.json()
        response = await client.post(f"/api/artifacts/{first['id']}/validate")
        assert response.json()["sandbox_status"] == "success"
        execute.assert_awaited_once_with("print(1)", "python", timeout=10)
        assert get_artifact(second["id"], "alice")["sandbox_status"] == "untested"


@pytest.mark.asyncio
async def test_project_brief_roundtrip_is_scoped_and_idempotent():
    import hashlib
    import json
    from app.routers import handoff

    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.tenant_id = request.headers.get("x-user", "alice")
        return await call_next(request)

    app.include_router(handoff.router, prefix="/api")
    evidence = [{"kind": "note", "id": "n1", "title": "预算", "text": "预算 100 元", "page_start": None, "page_end": None}]
    task = {
        "format": "personal-ai-os.task.v1",
        "handoff_id": "12345678-1234-1234-1234-123456789abc",
        "project": {"id": "p1", "name": "任务交接", "goal": "实现预算页面"},
        "evidence": evidence,
        "evidence_hash": hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/handoffs", json=task)
        assert response.status_code == 201, response.text
        conv = response.json()["conversation_id"]
        again = await client.post("/api/handoffs", json=task)
        assert again.json()["already_imported"]
        scoped = scope_conversation_id("alice", conv)
        save_artifact(scoped, "agent_frontend", "html", "<h1>100</h1>", "index.html")
        receipt = (await client.get("/api/handoffs/" + conv + "/receipt")).json()
        assert receipt["evidence_hash"] == task["evidence_hash"]
        assert receipt["artifacts"][0]["sandbox_status"] == "untested"
        assert "code" not in receipt["artifacts"][0]
        forbidden = await client.get("/api/handoffs/" + conv + "/receipt", headers={"x-user": "bob"})
        assert forbidden.status_code == 404
        task["evidence"][0]["text"] = "tampered"
        invalid = await client.post("/api/handoffs", json=task)
        assert invalid.status_code == 422
        task["evidence_hash"] = hashlib.sha256(json.dumps(task["evidence"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        conflicting = await client.post("/api/handoffs", json=task)
        assert conflicting.status_code == 409


def test_migration_backfills_artifact_lineage_and_can_downgrade(tmp_path):
    import hashlib
    import sqlite3
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[1]
    db = tmp_path / "migration.db"
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", "sqlite:///" + str(db))
    command.upgrade(config, "b6f3920ad4e1")
    with sqlite3.connect(db) as conn:
        # Earlier initial migrations use current metadata on a fresh database.
        # Remove the new columns to exercise a real pre-change database.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(artifacts)")}
        for name in ("version", "parent_id", "content_hash"):
            if name in columns:
                conn.execute("ALTER TABLE artifacts DROP COLUMN " + name)
        for table in ("delivery_records", "delivery_snapshots"):
            conn.execute("DROP TABLE IF EXISTS " + table)
        conn.execute("INSERT INTO conversations(id,type,name,goal_stage,created_at) VALUES ('old','single','Old','not_started','2026-01-01')")
        for code in ("first", "second"):
            conn.execute("INSERT INTO artifacts(conversation_id,agent_id,name,language,code,sandbox_status,created_at) VALUES ('old','agent_frontend','index.html','html',?,'untested','2026-01-01')", (code,))
    command.upgrade(config, "head")
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT id,version,parent_id,content_hash,code FROM artifacts ORDER BY id").fetchall()
        assert [(row[1],row[2]) for row in rows] == [(1,None),(2,rows[0][0])]
        assert all(row[3] == hashlib.sha256(row[4].encode()).hexdigest() for row in rows)
        assert conn.execute("SELECT count(*) FROM delivery_snapshots").fetchone()[0] == 0
    command.downgrade(config, "b6f3920ad4e1")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT code FROM artifacts ORDER BY id").fetchall() == [("first",),("second",)]
        assert "version" not in {row[1] for row in conn.execute("PRAGMA table_info(artifacts)")}
