"""Stable account tenant and browser isolation regression tests."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.models import Conversation  # noqa: F401 - register SQLModel tables before fixtures run
from app.core.tenancy import belongs_to_user, public_conversation_id, scope_conversation_id


def test_conversation_namespace_roundtrip():
    scoped = scope_conversation_id("user-A", "conv_pm")
    assert scoped != scope_conversation_id("user-B", "conv_pm")
    assert public_conversation_id(scoped) == "conv_pm"
    assert belongs_to_user(scoped, "user-A")
    assert not belongs_to_user(scoped, "user-B")


@pytest.mark.asyncio
async def test_two_accounts_can_use_same_public_conversation_id():
    from app.routers import auth, conversations

    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as first, AsyncClient(
        transport=transport, base_url="http://test"
    ) as second:
        first_registration = await first.post(
            "/api/auth/register",
            json={"username": "first-user", "password": "password123"},
        )
        second_registration = await second.post(
            "/api/auth/register",
            json={"username": "second-user", "password": "password123"},
        )
        assert first_registration.status_code == 201
        assert second_registration.status_code == 201
        assert (
            first_registration.json()["user"]["tenant_id"]
            != second_registration.json()["user"]["tenant_id"]
        )
        await first.post("/api/conversations", json={"id": "shared-id", "name": "First", "type": "single"})
        await second.post("/api/conversations", json={"id": "shared-id", "name": "Second", "type": "single"})
        first_rows = await first.get("/api/conversations")
        second_rows = await second.get("/api/conversations")

    first_shared = next(row for row in first_rows.json() if row["id"] == "shared-id")
    second_shared = next(row for row in second_rows.json() if row["id"] == "shared-id")
    assert first_shared["name"] == "First"
    assert second_shared["name"] == "Second"
