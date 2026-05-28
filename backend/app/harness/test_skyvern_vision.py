import sys
import os
import unittest
import asyncio
import shutil
import json
from unittest.mock import AsyncMock, patch, MagicMock

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.tools.browser_tools import browser_session_manager, BrowserActionTool
from app.tools.registry import execute_tool_call
from app.core.llm_client import llm_client

class MockWebSocketManager:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, conversation_id: str, message: dict):
        self.broadcasts.append((conversation_id, message))

class TestSkyvernVisionLocator(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Patch the websocket manager so we can mock and check updates
        import app.tools.browser_tools as bt
        self.mock_manager = MockWebSocketManager()
        self.original_manager = bt.manager
        bt.manager = self.mock_manager

        # Prepare sandboxed test workspace
        self.conv_id = "test_skyvern_vision_conv"
        self.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.sandbox_dir = os.path.join(self.workspace_dir, "agenthub_export", self.conv_id)
        os.makedirs(self.sandbox_dir, exist_ok=True)

        # Create a mock HTML file in sandbox
        self.html_file = "test_vision.html"
        self.html_path = os.path.join(self.sandbox_dir, self.html_file)
        self.html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Skyvern Test Page</title>
    <style>
        body { margin: 0; padding: 0; }
        .pink-button {
            position: absolute;
            left: 200px;
            top: 300px;
            width: 100px;
            height: 50px;
            background-color: pink;
        }
    </style>
</head>
<body>
    <h1>Skyvern Target Page</h1>
    <button class="pink-button" id="target-btn" onclick="document.getElementById('msg').innerText='Skyvern Clicked!'">
        Pink Submit
    </button>
    <div id="msg">Not Clicked</div>
</body>
</html>
"""
        with open(self.html_path, "w", encoding="utf-8") as f:
            f.write(self.html_content)

    def tearDown(self):
        import app.tools.browser_tools as bt
        bt.manager = self.original_manager

        # Clean up sandbox
        if os.path.exists(self.sandbox_dir):
            try:
                shutil.rmtree(self.sandbox_dir)
            except Exception:
                pass

    async def asyncTearDown(self):
        # Clean up browser session
        await browser_session_manager.close_all()

    async def test_click_by_element_id(self):
        """1. Verify standard ACI element_id locator works correctly."""
        # Goto page
        res = await execute_tool_call(
            "browser_action",
            {"action": "goto", "url": self.html_file, "conversation_id": self.conv_id}
        )
        self.assertTrue(res.success)
        
        elements = res.data["elements"]
        btn_id = None
        for el in elements:
            if "Pink Submit" in el["text"]:
                btn_id = el["id"]
        
        self.assertIsNotNone(btn_id, "Should find the interactive button in DOM element list")

        # Perform standard element ID click
        click_res = await execute_tool_call(
            "browser_action",
            {"action": "click", "element_id": btn_id, "conversation_id": self.conv_id}
        )
        self.assertTrue(click_res.success)

        # Verify page state updated successfully
        page = await browser_session_manager.get_page(self.conv_id)
        msg_text = await page.locator("#msg").inner_text()
        self.assertEqual(msg_text, "Skyvern Clicked!")

    async def test_click_by_fuzzy_dom_failover(self):
        """2. Verify fuzzy match failover works when element_id is missing and vision loop fails."""
        # Goto page first to load the elements cache
        goto_res = await execute_tool_call(
            "browser_action",
            {"action": "goto", "url": self.html_file, "conversation_id": self.conv_id}
        )
        self.assertTrue(goto_res.success)

        # We will mock llm_client.chat_stream to raise an Exception to simulate vision loop failure.
        # This will force the tool to fall back to _locate_by_fuzzy_dom.
        async def mock_fail_chat_stream(*args, **kwargs):
            raise RuntimeError("Vision model timeout or connection failure")
            yield  # To make it a generator
            
        with patch.object(llm_client, "chat_stream", side_effect=mock_fail_chat_stream):
            # Click with visual_description matching text
            click_res = await execute_tool_call(
                "browser_action",
                {
                    "action": "click",
                    "visual_description": "Pink Submit button",
                    "conversation_id": self.conv_id
                }
            )
            self.assertTrue(click_res.success)
            self.assertTrue(click_res.data.get("failover_used"))
            self.assertFalse(click_res.data.get("vision_used"))

            # Verify click action succeeded
            page = await browser_session_manager.get_page(self.conv_id)
            msg_text = await page.locator("#msg").inner_text()
            self.assertEqual(msg_text, "Skyvern Clicked!")

    async def test_click_by_vision_loop(self):
        """3. Verify multi-modal vision loop parses percentages and triggers physical viewport clicks."""
        # Goto page
        goto_res = await execute_tool_call(
            "browser_action",
            {"action": "goto", "url": self.html_file, "conversation_id": self.conv_id}
        )
        self.assertTrue(goto_res.success)

        # The pink button is at 200, 300, sized 100x50.
        # Center coordinates should be x = 250, y = 325.
        # In a 1280x800 viewport:
        # x_pct = (250 / 1280) * 100 = 19.53125
        # y_pct = (325 / 800) * 100 = 40.625
        
        # Let's mock llm_client.chat_stream to return exactly this JSON
        async def mock_success_chat_stream(*args, **kwargs):
            yield '{"x": 19.53125, "y": 40.625, "confidence": 0.99}'

        # Let's patch llm_client.chat_stream and verify
        with patch.object(llm_client, "chat_stream", side_effect=mock_success_chat_stream):
            click_res = await execute_tool_call(
                "browser_action",
                {
                    "action": "click",
                    "visual_description": "the pink box button in the middle",
                    "conversation_id": self.conv_id
                }
            )
            self.assertTrue(click_res.success)
            self.assertTrue(click_res.data.get("vision_used"))
            self.assertFalse(click_res.data.get("failover_used"))

            # Verify it clicked the right place and triggered our page action
            page = await browser_session_manager.get_page(self.conv_id)
            msg_text = await page.locator("#msg").inner_text()
            self.assertEqual(msg_text, "Skyvern Clicked!")
