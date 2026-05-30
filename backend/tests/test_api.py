"""Tests for API health and root endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    """Create a test app instance without full initialization."""
    # We test the routers directly to avoid full DB/LLM init
    from fastapi import FastAPI
    from app.routers import conversations, quality, webhook, sandbox, benchmark

    app = FastAPI()
    app.include_router(conversations.router, prefix="/api")
    app.include_router(quality.router, prefix="/api")
    app.include_router(sandbox.router, prefix="/api")
    app.include_router(benchmark.router, prefix="/api")
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
    """Test that Slack webhook returns 503 when secret not configured."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/webhook/callback/slack", content=b"test")
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_webhook_telegram_not_configured(app):
    """Test that Telegram webhook returns 503 when secret not configured."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/webhook/callback/telegram", content=b"test")
        assert resp.status_code == 503
