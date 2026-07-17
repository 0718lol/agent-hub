"""
Metrics Collector — tracks agent performance for the Evaluation Dashboard.

Collects:
  - Per-agent quality scores
  - Token usage & latency
  - Best-of-N hit rates
  - Debate outcomes
  - Code execution results
  - Structured nested child spans for LLM, Tools, and RAG execution (APM Tracking)
"""

import contextvars
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("metrics")

# Thread-safe Context Variables for decoupled trace span propagation
active_trace_var = contextvars.ContextVar("active_trace", default=None)
active_step_var = contextvars.ContextVar("active_step", default=None)


class TraceSpan(BaseModel):
    """A single child span inside a TraceStep (e.g. LLM call, Tool execute, RAG search)
    representing fine-grained APM telemetry.
    """
    name: str
    span_type: str  # "llm" | "tool" | "rag" | "custom"
    start_time: float
    end_time: float = 0.0
    duration_ms: int = 0
    status: str = "success"  # success | error | timeout | skipped
    error: str | None = None  # error message if status is error
    input_data: Any | None = None
    output_data: Any | None = None
    metadata: dict = Field(default_factory=dict)

    def finish(self, output_data: Any = None, status: str = "success", error: str | None = None, metadata: dict | None = None):
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        self.status = status
        if error:
            self.error = error
        if output_data is not None:
            self.output_data = output_data
        if metadata:
            self.metadata.update(metadata)


@dataclass
class TraceStep:
    """A single step in an agent execution trace (parent node)."""
    agent_id: str
    agent_name: str
    start_time: float
    end_time: float = 0.0
    duration_ms: int = 0
    tokens_used: int = 0
    quality_score: float = 0.0
    status: str = "running"  # running | success | retry | error
    detail: str = ""
    spans: list[TraceSpan] = field(default_factory=list)

    def start_span(self, name: str, span_type: str, input_data: Any = None) -> TraceSpan:
        """Start a new child span inside this step trace context."""
        span = TraceSpan(name=name, span_type=span_type, start_time=time.time(), input_data=input_data)
        self.spans.append(span)
        return span

    def finish(self, status: str = "success", tokens: int = 0, score: float = 0.0, detail: str = ""):
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        self.status = status
        self.tokens_used = tokens
        self.quality_score = score
        self.detail = detail

        # Reset the active step context variable if it matches this step
        if active_step_var.get() == self:
            active_step_var.set(None)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "quality_score": self.quality_score,
            "status": self.status,
            "detail": self.detail,
            "spans": [s.model_dump() for s in self.spans],
        }


@dataclass
class TaskTrace:
    """Full trace for a single user request → multi-agent response (Trace boundary)."""
    task_id: str
    conversation_id: str
    user_input: str
    start_time: float = field(default_factory=time.time)
    steps: list[TraceStep] = field(default_factory=list)
    total_duration_ms: int = 0
    total_tokens: int = 0

    def add_step(self, agent_id: str, agent_name: str) -> TraceStep:
        """Start and register a parent execution step, updating active ContextVar."""
        step = TraceStep(agent_id=agent_id, agent_name=agent_name, start_time=time.time())
        self.steps.append(step)
        active_step_var.set(step)
        return step

    def finish(self):
        self.total_duration_ms = int((time.time() - self.start_time) * 1000)
        self.total_tokens = sum(s.tokens_used for s in self.steps)

        # Export completed trace data asynchronously in the background
        metrics._export_to_langfuse(self)

        # Push trace to SSE subscribers (non-blocking)
        try:
            import asyncio

            from app.routers.metrics import push_trace
            trace_dict = self.to_dict()
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(push_trace(trace_dict))
            except RuntimeError:
                pass
        except Exception:
            pass

        # Reset context variable if it matches this trace
        if active_trace_var.get() == self:
            active_trace_var.set(None)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "user_input": self.user_input[:100],
            "start_time": self.start_time,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "steps": [s.to_dict() for s in self.steps],
        }


