"""Unit tests for file_ops._safe_path — path traversal prevention.

All generated workspaces are isolated in a temporary directory.
"""

import os
import sys
import pytest

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import workspace as workspace_module
from app.tools.file_ops import _read_text_file, _safe_path


@pytest.fixture(autouse=True)
def sandbox_root(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", tmp_path)
    return tmp_path


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
    """Resolve real links and reject sibling workspaces."""

    def test_symlink_pointing_outside_sandbox(self, sandbox_root):
        workspace = sandbox_root / "conv123"
        workspace.mkdir()
        sibling = sandbox_root / "conv123_evil"
        sibling.mkdir()
        (workspace / "escape").symlink_to(sibling, target_is_directory=True)

        assert _safe_path("conv123", "escape/file.txt") is None

    def test_symlink_resolving_inside_sandbox(self, sandbox_root):
        workspace = sandbox_root / "conv123"
        workspace.mkdir()
        file = workspace / "file.txt"
        file.write_text("safe")
        (workspace / "link.txt").symlink_to(file)

        assert _safe_path("conv123", "link.txt") == str(file)

    def test_workspace_alias_is_rejected(self, sandbox_root):
        target = sandbox_root / "conv_owner"
        target.mkdir()
        (sandbox_root / "conv_other").symlink_to(target, target_is_directory=True)

        assert _safe_path("conv_other", "private.txt") is None

    def test_empty_filepath_resolves_to_own_workspace(self, sandbox_root):
        assert _safe_path("conv123", "") == str(sandbox_root / "conv123")


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
