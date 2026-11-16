"""Stable account tenant and browser isolation regression tests."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.models import Conversation  # noqa: F401 - register SQLModel tables before fixtures run
from app.core.tenancy import belongs_to_user, public_conversation_id, scope_conversation_id


def test_conversation_namespace_roundtrip():
    scoped = scope_conversation_id("user-A", "conv_pm")
    assert scoped != scope_conversation_id("user-B", "conv_pm")
    assert public_conversation_id(scoped) == "conv_pm"
    assert belongs_to_user(scoped, "user-A")
    assert not belongs_to_user(scoped, "user-B")


@pytest.mark.asyncio
async def test_two_accounts_can_use_same_public_conversation_id():
    from app.routers import auth, conversations

    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as first, AsyncClient(
        transport=transport, base_url="http://test"
    ) as second:
        first_registration = await first.post(
            "/api/auth/register",
            json={"username": "first-user", "password": "password123"},
        )
        second_registration = await second.post(
            "/api/auth/register",
            json={"username": "second-user", "password": "password123"},
        )
        assert first_registration.status_code == 201
        assert second_registration.status_code == 201
        assert (
            first_registration.json()["user"]["tenant_id"]
            != second_registration.json()["user"]["tenant_id"]
        )
        await first.post("/api/conversations", json={"id": "shared-id", "name": "First", "type": "single"})
        await second.post("/api/conversations", json={"id": "shared-id", "name": "Second", "type": "single"})
        first_rows = await first.get("/api/conversations")
        second_rows = await second.get("/api/conversations")

    first_shared = next(row for row in first_rows.json() if row["id"] == "shared-id")
    second_shared = next(row for row in second_rows.json() if row["id"] == "shared-id")
    assert first_shared["name"] == "First"
    assert second_shared["name"] == "Second"


@pytest.mark.asyncio
async def test_new_tenant_copies_only_builtin_conversation_templates():
    from app.core.crud import create_conversation
    from app.routers.conversations import _tenant_conversations

    create_conversation("conv_pm", "single", "PM", "", "agent_pm")
    create_conversation("private_legacy", "single", "Private legacy metadata", "", "agent_private")

    rows = await _tenant_conversations("tenant-new")

    assert any(row["id"] == "conv_pm" for row in rows)
    assert not any(row["id"] == "private_legacy" for row in rows)


async def test_workflow_round_trip_and_compilation_are_tenant_scoped(monkeypatch):
    from app.core.config import settings
    from app.core.llm_client import llm_client
    from app.main import app

    monkeypatch.setattr(settings, "llm_api_key", "")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as first, AsyncClient(
        transport=transport, base_url="http://test"
    ) as second:
        tenants = []
        try:
            for client, username in [(first, "workflow-first"), (second, "workflow-second")]:
                registration = await client.post(
                    "/api/auth/register", json={"username": username, "password": "password123"}
                )
                assert registration.status_code == 201
                tenants.append(registration.json()["user"]["tenant_id"])

            secret = "workflow-test-credential"
            llm = await first.post("/api/settings/llm", json={
                "provider": "openai", "api_key": secret, "base_url": "https://example.test/v1", "model": 'quote"test',
            })
            assert llm.status_code == 200

            imported = await first.post("/api/workflow/import", json={
                "custom_agents": [{
                    "agent_id": "agent_workflow_private",
                    "name": "Private agent",
                    "system_prompt": "Only the owner's script should initially contain this prompt.",
                }],
                "hil": {"human_input_mode": "COOLDOWN", "cooldown_steps": 3},
            })
            assert imported.json() == {"status": "ok", "imported_agents_count": 1}
            owner_workflow = (await first.get("/api/workflow/export/conv_pm")).json()
            stranger_workflow = (await second.get("/api/workflow/export/conv_pm")).json()
            assert len(owner_workflow["custom_agents"]) == 1
            assert owner_workflow["hil"]["cooldown_steps"] == 3
            assert stranger_workflow["custom_agents"] == []
            assert stranger_workflow["hil"]["human_input_mode"] == "NEVER"

            for client in [first, second]:
                compiled = await client.post("/api/workflow/compile/conv_pm")
                assert compiled.status_code == 200
                code = compiled.json()["code"]
                compile(code, "exported_team.py", "exec")
                assert ("agent_workflow_private" in code) is (client is first)
                assert secret not in code
                assert "AGENTHUB_LLM_API_KEY" in code

            copied = await second.post("/api/workflow/import", json=owner_workflow)
            assert copied.json() == {"status": "ok", "imported_agents_count": 1}
            repeated = await second.post("/api/workflow/import", json=owner_workflow)
            assert repeated.status_code == 200
            copies = (await second.get("/api/workflow/export/conv_pm")).json()["custom_agents"]
            assert len(copies) == 1
            copy = copies[0]
            original = owner_workflow["custom_agents"][0]
            assert copy["agent_id"] != original["agent_id"]
            assert copy["system_prompt"] == original["system_prompt"]
        finally:
            for tenant in tenants:
                llm_client.evict(tenant)
