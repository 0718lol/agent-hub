"""Minimal API endpoint tests — smoke tests for core REST routes."""

import pytest


@pytest.mark.anyio
async def test_get_llm_settings(client):
    """GET /api/settings/llm should return current LLM config."""
    resp = await client.get("/api/settings/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "configured" in data


@pytest.mark.anyio
async def test_get_conversations(client):
    """GET /api/conversations should return a list."""
    resp = await client.get("/api/conversations")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_get_runtime_tools(client):
    """GET /api/runtime-tools should list registered tools."""
    resp = await client.get("/api/runtime-tools")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3  # web_search, http_request, file_read/write/list
    names = [t["name"] for t in data]
    assert "web_search" in names
    assert "http_request" in names


@pytest.mark.anyio
async def test_get_prompt_tools(client):
    """GET /api/tools should list prompt-addon tools."""
    resp = await client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(t["id"] == "code_gen" for t in data)


@pytest.mark.anyio
async def test_get_quality_settings(client):
    """GET /api/settings/quality should return quality gate config."""
    resp = await client.get("/api/settings/quality")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data


@pytest.mark.anyio
async def test_get_prompt_layers(client):
    """GET /api/prompt/layers should return layer list."""
    resp = await client.get("/api/prompt/layers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_get_cron_tasks(client):
    """GET /api/cron should return cron task list."""
    resp = await client.get("/api/cron")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


@pytest.mark.anyio
async def test_runtime_tool_toggle(client):
    """POST /api/runtime-tools/{name}/toggle should toggle tool state."""
    resp = await client.post("/api/runtime-tools/web_search/toggle")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    # Toggle back
    await client.post("/api/runtime-tools/web_search/toggle")
