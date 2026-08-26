"""Regression tests for structured quality scoring and evaluator failures."""

import pytest

from app.agents.auto_evaluator import (
    execute_automated_evaluation,
    llm_as_a_judge_scoring,
)


class StreamingClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def chat_stream(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        yield self.response


@pytest.mark.asyncio
async def test_scoring_requests_json_mode_and_disables_tools():
    client = StreamingClient(
        '{"total_score":82,"dimensions":{"logic":34,'
        '"robustness":23,"architecture":25},"feedback":"可用"}'
    )

    result = await llm_as_a_judge_scoring("做页面", "```html\n<html></html>\n```", client)

    assert result == {
        "status": "ok",
        "total_score": 82,
        "dimensions": {"logic": 34, "robustness": 23, "architecture": 25},
        "feedback": "可用",
        "error": None,
    }
    assert client.calls[0]["enabled_tools"] == []
    assert client.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_tool_call_response_is_evaluator_error_not_fake_score():
    client = StreamingClient(
        '[tool_call:file_write]{"path":"index.html","content":"<html></html>"}[/tool_call]'
    )

    result = await llm_as_a_judge_scoring("做页面", "```html\n<html></html>\n```", client)

    assert result["status"] == "error"
    assert result["total_score"] is None
    assert result["dimensions"] == {}


@pytest.mark.asyncio
async def test_evaluator_error_does_not_fail_valid_html():
    client = StreamingClient("not json")

    report = await execute_automated_evaluation(
        "做页面",
        "```html\n<!doctype html><html><body>ok</body></html>\n```",
        client,
    )

    assert report["evaluation_passed"] is True
    assert report["total_score"] is None
    assert report["evaluator_status"] == "error"
    assert "暂不可用" in report["summary"]
