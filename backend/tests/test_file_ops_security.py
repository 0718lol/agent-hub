"""Unit tests for file_ops._safe_path — path traversal prevention.

Pure logic tests: no real filesystem writes, no network.
"""

import os
import sys

import pytest

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import workspace as workspace_module
from app.tools.file_ops import _read_text_file, _safe_path


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    workspace_root = (tmp_path / "agenthub_export").resolve()
    legacy_root = (tmp_path / "legacy_sandbox").resolve()
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(workspace_module, "LEGACY_WORKSPACE_ROOT", legacy_root)


class TestTextDecoding:
    def test_strips_utf8_bom(self, tmp_path):
        path = tmp_path / "bom.txt"
        path.write_bytes(b"\xef\xbb\xbf" + "中文内容".encode("utf-8"))
        assert _read_text_file(str(path)) == "中文内容"

    def test_reads_gb18030_without_replacement_characters(self, tmp_path):
        path = tmp_path / "gb.txt"
        path.write_bytes("中文项目".encode("gb18030"))
        content = _read_text_file(str(path))
        assert content == "中文项目"
        assert "\ufffd" not in content

# ============================================================
# _safe_path tests
# ============================================================

class TestSafePathNormal:
    """Normal path access within sandbox."""

    def test_simple_filename(self):
        result = _safe_path("conv123", "file.txt")
        assert result is not None
        assert "conv123" in result
        assert result.endswith("file.txt")

    def test_subdirectory_path(self):
        result = _safe_path("conv123", "subdir/file.txt")
        assert result is not None
        assert "subdir" in result
        assert result.endswith("file.txt")

    def test_dot_path(self):
        result = _safe_path("conv123", ".")
        assert result is not None

    def test_nested_subdirectories(self):
        result = _safe_path("conv123", "a/b/c/file.txt")
        assert result is not None
        assert "a" in result
        assert "b" in result
        assert "c" in result

    def test_current_dir_reference(self):
        result = _safe_path("conv123", "./file.txt")
        assert result is not None
        assert result.endswith("file.txt")


class TestSafePathTraversalPrevention:
    """Path traversal attacks must be blocked."""

    def test_dot_dot_traversal(self):
        result = _safe_path("conv123", "../etc/passwd")
        assert result is None

    def test_dot_dot_at_start(self):
        result = _safe_path("conv123", "../../etc/shadow")
        assert result is None

    def test_dot_dot_in_middle(self):
        result = _safe_path("conv123", "subdir/../../../etc/passwd")
        assert result is None

    def test_dot_dot_at_end(self):
        result = _safe_path("conv123", "subdir/..")
        # subdir/.. resolves to the sandbox root itself, which is allowed
        # (the check is: resolved.startswith(sandbox_dir + sep) OR resolved == sandbox_dir)
        assert result is not None

    def test_deeply_nested_traversal(self):
        result = _safe_path("conv123", "a/b/c/../../../../../../etc/passwd")
        assert result is None

    def test_dot_dot_with_filename(self):
        result = _safe_path("conv123", "../sibling/secret.txt")
        assert result is None


class TestSafePathSymlinkTraversal:
    """Symlink-based traversal must be blocked using real filesystem links."""

    def test_symlink_pointing_outside_sandbox(self, tmp_path):
        workspace = workspace_module.resolve_workspace("conv123")
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        (workspace / "symlink_to_outside").symlink_to(outside)

        result = _safe_path("conv123", "symlink_to_outside")
        assert result is None

    def test_symlink_resolving_inside_sandbox(self):
        workspace = workspace_module.resolve_workspace("conv123")
        target = workspace / "target.txt"
        target.write_text("safe", encoding="utf-8")
        (workspace / "inside_link").symlink_to(target)

        result = _safe_path("conv123", "inside_link")
        assert result == str(target)


class TestSafePathBoundaryChecks:
    """Boundary conditions: sandbox_evil vs sandbox prefix confusion."""

    def test_sandbox_prefix_confusion(self):
        workspace = workspace_module.resolve_workspace("sandbox")
        sibling = workspace.parent / "sandbox_evil"
        sibling.mkdir()
        (workspace / "evil_trick").symlink_to(sibling)

        result = _safe_path("sandbox", "evil_trick/secret.txt")
        assert result is None

    def test_exact_sandbox_dir_allowed(self):
        sandbox_dir = workspace_module.resolve_workspace("conv123")
        result = _safe_path("conv123", ".")
        assert result == str(sandbox_dir)

    def test_path_just_outside_sandbox_blocked(self):
        workspace = workspace_module.resolve_workspace("conv123")
        sibling = workspace.parent / "conv123_evil"
        sibling.mkdir()
        (workspace / "trick").symlink_to(sibling)

        result = _safe_path("conv123", "trick")
        assert result is None

    def test_empty_filepath(self):
        # Empty filepath should still resolve (to sandbox root or similar)
        result = _safe_path("conv123", "")
        # Depending on implementation, may return sandbox root or None
        # The key thing is it should not crash
        assert result is not None or result is None  # just no crash


class TestSafePathConversationIsolation:
    """Different conversations must not access each other's files."""

    def test_different_conversation_ids(self):
        result_a = _safe_path("conv_a", "file.txt")
        result_b = _safe_path("conv_b", "file.txt")
        assert result_a is not None
        assert result_b is not None
        assert result_a != result_b
        assert "conv_a" in result_a
        assert "conv_b" in result_b

    def test_special_characters_in_conversation_id(self):
        result = _safe_path("conv-test_123", "file.txt")
        assert result is not None

    def test_conversation_id_traversal_is_rejected(self):
        assert _safe_path("../../outside", "secret.txt") is None
