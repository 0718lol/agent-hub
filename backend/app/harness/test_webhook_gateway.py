import sys
import os
import unittest
import asyncio
import json
from unittest.mock import AsyncMock, patch

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.services.webhook_gateway import webhook_gateway
from app.core.state_graph import StateGraph
from app.tools.judge_tools import UserInteractionJudgeTool, JudgeResult

class MockWebSocketManager:
    def __init__(self):
        self.broadcasts = []
        self.active_connections = ["webhook_conv_id"]

    async def broadcast(self, conversation_id: str, message: dict):
        self.broadcasts.append((conversation_id, message))


class TestWebhookGateway(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Patch WebSocket manager
        import app.core.websocket as ws
        self.mock_manager = MockWebSocketManager()
        self.original_manager = ws.manager
        ws.manager = self.mock_manager

        # Clear simulated history on startup
        webhook_gateway.clear_simulated_messages()

    def tearDown(self):
        import app.core.websocket as ws
        ws.manager = self.original_manager
        
        # Ensure temporary HIL settings file is removed if created
        from app.main import HIL_CONFIG_PATH
        if os.path.exists(HIL_CONFIG_PATH):
            try:
                os.remove(HIL_CONFIG_PATH)
            except Exception:
                pass

    def test_webhook_registration(self):
        """1. Verify Slack and Telegram channel registration is saved properly."""
        webhook_gateway.register_channels(
            slack_url="https://hooks.slack.com/services/T00/B00/X00",
            telegram_token="123456:ABC-DEF",
            telegram_chat_id="987654321"
        )
        self.assertEqual(webhook_gateway.slack_webhook_url, "https://hooks.slack.com/services/T00/B00/X00")
        self.assertEqual(webhook_gateway.telegram_token, "123456:ABC-DEF")
        self.assertEqual(webhook_gateway.telegram_chat_id, "987654321")

    async def test_slack_interactive_notification(self):
        """2. Verify HIL triggers correctly formatted interactive Slack blocks and Telegram keyboards."""
        conv_id = "webhook_conv_id"
        question = "🎭 智能体 PM 已运行完毕。是否批准？"
        options = [
            {"label": "Approve", "description": "批准并推进", "recommended": True},
            {"label": "Terminate", "description": "终止流程", "recommended": False}
        ]

        await webhook_gateway.send_hil_notification(conv_id, question, options)
        
        # Check simulated queue
        self.assertEqual(len(webhook_gateway.simulated_sent_messages), 1)
        msg = webhook_gateway.simulated_sent_messages[0]
        self.assertEqual(msg["conversation_id"], conv_id)
        self.assertEqual(msg["question"], question)

        # Verify Slack Blocks formatting
        slack = msg["slack_payload"]
        self.assertIn("blocks", slack)
        self.assertEqual(slack["blocks"][0]["text"]["text"], f"*🎭 [AgentHub HIL Intercept]*\n{question}\n\n_请在下方选择操作或输入反馈回复继续开发：_")
        
        actions = slack["blocks"][1]["elements"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["text"]["text"], "Approve (批准并推进)")
        self.assertEqual(actions[0]["style"], "primary") # Recommended style
        
        # Verify Telegram formatting
        telegram = msg["telegram_payload"]
        self.assertIn("inline_keyboard", telegram["reply_markup"])
        btns = telegram["reply_markup"]["inline_keyboard"][0]
        self.assertEqual(len(btns), 2)
        self.assertEqual(btns[0]["text"], "🌟 Approve - 批准并推进")

    async def test_slack_callback_approval_resumption(self):
        """3. Verify simulated Slack webhook button click (Approve) resumes suspended StateGraph execution successfully."""
        conv_id = "webhook_conv_id"
        
        # 1. Setup HIL config ALWAYS
        from app.main import _save_hil_settings
        _save_hil_settings({"human_input_mode": "ALWAYS", "cooldown_steps": 1})

        graph = StateGraph()
        execution_order = []

        async def run_pm(state: dict) -> dict:
            execution_order.append("agent_pm")
            return {}

        graph.add_node("agent_pm", run_pm)
        graph.add_edge("agent_pm", "END")

        # Start graph in background because it will suspend at HIL intercept waiting for input
        stop_event = asyncio.Event()
        graph_task = asyncio.create_task(graph.run({}, conv_id, stop_event))

        # Wait a short moment to ensure the graph execution reaches HIL intercept and suspends
        await asyncio.sleep(0.1)

        # Assert graph is suspended (HIL notification sent)
        self.assertEqual(len(webhook_gateway.simulated_sent_messages), 1)
        self.assertEqual(execution_order, ["agent_pm"])

        # 2. Simulate incoming Slack webhook callback payload for "Approve"
        slack_callback_payload = {
            "actions": [
                {
                    "value": json.dumps({
                        "conversation_id": conv_id,
                        "action": "Approve"
                    })
                }
            ]
        }

        # Dispatch callback
        callback_res = await webhook_gateway.handle_slack_callback(slack_callback_payload)
        self.assertTrue(callback_res["success"])
        self.assertEqual(callback_res["action"], "Approve")

        # 3. Await graph completion and verify it proceeded to the next node
        final_state = await graph_task
        self.assertEqual(execution_order, ["agent_pm"])
        self.assertIn("agent_pm", final_state["completed_nodes"])

    async def test_slack_callback_revision_resumption(self):
        """4. Verify simulated Slack webhook callback (Feedback Revision) resumes graph and forces node to re-run with user feedback."""
        conv_id = "webhook_conv_id"
        
        # 1. Setup HIL config ALWAYS
        from app.main import _save_hil_settings
        _save_hil_settings({"human_input_mode": "ALWAYS", "cooldown_steps": 1})

        graph = StateGraph()
        execution_counts = {"agent_pm": 0}
        recorded_feedbacks = []

        async def run_pm(state: dict) -> dict:
            execution_counts["agent_pm"] += 1
            feedback = state.get("agent_pm_feedback", "")
            recorded_feedbacks.append(feedback)
            return {}

        graph.add_node("agent_pm", run_pm)
        graph.add_edge("agent_pm", "END")

        # Run first time — will suspend
        stop_event = asyncio.Event()
        graph_task = asyncio.create_task(graph.run({}, conv_id, stop_event))
        await asyncio.sleep(0.1)

        self.assertEqual(execution_counts["agent_pm"], 1)

        # 2. Simulate Slack feedback callback (user requests purple style)
        slack_callback_payload = {
            "actions": [
                {
                    "value": json.dumps({
                        "conversation_id": conv_id,
                        "action": "Please change main color to purple"
                    })
                }
            ]
        }

        callback_res = await webhook_gateway.handle_slack_callback(slack_callback_payload)
        self.assertTrue(callback_res["success"])

        # Since it is a revision, graph will re-run the same node, triggering another HIL suspension
        # Let's wait and verify the second execution of PM with user feedback occurred
        await asyncio.sleep(0.1)
        self.assertEqual(execution_counts["agent_pm"], 2)
        self.assertEqual(recorded_feedbacks, ["", "Please change main color to purple"])

        # Now approve the second HIL suspend to let the graph complete
        slack_approve_payload = {
            "actions": [
                {
                    "value": json.dumps({
                        "conversation_id": conv_id,
                        "action": "Approve"
                    })
                }
            ]
        }
        await webhook_gateway.handle_slack_callback(slack_approve_payload)

        # Await completion
        final_state = await graph_task
        self.assertIn("agent_pm", final_state["completed_nodes"])


if __name__ == "__main__":
    unittest.main()
