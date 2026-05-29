"""Unit tests for the runtime tool system."""

import pytest
from app.tools.registry import (
    TOOL_REGISTRY, parse_tool_calls, execute_tool_call, get_tools_prompt,
)


def test_registry_has_tools():
    """All 5 built-in tools should be registered."""
    assert "web_search" in TOOL_REGISTRY
    assert "http_request" in TOOL_REGISTRY
    assert "file_read" in TOOL_REGISTRY
    assert "file_write" in TOOL_REGISTRY
    assert "file_list" in TOOL_REGISTRY


def test_parse_tool_calls_basic():
    """Should parse a simple tool_call tag."""
    text = '让我搜索一下 [tool_call:web_search]{"query": "FastAPI"}[/tool_call] 好的'
    results = parse_tool_calls(text)
    assert len(results) == 1
    name, params, start, end = results[0]
    assert name == "web_search"
    assert params == {"query": "FastAPI"}
    assert start > 0
    assert end > start


def test_parse_tool_calls_empty():
    """No tags should return empty list."""
    assert parse_tool_calls("hello world") == []


def test_parse_tool_calls_multiple():
    """Should parse multiple tool_call tags."""
    text = '[tool_call:web_search]{"query": "a"}[/tool_call] then [tool_call:http_request]{"url": "http://x.com"}[/tool_call]'
    results = parse_tool_calls(text)
    assert len(results) == 2
    assert results[0][0] == "web_search"
    assert results[1][0] == "http_request"


def test_get_tools_prompt_not_empty():
    """Prompt should contain tool descriptions."""
    prompt = get_tools_prompt()
    assert "web_search" in prompt
    assert "tool_call" in prompt
    assert len(prompt) > 100


@pytest.mark.anyio
async def test_execute_unknown_tool():
    """Unknown tool should return error."""
    result = await execute_tool_call("nonexistent_tool", {})
    assert not result.success
    assert "未知工具" in result.error


@pytest.mark.anyio
async def test_file_list_empty_sandbox():
    """file_list on a fresh conversation should return empty or success."""
    result = await execute_tool_call("file_list", {"conversation_id": "test_conv_xyz"})
    assert result.success
    assert "files" in result.data


@pytest.mark.anyio
async def test_file_write_and_read():
    """Write a file then read it back."""
    conv_id = "test_conv_rw"
    # Write
    w_result = await execute_tool_call("file_write", {
        "conversation_id": conv_id,
        "path": "hello.txt",
        "content": "Hello, AgentHub!",
    })
    assert w_result.success

    # Read back
    r_result = await execute_tool_call("file_read", {
        "conversation_id": conv_id,
        "path": "hello.txt",
    })
    assert r_result.success
    assert r_result.data["content"] == "Hello, AgentHub!"


@pytest.mark.anyio
async def test_file_read_path_traversal():
    """Attempting path traversal should fail."""
    result = await execute_tool_call("file_read", {
        "conversation_id": "test_conv_sec",
        "path": "../../etc/passwd",
    })
    assert not result.success
    assert "越界" in result.error


@pytest.mark.anyio
async def test_http_request_invalid_url():
    """Invalid URL should return error."""
    result = await execute_tool_call("http_request", {"url": "not-a-url"})
    assert not result.success
    assert "http://" in result.error or "https://" in result.error
