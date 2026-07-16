"""Tests for Reflexion engine."""
from unittest.mock import AsyncMock

import pytest

from app.core.reflexion_engine import ReflexionEngine


class TestReflexionEngine:
    def test_initial_state(self):
        engine = ReflexionEngine()
        assert engine.reflections == {}
        assert engine.max_reflections == 20

    @pytest.mark.asyncio
    async def test_reflect_stores_lesson(self):
        engine = ReflexionEngine()
        mock_client = AsyncMock()
        async def mock_stream(messages):
            yield "[lesson] Missing error handling"
        mock_client.chat_stream = mock_stream
        result = await engine.reflect("agent_test", "task", "output", "error", mock_client)
        assert result is not None
        assert "lesson" in result.lower()
        assert len(engine.reflections["agent_test"]) == 1

    @pytest.mark.asyncio
    async def test_reflect_without_llm(self):
        engine = ReflexionEngine()
        result = await engine.reflect("agent_test", "task", "output", "error", llm_client=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_sliding_window(self):
        engine = ReflexionEngine(max_reflections=3)
        mock_client = AsyncMock()
        for i in range(5):
            async def mock_stream(messages, i=i):
                yield f"[lesson] lesson {i}"
            mock_client.chat_stream = mock_stream
            await engine.reflect("agent_test", f"task {i}", "output", "error", mock_client)
        assert len(engine.reflections["agent_test"]) == 3

    @pytest.mark.asyncio
    async def test_empty_response(self):
        engine = ReflexionEngine()
        mock_client = AsyncMock()
        async def mock_stream(messages):
            yield ""
        mock_client.chat_stream = mock_stream
        result = await engine.reflect("agent_test", "task", "output", "error", mock_client)
        assert result is None

    def test_get_context_empty(self):
        engine = ReflexionEngine()
        assert engine.get_context("agent_test") == ""

    def test_get_context_with_reflections(self):
        engine = ReflexionEngine()
        engine.reflections["agent_test"] = [
            {"reflection": "[lesson] lesson 1", "task": "t1", "ts": "2024-01-01"},
            {"reflection": "[lesson] lesson 2", "task": "t2", "ts": "2024-01-02"},
        ]
        ctx = engine.get_context("agent_test")
        assert "lesson 1" in ctx
        assert "lesson 2" in ctx

    def test_should_retry(self):
        engine = ReflexionEngine(max_retries=2)
        assert engine.should_retry("agent_test", 0) is True
        assert engine.should_retry("agent_test", 1) is True
        assert engine.should_retry("agent_test", 2) is False

    def test_clear(self):
        engine = ReflexionEngine()
        engine.reflections["agent_test"] = [{"reflection": "test", "task": "", "ts": ""}]
        engine.clear("agent_test")
        assert "agent_test" not in engine.reflections