class MetricsCollector:
    """Global metrics collector singleton."""

    def __init__(self):
        self.traces: list[TaskTrace] = []
        self.agent_scores: dict[str, list[float]] = defaultdict(list)
        self.agent_latencies: dict[str, list[int]] = defaultdict(list)
        self.agent_tokens: dict[str, list[int]] = defaultdict(list)
        self.best_of_n_results: list[dict] = []
        self.debate_results: list[dict] = []
        self.sandbox_results: list[dict] = []
        self.quality_gate_results: list[dict] = []
        self.total_requests: int = 0
        self.quality_gate_passes: int = 0
        self.quality_gate_retries: int = 0

    def start_trace(self, task_id: str, conversation_id: str, user_input: str) -> TaskTrace:
        """Start a new global trace flow, updating active ContextVar."""
        trace = TaskTrace(task_id=task_id, conversation_id=conversation_id, user_input=user_input)
        self.traces.append(trace)
        # Keep last 100 traces
        if len(self.traces) > 100:
            self.traces = self.traces[-100:]
        self.total_requests += 1
        active_trace_var.set(trace)
        return trace

    def record_agent_result(self, agent_id: str, score: float, latency_ms: int, tokens: int):
        self.agent_scores[agent_id].append(score)
        self.agent_latencies[agent_id].append(latency_ms)
        self.agent_tokens[agent_id].append(tokens)
        # Keep last 50 per agent
        for d in (self.agent_scores, self.agent_latencies, self.agent_tokens):
            if len(d[agent_id]) > 50:
                d[agent_id] = d[agent_id][-50:]

    @staticmethod
    def _active_conversation_id() -> str:
        trace = active_trace_var.get()
        return trace.conversation_id if trace else ""

    def record_quality_gate(
        self,
        passed: bool,
        retried: bool = False,
        conversation_id: str = "",
    ):
        if passed:
            self.quality_gate_passes += 1
        if retried:
            self.quality_gate_retries += 1
        self.quality_gate_results.append({
            "passed": passed,
            "retried": retried,
            "conversation_id": conversation_id or self._active_conversation_id(),
        })
        if len(self.quality_gate_results) > 100:
            self.quality_gate_results = self.quality_gate_results[-100:]

    def record_best_of_n(
        self,
        n: int,
        scores: list[float],
        best_idx: int,
        conversation_id: str = "",
    ):
        self.best_of_n_results.append({
            "n": n,
            "scores": scores,
            "best_idx": best_idx,
            "best_score": scores[best_idx] if scores else 0,
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "conversation_id": conversation_id or self._active_conversation_id(),
        })
        if len(self.best_of_n_results) > 50:
            self.best_of_n_results = self.best_of_n_results[-50:]

    def record_debate(
        self,
        proposer_score: float,
        reviewer_score: float,
        final_score: float,
        conversation_id: str = "",
    ):
        self.debate_results.append({
            "proposer_score": proposer_score,
            "reviewer_score": reviewer_score,
            "final_score": final_score,
            "conversation_id": conversation_id or self._active_conversation_id(),
        })
        if len(self.debate_results) > 50:
            self.debate_results = self.debate_results[-50:]

    def record_sandbox(
        self,
        language: str,
        status: str,
        duration_ms: int,
        *,
        user_id: str = "",
        conversation_id: str = "",
    ):
        self.sandbox_results.append({
            "language": language,
            "status": status,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "conversation_id": conversation_id or self._active_conversation_id(),
        })
        if len(self.sandbox_results) > 50:
            self.sandbox_results = self.sandbox_results[-50:]

    def _export_to_langfuse(self, trace: TaskTrace):
        """Asynchronously export completed trace to Langfuse APM Collector if environment keys are configured."""
        import os
        import threading

        lf_public = os.environ.get("AGENTHUB_LANGFUSE_PUBLIC_KEY")
        lf_secret = os.environ.get("AGENTHUB_LANGFUSE_SECRET_KEY")
        lf_host = os.environ.get("AGENTHUB_LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")

        if not (lf_public and lf_secret):
            return

        def _post_payload():
            try:
                import httpx
                url = f"{lf_host}/api/public/ingestion"
                auth = (lf_public, lf_secret)

                batch = []

                # 1. Main Trace event
                batch.append({
                    "id": f"trace-{trace.task_id}",
                    "type": "trace",
                    "body": {
                        "id": trace.task_id,
                        "name": f"agenthub_conv_{trace.conversation_id}",
                        "userId": "agenthub_user",
                        "input": trace.user_input,
                        "metadata": {
                            "conversation_id": trace.conversation_id,
                            "total_tokens": trace.total_tokens
                        }
                    }
                })

                # 2. Spans for each TraceStep and children spans
                for step in trace.steps:
                    step_id = f"step-{step.agent_id}-{step.start_time}"
                    batch.append({
                        "id": step_id,
                        "type": "span",
                        "body": {
                            "traceId": trace.task_id,
                            "name": step.agent_name,
                            "startTime": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(step.start_time)),
                            "endTime": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(step.end_time or time.time())),
                            "metadata": {
                                "agent_id": step.agent_id,
                                "quality_score": step.quality_score,
                                "status": step.status,
                                "tokens_used": step.tokens_used
                            }
                        }
                    })

                    # Children Spans (LLM / Tool / RAG)
                    for span in step.spans:
                        span_id = f"span-{span.name}-{span.start_time}"
                        batch.append({
                            "id": span_id,
                            "type": "span" if span.span_type != "llm" else "generation",
                            "body": {
                                "traceId": trace.task_id,
                                "parentObserveId": step_id,
                                "name": span.name,
                                "startTime": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(span.start_time)),
                                "endTime": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(span.end_time or time.time())),
                                "input": span.input_data,
                                "output": span.output_data,
                                "metadata": span.metadata
                            }
                        })

                payload = {"batch": batch}
                headers = {"Content-Type": "application/json"}

                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, json=payload, auth=auth, headers=headers)
                    if resp.status_code != 200:
                        logger.warning(f"Langfuse APM export failed with status {resp.status_code}: {resp.text}")
            except Exception as ex:
                logger.warning(f"Failed to post APM trace to Langfuse: {ex}")

        thread = threading.Thread(target=_post_payload, daemon=True)
        thread.start()

    @staticmethod
    def _summarize_traces(traces: list[TaskTrace]) -> dict:
        by_agent: dict[str, dict[str, list]] = defaultdict(
            lambda: {"scores": [], "latencies": [], "tokens": []}
        )
        for trace in traces:
            for step in trace.steps:
                values = by_agent[step.agent_id]
                values["scores"].append(step.quality_score)
                values["latencies"].append(step.duration_ms)
                values["tokens"].append(step.tokens_used)

        summary = {}
        for agent_id, values in by_agent.items():
            scores = values["scores"]
            latencies = values["latencies"]
            tokens = values["tokens"]
            summary[agent_id] = {
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "max_score": round(max(scores), 1) if scores else 0,
                "min_score": round(min(scores), 1) if scores else 0,
                "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
                "total_tokens": sum(tokens),
                "call_count": len(scores),
            }
        return summary

    @staticmethod
    def _best_of_n_stats(results: list[dict]) -> dict:
        if not results:
            return {}
        best_scores = [result["best_score"] for result in results]
        avg_scores = [result["avg_score"] for result in results]
        return {
            "total_runs": len(results),
            "avg_best_score": round(sum(best_scores) / len(best_scores), 1),
            "avg_avg_score": round(sum(avg_scores) / len(avg_scores), 1),
            "improvement": round(
                (sum(best_scores) / len(best_scores)) - (sum(avg_scores) / len(avg_scores)), 1
            ),
        }

    @staticmethod
    def _sandbox_stats(results: list[dict]) -> dict:
        if not results:
            return {}
        success = sum(1 for result in results if result["status"] == "success")
        return {
            "total_runs": len(results),
            "success_rate": round(success / len(results) * 100, 1),
            "avg_duration_ms": int(
                sum(result["duration_ms"] for result in results) / len(results)
            ),
        }

    @staticmethod
    def _quality_stats(results: list[dict]) -> dict:
        passes = sum(1 for result in results if result["passed"])
        retries = sum(1 for result in results if result["retried"])
        total = passes + retries
        return {
            "total_evaluations": total,
            "pass_rate": round(passes / total * 100, 1) if total else 0,
            "retry_count": retries,
        }

    def get_dashboard_data(self, user_id: str | None = None) -> dict:
        """Get dashboard metrics, optionally restricted to one tenant."""
        if user_id is not None:
            from app.core.tenancy import belongs_to_user

            traces = [
                trace for trace in self.traces
                if belongs_to_user(trace.conversation_id, user_id)
            ]
            def event_belongs(event: dict) -> bool:
                conversation_id = event.get("conversation_id", "")
                return bool(conversation_id and belongs_to_user(conversation_id, user_id))
            best_of_n_results = [event for event in self.best_of_n_results if event_belongs(event)]
            debate_results = [event for event in self.debate_results if event_belongs(event)]
            quality_results = [event for event in self.quality_gate_results if event_belongs(event)]
            sandbox_results = [
                event for event in self.sandbox_results
                if event.get("user_id") == user_id or event_belongs(event)
            ]
            return {
                "total_requests": len(traces),
                "agent_summary": self._summarize_traces(traces),
                "best_of_n": self._best_of_n_stats(best_of_n_results),
                "sandbox": self._sandbox_stats(sandbox_results),
                "quality_gate": self._quality_stats(quality_results),
                "recent_traces": [trace.to_dict() for trace in traces[-10:]],
                "debate_results": debate_results[-10:],
            }

        # Agent performance summary for trusted internal callers.
        # Agent performance summary
        agent_summary = {}
        for agent_id in self.agent_scores:
            scores = self.agent_scores[agent_id]
            latencies = self.agent_latencies.get(agent_id, [])
            tokens = self.agent_tokens.get(agent_id, [])
            agent_summary[agent_id] = {
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "max_score": round(max(scores), 1) if scores else 0,
                "min_score": round(min(scores), 1) if scores else 0,
                "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
                "total_tokens": sum(tokens),
                "call_count": len(scores),
            }

        # Best-of-N stats
        bon_stats = self._best_of_n_stats(self.best_of_n_results)

        # Sandbox stats
        sandbox_stats = self._sandbox_stats(self.sandbox_results)

        # Quality gate stats
        total_gate = self.quality_gate_passes + self.quality_gate_retries
        quality_stats = {
            "total_evaluations": total_gate,
            "pass_rate": round(self.quality_gate_passes / total_gate * 100, 1) if total_gate > 0 else 0,
            "retry_count": self.quality_gate_retries,
        }

        return {
            "total_requests": self.total_requests,
            "agent_summary": agent_summary,
            "best_of_n": bon_stats,
            "sandbox": sandbox_stats,
            "quality_gate": quality_stats,
            "recent_traces": [t.to_dict() for t in self.traces[-10:]],
            "debate_results": self.debate_results[-10:],
        }


# Global singleton
metrics = MetricsCollector()
