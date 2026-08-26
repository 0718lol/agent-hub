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
    """Test output validation compatibility shim."""

    def test_valid_pm_output(self):
        text = "方案概述\n1. 前端\n2. 后端\n[assign:agent_frontend] [assign:agent_backend]"
        ok, reason, meta = validate_output(text, "agent_pm")
        assert ok is True

    def test_plain_text_also_passes(self):
        text = "这是普通回复，没有任何格式要求。"
        ok, reason, meta = validate_output(text, "agent_frontend")
        assert ok is True
        assert reason == "disabled"
        assert meta["length"] == len(text)

    def test_metadata_populated(self):
        text = "摘要\n\n```python\ndef hello(): pass\n```"
        ok, reason, meta = validate_output(text, "agent_backend")
        assert meta["has_code"] is True
        assert meta["length"] > 0


class TestGetRetryPrompt:
    """Test retry prompt compatibility text."""

    def test_pm_retry_prompt(self):
        prompt = get_retry_prompt("agent_pm", "no assign tags", "old output", "user text")
        assert "输出校验已停用" in prompt
        assert "user text" in prompt

    def test_frontend_retry_prompt(self):
        prompt = get_retry_prompt("agent_frontend", "no code block", "old output", "user text")
        assert "输出校验已停用" in prompt
        assert "user text" in prompt

    def test_unknown_agent(self):
        prompt = get_retry_prompt("agent_unknown", "reason", "old", "user text")
        assert "输出校验已停用" in prompt


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
