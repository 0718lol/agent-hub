"""Tests for Personal Workbench mode: zero-login local UX, loopback CSRF guard,
real local folder binding, safe Git handling, and Personal AI OS bridge."""
from __future__ import annotations

import hashlib
import json
import subprocess
import uuid

from httpx import ASGITransport, AsyncClient
import pytest


@pytest.fixture(autouse=True)
def _enable_workbench_runtime(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mode", "workbench")
    monkeypatch.setattr(settings, "workbench_mode", True)
    monkeypatch.setattr(settings, "api_secret", "")
    monkeypatch.setattr(settings, "host", "127.0.0.1")


@pytest.mark.asyncio
async def test_cloud_mode_locks_down_host_workspace_binding(monkeypatch):
    from app.core.accounts import create_account
    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "mode", "cloud")
    monkeypatch.setattr(settings, "workbench_mode", False)
    monkeypatch.setattr(settings, "debug", True)

    create_account("cloud_member", "password123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/login", json={"username": "cloud_member", "password": "password123"})
        assert (await client.get("/api/workbench/status")).status_code == 403
        assert (
            await client.post(
                "/api/conversations/conv_pm/workspace",
                json={"path": "/tmp", "create": False},
            )
        ).status_code == 403
        health = (await client.get("/api/health")).json()
        assert health["mode"] == "cloud"
        assert health["capabilities"]["workbench"] is False


@pytest.mark.asyncio
async def test_workbench_zero_login_and_loopback_csrf_guard():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        status = await client.get("/api/auth/status")
        assert status.status_code == 200
        body = status.json()
        assert body["authenticated"] is True
        assert body["workbench_mode"] is True
        assert body["user"]["tenant_id"] == "local"

        # Clean unprefixed conversation IDs in workbench mode
        created = await client.post(
            "/api/conversations",
            json={"id": "clean-local-project", "name": "我的本地项目", "type": "single"},
        )
        assert created.status_code == 200
        convs = (await client.get("/api/conversations")).json()
        assert any(c["id"] == "clean-local-project" for c in convs)

        # Cross-site Origin / Sec-Fetch-Site / DNS Rebinding Host must be 403
        cross_origin = await client.post(
            "/api/conversations",
            json={"id": "evil", "name": "Evil"},
            headers={"Origin": "https://evil.example"},
        )
        assert cross_origin.status_code == 403

        null_origin = await client.post(
            "/api/conversations",
            json={"id": "evil2", "name": "Evil"},
            headers={"Origin": "null"},
        )
        assert null_origin.status_code == 403

        cross_site = await client.get(
            "/api/conversations",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert cross_site.status_code == 403

        bad_host = await client.get(
            "/api/conversations",
            headers={"Host": "evil-rebind.example:8000"},
        )
        assert bad_host.status_code == 403


@pytest.mark.asyncio
async def test_bind_real_local_folder_preserves_user_git_history(tmp_path):
    from app.core.mcp_client import mcp_manager
    from app.core.workspace import BACKEND_ROOT
    from app.main import app
    from app.tools import execute_tool_call

    project_dir = tmp_path / "real-app"
    project_dir.mkdir()
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "dev@local"], cwd=project_dir, check=True, capture_output=True)
    (project_dir / "README.md").write_text("# Real App\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial user commit"], cwd=project_dir, check=True, capture_output=True)
    initial_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_dir, check=True, capture_output=True, text=True
    ).stdout.strip()

    # Keep an uncommitted user scratch file to verify agent writes don't wipe or auto-commit it
    (project_dir / "notes.wip.txt").write_text("do not lose me", encoding="utf-8")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Sensitive directory must be rejected
        forbidden = await client.post(
            "/api/conversations/local-dev/workspace",
            json={"path": str(BACKEND_ROOT), "create": False},
        )
        assert forbidden.status_code == 400

        bound = await client.post(
            "/api/conversations/local-dev/workspace",
            json={"path": str(project_dir), "create": False},
        )
        assert bound.status_code == 200
        info = bound.json()
        assert info["is_bound"] is True
        assert info["path"] == str(project_dir.resolve())
        assert info["git"]["is_git"] is True

    # Agent writes valid Python file into the bound folder: no automatic git commit should occur
    write_ok = await mcp_manager.execute_tool(
        "SystemServer__workspace_write_file",
        {"path": "hello.py", "content": "def add(a, b):\n    return a + b\n"},
        "local-dev",
    )
    assert not write_ok.get("isError")
    assert (project_dir / "hello.py").read_text(encoding="utf-8").startswith("def add")
    head_after_write = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_dir, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert head_after_write == initial_head

    # Agent writes invalid Python syntax: only hello.py rolls back, notes.wip.txt stays intact!
    write_bad = await mcp_manager.execute_tool(
        "SystemServer__workspace_write_file",
        {"path": "hello.py", "content": "def broken(:\n"},
        "local-dev",
    )
    assert write_bad.get("isError") is True
    assert (project_dir / "hello.py").read_text(encoding="utf-8").startswith("def add")
    assert (project_dir / "notes.wip.txt").read_text(encoding="utf-8") == "do not lose me"

    # Explicit git_commit runtime tool works via ToolResult inside the bound directory
    commit_res = await execute_tool_call(
        "git_commit",
        {"message": "feat: add hello.py", "files": ["hello.py"], "conversation_id": "local-dev"},
    )
    assert commit_res.success is True
    assert commit_res.data["commit_hash"] != initial_head


