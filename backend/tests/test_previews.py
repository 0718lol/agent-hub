"""Generated project preview API tests."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers import previews
from app.services.preview_runtime import PreviewRuntime, PreviewRuntimeManager


@pytest.fixture
def preview_app(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "tenant__user-A__conv__conv-web"
    workspace.mkdir()
    (workspace / "index.html").write_text(
        '<!doctype html><html><head></head><body><script src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    (workspace / "app.js").write_text("document.body.dataset.ready = 'yes'", encoding="utf-8")
    monkeypatch.setattr(previews, "request_user_id", lambda _request: "user-A")
    monkeypatch.setattr(
        previews,
        "resolve_workspace",
        lambda conversation_id, create=False: workspace
        if conversation_id == "tenant__user-A__conv__conv-web" and create is False
        else None,
    )

    app = FastAPI()
    app.include_router(previews.router, prefix="/api")
    return app


@pytest.mark.asyncio
async def test_static_preview_serves_workspace_files_with_security_headers(preview_app):
    transport = ASGITransport(app=preview_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        index = await client.get("/api/previews/conv-web/files/index.html")
        script = await client.get("/api/previews/conv-web/files/app.js")

    assert index.status_code == 200
    assert '<base href="/api/previews/conv-web/files/">' in index.text
    assert "frame-ancestors 'self'" in index.headers["content-security-policy"]
    assert script.status_code == 200
    assert "dataset.ready" in script.text
    assert script.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_static_preview_rejects_hidden_and_traversal_paths(preview_app):
    transport = ASGITransport(app=preview_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        hidden = await client.get("/api/previews/conv-web/files/.agenthub/project.json")
        traversal = await client.get("/api/previews/conv-web/files/%2E%2E/secret.txt")

    assert hidden.status_code == 404
    assert traversal.status_code == 404


@pytest.mark.asyncio
async def test_preview_summary_reports_real_static_url(preview_app, monkeypatch):
    async def unavailable():
        return False

    async def no_api(_scoped_id, _user_id):
        return None

    monkeypatch.setattr(previews.preview_runtime_manager, "docker_available", unavailable)
    monkeypatch.setattr(previews, "_live_api", no_api)
    transport = ASGITransport(app=preview_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/previews/conv-web")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_type"] == "web"
    assert payload["web"]["static_url"].endswith("/files/index.html")
    assert payload["web"]["runtime_active"] is False


def test_vite_runtime_detection_uses_structured_package_json(tmp_path: Path):
    manager = PreviewRuntimeManager()
    (tmp_path / "package.json").write_text(
        '{"scripts":{"dev":"vite"},"devDependencies":{"vite":"5.0.0"}}',
        encoding="utf-8",
    )
    assert manager.supports_vite(tmp_path)

    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")
    assert not manager.supports_vite(tmp_path)


@pytest.mark.asyncio
async def test_preview_runtime_can_be_rediscovered_by_another_backend_instance(
    tmp_path: Path, monkeypatch
):
    manager = PreviewRuntimeManager()
    calls = []

    async def docker(*args, **_kwargs):
        calls.append(args)
        if args[0] == "inspect":
            return "true\n"
        if args[0] == "port":
            return "127.0.0.1:49173\n"
        return ""

    monkeypatch.setattr(manager, "_docker", docker)
    runtime = await manager.get_or_discover(
        "tenant__user-A__conv__conv-web", "conv-web", tmp_path
    )

    assert runtime is not None
    assert runtime.runtime_url == "http://127.0.0.1:49173"
    assert runtime.public_path == "/api/previews/conv-web/runtime/"
    assert any(call[0] == "inspect" for call in calls)


@pytest.mark.asyncio
async def test_preview_websocket_relays_vite_hmr_messages(preview_app, monkeypatch):
    runtime = PreviewRuntime(
        conversation_id="tenant__user-A__conv__conv-web",
        container_name="agenthub-preview-0123456789abcdef",
        runtime_url="http://agenthub-preview-0123456789abcdef:4173",
        public_path="/api/previews/conv-web/runtime/",
        started_at=1,
    )

    async def discover(*_args):
        return runtime

    class Upstream:
        async def send(self, _data):
            return None

        def __aiter__(self):
            async def messages():
                yield "vite-update"
            return messages()

    class Connector:
        async def __aenter__(self):
            return Upstream()

        async def __aexit__(self, *_args):
            return False

    class ClientWebSocket:
        headers = {}
        cookies = {}
        url = SimpleNamespace(query="")

        def __init__(self):
            self.accepted = False
            self.messages = []

        async def accept(self):
            self.accepted = True

        async def receive(self):
            await asyncio.sleep(60)

        async def send_text(self, data):
            self.messages.append(data)

        async def send_bytes(self, data):
            self.messages.append(data)

    client = ClientWebSocket()
    monkeypatch.setattr(previews.settings, "api_secret", "")
    monkeypatch.setattr(previews, "websocket_user_id", lambda _websocket: "user-A")
    monkeypatch.setattr(previews.preview_runtime_manager, "get_or_discover", discover)
    monkeypatch.setattr(previews.websockets, "connect", lambda *_args, **_kwargs: Connector())

    await previews._proxy_runtime_websocket(client, "conv-web", "")

    assert client.accepted is True
    assert client.messages == ["vite-update"]
