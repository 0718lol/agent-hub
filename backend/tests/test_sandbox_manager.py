"""Sandbox dispatch regression tests."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.core.sandbox_dependencies import resolve_dependencies
from app.core.sandbox_manager import DockerSandbox, E2BSandbox, SandboxManager


@pytest.mark.asyncio
async def test_host_subprocess_is_disabled_by_default():
    manager = SandboxManager()
    manager.enable_docker = False
    manager.e2b_api_key = ""

    with patch("app.core.sandbox_manager.settings.allow_unsandboxed_shell", False):
        result = await manager.execute("print('should not run')", "python")

    assert result["status"] == "error"
    assert "No isolated sandbox" in result["stderr"]


class _HungDockerProcess:
    returncode = None

    async def communicate(self, input=None):
        await asyncio.sleep(60)

    def kill(self):
        self.returncode = -9

    async def wait(self):
        return self.returncode


class _CleanupProcess:
    returncode = 0

    async def wait(self):
        return 0


class _CompletedDockerProcess:
    returncode = 0

    async def communicate(self, input=None):
        return b"ok\n", b""


@pytest.mark.asyncio
async def test_docker_timeout_forcibly_removes_named_container():
    calls = []

    async def create_process(*args, **kwargs):
        calls.append(args)
        if args[:3] == ("docker", "start", "-a"):
            return _HungDockerProcess()
        return _CompletedDockerProcess()

    with patch("app.core.sandbox_manager.asyncio.create_subprocess_exec", side_effect=create_process):
        result = await DockerSandbox().execute("while True: pass", "python", timeout=0.01)

    assert result["status"] == "timeout"
    assert calls[0][:3] == ("docker", "create", "-i")
    assert calls[1][:3] == ("docker", "start", "-a")
    assert calls[2][:3] == ("docker", "rm", "-f")


@pytest.mark.asyncio
async def test_docker_workspace_is_copied_into_running_read_only_container(tmp_path):
    calls = []

    async def create_process(*args, **kwargs):
        calls.append(args)
        return _CompletedDockerProcess()

    with patch("app.core.sandbox_manager.asyncio.create_subprocess_exec", side_effect=create_process):
        result = await DockerSandbox().execute(
            "pytest -q",
            "shell",
            timeout=10,
            workspace=tmp_path,
        )

    assert result["status"] == "success"
    command = calls[0]
    assert "--network" in command
    assert command[command.index("--network") + 1] == "none"
    assert "agenthub-runtime-sandbox:local" in command
    bootstrap = command[command.index("-lc") + 1]
    assert "tar -xf /tmp/project.tar -C /tmp/workspace" in bootstrap
    assert "cd /tmp/workspace" in bootstrap
    assert "type=bind" not in command
    assert calls[1][1] == "start"
    assert calls[1][2].startswith("agenthub-sandbox-")
    assert calls[2][:3] == ("docker", "attach", "-i")
    assert calls[3][1] == "cp"
    assert calls[3][-1].endswith(":/tmp/project.tar")
    assert calls[4][1:4] == ("exec", "-u", "0:0")
    assert calls[5][:3] == ("docker", "rm", "-f")


@pytest.mark.asyncio
async def test_docker_availability_probe_is_cached():
    sandbox = DockerSandbox()
    sandbox._run_cli = AsyncMock(return_value=(0, b"", b""))

    assert await sandbox.check_availability()
    assert await sandbox.check_availability()
    sandbox._run_cli.assert_awaited_once()


@pytest.mark.asyncio
async def test_incomplete_dependency_volume_is_not_a_cache_hit(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi==0.115.0\n", encoding="utf-8")
    plan = resolve_dependencies(tmp_path, "pytest").plans[0]
    sandbox = DockerSandbox()
    sandbox._run_cli = AsyncMock(side_effect=[
        (0, b"exists", b""),
        (1, b"", b"missing marker"),
        (0, b"", b""),
    ])

    assert not await sandbox._dependency_ready(plan)
    assert sandbox._run_cli.await_args_list[-1].args[0][:3] == ["volume", "rm", "-f"]


@pytest.mark.asyncio
async def test_dependency_cache_prunes_old_unprotected_volume():
    sandbox = DockerSandbox()
    sandbox._run_cli = AsyncMock(side_effect=[
        (0, b"old-volume\nnew-volume\n", b""),
        (
            0,
            b'[{"Name":"new-volume","CreatedAt":"2026-02-01"},'
            b'{"Name":"old-volume","CreatedAt":"2026-01-01"}]',
            b"",
        ),
        (0, b"", b""),
    ])

    with patch("app.core.sandbox_manager.settings.runtime_sandbox_dependency_cache_max", 1):
        await sandbox._prune_dependency_volumes({"new-volume"})

    assert sandbox._run_cli.await_args_list[-1].args[0] == ["volume", "rm", "old-volume"]


@pytest.mark.asyncio
async def test_same_tenant_is_limited_to_one_execution():
    manager = SandboxManager()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"status": "success"}

    manager._dispatch = AsyncMock(side_effect=dispatch)
    first = asyncio.create_task(manager.execute("one", quota_key="tenant__a__conv__1"))
    await entered.wait()
    with patch("app.core.sandbox_manager.settings.runtime_sandbox_queue_timeout", 0.01):
        second = await manager.execute("two", quota_key="tenant__a__conv__2")
    release.set()
    await first

    assert second["status"] == "error"
    assert "queue" in second["stderr"].lower()


class _Response:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_e2b_instance_is_deleted_when_upload_fails():
    client = AsyncMock()
    client.post.side_effect = [
        _Response(201, {"instanceID": "instance_123"}),
        RuntimeError("upload connection lost"),
    ]

    @asynccontextmanager
    async def fake_context():
        yield client

    with patch("app.core.sandbox_manager.httpx_client_context", fake_context):
        with pytest.raises(RuntimeError, match="upload connection lost"):
            await E2BSandbox("secret").execute("print(1)", "python", 10)

    client.delete.assert_awaited_once()
    assert "instance_123" in client.delete.await_args.args[0]


@pytest.mark.asyncio
async def test_e2b_rejects_template_without_data_science_packages():
    client = AsyncMock()
    client.post.side_effect = [
        _Response(201, {"instanceID": "instance_456"}),
        _Response(200),
        _Response(200, {"exitCode": 1}),
    ]

    @asynccontextmanager
    async def fake_context():
        yield client

    with patch("app.core.sandbox_manager.httpx_client_context", fake_context):
        with pytest.raises(RuntimeError, match="does not provide"):
            await E2BSandbox("secret").execute("print(1)", "python", 10)

    client.delete.assert_awaited_once()
