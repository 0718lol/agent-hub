"""Generated workspace path validation tests."""

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
