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

        # Initialize database
        from app.core.database import init_db
        init_db()

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

        # Clean up test checkpoints
        from app.core.database import delete_hil_checkpoint
        try:
            delete_hil_checkpoint("webhook_conv_id")
        except Exception:
            pass

        # Clean up custom graph builders
        from app.main import _graph_builders
        _graph_builders.pop("webhook_conv_id", None)

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

    async def test_hil_checkpoint_persistence_on_suspend(self):
        """5. Verify triggering HIL inserts a pending checkpoint record into the database."""
        conv_id = "webhook_conv_id"
        from app.main import _save_hil_settings
        _save_hil_settings({"human_input_mode": "ALWAYS", "cooldown_steps": 1})

        graph = StateGraph()
        async def run_pm(state: dict) -> dict:
            return {}
        graph.add_node("agent_pm", run_pm)
        graph.add_edge("agent_pm", "END")

        # Run in background — will suspend
        stop_event = asyncio.Event()
        graph_task = asyncio.create_task(graph.run({"original_prompt": "Hello Checkpointer"}, conv_id, stop_event))
        await asyncio.sleep(0.1)

        # Retrieve checkpoint from SQLite
        from app.core.database import get_pending_hil_checkpoint
        checkpoint = get_pending_hil_checkpoint(conv_id)
        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint["conversation_id"], conv_id)
        self.assertEqual(checkpoint["current_node"], "agent_pm")
        self.assertEqual(checkpoint["next_node"], "END")
        self.assertEqual(checkpoint["original_prompt"], "Hello Checkpointer")
        self.assertEqual(checkpoint["status"], "pending")

        # Resolve memory future to finish graph and clean up
        from app.tools.judge_tools import _pending_interactions
        if conv_id in _pending_interactions:
            _pending_interactions[conv_id].set_result("Approve")
        await graph_task

    async def test_hil_recovery_after_mock_server_crash(self):
        """6. Verify HIL recovery after mock server crash (wiping memory futures dictionary)."""
        conv_id = "webhook_conv_id"
        from app.main import _save_hil_settings
        _save_hil_settings({"human_input_mode": "ALWAYS", "cooldown_steps": 1})

        graph = StateGraph()
        execution_order = []
        async def run_pm(state: dict) -> dict:
            execution_order.append("agent_pm")
            return {}
        async def run_designer(state: dict) -> dict:
            execution_order.append("agent_designer")
            return {}

        graph.add_node("agent_pm", run_pm)
        graph.add_node("agent_designer", run_designer)
        graph.add_edge("agent_pm", "agent_designer")
        graph.add_edge("agent_designer", "END")

        # Register custom test graph builder for recovery
        from app.main import _graph_builders
        def build_test_graph(cid, text, trace, stop_event):
            test_graph = StateGraph()
            test_graph.add_node("agent_pm", run_pm)
            test_graph.add_node("agent_designer", run_designer)
            test_graph.add_edge("agent_pm", "agent_designer")
            test_graph.add_edge("agent_designer", "END")
            return test_graph
        _graph_builders[conv_id] = build_test_graph

        # Start graph — will suspend at PM's HIL checkpoint
        stop_event = asyncio.Event()
        graph_task = asyncio.create_task(graph.run({"original_prompt": "Build website"}, conv_id, stop_event))
        await asyncio.sleep(0.1)

        self.assertEqual(execution_order, ["agent_pm"])

        # Simulate Server Crash: Wipe memory future completely
        from app.tools.judge_tools import _pending_interactions
        _pending_interactions.pop(conv_id, None)

        # Trigger Slack webhook approval callback
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

        # Dispatch callback: it will find no in-memory future, query the checkpoint DB,
        # and start the background resumption recovery task.
        callback_res = await webhook_gateway.handle_slack_callback(slack_callback_payload)
        self.assertTrue(callback_res["success"])

        # Wait a moment for the recovered background graph task to launch and run
        await asyncio.sleep(0.2)

        # Verify designer has now executed because of resumption
        self.assertIn("agent_designer", execution_order)

        # Clean up by resolving the second HIL (at designer)
        if conv_id in _pending_interactions:
            _pending_interactions[conv_id].set_result("Approve")

    def test_webhook_endpoints_signature_verification(self):
        """7. Verify Slack HMAC-SHA256 signature and Telegram Secret Token verification in FastAPI REST API."""
        from fastapi.testclient import TestClient
        from app.main import app
        import hmac
        import hashlib
        import time

        client = TestClient(app)

        # A. Slack tests without secret set: should pass through bypass
        with patch.dict(os.environ, {}, clear=True):
            resp = client.post(
                "/api/webhook/callback/slack",
                json={"actions": [{"value": json.dumps({"conversation_id": "test_conv", "action": "Approve"})}]}
            )
            # The signature check is bypassed, but we get success: False because 'test_conv' isn't an active interaction
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.json()["success"])

        # B. Slack tests with secret configured
        secret = "super_slack_secret"
        with patch.dict(os.environ, {"AGENTHUB_SLACK_SIGNING_SECRET": secret}):
            # 1. Missing headers: should return 401
            resp = client.post(
                "/api/webhook/callback/slack",
                json={"actions": [{"value": "..."}]}
            )
            self.assertEqual(resp.status_code, 401)
            self.assertIn("Missing Slack verification headers", resp.json()["detail"])

            # 2. Invalid signature: should return 403
            resp = client.post(
                "/api/webhook/callback/slack",
                headers={
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=invalid_sig_here"
                },
                json={"actions": [{"value": "..."}]}
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("Invalid Slack signature", resp.json()["detail"])

            # 3. Valid signature: should pass and return 200 (with mock bypass)
            ts = str(int(time.time()))
            body = b'{"actions": []}'
            sig_basestring = f"v0:{ts}:".encode('utf-8') + body
            valid_sig = "v0=" + hmac.new(
                secret.encode('utf-8'),
                sig_basestring,
                hashlib.sha256
            ).hexdigest()

            resp = client.post(
                "/api/webhook/callback/slack",
                headers={
                    "X-Slack-Request-Timestamp": ts,
                    "X-Slack-Signature": valid_sig
                },
                content=body
            )
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.json()["success"]) # Because of empty actions

        # C. Telegram tests without secret set: should pass through bypass
        with patch.dict(os.environ, {}, clear=True):
            resp = client.post(
                "/api/webhook/callback/telegram",
                json={"callback_query": {"data": json.dumps({"c_id": "test", "act": "Yes"})}}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.json()["success"]) # Bypassed but no interaction in memory

        # D. Telegram tests with secret configured
        tg_secret = "super_tg_secret"
        with patch.dict(os.environ, {"AGENTHUB_TELEGRAM_SECRET_TOKEN": tg_secret}):
            # 1. Missing header: should return 401
            resp = client.post(
                "/api/webhook/callback/telegram",
                json={"callback_query": {"data": "..."}}
            )
            self.assertEqual(resp.status_code, 401)
            self.assertIn("Missing Telegram verification token", resp.json()["detail"])

            # 2. Invalid secret token: should return 403
            resp = client.post(
                "/api/webhook/callback/telegram",
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_token"},
                json={"callback_query": {"data": "..."}}
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("Invalid Telegram secret token", resp.json()["detail"])

            # 3. Valid secret token: should pass and return 200
            resp = client.post(
                "/api/webhook/callback/telegram",
                headers={"X-Telegram-Bot-Api-Secret-Token": tg_secret},
                json={"callback_query": {"data": json.dumps({"c_id": "test", "act": "Yes"})}}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.json()["success"])


if __name__ == "__main__":
    unittest.main()
