"""Generated project preview API tests."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers import previews
from app.services.preview_runtime import PreviewRuntimeManager


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
