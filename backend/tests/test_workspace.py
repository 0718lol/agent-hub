"""Generated workspace path validation tests."""

import subprocess
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.core import workspace as workspace_module


def test_resolve_workspace_accepts_scoped_conversation_id(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)

    resolved = workspace_module.resolve_workspace("tenant__abc.conv-1")

    assert resolved == tmp_path / "tenant__abc.conv-1"
    assert resolved.is_dir()


def test_resolve_workspace_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)

    assert workspace_module.resolve_workspace("../outside") is None
    assert not (tmp_path.parent / "outside").exists()


async def test_sandbox_history_and_rollback_are_scoped_to_workspace(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.core.git_sandbox import git_checkpoint, run_git_cmd
    from app.core.tenancy import bearer_tenant_id, scope_conversation_id
    from app.main import app
    from app.routers.workflows import manager

    monkeypatch.setattr(settings, "api_secret", "sandbox-history-test")
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(manager, "broadcast", AsyncMock())
    headers = {"x-api-secret": settings.api_secret, "x-agenthub-client-id": "workspace-owner"}
    other = {**headers, "x-agenthub-client-id": "workspace-observer"}
    owner_id = scope_conversation_id(bearer_tenant_id(headers), "conv_pm")
    other_id = scope_conversation_id(bearer_tenant_id(other), "conv_pm")
    workspace = workspace_module.resolve_workspace(owner_id)
    file = workspace / "index.txt"
    file.write_text("first")
    first = await git_checkpoint(str(workspace), "First revision")
    file.write_text("second")
    second = await git_checkpoint(str(workspace), "Second revision")
    scratch = workspace / "scratch.txt"
    scratch.write_text("untracked")
    # An alias to another tenant's workspace must not expose that tenant's commits.
    (tmp_path / other_id).symlink_to(workspace, target_is_directory=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        url = "/api/sandbox/conv_pm"
        assert (await client.get(f"{url}/commits", headers=other)).json() == []
        assert (await client.post(f"{url}/rollback", headers=other, json={"commit_hash": first})).json()["status"] == "error"
        tool_url = "/api/runtime-tools/file_read/test"
        payload = {"params": {"conversation_id": owner_id, "path": "index.txt"}}
        assert (await client.post(tool_url, headers=other, json=payload)).status_code == 403
        payload["params"]["conversation_id"] = "conv_pm"
        own_result = await client.post(tool_url, json=payload)
        assert own_result.json()["success"] is True
        assert (await client.post(tool_url, headers=other, json=payload)).json()["success"] is False
        history = (await client.get(f"{url}/commits")).json()
        assert [item["hash"] for item in history[:2]] == [second, first]

        invalid = await client.post(f"{url}/rollback", json={"commit_hash": "--help"})
        assert invalid.json()["status"] == "error"
        assert file.read_text() == "second"
        assert scratch.exists()

        await run_git_cmd(str(workspace), "config", "filter.untrusted.smudge", "cat")
        unsafe = await client.post(f"{url}/rollback", json={"commit_hash": first})
        assert unsafe.json()["status"] == "error"
        assert file.read_text() == "second"
        assert scratch.exists()
        await run_git_cmd(str(workspace), "config", "--unset", "filter.untrusted.smudge")

        rolled_back = await client.post(f"{url}/rollback", json={"commit_hash": first[:7]})
        assert rolled_back.json()["status"] == "ok"
        assert file.read_text() == "first"
        assert not scratch.exists()
        manager.broadcast.assert_awaited_once()


async def test_git_history_does_not_execute_repository_signature_verifier(tmp_path):
    from app.core.git_sandbox import git_checkpoint, git_log, run_git_cmd

    (tmp_path / "index.txt").write_text("commit data")
    assert await git_checkpoint(str(tmp_path), "Signed checkpoint")
    _, original, _ = await run_git_cmd(str(tmp_path), "cat-file", "-p", "HEAD")
    header, message = original.split("\n\n", 1)
    signature = "gpgsig -----BEGIN PGP SIGNATURE-----\n \n c2ln\n -----END PGP SIGNATURE-----"
    commit = subprocess.run(
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        input=f"{header}\n{signature}\n\n{message}\n",
        cwd=tmp_path, text=True, capture_output=True, check=True,
    ).stdout.strip()
    await run_git_cmd(str(tmp_path), "update-ref", "HEAD", commit)

    verifier = tmp_path / "verifier"
    verifier.write_text("#!/bin/sh\ntouch .verifier-ran\nexit 1\n")
    verifier.chmod(0o700)
    await run_git_cmd(str(tmp_path), "config", "gpg.program", str(verifier))
    await run_git_cmd(str(tmp_path), "config", "log.showSignature", "true")

    assert (await git_log(str(tmp_path)))[0]["hash"] == commit
    assert not (tmp_path / ".verifier-ran").exists()


async def test_workspace_tools_reject_sibling_paths(tmp_path, monkeypatch):
    from app.core.mcp_client import SystemMCPServer
    from app.tools.block_editor_tools import FilePatchBlockTool

    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)
    sibling = workspace_module.resolve_workspace("example_other")
    (sibling / "private.txt").write_text("secret")
    (tmp_path / "alias").symlink_to(sibling, target_is_directory=True)

    blocked = await FilePatchBlockTool().execute({
        "conversation_id": "example",
        "path": "../example_other/private.txt",
        "patch_blocks": "<<<<<<< SEARCH\nsecret\n=======\nupdated\n>>>>>>> REPLACE",
    })
    assert not blocked.success
    assert (sibling / "private.txt").read_text() == "secret"

    result = await SystemMCPServer().call_tool("workspace_list_dir", {}, conversation_id="alias")
    assert result["isError"] is True
