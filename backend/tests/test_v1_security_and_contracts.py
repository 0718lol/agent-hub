"""Regression tests for Edition 1 (multi-tenant) P0 security hardening and P1 bug fixes."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport


# ---------------------------------------------------------------------------
# P0-1 & P0-2: Admin-only host execution & SSRF protection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_codex_adapter_and_proxy_require_admin():
    from app.routers.adapters import router as adapters_router

    app = FastAPI()

    @app.middleware("http")
    async def inject_role(request: Request, call_next):
        is_admin = request.headers.get("x-test-admin") == "1"
        request.state.tenant_id = "tn_admin" if is_admin else "tn_member"
        request.state.is_admin = is_admin
        return await call_next(request)

    app.include_router(adapters_router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Member cannot register codex adapter
        member_codex = await client.post(
            "/api/adapters",
            json={"agent_id": "codex", "adapter_type": "codex"},
        )
        assert member_codex.status_code == 403

        # Member cannot start or stop global host proxy
        assert (await client.post("/api/proxy/start")).status_code == 403
        assert (await client.post("/api/proxy/stop")).status_code == 403

        # Member SSRF via adapter api_url is blocked
        ssrf_resp = await client.post(
            "/api/adapters",
            json={
                "agent_id": "custom_bot",
                "adapter_type": "self_deployed",
                "api_url": "http://169.254.169.254/latest/meta-data/",
            },
        )
        assert ssrf_resp.status_code == 422

        # Admin can register codex adapter
        admin_codex = await client.post(
            "/api/adapters",
            headers={"x-test-admin": "1"},
            json={"agent_id": "codex", "adapter_type": "codex"},
        )
        assert admin_codex.status_code == 200


def test_codex_default_workspace_isolated_and_env_scrubbed(monkeypatch):
    from app.adapters.base import AdapterConfig
    from app.adapters.codex_adapter import CodexAdapter

    monkeypatch.setenv("AGENTHUB_API_SECRET", "super-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    adapter = CodexAdapter(AdapterConfig(adapter_type="codex", extra={"_tenant_id": "tn_1"}))

    assert "agenthub_export" in str(adapter.workspace)
    env = adapter._subprocess_env()
    assert "AGENTHUB_API_SECRET" not in env
    assert "DATABASE_URL" not in env


@pytest.mark.asyncio
async def test_llm_settings_blocks_member_host_providers_and_ssrf():
    from app.core.tenancy import reset_current_tenant, set_current_tenant
    from app.routers.settings import router as settings_router

    app = FastAPI()

    @app.middleware("http")
    async def inject_member(request: Request, call_next):
        request.state.tenant_id = "tn_member_llm"
        request.state.is_admin = False
        tok = set_current_tenant("tn_member_llm")
        try:
            return await call_next(request)
        finally:
            reset_current_tenant(tok)

    app.include_router(settings_router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ollama_resp = await client.post("/api/settings/llm", json={"provider": "ollama", "model": "qwen2.5:7b"})
        assert ollama_resp.status_code == 403

        ssrf_resp = await client.post(
            "/api/settings/llm",
            json={
                "provider": "openai",
                "api_key": "sk-test",
                "base_url": "http://127.0.0.1:6379/v1",
                "model": "gpt-4o-mini",
            },
        )
        assert ssrf_resp.status_code == 422

        models_resp = await client.get("/api/ollama/models")
        assert models_resp.status_code == 200
        assert models_resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# P0-3 & P0-4: Browser LFI/SSRF, Builtin repomap leak, & conversation_id override
# ---------------------------------------------------------------------------


def test_browser_url_resolver_blocks_file_protocol_traversal_and_ssrf(tmp_path, monkeypatch):
    from app.tools.browser_tools import _resolve_browser_target_url

    sandbox = tmp_path / "tenant__tn_a__conv__c1"
    sandbox.mkdir(parents=True)
    (sandbox / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("top-secret", encoding="utf-8")
    try:
        (sandbox / "escape.html").symlink_to(outside)
        has_symlink = True
    except OSError:
        has_symlink = False

    monkeypatch.setattr("app.tools.browser_tools.resolve_workspace", lambda cid: sandbox)

    # Block direct file:// protocol
    url, err = _resolve_browser_target_url("file:///etc/passwd", "tenant__tn_a__conv__c1")
    assert url is None and "file://" in err

    # Block javascript: scheme
    url, err = _resolve_browser_target_url("javascript:alert(1)", "tenant__tn_a__conv__c1")
    assert url is None and err is not None

    # Block ../ traversal
    url, err = _resolve_browser_target_url("../secret.txt", "tenant__tn_a__conv__c1")
    assert url is None and "越权" in err

    # Block symlink escape
    if has_symlink:
        url, err = _resolve_browser_target_url("escape.html", "tenant__tn_a__conv__c1")
        assert url is None and "越权" in err

    # Block cloud metadata SSRF
    url, err = _resolve_browser_target_url("http://169.254.169.254/latest/meta-data/", "tenant__tn_a__conv__c1")
    assert url is None and err is not None

    # Allow legitimate relative file inside sandbox
    url, err = _resolve_browser_target_url("index.html", "tenant__tn_a__conv__c1")
    assert err is None and url.startswith("file:///") and url.endswith("index.html")


def test_builtin_repomap_does_not_leak_backend_source(tmp_path, monkeypatch):
    from app.core.mcp_bridge import BuiltinMCPServer

    empty_ws = tmp_path / "empty_ws"
    empty_ws.mkdir()
    monkeypatch.setattr("app.core.workspace.resolve_workspace", lambda _cid: empty_ws)
    srv = BuiltinMCPServer()
    out = srv.read_resource_sync("workspace://repomap", "tenant__tn_nobody__conv__empty")
    assert "没有可解析" in out or "Workspace is empty" in out
    assert "agent_orchestrator" not in out


# ---------------------------------------------------------------------------
# P0-5: SafeASTInterpreter format escape & CPU/memory DoS bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_interpreter_blocks_format_escape_and_resource_bombs():
    from app.core.ast_interpreter import SafeASTInterpreter

    interp = SafeASTInterpreter()

    # Block str.format C-level attribute traversal
    escape_res = await interp.execute("'{0.__init__.__globals__}'.format(print)")
    assert escape_res["success"] is False

    # Block single-underscore private attributes
    priv_res = await interp.execute("x = print._isolated_print")
    assert priv_res["success"] is False

    # Block huge exponent CPU DoS
    pow_res = await interp.execute("x = 9 ** 9 ** 9")
    assert pow_res["success"] is False
    assert "安全限制" in pow_res["error"]

    # Block sequence multiplication RAM DoS
    mem_res = await interp.execute("x = 'a' * (10 ** 8)")
    assert mem_res["success"] is False
    assert "安全限制" in mem_res["error"]

    # Support safe tuples and sorted()
    ok_res = await interp.execute("t = (3, 1, 2)\nsorted(t)")
    assert ok_res["success"] is True
    assert ok_res["result"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# P0-6: Session revocation on logout & password change + proxy IP + WS Origin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_and_password_change_revoke_old_cookies(monkeypatch):
    from app.core.accounts import create_account
    from app.core.auth import SESSION_COOKIE
    from app.core.config import settings
    from app.routers.auth import router as auth_router

    monkeypatch.setattr(settings, "debug", True)
    create_account("alice_sec", "oldpassword123")
    app = FastAPI()
    app.include_router(auth_router, prefix="/api")
    transport = ASGITransport(app=app)

    # 1. Logout revokes replayed token
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login1 = await client.post("/api/auth/login", json={"username": "alice_sec", "password": "oldpassword123"})
        stolen_cookie = login1.cookies.get(SESSION_COOKIE)
        assert stolen_cookie
        await client.post("/api/auth/logout")

    async with AsyncClient(transport=transport, base_url="http://test", cookies={SESSION_COOKIE: stolen_cookie}) as replay:
        status1 = await replay.get("/api/auth/status")
        assert status1.json()["authenticated"] is False

    # 2. Password change invalidates concurrent session cookie while keeping active client logged in
    async with AsyncClient(transport=transport, base_url="http://test") as client_a, \
               AsyncClient(transport=transport, base_url="http://test") as client_b:
        await client_a.post("/api/auth/login", json={"username": "alice_sec", "password": "oldpassword123"})
        await client_b.post("/api/auth/login", json={"username": "alice_sec", "password": "oldpassword123"})

        chg = await client_a.post(
            "/api/auth/change-password",
            json={"current_password": "oldpassword123", "new_password": "newpassword456"},
        )
        assert chg.status_code == 200
        assert (await client_a.get("/api/auth/status")).json()["authenticated"] is True
        assert (await client_b.get("/api/auth/status")).json()["authenticated"] is False


def test_proxy_aware_client_ip_extraction():
    from app.routers.auth import _extract_client_ip

    # Trusted private proxy (e.g., Docker Nginx container) -> honors X-Real-IP
    req_behind_nginx = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [(b"x-real-ip", b"198.51.100.77")],
        "client": ("172.18.0.5", 43210),
    })
    assert _extract_client_ip(req_behind_nginx) == "198.51.100.77"

    # Untrusted public client -> ignores spoofed X-Real-IP
    req_spoofed = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [(b"x-real-ip", b"1.1.1.1")],
        "client": ("203.0.113.99", 43210),
    })
    assert _extract_client_ip(req_spoofed) == "203.0.113.99"


@pytest.mark.asyncio
async def test_websocket_rejects_cross_origin_hijack(monkeypatch):
    from app.core.config import settings
    from app.routers.ws import router as ws_router

    monkeypatch.setattr(settings, "api_secret", "test-ws-secret")
    app = FastAPI()
    app.include_router(ws_router)

    async with ASGIWebSocketTransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with pytest.raises(BaseExceptionGroup) as exc_info:
                async with aconnect_ws(
                    "ws://testserver/ws/conv_pm",
                    client,
                    headers={
                        "x-api-secret": "test-ws-secret",
                        "origin": "https://evil-attacker.example",
                    },
                ) as ws:
                    await ws.receive_text()
            disconnects = [e for e in exc_info.value.exceptions if isinstance(e, WebSocketDisconnect)]
            assert disconnects and disconnects[0].code == 4003


# ---------------------------------------------------------------------------
# P1 Runtime & Contract Regressions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_git_commit_validate_and_execute_returns_tool_result(tmp_path, monkeypatch):
    from app.tools.git_tools import GitCommitTool

    monkeypatch.setattr("app.tools.git_tools.resolve_workspace", lambda cid: tmp_path)
    with patch("app.tools.git_tools._run_git") as mock_git:
        mock_git.side_effect = [(0, "", ""), (0, "[main 1234] msg", ""), (0, "1234abcd", "")]
        res = await GitCommitTool().validate_and_execute(
            {"message": "feat: add page", "conversation_id": "tenant__tn_1__conv__c1"}
        )
    assert res.success is True
    assert res.data["commit_hash"] == "1234abcd"


@pytest.mark.asyncio
async def test_llm_test_endpoint_detects_streamed_terminal_errors(monkeypatch):
    from app.core.llm_client import llm_client
    from app.routers.settings import test_llm_connection

    monkeypatch.setattr(llm_client._default, "api_key", "sk-bad")
    monkeypatch.setattr(llm_client._default, "base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(llm_client._default, "model", "gpt-4o-mini")

    async def _bad_stream(*args, **kwargs):
        yield "\n[LLM 终端错误 (不可重试): LLM API Error (HTTP 401): Invalid API key]"

    monkeypatch.setattr(llm_client._default, "chat_stream", _bad_stream)
    result = await test_llm_connection()
    assert result["success"] is False
    assert "401" in result["error"]


@pytest.mark.asyncio
async def test_circuit_breaker_isolated_per_tenant_and_ignores_401():
    from app.core.llm_client import LLMAPIError, LLMClient, ResilienceManager
    from app.core.tenancy import reset_current_tenant, set_current_tenant

    rm = ResilienceManager()
    b_a = rm.get_breaker("openai", "https://api.openai.com/v1", tenant_id="tn_a")
    b_b = rm.get_breaker("openai", "https://api.openai.com/v1", tenant_id="tn_b")
    assert b_a is not b_b

    client = LLMClient()
    client.configure("openai", "bad-key", "https://api.openai.com/v1", "gpt-4o-mini")

    async def _fail_401(*args, **kwargs):
        raise LLMAPIError(401, "Invalid API key")
        yield  # pragma: no cover

    tok = set_current_tenant("tn_a")
    try:
        for _ in range(4):
            chunks = [c async for c in rm.execute_with_retry(client, _fail_401, [{"role": "user", "content": "hi"}], "")]
            assert any("401" in c for c in chunks)
        breaker = rm.get_breaker("openai", "https://api.openai.com/v1")
        assert await breaker.allow_request() is True
    finally:
        reset_current_tenant(tok)


def test_attachment_enrichment_enforces_tenant_ownership(tmp_path, monkeypatch):
    from app.agents.base import _enrich_user_content

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    own_file = upload_dir / "tenantfile__tn_owner__doc1.txt"
    own_file.write_text("秘密需求规格说明", encoding="utf-8")
    other_file = upload_dir / "tenantfile__tn_victim__secret.txt"
    other_file.write_text("其他租户机密", encoding="utf-8")

    monkeypatch.setattr("app.core.file_storage.UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr("app.core.file_storage.FileStorageManager.exists", lambda fid: (upload_dir / fid).is_file())
    monkeypatch.setattr("app.core.file_storage.FileStorageManager.get_absolute_path", lambda fid: str(upload_dir / fid))

    enriched_own = _enrich_user_content(
        "总结附件",
        [{"original_name": "doc1.txt", "stored_name": "tenantfile__tn_owner__doc1.txt"}],
        "tenant__tn_owner__conv__c1",
    )
    assert "秘密需求规格说明" in enriched_own

    enriched_cross = _enrich_user_content(
        "偷看附件",
        [{"original_name": "secret.txt", "stored_name": "tenantfile__tn_victim__secret.txt"}],
        "tenant__tn_owner__conv__c1",
    )
    assert "其他租户机密" not in enriched_cross


@pytest.mark.asyncio
async def test_group_mention_routes_directly_to_mentioned_agent(monkeypatch):
    from app.services import agent_orchestrator

    called_agents: list[str] = []

    class DummyAgent:
        def __init__(self, aid: str, name: str):
            self.agent_id = aid
            self.name = name

    fe = DummyAgent("agent_frontend", "前端工程师")
    pm = DummyAgent("agent_pm", "PM 小助手")

    async def fake_stream_reply(conv_id, agent, text, stop_event=None, context="", attachments=None):
        called_agents.append(agent.agent_id)
        return [], f"reply from {agent.agent_id}"

    monkeypatch.setattr(agent_orchestrator, "get_agents", lambda _uid=None: {"agent_frontend": fe, "agent_pm": pm})
    monkeypatch.setattr(agent_orchestrator, "stream_agent_reply", fake_stream_reply)
    monkeypatch.setattr(agent_orchestrator.manager, "broadcast", AsyncMock())
    monkeypatch.setattr("app.routers.harness_handler.try_intercept_with_harness", AsyncMock(return_value=False))

    await agent_orchestrator.run_user_message_flow(
        "tenant__tn_1__conv__conv_group_demo",
        "@前端工程师 帮我调一下按钮圆角",
        None,
        mentioned_agents=["agent_frontend"],
    )
    assert called_agents == ["agent_frontend"]


@pytest.mark.asyncio
async def test_state_graph_stops_at_max_steps(monkeypatch):
    from app.core.state_graph import StateGraph
    from app.core.websocket import manager

    monkeypatch.setattr(manager, "broadcast", AsyncMock())
    graph = StateGraph(max_steps=3)
    runs = 0

    async def loop_node(state):
        nonlocal runs
        runs += 1
        return {}

    graph.add_node("agent_pm", loop_node)
    graph.add_edge("agent_pm", "agent_pm")
    await graph.run({}, "test_conv_loop", asyncio.Event())
    assert runs == 3
