"""Tests for API health and root endpoints."""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    """Create a test app instance without full initialization."""
    # We test the routers directly to avoid full DB/LLM init
    from fastapi import FastAPI

    from app.routers import benchmark, conversations, quality, sandbox, uploads, webhook

    app = FastAPI()
    app.include_router(conversations.router, prefix="/api")
    app.include_router(quality.router, prefix="/api")
    app.include_router(sandbox.router, prefix="/api")
    app.include_router(benchmark.router, prefix="/api")
    app.include_router(uploads.router, prefix="/api")
    app.include_router(webhook.router, prefix="/api")
    return app


@pytest.mark.asyncio
async def test_benchmark_cases_list(app):
    """Test that benchmark cases endpoint returns a list."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/benchmark/cases")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_quality_standards_list(app):
    """Test that quality standards endpoint returns standards dict."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/quality/standards")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        # Should have at least 'general' and 'python' standards
        assert "general" in data


@pytest.mark.asyncio
async def test_quality_evaluate_empty_text(app):
    """Test that quality evaluate returns error for empty text."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/quality/evaluate", json={"text": "", "agent_id": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data


@pytest.mark.asyncio
async def test_quality_evaluate_valid_text(app):
    """Test that quality evaluate returns a report for valid text."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/quality/evaluate", json={
            "text": "def hello():\n    print('hello world')\n",
            "agent_id": "agent_backend"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "passed" in data


@pytest.mark.asyncio
async def test_webhook_slack_not_configured(app):
    """Test that Slack webhook endpoint is accessible."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/webhook/callback/slack", content=b"test")
        assert resp.status_code in (200, 302, 400, 401, 503)


@pytest.mark.asyncio
async def test_webhook_telegram_not_configured(app):
    """Test that Telegram webhook endpoint is accessible."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/webhook/callback/telegram", content=b"test")
        assert resp.status_code in (200, 400, 401, 500, 503)


@pytest.mark.asyncio
async def test_webhook_channel_status_exposes_only_configuration_flags(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/webhook/channels")
    assert resp.status_code == 200
    assert set(resp.json()["channels"]) == {"slack", "telegram"}


@pytest.mark.asyncio
async def test_upload_download_forces_active_content_as_attachment(app, tmp_path, monkeypatch):
    from app.core import file_storage
    from app.routers import uploads

    monkeypatch.setattr(uploads, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_storage, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "sample.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/uploads/sample.html")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_upload_router_has_single_api_prefix(app):
    included = next(
        route for route in app.routes
        if getattr(route, "original_router", None) is not None
        and any(child.path == "/upload" for child in route.original_router.routes)
    )
    prefix = included.include_context.prefix
    paths = {prefix + route.path for route in included.original_router.routes}
    assert "/api/upload" in paths
    assert "/api/api/upload" not in paths
