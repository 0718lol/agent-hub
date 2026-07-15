"""Tests that external MCP processes receive only explicit environment values."""

from app.core.mcp_bridge import MCPServerProcess


def test_mcp_process_does_not_inherit_host_secrets(monkeypatch):
    monkeypatch.setenv("AGENTHUB_LLM_API_KEY", "super-secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    server = MCPServerProcess("example", "echo", [], {"SERVICE_TOKEN": "allowed"})

    assert server.env["PATH"] == "/usr/bin"
    assert server.env["SERVICE_TOKEN"] == "allowed"
    assert "AGENTHUB_LLM_API_KEY" not in server.env
