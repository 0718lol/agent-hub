"""Tests for metrics trace enhancements."""
import pytest
from app.core.metrics import TraceSpan, TraceStep, TaskTrace


class TestTraceSpan:
    def test_span_creation(self):
        span = TraceSpan(name="test", span_type="llm", start_time=1.0)
        assert span.name == "test"
        assert span.status == "success"
        assert span.error is None

    def test_span_finish_success(self):
        span = TraceSpan(name="test", span_type="llm", start_time=1.0)
        span.finish(output_data="response", status="success")
        assert span.status == "success"
        assert span.duration_ms >= 0
        assert span.error is None

    def test_span_finish_with_error(self):
        span = TraceSpan(name="test", span_type="llm", start_time=1.0)
        span.finish(status="error", error="Connection timeout")
        assert span.status == "error"
        assert span.error == "Connection timeout"

    def test_span_to_dict_includes_error(self):
        span = TraceSpan(name="test", span_type="tool", start_time=1.0)
        span.finish(status="error", error="Tool failed")
        d = span.model_dump()
        assert d["error"] == "Tool failed"
        assert d["status"] == "error"
        assert d["status"] == "error"


class TestTraceStep:
    def test_step_creation(self):
        step = TraceStep(agent_id="agent_test", agent_name="Test Agent", start_time=1.0)
        assert step.status == "running"
        assert step.tokens_used == 0

    def test_step_start_span(self):
        step = TraceStep(agent_id="agent_test", agent_name="Test", start_time=1.0)
        span = step.start_span("llm_call", "llm", input_data="prompt")
        assert span.name == "llm_call"
        assert len(step.spans) == 1

    def test_step_to_dict(self):
        step = TraceStep(agent_id="agent_test", agent_name="Test", start_time=1.0)
        step.finish(status="success", tokens=100)
        d = step.to_dict()
        assert d["agent_id"] == "agent_test"
        assert d["tokens_used"] == 100


class TestTaskTrace:
    def test_trace_creation(self):
        trace = TaskTrace(task_id="t1", conversation_id="c1", user_input="hello")
        assert trace.task_id == "t1"
        assert trace.conversation_id == "c1"

    def test_trace_to_dict(self):
        trace = TaskTrace(task_id="t1", conversation_id="c1", user_input="hello")
        d = trace.to_dict()
        assert d["task_id"] == "t1"
        assert "steps" in d
        assert "total_duration_ms" in d
