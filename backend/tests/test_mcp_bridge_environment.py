"""Tests that external MCP processes receive only explicit environment values."""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.mcp_bridge import MCPServerProcess


def test_mcp_process_does_not_inherit_host_secrets(monkeypatch):
    monkeypatch.setenv("AGENTHUB_LLM_API_KEY", "super-secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    server = MCPServerProcess("example", "echo", [], {"SERVICE_TOKEN": "allowed"})

    assert server.env["PATH"] == "/usr/bin"
    assert server.env["SERVICE_TOKEN"] == "allowed"
    assert "AGENTHUB_LLM_API_KEY" not in server.env


class _FakeStdin:
    def write(self, data):
        return None

    async def drain(self):
        return None


@pytest.mark.asyncio
async def test_mcp_process_fails_pending_request_when_stdout_closes():
    """A dead MCP process must not leave an RPC future waiting forever."""
    stdout = asyncio.StreamReader()
    server = MCPServerProcess("example", "echo", [])
    server.process = SimpleNamespace(stdout=stdout, stdin=_FakeStdin(), stderr=None)
    server._running = True
    listener = asyncio.create_task(server._listen_stdout())

    request = asyncio.create_task(server.list_tools())
    await asyncio.sleep(0)
    stdout.feed_eof()

    with pytest.raises(RuntimeError, match="closed its stdout"):
        await asyncio.wait_for(request, timeout=0.5)

    await listener
    assert server.pending_requests == {}
    assert not server._running
