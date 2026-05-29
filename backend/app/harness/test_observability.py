import sys
import os
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.metrics import metrics, active_trace_var, active_step_var
from app.tools.registry import execute_tool_call
from app.core.rag_engine import rag_engine


class TestObservability(unittest.TestCase):

    def setUp(self):
        # Clear metrics traces to start fresh
        metrics.traces = []
        # Clear active context vars
        active_trace_var.set(None)
        active_step_var.set(None)

    def test_context_var_propagation(self):
        """Test ContextVar active step propagation across async boundaries."""
        trace = metrics.start_trace(
            task_id="test_task_1",
            conversation_id="test_conv_1",
            user_input="Hello AI"
        )
        self.assertEqual(active_trace_var.get(), trace)

        step = trace.add_step("agent_pm", "PM Agent")
        self.assertEqual(active_step_var.get(), step)

        # Test nested async execution maintains ContextVar
        async def async_check():
            self.assertEqual(active_trace_var.get(), trace)
            self.assertEqual(active_step_var.get(), step)
            # Create a child span in the async task
            span = step.start_span("async_span", "custom", {"foo": "bar"})
            self.assertEqual(len(step.spans), 1)
            self.assertEqual(step.spans[0], span)
            span.finish(output_data="async_success")
            self.assertEqual(span.status, "success")
            self.assertGreaterEqual(span.duration_ms, 0)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(async_check())

        step.finish(status="success")
        self.assertIsNone(active_step_var.get())

        trace.finish()
        self.assertIsNone(active_trace_var.get())

    def test_nested_spans_tree_llm_tool_rag(self):
        """Test spans tree building under the parent step during simulated LLM, Tool, and RAG execution."""
        trace = metrics.start_trace(
            task_id="test_task_2",
            conversation_id="test_conv_2",
            user_input="Retrieve and edit"
        )
        step = trace.add_step("agent_backend", "Backend Agent")

        # 1. Simulate LLM execute_with_retry span creation via context var
        from app.core.llm_client import resilience_manager, LLMClient
        client = LLMClient()
        client.configure(provider="openai", api_key="test_key", base_url="api.openai.com", model="gpt-4o")

        async def simulate_llm_stream():
            yield "Hello "
            yield "World"

        async def run_llm_call():
            generator = resilience_manager.execute_with_retry(
                client_instance=client,
                stream_func=lambda msgs, sys, tools=None: simulate_llm_stream(),
                messages=[{"role": "user", "content": "test"}],
                system="system prompt"
            )
            chunks = []
            async for chunk in generator:
                chunks.append(chunk)
            return "".join(chunks)

        loop = asyncio.get_event_loop()
        res = loop.run_until_complete(run_llm_call())
        self.assertEqual(res, "Hello World")

        # Verify LLM span was recorded
        llm_spans = [s for s in step.spans if s.span_type == "llm"]
        self.assertEqual(len(llm_spans), 1)
        self.assertEqual(llm_spans[0].name, "llm_openai_gpt-4o")
        self.assertEqual(llm_spans[0].status, "success")

        # 2. Simulate Tool execution span creation
        from app.tools.registry import AgentTool, register_tool, ToolResult
        class DummyTool(AgentTool):
            name = "dummy_tool"
            description = "A dummy tool for testing"
            parameters = {"type": "object", "properties": {"val": {"type": "string"}}}
            
            async def execute(self, params: dict) -> ToolResult:
                return ToolResult(success=True, data="tool_output")

        register_tool(DummyTool())

        res_tool = loop.run_until_complete(execute_tool_call("dummy_tool", {"val": "hello"}))
        self.assertTrue(res_tool.success)
        self.assertEqual(res_tool.data, "tool_output")

        # Verify Tool span was recorded
        tool_spans = [s for s in step.spans if s.span_type == "tool"]
        self.assertEqual(len(tool_spans), 1)
        self.assertEqual(tool_spans[0].name, "tool_dummy_tool")
        self.assertEqual(tool_spans[0].status, "success")
        self.assertEqual(tool_spans[0].input_data, {"params": {"val": "hello"}})
        self.assertEqual(tool_spans[0].output_data, {"success": True, "data": "tool_output", "error": ""})

        # 3. Simulate RAG semantic search span creation
        with patch("app.core.rag_engine._get_or_create_collection") as mock_col_func:
            mock_collection = MagicMock()
            mock_collection.count.return_value = 5
            mock_collection.query.return_value = {
                "documents": [["Relevant semantic text chunk"]],
                "distances": [[0.15]],
                "metadatas": [[{"doc_id": "doc1", "filename": "doc1.txt"}]]
            }
            mock_col_func.return_value = mock_collection

            hits = rag_engine.query("query test", top_k=2)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["text"], "Relevant semantic text chunk")
            self.assertEqual(hits[0]["score"], 0.85)

        # Verify RAG span was recorded
        rag_spans = [s for s in step.spans if s.span_type == "rag"]
        self.assertEqual(len(rag_spans), 1)
        self.assertEqual(rag_spans[0].name, "rag_semantic_search")
        self.assertEqual(rag_spans[0].status, "success")
        self.assertEqual(rag_spans[0].metadata["hits_count"], 1)

        step.finish()
        trace.finish()

    def test_metrics_rest_api_endpoint(self):
        """Test telemetry structure mapping in REST endpoint GET /api/metrics/traces."""
        trace = metrics.start_trace(
            task_id="api_task",
            conversation_id="api_conv",
            user_input="Show metrics"
        )
        step = trace.add_step("agent_tester", "Tester Agent")
        step.start_span("sub_span", "custom").finish("done")
        step.finish()
        trace.finish()

        # Simulate FastAPI route response
        traces_data = [t.to_dict() for t in metrics.traces[-20:]]
        
        # Verify the structure has all key fields
        api_trace = next(t for t in traces_data if t["task_id"] == "api_task")
        self.assertEqual(api_trace["conversation_id"], "api_conv")
        self.assertEqual(api_trace["user_input"], "Show metrics")
        self.assertEqual(len(api_trace["steps"]), 1)
        
        api_step = api_trace["steps"][0]
        self.assertEqual(api_step["agent_id"], "agent_tester")
        self.assertEqual(api_step["agent_name"], "Tester Agent")
        self.assertEqual(len(api_step["spans"]), 1)
        
        api_span = api_step["spans"][0]
        self.assertEqual(api_span["name"], "sub_span")
        self.assertEqual(api_span["span_type"], "custom")
        self.assertEqual(api_span["output_data"], "done")
        self.assertEqual(api_span["status"], "success")


if __name__ == "__main__":
    unittest.main()
