import sys
import os
import unittest
import asyncio
import shutil
from unittest.mock import AsyncMock, patch

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.tools.browser_tools import browser_session_manager, BrowserActionTool
from app.tools.registry import execute_tool_call

class MockWebSocketManager:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, conversation_id: str, message: dict):
        self.broadcasts.append((conversation_id, message))

class TestBrowserAutomation(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Patch the websocket manager so we can mock and check updates
        import app.tools.browser_tools as bt
        self.mock_manager = MockWebSocketManager()
        self.original_manager = bt.manager
        bt.manager = self.mock_manager

        # Prepare sandboxed test workspace
        self.conv_id = "test_browser_session_conv"
        self.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.sandbox_dir = os.path.join(self.workspace_dir, "agenthub_export", self.conv_id)
        os.makedirs(self.sandbox_dir, exist_ok=True)

        # Create a mock HTML file in sandbox
        self.html_file = "test.html"
        self.html_path = os.path.join(self.sandbox_dir, self.html_file)
        self.html_content = """<!DOCTYPE html>
<html>
<head>
    <title>CyberBrowser Test</title>
</head>
<body>
    <h1>Hello CyberBrowser</h1>
    <button id="btn" onclick="document.getElementById('msg').innerText='Clicked!'">Click Me</button>
    <div id="msg">Not Clicked</div>
    <input id="txt" type="text" placeholder="Type here" />
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

    async def test_browser_session_creation(self):
        """Test that browser_session_manager launches playwright and returns a page."""
        page = await browser_session_manager.get_page(self.conv_id)
        self.assertIsNotNone(page)
        self.assertEqual(browser_session_manager.playwright is not None, True)
        self.assertEqual(browser_session_manager.browser is not None, True)

    async def test_goto_sandbox_and_coordinates_clicks(self):
        """Test loading local file in sandbox and executing coordinate-based click and input actions."""
        # 1. Navigation (goto)
        res = await execute_tool_call(
            "browser_action",
            {"action": "goto", "url": self.html_file, "conversation_id": self.conv_id}
        )
        self.assertTrue(res.success)
        self.assertIsNotNone(res.data)
        self.assertIn("Click Me", res.data["message"])

        # Check websocket broadcast happened
        self.assertGreater(len(self.mock_manager.broadcasts), 0)
        last_broadcast = self.mock_manager.broadcasts[-1]
        self.assertEqual(last_broadcast[0], self.conv_id)
        self.assertEqual(last_broadcast[1]["type"], "browser_viewport")
        self.assertIsNotNone(last_broadcast[1]["screenshot"])
        self.assertGreater(len(last_broadcast[1]["elements"]), 0)

        # 2. Click (Find element ID from cache)
        elements = res.data["elements"]
        btn_id = None
        txt_id = None
        for el in elements:
            if "Click Me" in el["text"]:
                btn_id = el["id"]
            if "Type here" in el["text"] or el["tagName"] == "input":
                txt_id = el["id"]

        self.assertIsNotNone(btn_id)
        self.assertIsNotNone(txt_id)

        # Click the button
        click_res = await execute_tool_call(
            "browser_action",
            {"action": "click", "element_id": btn_id, "conversation_id": self.conv_id}
        )
        self.assertTrue(click_res.success)

        # Wait a bit and verify click action in DOM using evaluate
        page = await browser_session_manager.get_page(self.conv_id)
        msg_text = await page.locator("#msg").inner_text()
        self.assertEqual(msg_text, "Clicked!")

        # 3. Type into input
        type_res = await execute_tool_call(
            "browser_action",
            {"action": "type", "element_id": txt_id, "text": "Hello World!", "conversation_id": self.conv_id}
        )
        self.assertTrue(type_res.success)

        input_val = await page.locator("#txt").input_value()
        self.assertEqual(input_val, "Hello World!")

    async def test_path_traversal_prevention(self):
        """Test sandboxed browser prevents relative directory traversal path escapes."""
        res = await execute_tool_call(
            "browser_action",
            {"action": "goto", "url": "../../../etc/passwd", "conversation_id": self.conv_id}
        )
        self.assertFalse(res.success)
        self.assertIn("路径越权", res.error)
