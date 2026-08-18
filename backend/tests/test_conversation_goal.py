"""Conversation goal continuity and artifact authority regression tests."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.crud import create_conversation, get_conversations, save_artifact
from app.core.event_stream import MessageEvent, event_stream_manager
from app.core.tenancy import scope_conversation_id


@pytest.mark.asyncio
async def test_goal_api_is_partial_and_tenant_scoped():
    from app.routers import conversations

    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request, call_next):
        request.state.tenant_id = request.headers.get("x-test-tenant", "tenant-a")
        return await call_next(request)

    app.include_router(conversations.router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for tenant in ("tenant-a", "tenant-b"):
            await client.post(
                "/api/conversations",
                headers={"x-test-tenant": tenant},
                json={"id": "shared", "name": "Shared"},
            )
        first = await client.patch(
            "/api/conversations/shared/goal",
            headers={"x-test-tenant": "tenant-a"},
            json={"objective": "Build tenant A product", "stage": "building"},
        )
        second = await client.patch(
            "/api/conversations/shared/goal",
            headers={"x-test-tenant": "tenant-b"},
            json={"objective": "Audit tenant B product", "stage": "planning"},
        )
        first_goal = await client.get(
            "/api/conversations/shared/goal",
            headers={"x-test-tenant": "tenant-a"},
        )
        second_goal = await client.get(
            "/api/conversations/shared/goal",
            headers={"x-test-tenant": "tenant-b"},
        )

    assert first.status_code == second.status_code == 200
    assert first_goal.json()["objective"] == "Build tenant A product"
    assert first_goal.json()["stage"] == "building"
    assert second_goal.json()["objective"] == "Audit tenant B product"
    assert second_goal.json()["stage"] == "planning"


def test_artifact_updates_authoritative_goal_deliverable():
    conversation_id = scope_conversation_id("tenant-a", "artifact-goal")
    create_conversation(conversation_id, "single", "Artifact goal", "", "agent_frontend")

    artifact = save_artifact(conversation_id, "agent_frontend", "html", "<h1>Ready</h1>", "index.html")
    row = next(item for item in get_conversations() if item["id"] == conversation_id)

    assert row["goal_latest_artifact_id"] == artifact["id"]
    assert row["goal_latest_deliverable"] == "index.html"
    assert row["goal_stage"] == "validating"


@pytest.mark.asyncio
async def test_tool_round_keeps_original_user_goal_in_local_context(monkeypatch):
    from app.agents.base import BaseAgent
    from app.core.llm_client import llm_client
    from app.tools import registry

    conversation_id = "event-stream-goal"
    create_conversation(conversation_id, "single", "Event stream", "", "agent_test")
    event_stream_manager.clear_stream(conversation_id)
    model_calls = []

    async def fake_chat_stream(messages, _system, _tools=None):
        model_calls.append(messages)
        if len(model_calls) == 1:
            yield 'Checking files. [tool_call:file_list]{"path":"."}[/tool_call]'
        else:
            yield "The original goal is still available."

    async def fake_execute(_tool_name, _params):
        return SimpleNamespace(success=True, data={"files": ["index.html"]}, error=None)

    agent = BaseAgent()
    agent.agent_id = "agent_test"
    agent.system_prompt = "Test system prompt"
    monkeypatch.setattr(llm_client._default, "is_configured", lambda: True)
    monkeypatch.setattr(llm_client._default, "chat_stream", fake_chat_stream)
    monkeypatch.setattr(registry, "execute_tool_call", fake_execute)

    chunks = []
    async for chunk in agent.stream_reply("Build a stable dashboard", conversation_id=conversation_id):
        chunks.append(chunk)

    assert len(model_calls) == 2
    assert model_calls[1][0] == {"role": "user", "content": "Build a stable dashboard"}
    assert "工具结果" in model_calls[1][-1]["content"]
    events = event_stream_manager.get_stream(conversation_id)
    assert isinstance(events[0], MessageEvent)
    assert events[0].content == "Build a stable dashboard"
    assert "original goal" in "".join(chunks)
