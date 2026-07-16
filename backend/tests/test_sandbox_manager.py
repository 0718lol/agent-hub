"""Sandbox dispatch regression tests."""

import asyncio
from unittest.mock import patch

import pytest

from app.core.sandbox_manager import DockerSandbox, SandboxManager


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
        return _HungDockerProcess() if len(calls) == 1 else _CleanupProcess()

    with patch("app.core.sandbox_manager.asyncio.create_subprocess_exec", side_effect=create_process):
        result = await DockerSandbox().execute("while True: pass", "python", timeout=0.01)

    assert result["status"] == "timeout"
    assert calls[0][:4] == ("docker", "run", "-i", "--rm")
    assert calls[1][:3] == ("docker", "rm", "-f")


@pytest.mark.asyncio
async def test_docker_workspace_is_read_only_and_copied_before_execution(tmp_path):
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
    mount_index = command.index("--mount")
    assert command[mount_index + 1] == f"type=bind,src={tmp_path},dst=/workspace,readonly"
    assert "--network" in command
    assert command[command.index("--network") + 1] == "none"
    assert "agenthub-runtime-sandbox:local" in command
    bootstrap = command[command.index("-lc") + 1]
    assert "cp -R /workspace/. /tmp/workspace/" in bootstrap
    assert "cd /tmp/workspace" in bootstrap
