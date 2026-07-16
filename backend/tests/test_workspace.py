"""Generated workspace path validation tests."""

from app.core import workspace as workspace_module
from app.tools.file_ops import _safe_workspace_path


def test_resolve_workspace_accepts_scoped_conversation_id(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)

    resolved = workspace_module.resolve_workspace("tenant__abc.conv-1")

    assert resolved == tmp_path / "tenant__abc.conv-1"
    assert resolved.is_dir()


def test_resolve_workspace_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)

    assert workspace_module.resolve_workspace("../outside") is None
    assert not (tmp_path.parent / "outside").exists()


def test_file_workspace_path_rejects_invalid_conversation_id():
    assert _safe_workspace_path("../../outside", "secret.txt") is None
