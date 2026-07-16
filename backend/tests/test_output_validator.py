"""Tests for output validation and auto-retry logic."""
import pytest

from app.core.output_validator import (
    AgentOutput,
    ToolCall,
    get_retry_prompt,
    parse_tool_calls,
    validate_output,
)


class TestParseToolCalls:
    """Test tool call parsing."""

    def test_single_tool_call(self):
        text = '[tool_call:browser_open_url]{"url": "https://example.com"}[/tool_call]'
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["name"] == "browser_open_url"
        assert calls[0]["params"]["url"] == "https://example.com"

    def test_multiple_tool_calls(self):
        text = (
            '[tool_call:browser_open_url]{"url": "https://example.com"}[/tool_call]'
            '[tool_call:browser_get_content]{"selector": "article"}[/tool_call]'
        )
        calls = parse_tool_calls(text)
        assert len(calls) == 2
        assert calls[0]["name"] == "browser_open_url"
        assert calls[1]["name"] == "browser_get_content"

    def test_no_tool_calls(self):
        text = "This is just a regular message."
        calls = parse_tool_calls(text)
        assert len(calls) == 0

    def test_invalid_json(self):
        text = "[tool_call:browser_open_url]not json[/tool_call]"
        calls = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["params"] == {}


class TestValidateOutput:
    """Test output validation."""

    def test_valid_pm_output(self):
        text = "方案概述\n1. 前端\n2. 后端\n[assign:agent_frontend] [assign:agent_backend]"
        ok, reason, meta = validate_output(text, "agent_pm")
        assert ok is True

    def test_pm_without_assign_fails(self):
        text = "方案概述\n1. 前端页面\n2. 后端接口"
        ok, reason, meta = validate_output(text, "agent_pm")
        assert ok is False
        assert "assign" in reason

    def test_valid_frontend_output(self):
        text = "摘要\n\n```html\n<!DOCTYPE html>\n<html><body>Hello</body></html>\n```"
        ok, reason, meta = validate_output(text, "agent_frontend")
        assert ok is True

    def test_frontend_without_code_fails(self):
        text = "这是一个前端回复但没有代码块，只是文字描述"
        ok, reason, meta = validate_output(text, "agent_frontend")
        assert ok is False

    def test_valid_backend_output(self):
        text = "摘要\n\n```python\nfrom fastapi import FastAPI\napp = FastAPI()\n```"
        ok, reason, meta = validate_output(text, "agent_backend")
        assert ok is True

    def test_question_fails(self):
        text = "你想用什么数据库？"
        ok, reason, meta = validate_output(text, "agent_tester")
        assert ok is False
        assert "question" in reason

    def test_too_short_fails(self):
        text = "短"
        ok, reason, meta = validate_output(text, "agent_devops")
        assert ok is False
        assert "short" in reason

    def test_browser_tool_passes_without_code(self):
        text = '[tool_call:browser_open_url]{"url": "https://example.com"}[/tool_call]'
        ok, reason, meta = validate_output(text, "agent_frontend")
        assert ok is True

    def test_metadata_populated(self):
        text = "摘要\n\n```python\ndef hello(): pass\n```"
        ok, reason, meta = validate_output(text, "agent_backend")
        assert meta["has_code"] is True
        assert meta["length"] > 0


class TestGetRetryPrompt:
    """Test retry prompt generation."""

    def test_pm_retry_prompt(self):
        prompt = get_retry_prompt("agent_pm", "no assign tags", "old output", "user text")
        assert "assign" in prompt
        assert "user text" in prompt

    def test_frontend_retry_prompt(self):
        prompt = get_retry_prompt("agent_frontend", "no code block", "old output", "user text")
        assert "代码" in prompt or "code" in prompt.lower()
        assert "user text" in prompt

    def test_unknown_agent(self):
        prompt = get_retry_prompt("agent_unknown", "reason", "old", "user text")
        assert "标准格式" in prompt


class TestPydanticModels:
    """Test Pydantic validation models."""

    def test_valid_tool_call(self):
        tc = ToolCall(name="browser_open_url", params={"url": "https://example.com"})
        assert tc.name == "browser_open_url"

    def test_invalid_tool_name(self):
        with pytest.raises(Exception):
            ToolCall(name="nonexistent_tool", params={})

    def test_agent_output_with_code(self):
        output = AgentOutput(
            text="Here is the code",
            tool_calls=[],
            has_code_block=True,
            ends_with_question=False,
        )
        assert output.has_code_block is True

    def test_agent_output_question_detection(self):
        output = AgentOutput(text="你想用什么？", tool_calls=[])
        assert output.ends_with_question is True

    def test_agent_output_no_question(self):
        output = AgentOutput(text="这是代码", tool_calls=[])
        assert output.ends_with_question is False
