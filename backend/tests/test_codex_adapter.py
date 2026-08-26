import json
import os

import pytest

from app.adapters.base import AdapterConfig
from app.adapters.codex_adapter import CodexAdapter, SESSION_CONFIG_KEY
from app.core.tenant_config import get_tenant_json


class FakeWriter:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, data):
        self.data += data

    async def drain(self):
        return None

    def close(self):
        self.closed = True


class FakeReader:
    def __init__(self, lines=None, payload=b""):
        self.lines = list(lines or [])
        self.payload = payload

    async def readline(self):
        return self.lines.pop(0) if self.lines else b""

    async def read(self):
        return self.payload


class FakeProcess:
    def __init__(self, events=None, stderr=b"", returncode=0, communicate=None):
        lines = [json.dumps(event, ensure_ascii=False).encode() + b"\n" for event in (events or [])]
        self.stdin = FakeWriter()
        self.stdout = FakeReader(lines)
        self.stderr = FakeReader(payload=stderr)
        self.returncode = returncode
        self._communicate = communicate

    async def wait(self):
        return self.returncode

    async def communicate(self):
        return self._communicate or (b"", self.stderr.payload)

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def make_adapter(tmp_path, executable, **overrides):
    extra = {
        "_tenant_id": "tenant-codex",
        "codex_path": str(executable),
        "workspace": str(tmp_path),
        "sandbox": "workspace-write",
    }
    extra.update(overrides.pop("extra", {}))
    return CodexAdapter(AdapterConfig(adapter_type="codex", extra=extra, **overrides))


@pytest.fixture
def executable(tmp_path):
    path = tmp_path / "codex"
    path.touch()
    os.chmod(path, 0o700)
    return path


@pytest.mark.asyncio
async def test_streams_only_assistant_text_and_resumes_same_conversation(
    tmp_path, executable, monkeypatch
):
    first = FakeProcess(events=[
        {"type": "thread.started", "thread_id": "thread-123"},
        {"type": "item.completed", "item": {"type": "command_execution", "aggregated_output": "secret cli output"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "自然语言回复"}},
        {"type": "turn.completed", "usage": {"input_tokens": 10}},
    ])
    second = FakeProcess(events=[
        {"type": "thread.started", "thread_id": "thread-123"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "继续回复"}},
    ])
    processes = [first, second]
    calls = []

    async def fake_create(*args, **kwargs):
        calls.append(args)
        return processes.pop(0)

    monkeypatch.setattr("app.adapters.codex_adapter.asyncio.create_subprocess_exec", fake_create)
    adapter = make_adapter(tmp_path, executable)

    output = "".join([
        chunk async for chunk in adapter.stream_reply(
            "开始", history=[{"role": "assistant", "content": "旧回复"}],
            system_prompt="系统要求", conversation_id="conversation-a",
        )
    ])
    resumed = "".join([
        chunk async for chunk in adapter.stream_reply("继续", conversation_id="conversation-a")
    ])

    assert output == "自然语言回复"
    assert resumed == "继续回复"
    assert "secret cli output" not in output
    assert "系统要求" in first.stdin.data.decode()
    assert first.stdin.closed is True
    assert second.stdin.data.decode() == "继续"
    assert calls[1][1:4] == ("exec", "resume", "thread-123")
    sessions = get_tenant_json("tenant-codex", SESSION_CONFIG_KEY, {})
    assert sessions[f"{tmp_path}:conversation-a"] == "thread-123"


@pytest.mark.asyncio
async def test_different_conversations_do_not_share_sessions(tmp_path, executable, monkeypatch):
    processes = [
        FakeProcess(events=[
            {"type": "thread.started", "thread_id": "thread-a"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "A"}},
        ]),
        FakeProcess(events=[
            {"type": "thread.started", "thread_id": "thread-b"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "B"}},
        ]),
    ]
    calls = []

    async def fake_create(*args, **kwargs):
        calls.append(args)
        return processes.pop(0)

    monkeypatch.setattr("app.adapters.codex_adapter.asyncio.create_subprocess_exec", fake_create)
    adapter = make_adapter(tmp_path, executable)
    assert "".join([chunk async for chunk in adapter.stream_reply("A", conversation_id="a")]) == "A"
    assert "".join([chunk async for chunk in adapter.stream_reply("B", conversation_id="b")]) == "B"
    assert "resume" not in calls[0]
    assert "resume" not in calls[1]


@pytest.mark.asyncio
async def test_connection_check_uses_login_status_without_model_call(tmp_path, executable, monkeypatch):
    process = FakeProcess(communicate=(b"Logged in using ChatGPT\n", b""))
    calls = []

    async def fake_create(*args, **kwargs):
        calls.append(args)
        return process

    monkeypatch.setattr("app.adapters.codex_adapter.asyncio.create_subprocess_exec", fake_create)
    adapter = make_adapter(tmp_path, executable)

    success, detail = await adapter.test_connection()

    assert success is True
    assert detail == "Codex CLI 已登录"
    assert calls[0][1:] == ("login", "status")


@pytest.mark.asyncio
async def test_cli_error_is_natural_language_and_redacts_api_key(tmp_path, executable, monkeypatch):
    process = FakeProcess(stderr=b"authentication failed for sk-secret123\n", returncode=1)

    async def fake_create(*args, **kwargs):
        return process

    monkeypatch.setattr("app.adapters.codex_adapter.asyncio.create_subprocess_exec", fake_create)
    adapter = make_adapter(tmp_path, executable)
    output = "".join([chunk async for chunk in adapter.stream_reply("test")])

    assert output == "[Codex 本机连接错误: authentication failed for sk-***]"
    assert "secret123" not in output
