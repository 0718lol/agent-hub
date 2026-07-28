"""Deployment preflight result semantics and API tests."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.preflight import PreflightCheck
from app.routers import system


def test_preflight_check_serializes_required_state():
    check = PreflightCheck("redis", "Redis", "fail", "offline", required=True)
    assert check.to_dict() == {
        "key": "redis",
        "label": "Redis",
        "status": "fail",
        "detail": "offline",
        "required": True,
    }


@pytest.mark.asyncio
async def test_preflight_endpoint_returns_selected_profile(monkeypatch):
    async def fake_preflight(profile):
        return {
            "profile": profile,
            "ready": profile == "core",
            "summary": {"pass": 1, "warn": 0, "fail": 0},
            "checks": [],
        }

    monkeypatch.setattr(system, "run_preflight", fake_preflight)
    app = FastAPI()
    app.include_router(system.router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/system/preflight?profile=deployment")

    assert response.status_code == 200
    assert response.json()["profile"] == "deployment"
    assert response.json()["ready"] is False


@pytest.mark.asyncio
async def test_preflight_endpoint_rejects_unknown_profile():
    app = FastAPI()
    app.include_router(system.router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/system/preflight?profile=unknown")

    assert response.status_code == 422
