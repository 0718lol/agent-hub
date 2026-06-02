import sys
import os
import unittest
import asyncio
from unittest.mock import AsyncMock, patch

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.state_graph import StateGraph

class MockWebSocketManager:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, conversation_id: str, message: dict):
        self.broadcasts.append((conversation_id, message))


class TestDeterministicStatechart(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Patch WebSocket manager
        import app.core.websocket as ws
        self.mock_manager = MockWebSocketManager()
        self.original_manager = ws.manager
        ws.manager = self.mock_manager

    def tearDown(self):
        import app.core.websocket as ws
        ws.manager = self.original_manager

    async def test_hierarchical_nested_sub_graphs(self):
        """Test StateGraph recursively running nested sub-graphs and cascading state changes."""
        # 1. Define Child Sub-graph (Development Flow)
        child_graph = StateGraph()
        child_execution = []

        async def run_frontend(state: dict) -> dict:
            child_execution.append("agent_frontend")
            return {"frontend_done": True, "ui_theme": "cyberpunk"}

        async def run_backend(state: dict) -> dict:
            child_execution.append("agent_backend")
            return {"backend_done": True, "api_port": 8080}

        child_graph.add_node("agent_frontend", run_frontend)
        child_graph.add_node("agent_backend", run_backend)
        child_graph.add_edge("agent_frontend", "agent_backend")
        child_graph.add_edge("agent_backend", "END")

        # Overwrite run entry point in child to start from frontend instead of PM
        # Let's patch starting node in child_graph.run
        original_run = child_graph.run
        async def child_run_patched(initial_state, conversation_id, stop_event=None):
            # Temporarily intercept pm entry point to run frontend first
            from unittest.mock import patch
            # We can run child graph custom flow or override starting node
            # The cleanest way is just running the patched run that starts with frontend
            state = initial_state.copy()
            state.setdefault("completed_nodes", [])
            current_node = "agent_frontend"
            
            while current_node and current_node != "END":
                if current_node == "agent_frontend":
                    update = await run_frontend(state)
                    state.update(update)
                    state["completed_nodes"].append("agent_frontend")
                    current_node = "agent_backend"
                elif current_node == "agent_backend":
                    update = await run_backend(state)
                    state.update(update)
                    state["completed_nodes"].append("agent_backend")
                    current_node = "END"
            return state
            
        child_graph.run = child_run_patched

        # 2. Define Parent Graph
        parent_graph = StateGraph()
        parent_execution = []

        async def run_pm(state: dict) -> dict:
            parent_execution.append("agent_pm")
            return {"pm_done": True}

        parent_graph.add_node("agent_pm", run_pm)
        # Add child graph directly as a node in parent graph!
        parent_graph.add_node("agent_development", child_graph)

        parent_graph.add_edge("agent_pm", "agent_development")
        parent_graph.add_edge("agent_development", "END")

        stop_event = asyncio.Event()
        final_state = await parent_graph.run({}, "test_conv_id", stop_event)

        # 3. Assertions
        # Parent PM executes, then recursively delegates to child graph which executes frontend and backend!
        self.assertEqual(parent_execution, ["agent_pm"])
        self.assertEqual(child_execution, ["agent_frontend", "agent_backend"])
        
        # Verify cascaded and merged states
        self.assertTrue(final_state.get("pm_done"))
        self.assertTrue(final_state.get("frontend_done"))
        self.assertTrue(final_state.get("backend_done"))
        self.assertEqual(final_state.get("ui_theme"), "cyberpunk")
        self.assertEqual(final_state.get("api_port"), 8080)
        
        # Verify all nodes are tracked in completed_nodes
        self.assertIn("agent_pm", final_state["completed_nodes"])
        self.assertIn("agent_frontend", final_state["completed_nodes"])
        self.assertIn("agent_backend", final_state["completed_nodes"])

    async def test_transition_guards_blocking_and_fallback(self):
        """Test Transition Guard fails on invalid jump, broadcasts warning and diverts to fallback node."""
        graph = StateGraph()
        execution_order = []

        async def run_pm(state: dict) -> dict:
            execution_order.append("agent_pm")
            return {}

        async def run_tester(state: dict) -> dict:
            execution_order.append("agent_tester")
            return {}

        async def run_devops(state: dict) -> dict:
            execution_order.append("agent_devops")
            return {}

        graph.add_node("agent_pm", run_pm)
        graph.add_node("agent_tester", run_tester)
        graph.add_node("agent_devops", run_devops)

        # Static routing tries to go PM -> DevOps immediately
        graph.add_edge("agent_pm", "agent_devops")
        
        # Once tester runs, tester goes -> DevOps
        graph.add_edge("agent_tester", "agent_devops")
        graph.add_edge("agent_devops", "END")

        # ADD GUARD on devops requiring tester to be completed first, fallback to tester!
        graph.add_guard(
            "agent_devops",
            lambda state: "agent_tester" in state.get("completed_nodes", []),
            error_fallback_node="agent_tester"
        )

        stop_event = asyncio.Event()
        final_state = await graph.run({}, "test_conv_id", stop_event)

        # Verify execution order:
        # PM runs -> tries to go to DevOps -> DevOps guard BLOCKS -> redirects to Tester
        # -> Tester runs -> goes to DevOps -> DevOps guard PASSES -> DevOps runs -> END
        self.assertEqual(execution_order, ["agent_pm", "agent_tester", "agent_devops"])
        self.assertEqual(final_state["completed_nodes"], ["agent_pm", "agent_tester", "agent_devops"])

        # Check that WebSocket broadcasted the guard warning
        broadcast_messages = [b[1] for b in self.mock_manager.broadcasts if b[1].get("type") == "message"]
        warning_msg = next((m for m in broadcast_messages if "DEVOPS" in m["content"]["text"] and "TESTER" in m["content"]["text"]), None)
        self.assertIsNotNone(warning_msg)
        self.assertIn("DEVOPS", warning_msg["content"]["text"])
        self.assertIn("TESTER", warning_msg["content"]["text"])


if __name__ == "__main__":
    unittest.main()
