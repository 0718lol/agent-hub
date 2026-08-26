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


@pytest.mark.asyncio
async def test_evaluator_error_passes_through_without_retry():
    agent = SimpleNamespace(agent_id="agent_frontend", stream_reply=AsyncMock())
    manager = SimpleNamespace(broadcast=AsyncMock())
    unavailable_report = {
        "evaluation_passed": True,
        "total_score": None,
        "dimensions": {},
        "evaluator_status": "error",
        "static_check": {"passed": True, "error": None, "penalty": 0},
        "summary": "质量评分服务暂不可用",
    }

    with patch(
        "app.core.quality_retry._evaluate_code_with_sandbox",
        new_callable=AsyncMock,
        return_value=unavailable_report,
    ):
        result = await evaluate_and_retry(
            "conv_evaluator_error",
            agent,
            "做个页面",
            "```html\n<!doctype html><html><body>ok</body></html>\n```",
            AsyncMock(),
            manager,
        )

    agent.stream_reply.assert_not_awaited()
    assert result["evaluation_passed"] is True
    assert result["total_score"] is None
    messages = [call.args[1] for call in manager.broadcast.await_args_list]
    assert any("不会误判为代码失败" in item.get("content", {}).get("text", "") for item in messages)
    assert all("运行测试未通过" not in item.get("content", {}).get("text", "") for item in messages)
