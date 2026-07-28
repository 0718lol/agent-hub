"""Tenant-scoped metrics, trace, and artifact API tests."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.crud.artifacts import save_artifact
from app.core.metrics import TaskTrace
from app.core.tenancy import scope_conversation_id
from app.routers import artifacts as artifacts_router
from app.routers import metrics as metrics_router


@pytest.fixture
def observability_app(monkeypatch):
    app = FastAPI()
    app.include_router(metrics_router.router, prefix="/api")
    app.include_router(artifacts_router.router, prefix="/api")
    monkeypatch.setattr(metrics_router, "request_user_id", lambda _request: "user-A")
    monkeypatch.setattr(artifacts_router, "request_user_id", lambda _request: "user-A")
    return app


@pytest.mark.asyncio
async def test_metrics_and_traces_only_return_current_tenant(observability_app, monkeypatch):
    own_trace = TaskTrace(
        task_id="own",
        conversation_id=scope_conversation_id("user-A", "shared"),
        user_input="own request",
    )
    own_step = own_trace.add_step("agent_frontend", "Frontend")
    own_step.finish(tokens=25, score=88)
    own_trace.finish()

    other_trace = TaskTrace(
        task_id="other",
        conversation_id=scope_conversation_id("user-B", "shared"),
        user_input="other request",
    )
    other_step = other_trace.add_step("agent_backend", "Backend")
    other_step.finish(tokens=50, score=70)
    other_trace.finish()

    monkeypatch.setattr(metrics_router.metrics, "traces", [own_trace, other_trace])
    transport = ASGITransport(app=observability_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        dashboard_response = await client.get("/api/metrics")
        traces_response = await client.get("/api/metrics/traces?limit=10")

    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["total_requests"] == 1
    assert set(dashboard_response.json()["agent_summary"]) == {"agent_frontend"}
    assert [trace["task_id"] for trace in traces_response.json()] == ["own"]


@pytest.mark.asyncio
async def test_artifacts_only_return_current_tenant(observability_app):
    own_conversation = scope_conversation_id("user-A", "shared")
    other_conversation = scope_conversation_id("user-B", "shared")
    save_artifact(own_conversation, "agent_frontend", "html", "<h1>v1</h1>", "index.html")
    save_artifact(own_conversation, "agent_frontend", "html", "<h1>v2</h1>", "index.html")
    save_artifact(other_conversation, "agent_frontend", "html", "<h1>private</h1>", "secret.html")

    transport = ASGITransport(app=observability_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        all_response = await client.get("/api/artifacts?limit=15")
        conversation_response = await client.get("/api/artifacts?conversation_id=shared")

    assert all_response.status_code == 200
    assert [artifact["name"] for artifact in all_response.json()] == ["index.html"]
    assert all_response.json()[0]["total_versions"] == 2
    assert [artifact["name"] for artifact in conversation_response.json()] == ["index.html"]
