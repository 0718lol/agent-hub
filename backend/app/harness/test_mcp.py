import asyncio
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.mcp_bridge import mcp_bridge_manager
from app.tools.registry import get_tool, TOOL_REGISTRY, execute_tool_call
from app.tools.base import JudgeResult

class TestMCPIntegration(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Keep track of original TOOL_REGISTRY keys to restore them in tearDown
        self.original_keys = list(TOOL_REGISTRY.keys())
        self.config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "mcp_config.json"))

    async def asyncTearDown(self):
        # Gracefully stop all MCP Servers
        await mcp_bridge_manager.stop_all_servers()
        
        # Clean up any dynamically registered MCP tools from global registry to prevent test pollution
        current_keys = list(TOOL_REGISTRY.keys())
        for k in current_keys:
            if k not in self.original_keys:
                del TOOL_REGISTRY[k]

    def test_mcp_config_exists(self):
        """1. Verify that mcp_config.json is successfully generated and points to mock server."""
        self.assertTrue(os.path.exists(self.config_path), f"Config file missing at: {self.config_path}")

    async def test_mcp_lifecycle_and_execution(self):
        """2. Verify spawning MCP subprocess, dynamic tool mapping, execution, and graceful shutdown."""
        # Load config and spin up mock-server (also mounts builtin server)
        await mcp_bridge_manager.load_and_start_servers(self.config_path)
        
        # Check if the server is in the manager's tracking registry
        self.assertIn("mock-server", mcp_bridge_manager.servers)
        server = mcp_bridge_manager.servers["mock-server"]
        self.assertTrue(server._running)
        
        # Check if 'mock_echo' was dynamically registered into AgentHub's TOOL_REGISTRY
        tool = get_tool("mock_echo")
        self.assertIsNotNone(tool, "MCP tool 'mock_echo' was not registered dynamically.")
        self.assertEqual(tool.name, "mock_echo")
        self.assertEqual(tool.description, "Echo the input text back.")
        
        # Simulate calling the tool using AgentHub's core dispatching execution system
        res = await execute_tool_call("mock_echo", {"text": "Greetings from Wac Branch!"})
        self.assertTrue(res.success, f"Tool execution failed: {res.error}")
        self.assertEqual(res.data, "Echo: Greetings from Wac Branch!")
        
        # Stop servers and check that tools are unresolved cleanly
        await mcp_bridge_manager.stop_all_servers()
        self.assertFalse(server._running)

    async def test_mcp_builtin_hil_tool_execution(self):
        """3. [Phase 2] Verify dynamic mapping and routing of system builtin HIL tool user_interaction_judge."""
        # Load servers (mounts builtin in-memory server)
        await mcp_bridge_manager.load_and_start_servers(self.config_path)

        # Check if Builtin HIL Tool was mapped and registered into TOOL_REGISTRY
        hil_tool = get_tool("user_interaction_judge")
        self.assertIsNotNone(hil_tool, "Builtin HIL MCP Tool 'user_interaction_judge' was not registered dynamically.")
        self.assertEqual(hil_tool.server_name, "system-builtin")
        self.assertEqual(hil_tool.name, "user_interaction_judge")

        # Mock the run method of UserInteractionJudgeTool to bypass interactive prompt and instantly resolve
        mock_result = JudgeResult(
            decision="Approve",
            score=100.0,
            reason="User confirmed via mock HIL",
            signals={"answer": "Approve"}
        )

        with patch("app.tools.judge_tools.UserInteractionJudgeTool.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            
            # Execute tool call via standard MCP Bridge routing
            params = {
                "question": "🎯 Are you ready to deploy?",
                "options": ["Approve", "Terminate"],
                "conversation_id": "test_mcp_conv_id"
            }
            
            res = await execute_tool_call("user_interaction_judge", params)
            self.assertTrue(res.success)
            self.assertIn("Decision: Approve", res.data)
            self.assertIn("User confirmed via mock HIL", res.data)
            
            mock_run.assert_called_once_with(params)

    async def test_mcp_builtin_repomap_resource(self):
        """4. [Phase 2] Verify standard workspace://repomap read-only MCP Resource resolution and dynamic scanner integration."""
        # Load servers (mounts builtin in-memory server)
        await mcp_bridge_manager.load_and_start_servers(self.config_path)

        # Verify resources list metadata
        resources = await mcp_bridge_manager.builtin_server.list_resources()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["uri"], "workspace://repomap")
        self.assertEqual(resources[0]["mimeType"], "text/markdown")

        # Create temporary dummy file in backend/app/mock directory to verify AST scan works
        dummy_file = os.path.join(os.path.dirname(__file__), "..", "mock", "mcp_dummy_symbol.py")
        dummy_code = """
class MCPDummyClass:
    def dummy_method(self, value):
        return value * 2

def dummy_standalone_function(x, y):
    return x + y
"""
        with open(dummy_file, "w", encoding="utf-8") as f:
            f.write(dummy_code)

        try:
            # Read resource workspace://repomap using standard manager reading API
            content = await mcp_bridge_manager.read_builtin_resource("workspace://repomap")
            
            # Check if AST scanned the class, methods, and functions successfully
            self.assertIn("mcp_dummy_symbol.py", content)
            self.assertIn("MCPDummyClass", content)
            self.assertIn("dummy_method(self, value)", content)
            self.assertIn("dummy_standalone_function(x, y)", content)
        finally:
            # Safely remove dummy file
            if os.path.exists(dummy_file):
                os.remove(dummy_file)

if __name__ == "__main__":
    unittest.main()
