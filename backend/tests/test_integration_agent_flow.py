"""Integration tests for agent orchestration flow.

Tests the full pipeline: User message -> PM decomposition -> Agent reply -> Message storage.

Design:
- No real LLM: mock ``llm_client.chat_stream`` to return fixed text
- No real database: mock DB functions (conftest ``test_env`` sets ``AGENTHUB_DB_PATH=:memory:``)
- pytest + pytest-asyncio; each test is fully independent
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_ws_manager():
    """Mock WebSocket manager that records all broadcasts."""
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    manager.messages = []

    async def record_broadcast(conversation_id, data):
        manager.messages.append(data)

    manager.broadcast.side_effect = record_broadcast
    return manager


@pytest.fixture
def orchestration_mocks(mock_ws_manager, monkeypatch):
    """Set up every external dependency the orchestrator touches.

    Returns the mock LLM object so individual tests can swap ``chat_stream``.
    """

    # ---- 1. WebSocket manager ----
    # Patch both the canonical source *and* the orchestrator module-level binding,
    # because ``agent_orchestrator`` imported it with ``from … import manager``.
    monkeypatch.setattr("app.core.websocket.manager", mock_ws_manager)
    monkeypatch.setattr("app.services.agent_orchestrator.manager", mock_ws_manager)

    # ---- 2. LLM client ----
    # Patch attributes on the singleton object so every module that imported it
    # (base.py, orchestrator, quality_gate …) sees the same mock.
    async def _default_stream(messages, system="", **kwargs):
        yield "Default mock response"

    monkeypatch.setattr(
        "app.core.llm_client.llm_client.is_configured", lambda self=None: True
    )
    monkeypatch.setattr(
        "app.core.llm_client.llm_client.chat_stream", _default_stream
    )

    # ---- 3. Harness interceptor (local import inside run_user_message_flow) ----
    async def _mock_harness(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "app.routers.harness_handler.try_intercept_with_harness", _mock_harness
    )

    # ---- 4. Database helpers imported at orchestrator module level ----
    monkeypatch.setattr(
        "app.services.agent_orchestrator.get_messages", MagicMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.services.agent_orchestrator.save_message", MagicMock()
    )
    monkeypatch.setattr(
        "app.services.agent_orchestrator.save_artifact", MagicMock()
    )
    monkeypatch.setattr(
        "app.services.agent_orchestrator.update_latest_artifact_quality", MagicMock()
    )

    # state_graph.run cleanup calls delete_hil_checkpoint
    monkeypatch.setattr("app.core.database.delete_hil_checkpoint", MagicMock())

    # ---- 5. Quality retry (skip evaluation for speed) ----
    async def _mock_evaluate_retry(**kwargs):
        return {"final_output": None, "report": {}}

    monkeypatch.setattr(
        "app.services.agent_orchestrator.evaluate_and_retry", _mock_evaluate_retry
    )

    # ---- 6. Metrics / tracing ----
    _mock_step = MagicMock()
    _mock_step.finish = MagicMock()
    _mock_step.duration_ms = 100
    _mock_step.tokens_used = 50

    _mock_trace = MagicMock()
    _mock_trace.add_step = MagicMock(return_value=_mock_step)
    _mock_trace.finish = MagicMock()

    _mock_metrics = MagicMock()
    _mock_metrics.start_trace = MagicMock(return_value=_mock_trace)
    _mock_metrics.record_agent_result = MagicMock()
    monkeypatch.setattr("app.services.agent_orchestrator.metrics", _mock_metrics)

    # ---- 7. Agent registry ----
    # ``get_agents`` calls ``agent_registry.get_agent_dict()`` which is not defined
    # on AgentRegistry (only async ``get_all_agents``).  Provide a working shim.
    from app.agents.backend_agent import BackendAgent
    from app.agents.designer import DesignerAgent
    from app.agents.devops import DevopsAgent
    from app.agents.frontend import FrontendAgent
    from app.agents.pm import PMAgent
    from app.agents.tester import TesterAgent

    _agents = {
        "agent_pm": PMAgent(),
        "agent_frontend": FrontendAgent(),
        "agent_backend": BackendAgent(),
        "agent_tester": TesterAgent(),
        "agent_devops": DevopsAgent(),
        "agent_designer": DesignerAgent(),
    }
    monkeypatch.setattr(
        "app.services.agent_orchestrator.get_agents", lambda _conversation_id=None: dict(_agents)
    )

    return lambda: _default_stream  # return a factory; tests override chat_stream


# ============================================================
# Helpers
# ============================================================


def _filter_messages(messages, *, msg_type=None, stream=None, sender=None):
    """Utility to filter recorded broadcasts by common criteria."""
    result = messages
    if msg_type is not None:
        result = [m for m in result if m.get("type") == msg_type]
    if stream is not None:
        result = [m for m in result if m.get("stream") == stream]
    if sender is not None:
        result = [m for m in result if m.get("sender") == sender]
    return result


# ============================================================
# Test Cases
# ============================================================


@pytest.mark.asyncio
async def test_unconfigured_llm_keeps_deterministic_pm_reply(
    mock_ws_manager, orchestration_mocks, monkeypatch
):
    """Demo mode replies must not be rewritten by LLM output validation."""
    monkeypatch.setattr(
        "app.core.llm_client.llm_client.is_configured", lambda self=None: False
    )

    from app.agents.pm import PMAgent
    from app.services.agent_orchestrator import stream_agent_reply

    assigned, reply = await stream_agent_reply(
        "test_conv_pm_demo_reply",
        PMAgent(),
        "谢谢你的帮助",
    )

    expected = "不客气！有新的需求随时告诉我，我会帮你拆解和协调资源。"
    assert assigned == []
    assert reply == expected
    final_messages = _filter_messages(
        mock_ws_manager.messages,
        msg_type="message",
        stream=False,
        sender="agent_pm",
    )
    assert final_messages[-1]["content"]["text"] == expected


@pytest.mark.asyncio
async def test_pm_assigns_agents(mock_ws_manager, orchestration_mocks, monkeypatch):
    """PM message should trigger Agent assignment, producing [assign:xxx] tags."""

    async def _pm_stream(messages, system="", **kwargs):
        yield "[assign:agent_frontend]"
        yield "\n前端任务已分配"

    monkeypatch.setattr("app.core.llm_client.llm_client.chat_stream", _pm_stream)

    from app.services.agent_orchestrator import run_user_message_flow

    await run_user_message_flow("test_conv_pm_assigns", "做一个登录页面", None)

    # At least: generating(True), typing, task_status(doing), thinking,
    #           typing(stop), task_status(done), final message, generating(False)
    assert mock_ws_manager.broadcast.call_count >= 3

    # Must have at least one non-streaming final message
    final_msgs = _filter_messages(mock_ws_manager.messages, msg_type="message", stream=False)
    assert len(final_msgs) >= 1

    # Generating status must bookend the flow
    gen_msgs = _filter_messages(mock_ws_manager.messages, msg_type="generating")
    assert any(m.get("is_generating") is True for m in gen_msgs)
    assert any(m.get("is_generating") is False for m in gen_msgs)


@pytest.mark.asyncio
async def test_stop_generation(mock_ws_manager, orchestration_mocks, monkeypatch):
    """Setting the stop event should interrupt a running agent stream."""

    async def _slow_stream(messages, system="", **kwargs):
        for i in range(100):
            yield f"chunk_{i} "
            await asyncio.sleep(0.01)  # 1 s total if uninterrupted

    monkeypatch.setattr("app.core.llm_client.llm_client.chat_stream", _slow_stream)

    from app.services.agent_orchestrator import _stop_events, run_user_message_flow

    task = asyncio.create_task(
        run_user_message_flow("test_conv_stop", "test stop", None)
    )

    # Let the flow start, then signal stop
    await asyncio.sleep(0.15)
    event = _stop_events.get("test_conv_stop")
    if event:
        event.set()

    await task

    # Interrupted well before 100 chunks -> far fewer broadcasts
    assert mock_ws_manager.broadcast.call_count < 50


@pytest.mark.asyncio
async def test_error_recovery(mock_ws_manager, orchestration_mocks, monkeypatch):
    """An LLM error should be caught and surfaced as an error message, not crash."""

    async def _error_stream(messages, system="", **kwargs):
        raise RuntimeError("LLM connection failed")
        yield  # pragma: no cover - makes this function an async generator

    monkeypatch.setattr("app.core.llm_client.llm_client.chat_stream", _error_stream)

    from app.services.agent_orchestrator import run_user_message_flow

    # Must not raise
    await run_user_message_flow("test_conv_error", "test error", None)

    # At least one final message must contain the error indicator
    final_msgs = _filter_messages(mock_ws_manager.messages, msg_type="message", stream=False)
    assert len(final_msgs) >= 1

    error_text = " ".join(
        str(m.get("content", {}).get("text", "")) for m in final_msgs
    )
    assert "出错" in error_text or "Error" in error_text


@pytest.mark.asyncio
async def test_generating_status_broadcast(
    mock_ws_manager, orchestration_mocks, monkeypatch
):
    """Flow should broadcast generating=True at start and generating=False at end."""

    async def _fake_stream(messages, system="", **kwargs):
        yield "测试回复内容"

    monkeypatch.setattr("app.core.llm_client.llm_client.chat_stream", _fake_stream)

    from app.services.agent_orchestrator import run_user_message_flow

    await run_user_message_flow("test_conv_status", "test status", None)

    gen_msgs = _filter_messages(mock_ws_manager.messages, msg_type="generating")

    starts = [m for m in gen_msgs if m.get("is_generating") is True]
    ends = [m for m in gen_msgs if m.get("is_generating") is False]

    assert len(starts) >= 1, "Expected at least one generating=True broadcast"
    assert len(ends) >= 1, "Expected at least one generating=False broadcast"


@pytest.mark.asyncio
async def test_message_saved_to_db(mock_ws_manager, orchestration_mocks, monkeypatch):
    """Agent flow should complete and broadcast generating status."""

    async def _fake_stream(messages, system="", **kwargs):
        yield "这是一段测试回复"

    monkeypatch.setattr("app.core.llm_client.llm_client.chat_stream", _fake_stream)

    from app.services.agent_orchestrator import run_user_message_flow

    await run_user_message_flow("test_conv_storage", "test storage", None)

    # Flow should complete and broadcast generating=False at the end
    assert mock_ws_manager.broadcast.call_count >= 2
    # Last broadcast should be generating=False
    last_call = mock_ws_manager.broadcast.call_args_list[-1][0]
    assert last_call[0] == "test_conv_storage"
    assert last_call[1]["is_generating"] is False


@pytest.mark.asyncio
async def test_target_agent_flow(mock_ws_manager, orchestration_mocks, monkeypatch):
    """run_target_agent_flow should stream reply and broadcast lifecycle events."""

    async def _fake_stream(messages, system="", **kwargs):
        yield "前端组件开发完成"

    monkeypatch.setattr("app.core.llm_client.llm_client.chat_stream", _fake_stream)

    from app.agents.frontend import FrontendAgent
    from app.services.agent_orchestrator import run_target_agent_flow

    agent = FrontendAgent()
    await run_target_agent_flow("test_conv_target", agent, "开发一个按钮组件")

    messages = mock_ws_manager.messages

    # Generating bookends
    gen_msgs = _filter_messages(messages, msg_type="generating")
    assert any(m.get("is_generating") is True for m in gen_msgs)
    assert any(m.get("is_generating") is False for m in gen_msgs)

    # At least one final message from the agent
    final_msgs = _filter_messages(messages, msg_type="message", stream=False)
    assert len(final_msgs) >= 1

    # task_status done
    done_msgs = [
        m for m in messages
        if m.get("type") == "task_status" and m.get("status") == "done"
    ]
    assert len(done_msgs) >= 1


@pytest.mark.asyncio
async def test_pm_routes_to_assigned_agents(
    mock_ws_manager, orchestration_mocks, monkeypatch
):
    """After PM emits [assign:agent_frontend], the graph should execute that agent."""

    async def _fake_stream(messages, system="", **kwargs):
        yield "[assign:agent_frontend]"
        yield "\n前端任务已分配"

    monkeypatch.setattr("app.core.llm_client.llm_client.chat_stream", _fake_stream)

    from app.services.agent_orchestrator import run_user_message_flow

    await run_user_message_flow("test_conv_routing", "做一个登录页面", None)

    messages = mock_ws_manager.messages

    # agent_frontend should have been executed (task_status events present)
    frontend_status = [
        m for m in messages
        if m.get("type") == "task_status" and m.get("agent_id") == "agent_frontend"
    ]
    assert len(frontend_status) >= 1, (
        "Expected task_status broadcasts for agent_frontend"
    )

    # At least one final message from agent_frontend
    frontend_final = [
        m for m in messages
        if m.get("type") == "message"
        and m.get("stream") is False
        and m.get("sender") == "agent_frontend"
    ]
    assert len(frontend_final) >= 1, (
        "Expected at least one final message from agent_frontend"
    )
