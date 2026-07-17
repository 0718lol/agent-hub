"""Generated workspace path validation tests."""

import asyncio

from app.core import workspace as workspace_module
from app.services.deployment import get_workspace_path
from app.tools.file_ops import FileListTool, FileReadTool, FileWriteTool, _safe_workspace_path


def test_resolve_workspace_accepts_scoped_conversation_id(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(workspace_module, "LEGACY_WORKSPACE_ROOT", tmp_path / "legacy")

    resolved = workspace_module.resolve_workspace("tenant__abc.conv-1")

    assert resolved == tmp_path / "tenant__abc.conv-1"
    assert resolved.is_dir()


def test_resolve_workspace_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(workspace_module, "LEGACY_WORKSPACE_ROOT", tmp_path / "legacy")

    assert workspace_module.resolve_workspace("../outside") is None
    assert not (tmp_path.parent / "outside").exists()


def test_file_workspace_path_rejects_invalid_conversation_id():
    assert _safe_workspace_path("../../outside", "secret.txt") is None


def test_legacy_workspace_is_merged_without_overwriting(tmp_path, monkeypatch):
    workspace_root = tmp_path / "agenthub_export"
    legacy_root = tmp_path / "legacy"
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(workspace_module, "LEGACY_WORKSPACE_ROOT", legacy_root)

    legacy_workspace = legacy_root / "conv-1"
    legacy_workspace.mkdir(parents=True)
    (legacy_workspace / "index.html").write_text("legacy html", encoding="utf-8")
    (legacy_workspace / "keep.txt").write_text("legacy value", encoding="utf-8")

    current_workspace = workspace_root / "conv-1"
    current_workspace.mkdir(parents=True)
    (current_workspace / "keep.txt").write_text("current value", encoding="utf-8")

    resolved = workspace_module.resolve_workspace("conv-1")

    assert (resolved / "index.html").read_text(encoding="utf-8") == "legacy html"
    assert (resolved / "keep.txt").read_text(encoding="utf-8") == "current value"
    assert workspace_module.resolve_workspace("conv-1") == resolved


def test_file_tools_use_the_deployable_workspace(tmp_path, monkeypatch):
    workspace_root = tmp_path / "agenthub_export"
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(workspace_module, "LEGACY_WORKSPACE_ROOT", tmp_path / "legacy")

    write_result = asyncio.run(
        FileWriteTool().execute(
            {"conversation_id": "conv-2", "path": "src/app.js", "content": "export default 1"}
        )
    )
    read_result = asyncio.run(
        FileReadTool().execute({"conversation_id": "conv-2", "path": "src/app.js"})
    )
    list_result = asyncio.run(FileListTool().execute({"conversation_id": "conv-2"}))

    assert write_result.success is True
    assert (workspace_root / "conv-2" / "src" / "app.js").is_file()
    assert read_result.data["content"] == "export default 1"
    assert any(item["path"] == "src/app.js" for item in list_result.data["files"])
    assert get_workspace_path("conv-2") == workspace_root / "conv-2"


def test_deployment_migrates_an_existing_legacy_workspace(tmp_path, monkeypatch):
    workspace_root = tmp_path / "agenthub_export"
    legacy_root = tmp_path / "legacy"
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(workspace_module, "LEGACY_WORKSPACE_ROOT", legacy_root)
    legacy_workspace = legacy_root / "conv-3"
    legacy_workspace.mkdir(parents=True)
    (legacy_workspace / "index.html").write_text("legacy", encoding="utf-8")

    resolved = get_workspace_path("conv-3")

    assert resolved == workspace_root / "conv-3"
    assert (resolved / "index.html").read_text(encoding="utf-8") == "legacy"
