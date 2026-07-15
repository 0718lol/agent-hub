"""Regression tests for the quality retry dispatch path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.quality_retry import evaluate_and_retry


@pytest.mark.asyncio
async def test_plain_conversation_skips_code_evaluation():
    agent = SimpleNamespace(agent_id="agent_frontend")
    manager = SimpleNamespace(broadcast=AsyncMock())

    with patch(
        "app.core.quality_retry.execute_automated_evaluation",
        new_callable=AsyncMock,
    ) as evaluator:
        result = await evaluate_and_retry(
            "conv_plain",
            agent,
            "你好",
            "你好，请告诉我你想构建什么工具。",
            AsyncMock(),
            manager,
        )

    evaluator.assert_not_awaited()
    assert result["report"]["skipped_reason"] == "no_code_block"


@pytest.mark.asyncio
async def test_interactive_response_skips_code_evaluation():
    agent = SimpleNamespace(agent_id="agent_frontend")
    manager = SimpleNamespace(broadcast=AsyncMock())

    with patch(
        "app.core.quality_retry.execute_automated_evaluation",
        new_callable=AsyncMock,
    ) as evaluator:
        result = await evaluate_and_retry(
            "conv_question",
            agent,
            "做个工具",
            "[ask_user:你希望它运行在哪里？]",
            AsyncMock(),
            manager,
        )

    evaluator.assert_not_awaited()
    assert result["report"]["skipped_reason"] == "interactive_response"
