"""Regression tests for the retired quality retry gate."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.quality_retry import evaluate_and_retry


@pytest.mark.asyncio
async def test_quality_retry_passthrough_for_plain_text():
    agent = SimpleNamespace(agent_id="agent_frontend")
    manager = SimpleNamespace(broadcast=AsyncMock())

    result = await evaluate_and_retry(
        "conv_plain",
        agent,
        "你好",
        "你好，请告诉我你想构建什么工具。",
        AsyncMock(),
        manager,
    )

    assert result["final_output"] == "你好，请告诉我你想构建什么工具。"
    assert result["evaluation_passed"] is True
    assert result["report"]["skipped_reason"] == "disabled"
    manager.broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_quality_retry_passthrough_for_code():
    agent = SimpleNamespace(agent_id="agent_frontend", stream_reply=AsyncMock())
    manager = SimpleNamespace(broadcast=AsyncMock())
    raw = "```html\n<!doctype html><html><body>ok</body></html>\n```"

    result = await evaluate_and_retry(
        "conv_html",
        agent,
        "做个页面",
        raw,
        AsyncMock(),
        manager,
    )

    assert result["final_output"] == raw
    assert result["retried"] is False
    agent.stream_reply.assert_not_awaited()
    manager.broadcast.assert_not_awaited()
