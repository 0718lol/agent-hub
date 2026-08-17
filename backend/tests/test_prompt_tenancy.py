"""Prompt preview tenant ownership regression tests."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_prompt_preview_hides_unowned_agent():
    from app.routers import prompt

    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request, call_next):
        request.state.tenant_id = "tenant-prompt"
        return await call_next(request)

    app.include_router(prompt.router, prefix="/api")
    transport = ASGITransport(app=app)
    with patch.object(prompt.agent_registry, "get_agent", AsyncMock(return_value=None)) as get_agent:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/prompt/preview",
                json={"agent_id": "agent_private", "message": "test"},
            )

    assert response.status_code == 404
    assert response.json() == {"detail": "Agent not found"}
    get_agent.assert_awaited_once_with("agent_private", "tenant-prompt")
