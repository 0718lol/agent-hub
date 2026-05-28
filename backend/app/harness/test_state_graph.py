import sys
import os
import unittest
import asyncio

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.state_graph import StateGraph

class MockWebSocketManager:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, conversation_id: str, message: dict):
        self.broadcasts.append((conversation_id, message))


class TestStateGraph(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Patch the websocket manager so we can mock and check updates
        import app.core.websocket as ws
        self.mock_manager = MockWebSocketManager()
        self.original_manager = ws.manager
        ws.manager = self.mock_manager

    def tearDown(self):
        import app.core.websocket as ws
        ws.manager = self.original_manager

    async def test_state_graph_sequential_execution(self):
        """Test StateGraph executes nodes in sequence and correctly routes downstream."""
        graph = StateGraph()
        
        # Track node execution order
        execution_order = []

        async def run_pm(state: dict) -> dict:
            execution_order.append("agent_pm")
            return {"pm_done": True, "assigned": ["agent_frontend", "agent_tester"]}

        async def run_frontend(state: dict) -> dict:
            execution_order.append("agent_frontend")
            return {"frontend_done": True}

        async def run_backend(state: dict) -> dict:
            execution_order.append("agent_backend")
            return {"backend_done": True}

        async def run_tester(state: dict) -> dict:
            execution_order.append("agent_tester")
            return {"tester_done": True}

        graph.add_node("agent_pm", run_pm)
        graph.add_node("agent_frontend", run_frontend)
        graph.add_node("agent_backend", run_backend)
        graph.add_node("agent_tester", run_tester)

        # Dynamic routing rules
        def pm_router(state: dict) -> str:
            assigned = state.get("assigned", [])
            for aid in ["agent_frontend", "agent_backend", "agent_tester"]:
                if aid in assigned:
                    return aid
            return "END"

        def frontend_router(state: dict) -> str:
            assigned = state.get("assigned", [])
            for aid in ["agent_backend", "agent_tester"]:
                if aid in assigned:
                    return aid
            return "END"

        def backend_router(state: dict) -> str:
            assigned = state.get("assigned", [])
            for aid in ["agent_tester"]:
                if aid in assigned:
                    return aid
            return "END"

        graph.add_conditional_edge("agent_pm", pm_router)
        graph.add_conditional_edge("agent_frontend", frontend_router)
        graph.add_conditional_edge("agent_backend", backend_router)
        graph.add_edge("agent_tester", "END")

        # Run StateGraph
        stop_event = asyncio.Event()
        final_state = await graph.run({}, "test_conv_id", stop_event)

        # Verify execution order:
        # PM -> assigned Frontend -> Tester (Backend is skipped because it's not assigned)
        self.assertEqual(execution_order, ["agent_pm", "agent_frontend", "agent_tester"])
        
        # Verify final merged state
        self.assertTrue(final_state.get("pm_done"))
        self.assertTrue(final_state.get("frontend_done"))
        self.assertTrue(final_state.get("tester_done"))
        self.assertFalse(final_state.get("backend_done", False))

        # Verify WebSocket task status updates were broadcast
        # Check PM status transitions
        pm_broadcasts = [b for b in self.mock_manager.broadcasts if b[1].get("agent_id") == "agent_pm"]
        self.assertEqual(pm_broadcasts[0][1]["status"], "idle")
        self.assertEqual(pm_broadcasts[1][1]["status"], "doing")
        self.assertEqual(pm_broadcasts[2][1]["status"], "done")

        # Check skipped node remains idle
        backend_broadcasts = [b for b in self.mock_manager.broadcasts if b[1].get("agent_id") == "agent_backend"]
        # Only start resetting broadcast is sent for backend
        self.assertEqual(len(backend_broadcasts), 1)
        self.assertEqual(backend_broadcasts[0][1]["status"], "idle")


if __name__ == "__main__":
    unittest.main()
