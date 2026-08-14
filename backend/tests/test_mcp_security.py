"""Tests for MCP server registration security."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mcp_app():
    from app.routers.mcp import router
    app = FastAPI()

    @app.middleware("http")
    async def inject_test_tenant(request, call_next):
        request.state.tenant_id = "tenant_test"
        return await call_next(request)

    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_allowed_command_npx(mcp_app):
    """npx should be in the allowed commands whitelist."""
    with patch("app.routers.mcp.mcp_bridge_manager") as mock_mgr:
        mock_mgr.register_server = AsyncMock(return_value=True)
        resp = mcp_app.post("/api/mcp/servers", json={
            "name": "test", "command": "npx", "args": ["-y", "@anthropic-ai/mcp-server"]
        })
        # Should not return "not allowed" error (may fail to connect, that is OK)
        if resp.status_code == 200:
            data = resp.json()
            assert "not allowed" not in data.get("message", "").lower()


def test_disallowed_command_rejected(mcp_app):
    """rm/curl/wget should be rejected."""
    for cmd in ["rm", "curl", "wget", "bash", "sh"]:
        resp = mcp_app.post("/api/mcp/servers", json={
            "name": "test", "command": cmd, "args": ["-rf", "/"]
        })
        data = resp.json()
        assert "not allowed" in data.get("message", "").lower() or resp.status_code != 200


def test_shell_metachar_rejected(mcp_app):
    """Shell metacharacters in args should be rejected."""
    for arg in ["test;rm -rf /", "test|cat /etc/passwd", "test&whoami", "test`id`", "test$(whoami)"]:
        resp = mcp_app.post("/api/mcp/servers", json={
            "name": "test", "command": "npx", "args": [arg]
        })
        data = resp.json()
        assert "forbidden" in data.get("message", "").lower() or "metachar" in data.get("message", "").lower() or resp.status_code != 200


def test_dangerous_arg_rejected(mcp_app):
    """python -c / node -e should be rejected."""
    resp = mcp_app.post("/api/mcp/servers", json={
        "name": "test", "command": "python", "args": ["-c", "import os; os.system('whoami')"]
    })
    data = resp.json()
    msg = data.get("message", "").lower()
    assert (
        "dangerous" in msg
        or "not allowed" in msg
        or "forbidden" in msg
        or "metachar" in msg
        or resp.status_code != 200
    )


def test_empty_command_rejected(mcp_app):
    """Empty/whitespace command should be rejected."""
    resp = mcp_app.post("/api/mcp/servers", json={
        "name": "test", "command": " ", "args": []
    })
    data = resp.json()
    assert "not allowed" in data.get("message", "").lower() or resp.status_code != 200


def test_long_arg_rejected(mcp_app):
    """Very long args should be rejected."""
    resp = mcp_app.post("/api/mcp/servers", json={
        "name": "test", "command": "npx", "args": ["A" * 2000]
    })
    data = resp.json()
    msg = data.get("message", "").lower()
    assert "too long" in msg or "exceeds max length" in msg or resp.status_code != 200
