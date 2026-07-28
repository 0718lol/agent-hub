import pytest

from app.core.llm_client import LLMClient, ResilienceManager
from app.services.agent_orchestrator import is_llm_error_response


def test_partial_stream_marker_invalidates_otherwise_complete_code():
    output = (
        "```html path=index.html\n<h1>looks complete</h1>\n```\n"
        "[LLM 调用出错: 本轮结果已作废]"
    )

    assert is_llm_error_response(output)


@pytest.mark.asyncio
async def test_partial_stream_is_not_concatenated_with_retry():
    manager = ResilienceManager()
    client = LLMClient()
    client.provider = "partial-stream-test"
    attempts = 0

    async def interrupted_stream(_messages, _system, _tools=None):
        nonlocal attempts
        attempts += 1
        yield "```html\n<p>partial"
        raise ConnectionError("stream closed")

    chunks = [
        chunk
        async for chunk in manager.execute_with_retry(
            client, interrupted_stream, [], ""
        )
    ]

    assert attempts == 1
    assert chunks[0] == "```html\n<p>partial"
    assert "本轮结果已作废" in chunks[-1]


@pytest.mark.asyncio
async def test_failure_before_first_chunk_can_retry(monkeypatch):
    manager = ResilienceManager()
    client = LLMClient()
    client.provider = "pre-stream-retry-test"
    attempts = 0

    async def transient_stream(_messages, _system, _tools=None):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("connect failed")
        yield "complete"

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.core.llm_client.asyncio.sleep", no_sleep)
    chunks = [
        chunk
        async for chunk in manager.execute_with_retry(
            client, transient_stream, [], ""
        )
    ]

    assert attempts == 2
    assert chunks[-1] == "complete"
