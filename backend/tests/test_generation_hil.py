"""Distributed human-in-the-loop reply bridge tests."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.core.redis import redis_manager
from app.core.websocket import manager
from app.services.webhook_gateway import webhook_gateway
from app.tools.judge_tools import (
    UserInteractionJudgeTool,
    submit_distributed_hil_reply,
)


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, ex=None):
        del ex
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_worker_hil_waits_for_reply_from_api_process(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(settings, "generation_worker_enabled", True)
    monkeypatch.setattr(redis_manager, "check_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(redis_manager, "get_client", lambda: fake_redis)
    monkeypatch.setattr(manager, "active_connections", {})
    monkeypatch.setattr(manager, "broadcast", AsyncMock())
    monkeypatch.setattr(
        webhook_gateway,
        "send_hil_notification",
        AsyncMock(),
    )
    tool = UserInteractionJudgeTool()

    pending = asyncio.create_task(tool.run({
        "conversation_id": "tenant__u__conv__c",
        "question": "继续吗？",
        "options": ["*Approve::继续", "Terminate::停止"],
    }))
    for _ in range(20):
        if manager.broadcast.await_count:
            break
        await asyncio.sleep(0)

    assert not pending.done()
    assert await submit_distributed_hil_reply(
        "tenant__u__conv__c", "Approve"
    )
    result = await asyncio.wait_for(pending, timeout=2)

    assert result.decision == "Approve"
    assert result.score == 100
