import json

import httpx
import pytest

from app.core.llm_client import LLMClient


def _stream_response(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    _stream_response.payload = payload
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n',
    )


@pytest.mark.asyncio
async def test_deepseek_flash_disables_thinking_by_default(monkeypatch):
    transport = httpx.MockTransport(_stream_response)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_client(transport=transport, timeout=kwargs.get("timeout")),
    )
    client = LLMClient()
    client.configure("openai", "test-key", "https://api.deepseek.com", "deepseek-v4-flash")

    chunks = [chunk async for chunk in client._openai_stream([{"role": "user", "content": "hi"}], "", [])]

    assert chunks == ["ok"]
    assert _stream_response.payload["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_non_deepseek_request_has_no_thinking_option(monkeypatch):
    transport = httpx.MockTransport(_stream_response)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_client(transport=transport, timeout=kwargs.get("timeout")),
    )
    client = LLMClient()
    client.configure("openai", "test-key", "https://api.deepseek.com", "deepseek-v4-flash", thinking_enabled=False)
    client.configure("openai", "test-key", "https://api.example.com/v1", "example-model")

    chunks = [chunk async for chunk in client._openai_stream([{"role": "user", "content": "hi"}], "", [])]

    assert chunks == ["ok"]
    assert "thinking" not in _stream_response.payload


@pytest.mark.asyncio
async def test_openai_stream_forwards_json_response_format_without_tools(monkeypatch):
    transport = httpx.MockTransport(_stream_response)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_client(transport=transport, timeout=kwargs.get("timeout")),
    )
    client = LLMClient()
    client.configure("openai", "test-key", "https://api.deepseek.com", "deepseek-v4-flash")

    chunks = [
        chunk
        async for chunk in client._openai_stream(
            [{"role": "user", "content": "return json"}],
            "return json",
            [],
            {"type": "json_object"},
        )
    ]

    assert chunks == ["ok"]
    assert _stream_response.payload["response_format"] == {"type": "json_object"}
    assert "tools" not in _stream_response.payload
