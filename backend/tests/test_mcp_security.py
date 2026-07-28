"""Tests for MCP server registration security."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mcp_app():
    from app.routers.mcp import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_allowed_command_npx(mcp_app):
    """npx should be in the allowed commands whitelist."""
    with patch("app.routers.mcp.mcp_bridge_manager") as mock_mgr:
        mock_mgr.register_server = AsyncMock(return_value=True)
        resp = mcp_app.post("/api/mcp/servers", json={
            "name": "test", "command": "npx", "args": ["-y", "@anthropic-ai/mcp-server"]
        })
        # Should not return "not allowed" error (may fail to connect, that is OK)
        if resp.status_code == 200:
            data = resp.json()
            assert "not allowed" not in data.get("message", "").lower()


def test_disallowed_command_rejected(mcp_app):
    """rm/curl/wget should be rejected."""
    for cmd in ["rm", "curl", "wget", "bash", "sh"]:
        resp = mcp_app.post("/api/mcp/servers", json={
            "name": "test", "command": cmd, "args": ["-rf", "/"]
        })
        data = resp.json()
        assert "not allowed" in data.get("message", "").lower() or resp.status_code != 200


def test_shell_metachar_rejected(mcp_app):
    """Shell metacharacters in args should be rejected."""
    for arg in ["test;rm -rf /", "test|cat /etc/passwd", "test&whoami", "test`id`", "test$(whoami)"]:
        resp = mcp_app.post("/api/mcp/servers", json={
            "name": "test", "command": "npx", "args": [arg]
        })
        data = resp.json()
        assert "forbidden" in data.get("message", "").lower() or "metachar" in data.get("message", "").lower() or resp.status_code != 200


def test_dangerous_arg_rejected(mcp_app):
    """python -c / node -e should be rejected."""
    resp = mcp_app.post("/api/mcp/servers", json={
        "name": "test", "command": "python", "args": ["-c", "import os; os.system('whoami')"]
    })
    data = resp.json()
    msg = data.get("message", "").lower()
    assert (
        "dangerous" in msg
        or "not allowed" in msg
        or "forbidden" in msg
        or "metachar" in msg
        or resp.status_code != 200
    )


def test_empty_command_rejected(mcp_app):
    """Empty/whitespace command should be rejected."""
    resp = mcp_app.post("/api/mcp/servers", json={
        "name": "test", "command": " ", "args": []
    })
    data = resp.json()
    assert "not allowed" in data.get("message", "").lower() or resp.status_code != 200


def test_long_arg_rejected(mcp_app):
    """Very long args should be rejected."""
    resp = mcp_app.post("/api/mcp/servers", json={
        "name": "test", "command": "npx", "args": ["A" * 2000]
    })
    data = resp.json()
    msg = data.get("message", "").lower()
    assert "too long" in msg or "exceeds max length" in msg or resp.status_code != 200


def test_builtin_repo_map_scans_only_the_current_project(tmp_path, monkeypatch):
    from app.core import workspace as workspace_module
    from app.core.mcp_bridge import BuiltinMCPServer

    workspace_root = tmp_path / "projects"
    project = workspace_root / "conversation-1"
    project.mkdir(parents=True)
    (project / "app.js").write_text("export function run() {}", encoding="utf-8")
    (project / "page.wxml").write_text("<view>tool</view>", encoding="utf-8")
    (tmp_path / "platform_secret.py").write_text(
        "def should_not_be_scanned(): pass", encoding="utf-8"
    )
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", workspace_root)

    content = BuiltinMCPServer().read_resource_sync(
        "workspace://repomap", "conversation-1"
    )

    assert "app.js" in content
    assert "page.wxml" in content
    assert "platform_secret.py" not in content
    assert len(content) <= 12_200


def test_repo_map_has_a_hard_file_limit(tmp_path):
    from app.core.repo_map import CodebaseMapScanner

    for index in range(CodebaseMapScanner.MAX_FILES + 10):
        (tmp_path / f"file-{index:03}.json").write_text("{}", encoding="utf-8")

    content = CodebaseMapScanner().scan_directory(str(tmp_path))

    assert "file map truncated" in content
    assert content.count("📄") == CodebaseMapScanner.MAX_FILES


def test_repo_map_skips_large_files_and_symlinks(tmp_path):
    from app.core.repo_map import CodebaseMapScanner

    outside = tmp_path.parent / "outside.py"
    outside.write_text("def outside_secret(): pass", encoding="utf-8")
    (tmp_path / "large.py").write_bytes(
        b"x" * (CodebaseMapScanner.MAX_FILE_BYTES + 1)
    )
    (tmp_path / "linked.py").symlink_to(outside)
    (tmp_path / "normal.py").write_text("def normal(): pass", encoding="utf-8")

    content = CodebaseMapScanner().scan_directory(str(tmp_path))

    assert "normal.py" in content
    assert "large.py" not in content
    assert "linked.py" not in content
    assert "outside_secret" not in content
