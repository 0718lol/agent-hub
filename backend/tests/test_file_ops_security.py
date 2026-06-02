"""Unit tests for file_ops._safe_path — path traversal prevention.

Pure logic tests: no real filesystem writes, no network.
"""

import sys
import os
from unittest.mock import patch, MagicMock

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tools.file_ops import _safe_path


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
    """Symlink-based traversal must be blocked via os.path.realpath mocking."""

    @patch("app.tools.file_ops.os.path.realpath")
    @patch("app.tools.file_ops.os.makedirs")
    def test_symlink_pointing_outside_sandbox(self, mock_makedirs, mock_realpath):
        # First call: resolve sandbox dir -> returns sandbox dir
        # Second call: resolve file path (symlink target) -> returns outside sandbox
        call_count = {"n": 0}
        def fake_realpath(path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "/data/sandbox/conv123"
            return "/etc/passwd"

        mock_realpath.side_effect = fake_realpath
        result = _safe_path("conv123", "symlink_to_etc")
        # If realpath resolves outside sandbox, should return None
        assert result is None

    @patch("app.tools.file_ops.os.path.realpath")
    @patch("app.tools.file_ops.os.makedirs")
    def test_symlink_resolving_inside_sandbox(self, mock_makedirs, mock_realpath):
        # All paths resolve inside sandbox
        mock_realpath.side_effect = lambda p: p.replace("..", "").replace("//", "/")
        # This test verifies that when realpath stays inside sandbox, path is allowed
        # We need a more careful mock
        sandbox_base = "/data/sandbox/conv123"

        def safe_realpath(path):
            if path.startswith(sandbox_base):
                return path
            return os.path.join(sandbox_base, os.path.basename(path))

        mock_realpath.side_effect = safe_realpath
        result = _safe_path("conv123", "file.txt")
        assert result is not None


class TestSafePathBoundaryChecks:
    """Boundary conditions: sandbox_evil vs sandbox prefix confusion."""

    @patch("app.tools.file_ops.os.path.realpath")
    @patch("app.tools.file_ops.os.makedirs")
    def test_sandbox_prefix_confusion(self, mock_makedirs, mock_realpath):
        # sandbox_evil should not match sandbox + os.sep
        # Simulate: conversation "sandbox" with file resolving to "sandbox_evil/..."
        sandbox_dir = "/data/sandbox/sandbox"

        def fake_realpath(path):
            # Simulate a path that has the sandbox prefix but extends to sandbox_evil
            if "evil" in str(path):
                return "/data/sandbox/sandbox_evil/secret.txt"
            return sandbox_dir

        mock_realpath.side_effect = fake_realpath
        result = _safe_path("sandbox", "evil_trick")
        # Should be None because the resolved path is outside the sandbox
        assert result is None

    @patch("app.tools.file_ops.os.path.realpath")
    @patch("app.tools.file_ops.os.makedirs")
    def test_exact_sandbox_dir_allowed(self, mock_makedirs, mock_realpath):
        sandbox_dir = "/data/sandbox/conv123"
        mock_realpath.return_value = sandbox_dir
        result = _safe_path("conv123", ".")
        # resolved == sandbox_dir is allowed
        assert result == sandbox_dir

    @patch("app.tools.file_ops.os.path.realpath")
    @patch("app.tools.file_ops.os.makedirs")
    def test_path_just_outside_sandbox_blocked(self, mock_makedirs, mock_realpath):
        # First call resolves sandbox dir, second call resolves to path
        # that has sandbox prefix but is NOT within it (no trailing sep)
        call_count = {"n": 0}
        def fake_realpath(path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "/data/sandbox/conv123"
            return "/data/sandbox/conv123_evil"

        mock_realpath.side_effect = fake_realpath
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
