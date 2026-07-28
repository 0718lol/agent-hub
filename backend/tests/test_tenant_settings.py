"""Persistent tenant settings and task-local model isolation tests."""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.llm_client import llm_client
from app.core.quality_gate import quality_gate
from app.core.tenant_settings import (
    clear_tenant_client_cache,
    get_tenant_llm_client,
    get_tenant_quality_gate,
    save_tenant_llm_client,
    save_tenant_quality_gate,
)
from app.routers import quality as quality_router
from app.routers import settings as settings_router
from app.routers import tools as tools_router
from app.tools.registry import (
    TOOL_REGISTRY,
    AgentTool,
    ToolResult,
    execute_tool_call,
    reset_tool_tenant,
    set_tool_tenant,
)


def test_tenant_llm_configuration_is_persistent_and_isolated():
    first = get_tenant_llm_client("user-A")
    second = get_tenant_llm_client("user-B")
    first.configure("openai", "key-a", "https://a.example/v1", "model-a")
    second.configure("anthropic", "key-b", "https://b.example/v1", "model-b")
    save_tenant_llm_client("user-A", first)
    save_tenant_llm_client("user-B", second)

    clear_tenant_client_cache()
    restored_first = get_tenant_llm_client("user-A")
    restored_second = get_tenant_llm_client("user-B")

    assert restored_first.model == "model-a"
    assert restored_first.api_key == "key-a"
    assert restored_second.model == "model-b"
    assert restored_second.api_key == "key-b"


@pytest.mark.asyncio
async def test_contextual_llm_proxy_keeps_concurrent_tasks_isolated():
    first = get_tenant_llm_client("user-A")
    second = get_tenant_llm_client("user-B")
    first.model = "model-a"
    second.model = "model-b"

    async def read_in_context(client):
        token = llm_client.set_current(client)
        try:
            await asyncio.sleep(0)
            return llm_client.model
        finally:
            llm_client.reset_current(token)

    assert await asyncio.gather(read_in_context(first), read_in_context(second)) == [
        "model-a", "model-b",
    ]


@pytest.mark.asyncio
async def test_settings_api_uses_request_tenant(monkeypatch):
    monkeypatch.setattr(
        settings_router,
        "request_user_id",
        lambda request: request.headers["x-test-user"],
    )
    app = FastAPI()
    app.include_router(settings_router.router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_response = await client.post(
            "/api/settings/llm",
            headers={"x-test-user": "user-A"},
            json={
                "provider": "openai",
                "api_key": "key-a",
                "base_url": "https://a.example/v1",
                "model": "model-a",
            },
        )
        second_response = await client.get(
            "/api/settings/llm",
            headers={"x-test-user": "user-B"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["model"] != "model-a"


def test_contextual_quality_gate_keeps_tenants_isolated():
    first = get_tenant_quality_gate("user-A")
    second = get_tenant_quality_gate("user-B")
    first.best_of_n = 4
    second.best_of_n = 1
    save_tenant_quality_gate("user-A", first)
    save_tenant_quality_gate("user-B", second)

    first_token = quality_gate.set_current(first)
    try:
        assert quality_gate.best_of_n == 4
    finally:
        quality_gate.reset_current(first_token)

    second_token = quality_gate.set_current(second)
    try:
        assert quality_gate.best_of_n == 1
    finally:
        quality_gate.reset_current(second_token)


@pytest.mark.asyncio
async def test_quality_settings_api_is_tenant_scoped(monkeypatch):
    monkeypatch.setattr(
        quality_router,
        "request_user_id",
        lambda request: request.headers["x-test-user"],
    )
    app = FastAPI()
    app.include_router(quality_router.router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/settings/quality",
            headers={"x-test-user": "user-A"},
            json={"enabled": True, "best_of_n": 5, "max_retries": 2},
        )
        response = await client.get(
            "/api/settings/quality",
            headers={"x-test-user": "user-B"},
        )

    assert response.status_code == 200
    assert response.json()["best_of_n"] != 5


class _TenantTestTool(AgentTool):
    name = "tenant_test_tool"
    description = "Test tenant tool policy"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data="ok")


@pytest.mark.asyncio
async def test_runtime_tool_toggle_is_tenant_scoped(monkeypatch):
    monkeypatch.setattr(
        tools_router,
        "request_user_id",
        lambda request: request.headers["x-test-user"],
    )
    tool = _TenantTestTool()
    TOOL_REGISTRY[tool.name] = tool
    try:
        app = FastAPI()
        app.include_router(tools_router.router, prefix="/api")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            toggle = await client.post(
                f"/api/runtime-tools/{tool.name}/toggle",
                headers={"x-test-user": "user-A"},
            )
            first = await client.get(
                "/api/runtime-tools",
                headers={"x-test-user": "user-A"},
            )
            second = await client.get(
                "/api/runtime-tools",
                headers={"x-test-user": "user-B"},
            )

        first_tool = next(item for item in first.json() if item["name"] == tool.name)
        second_tool = next(item for item in second.json() if item["name"] == tool.name)
        assert toggle.json()["enabled"] is False
        assert first_tool["enabled"] is False
        assert second_tool["enabled"] is True

        first_token = set_tool_tenant("user-A")
        try:
            assert not (await execute_tool_call(tool.name, {})).success
        finally:
            reset_tool_tenant(first_token)
        second_token = set_tool_tenant("user-B")
        try:
            assert (await execute_tool_call(tool.name, {})).success
        finally:
            reset_tool_tenant(second_token)
    finally:
        TOOL_REGISTRY.pop(tool.name, None)