@pytest.mark.asyncio
async def test_handoff_import_versioned_artifacts_and_receipt_roundtrip(tmp_path):
    from app.core.crud.artifacts import save_artifact
    from app.main import app

    mount_dir = tmp_path / "handoff-workspace"
    handoff_id = str(uuid.uuid4())
    evidence = [
        {"kind": "note", "id": "n1", "title": "预算结论", "text": "单机版优先跑通 SQLite + 本地目录挂载。"}
    ]
    evidence_hash = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        imported = await client.post(
            "/api/handoffs",
            json={
                "format": "personal-ai-os.task.v1",
                "handoff_id": handoff_id,
                "project": {"id": "proj-1", "name": "知序联动项目", "goal": "完成双核交接验证"},
                "evidence": evidence,
                "evidence_hash": evidence_hash,
                "workspace_path": str(mount_dir),
                "create_workspace": True,
            },
        )
        assert imported.status_code == 201
        conv_id = imported.json()["conversation_id"]
        assert mount_dir.is_dir()

        art1 = save_artifact(conv_id, "agent_frontend", "html", "<html><body>v1</body></html>", "index.html")
        art2 = save_artifact(conv_id, "agent_frontend", "html", "<html><body>v2</body></html>", "index.html")
        assert art1["version"] == 1
        assert art2["version"] == 2
        assert art2["parent_id"] == art1["id"]
        assert art2["content_hash"]

        receipt_resp = await client.get(f"/api/handoffs/{conv_id}/receipt")
        assert receipt_resp.status_code == 200
        receipt = receipt_resp.json()
        assert receipt["format"] == "agent-hub.receipt.v1"
        assert receipt["handoff_id"] == handoff_id
        assert receipt["evidence_hash"] == evidence_hash
        assert receipt["artifacts"][0]["version"] == 2


@pytest.mark.asyncio
async def test_llm_connection_test_rejects_streamed_error_strings(monkeypatch):
    from app.main import app
    from app.routers import settings as settings_router

    monkeypatch.setattr(settings_router.llm_client, "is_configured", lambda: True)

    async def fake_error_stream(*args, **kwargs):
        yield "[LLM 终端错误: HTTP 401 Invalid API key]"

    monkeypatch.setattr(settings_router.llm_client, "chat_stream", fake_error_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.post("/api/settings/llm/test")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "401" in data["error"]


@pytest.mark.asyncio
async def test_live_personal_ai_os_dual_core_bridge(tmp_path):
    """If sibling personal-ai-os repo exists locally, verify full MCP + pull + push-receipt loop."""
    from pathlib import Path
    import socket
    import sys
    import time

    from app.core.crud.artifacts import save_artifact
    from app.core.mcp_bridge import mcp_bridge_manager
    from app.core.workspace import REPO_ROOT
    from app.main import app
    from app.tools import execute_tool_call

    paios_dir = REPO_ROOT.parent / "personal-ai-os"
    if not (paios_dir / "server.py").is_file():
        pytest.skip("sibling personal-ai-os repo not present in CI")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    paios_data = tmp_path / "paios-data"
    paios_data.mkdir()
    proc = subprocess.Popen(
        [sys.executable, str(paios_dir / "server.py")],
        env={"PATH": "/usr/bin:/bin", "PORT": str(port), "PERSONAL_AI_OS_DATA_DIR": str(paios_data)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    paios_url = f"http://127.0.0.1:{port}"
    try:
        async with AsyncClient(timeout=3.0, trust_env=False) as ext:
            for _ in range(40):
                try:
                    if (await ext.get(f"{paios_url}/api/health")).status_code == 200:
                        break
                except Exception:
                    time.sleep(0.1)
            else:
                pytest.fail("personal-ai-os test server did not start")

            proj = (await ext.post(f"{paios_url}/api/projects", json={"name": "双核实测项目", "goal": "打通知序与工坊"})).json()
            await ext.post(
                f"{paios_url}/api/notes",
                json={"project_id": proj["id"], "title": "架构约定", "body": "预算上限为 42000 元。"},
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000", trust_env=False) as client:
            # 1. Connect Personal AI OS read-only MCP into AgentHub
            mcp_res = await client.post(
                "/api/workbench/personal-ai-os/connect-mcp",
                json={"personal_ai_os_dir": str(paios_dir), "data_dir": str(paios_data)},
            )
            assert mcp_res.status_code == 200
            search_tool = await execute_tool_call("wiki_search", {"query": "预算上限", "project_id": proj["id"]})
            assert search_tool.success is True
            assert "42000" in str(search_tool.data)

            # 2. One-click pull project brief into AgentHub conversation + mount folder
            code_dir = tmp_path / "mounted-code"
            pulled = await client.post(
                "/api/workbench/personal-ai-os/pull",
                json={
                    "project_id": proj["id"],
                    "personal_ai_os_url": paios_url,
                    "workspace_path": str(code_dir),
                    "create_workspace": True,
                },
            )
            assert pulled.status_code == 200
            conv_id = pulled.json()["conversation_id"]
            save_artifact(conv_id, "agent_frontend", "html", "<h1>42000 Budget</h1>", "budget.html")

            # 3. One-click push execution receipt back into Personal AI OS pending review queue
            pushed = await client.post(
                "/api/workbench/personal-ai-os/push-receipt",
                json={"conversation_id": conv_id, "personal_ai_os_url": paios_url},
            )
            assert pushed.status_code == 200
            assert pushed.json()["receipt"]["status"] == "pending"

        async with AsyncClient(timeout=3.0, trust_env=False) as ext:
            detail = (await ext.get(f"{paios_url}/api/projects/{proj['id']}")).json()
            assert len(detail["receipts"]) == 1
            assert detail["receipts"][0]["payload"]["artifacts"][0]["name"] == "budget.html"
    finally:
        await mcp_bridge_manager.stop_all_servers()
        proc.terminate()
        proc.wait(timeout=5)
