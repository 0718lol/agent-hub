import sys
import os
import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.mcp_client import SystemMCPServer
from app.tools.registry import execute_tool_call

class TestDockerIsolation(unittest.IsolatedAsyncioTestCase):

    async def test_workspace_run_command_docker_arguments(self):
        """1. Verify workspace_run_command compiles correct docker run arguments under strict isolation."""
        server = SystemMCPServer()
        conv_id = "test_docker_isolation_conv"
        
        # Mock docker check to return True (available)
        mock_proc_check = AsyncMock()
        mock_proc_check.returncode = 0
        mock_proc_check.communicate.return_value = (b"docker is running", b"")
        
        # Mock docker run process
        mock_proc_run = AsyncMock()
        mock_proc_run.returncode = 0
        mock_proc_run.communicate.return_value = (b"success stdout", b"")
        
        async def mock_create_exec(*args, **kwargs):
            if args[0] == "docker" and args[1] == "info":
                return mock_proc_check
            elif args[0] == "docker" and args[1] == "run":
                # Assert that standard safety limits are set
                self.assertIn("--network", args)
                self.assertIn("none", args)
                self.assertIn("--memory", args)
                self.assertIn("128m", args)
                self.assertIn("--cpus", args)
                self.assertIn("0.5", args)
                
                # Assert volume mount and directory is set
                self.assertIn("-v", args)
                self.assertIn("-w", args)
                self.assertIn("/workspace", args)
                return mock_proc_run
            raise ValueError(f"Unexpected exec: {args}")

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_exec), \
             patch.dict(os.environ, {"AGENTHUB_DOCKER_SANDBOX": "true"}):
             
            result = await server.call_tool(
                "workspace_run_command",
                {"command": "npm run build"},
                conversation_id=conv_id
            )
            
            self.assertFalse(result.get("isError", False))
            self.assertIn("success stdout", result["content"][0]["text"])

    async def test_workspace_run_command_fallback(self):
        """2. Verify workspace_run_command gracefully falls back to host execution if Docker is unavailable."""
        server = SystemMCPServer()
        conv_id = "test_docker_fallback_conv"
        
        # Mock standard subprocess shell to run host-level command
        mock_proc_shell = AsyncMock()
        mock_proc_shell.returncode = 0
        mock_proc_shell.communicate.return_value = (b"host execution success", b"")
        mock_proc_shell.pid = 1234

        # Mock docker check to raise exception (representing docker not installed/running)
        async def mock_create_exec(*args, **kwargs):
            if args[0] == "docker" and args[1] == "info":
                raise FileNotFoundError("docker not found")
            if args[0] in ("cmd.exe", "/bin/bash"):
                return mock_proc_shell
            if args[0] == "git":
                git_proc = AsyncMock()
                git_proc.returncode = 0
                git_proc.communicate.return_value = (b"", b"")
                return git_proc
            raise ValueError(f"Unexpected exec: {args}")

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_exec), \
             patch("asyncio.create_subprocess_shell", return_value=mock_proc_shell), \
             patch("app.core.subprocess_security.limit_windows_process"), \
             patch("app.core.config.settings.allow_unsandboxed_shell", True), \
             patch.dict(os.environ, {"AGENTHUB_DOCKER_SANDBOX": "true"}):
             
            result = await server.call_tool(
                "workspace_run_command",
                {"command": "python test.py"},
                conversation_id=conv_id
            )
            
            self.assertFalse(result.get("isError", False))
            self.assertIn("host execution success", result["content"][0]["text"])

if __name__ == "__main__":
    unittest.main()
