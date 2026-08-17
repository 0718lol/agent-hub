"""Cron tenant context and ownership regression tests."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.crud import create_conversation
from app.core.tenancy import current_tenant_id, scope_conversation_id
from app.services.daemon_scheduler import DaemonScheduler


@pytest.mark.asyncio
async def test_scheduler_restores_tenant_context_for_background_task():
    scheduler = DaemonScheduler()
    seen = []

    async def run_for_tenant(task, tenant_id):
        seen.append((tenant_id, current_tenant_id()))

    task = {
        "id": "cron-test",
        "conversation_id": scope_conversation_id("tenant-cron", "conv_pm"),
        "agent_id": "agent_pm",
        "task_prompt": "test",
        "interval_seconds": 60,
    }
    with patch.object(scheduler, "_run_task_for_tenant", side_effect=run_for_tenant):
        await scheduler._run_task(task)

    assert seen == [("tenant-cron", "tenant-cron")]
    assert current_tenant_id() is None


@pytest.mark.asyncio
async def test_cron_creation_requires_owned_conversation_and_agent():
    from app.routers import cron

    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request, call_next):
        request.state.tenant_id = "tenant-cron"
        return await call_next(request)

    app.include_router(cron.router, prefix="/api")
    create_conversation(
        scope_conversation_id("tenant-cron", "conv_pm"),
        "single",
        "PM",
        "",
        "agent_pm",
    )
    payload = {
        "conversation_id": "conv_pm",
        "agent_id": "agent_pm",
        "task_prompt": "check",
        "interval_seconds": 60,
    }
    transport = ASGITransport(app=app)
    with patch.object(cron.agent_registry, "get_agent", AsyncMock(return_value=object())) as get_agent:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/cron", json=payload)
            missing_conversation = await client.post(
                "/api/cron",
                json={**payload, "conversation_id": "missing"},
            )

    assert created.status_code == 200
    assert missing_conversation.status_code == 404
    get_agent.assert_awaited_with("agent_pm", "tenant-cron")


@pytest.mark.asyncio
async def test_cron_creation_rejects_unowned_agent():
    from app.routers import cron

    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request, call_next):
        request.state.tenant_id = "tenant-cron"
        return await call_next(request)

    app.include_router(cron.router, prefix="/api")
    create_conversation(
        scope_conversation_id("tenant-cron", "conv_pm"),
        "single",
        "PM",
        "",
        "agent_pm",
    )
    transport = ASGITransport(app=app)
    with patch.object(cron.agent_registry, "get_agent", AsyncMock(return_value=None)):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/cron",
                json={
                    "conversation_id": "conv_pm",
                    "agent_id": "agent_private",
                    "task_prompt": "check",
                    "interval_seconds": 60,
                },
            )

    assert response.status_code == 404
