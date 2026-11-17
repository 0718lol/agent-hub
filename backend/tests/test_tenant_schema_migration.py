"""Regression tests for Step 2 explicit tenant_id schema, Alembic backfill, and SQL deployment persistence."""

import os
import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _alembic_config(db_file: str) -> Config:
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    return cfg


def test_alembic_upgrade_backfills_explicit_tenant_id_and_creates_deployment_records(tmp_path):
    db_path = str(tmp_path / "legacy_upgrade.db")
    cfg = _alembic_config(db_path)

    # 1. Construct a genuine pre-9c41e7b20a15 legacy database (without tenant_id columns)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
            INSERT INTO alembic_version (version_num) VALUES ('b6f3920ad4e1');

            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                avatar TEXT,
                agent_id TEXT,
                agents TEXT,
                preview TEXT,
                pinned BOOLEAN NOT NULL DEFAULT 0,
                archived BOOLEAN NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                goal_objective TEXT,
                goal_stage TEXT NOT NULL DEFAULT 'not_started',
                goal_latest_deliverable TEXT,
                goal_latest_artifact_id INTEGER,
                goal_pending_decision TEXT,
                goal_next_action TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                streaming INTEGER NOT NULL DEFAULT 0,
                pinned BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                name TEXT NOT NULL,
                language TEXT NOT NULL,
                code TEXT NOT NULL,
                quality_score INTEGER,
                sandbox_status TEXT NOT NULL DEFAULT 'untested',
                sandbox_output TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE cron_tasks (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                task_prompt TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL,
                last_run TEXT,
                next_run TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

            CREATE TABLE uploaded_files (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                extracted_text TEXT NOT NULL DEFAULT '',
                uploaded_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO conversations (id, type, name, created_at) VALUES (?, ?, ?, ?)",
            ("conv_pm", "single", "Local PM", "2026-11-17T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO conversations (id, type, name, created_at) VALUES (?, ?, ?, ?)",
            ("tenant__alice__conv__proj1", "single", "Alice Proj", "2026-11-17T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO conversations (id, type, name, created_at) VALUES (?, ?, ?, ?)",
            ("tenant__bob__conv__proj1", "single", "Bob Proj", "2026-11-17T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, sender, content, streaming, created_at) VALUES (?, ?, ?, ?, ?)",
            ("tenant__alice__conv__proj1", "user", '{"text": "alice secret"}', 0, "2026-11-17T00:01:00Z"),
        )
        conn.execute(
            "INSERT INTO artifacts (conversation_id, agent_id, name, language, code, sandbox_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("tenant__bob__conv__proj1", "agent_frontend", "index.html", "html", "<h1>Bob</h1>", "untested", "2026-11-17T00:02:00Z"),
        )
        conn.execute(
            "INSERT INTO cron_tasks (id, conversation_id, agent_id, task_prompt, interval_seconds, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("cron_1", "tenant__alice__conv__proj1", "agent_pm", "daily sync", 3600, "active", "2026-11-17T00:03:00Z"),
        )
        conn.execute(
            "INSERT INTO uploaded_files (id, original_name, stored_name, file_path, content_type, size, extracted_text, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "tenantfile__alice__abc.txt",
                "notes.txt",
                "tenantfile__alice__abc.txt",
                "/tmp/tenantfile__alice__abc.txt",
                "text/plain",
                12,
                "hello",
                "2026-11-17T00:04:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # 2. Upgrade to head (9c41e7b20a15)
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    try:
        convs = dict(conn.execute("SELECT id, tenant_id FROM conversations").fetchall())
        assert convs["conv_pm"] == "local"
        assert convs["tenant__alice__conv__proj1"] == "alice"
        assert convs["tenant__bob__conv__proj1"] == "bob"

        msg_tid = conn.execute(
            "SELECT tenant_id FROM messages WHERE conversation_id = 'tenant__alice__conv__proj1'"
        ).fetchone()[0]
        assert msg_tid == "alice"

        art_tid = conn.execute(
            "SELECT tenant_id FROM artifacts WHERE conversation_id = 'tenant__bob__conv__proj1'"
        ).fetchone()[0]
        assert art_tid == "bob"

        cron_tid = conn.execute("SELECT tenant_id FROM cron_tasks WHERE id = 'cron_1'").fetchone()[0]
        assert cron_tid == "alice"

        file_tid = conn.execute(
            "SELECT tenant_id FROM uploaded_files WHERE id = 'tenantfile__alice__abc.txt'"
        ).fetchone()[0]
        assert file_tid == "alice"

        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "deployment_records" in tables
        assert "delivery_records" in tables
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_indexed_tenant_queries_for_conversations_artifacts_and_local_search():
    from app.core.crud import (
        create_conversation,
        get_artifacts_grouped,
        get_conversations,
        save_artifact,
        save_message,
        search_messages,
    )
    from app.core.tenancy import scope_conversation_id
    from app.routers import artifacts as artifacts_router

    # Local workbench conversation (unprefixed ID, explicit tenant_id='local')
    create_conversation("conv_pm", "single", "Local PM", "", "agent_pm", tenant_id="local")
    save_message("conv_pm", "user", {"text": "知序双核本地检索关键字"}, tenant_id="local")

    # Two cloud tenants
    alice_conv = scope_conversation_id("tenant-alice", "app_v2")
    bob_conv = scope_conversation_id("tenant-bob", "app_v2")
    create_conversation(alice_conv, "single", "Alice App", "", "agent_frontend", tenant_id="tenant-alice")
    create_conversation(bob_conv, "single", "Bob App", "", "agent_frontend", tenant_id="tenant-bob")

    save_message(alice_conv, "user", {"text": "知序双核云端爱丽丝"}, tenant_id="tenant-alice")
    save_message(bob_conv, "user", {"text": "知序双核云端鲍勃"}, tenant_id="tenant-bob")

    save_artifact(alice_conv, "agent_frontend", "html", "<h1>Alice V1</h1>", name="app.html")
    save_artifact(bob_conv, "agent_frontend", "html", "<h1>Bob V1</h1>", name="app.html")

    assert [c["id"] for c in get_conversations(tenant_id="tenant-alice")] == [alice_conv]
    assert [c["id"] for c in get_conversations(tenant_id="tenant-bob")] == [bob_conv]
    assert [c["id"] for c in get_conversations(tenant_id="local")] == ["conv_pm"]

    # Local tenant message search works without tenant__local__conv__ prefix
    local_hits = search_messages("知序双核", tenant_id="local")
    assert len(local_hits) == 1
    assert local_hits[0]["conversation_id"] == "conv_pm"

    alice_hits = search_messages("知序双核", tenant_id="tenant-alice")
    assert len(alice_hits) == 1
    assert alice_hits[0]["conversation_id"] == alice_conv

    # Grouped artifacts endpoint strips internal tenant prefix and isolates tenants
    alice_grouped = get_artifacts_grouped(user_id="tenant-alice")
    assert len(alice_grouped) == 1
    assert alice_grouped[0]["code"] == "<h1>Alice V1</h1>"

    app = FastAPI()

    @app.middleware("http")
    async def _inject_alice(request, call_next):
        request.state.tenant_id = "tenant-alice"
        return await call_next(request)

    app.include_router(artifacts_router.router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/artifacts")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["conversation_id"] == "app_v2"
        assert items[0]["code"] == "<h1>Alice V1</h1>"


@pytest.mark.asyncio
async def test_deployment_queue_mirrors_to_sql_and_survives_redis_ttl_expiry(monkeypatch):
    from app.core.crud.deployments import get_deployment_record
    from app.services.deployment_queue import WORKER_HEARTBEAT_KEY, DeploymentQueue
    from tests.test_deployment_queue import FakeRedis

    queue = DeploymentQueue()
    redis = FakeRedis()
    redis.values[WORKER_HEARTBEAT_KEY] = "worker-sql-test"

    async def _available():
        return redis

    monkeypatch.setattr(queue, "ensure_available", _available)

    job = await queue.enqueue("tenant__alice__conv__web1", "alice", "web")
    await queue.update(job, status="success", stage="complete", progress=100, url="/published/web1/")

    # Verify SQL deployment_records row exists with explicit tenant_id
    sql_row = get_deployment_record(job.id, tenant_id="alice")
    assert sql_row is not None
    assert sql_row["tenant_id"] == "alice"
    assert sql_row["status"] == "success"
    assert sql_row["url"] == "/published/web1/"
    assert get_deployment_record(job.id, tenant_id="bob") is None

    # Simulate Redis status key TTL expiration; list_for_user still recovers from SQL!
    redis.values.pop(queue._status_key(job.id), None)
    redis.zsets.clear()

    recovered = await queue.list_for_user("alice", conversation_id="tenant__alice__conv__web1")
    assert len(recovered) == 1
    assert recovered[0].id == job.id
    assert recovered[0].url == "/published/web1/"

    isolated = await queue.list_for_user("bob")
    assert isolated == []
