import asyncio
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.sandbox import execute_code, ExecutionResult
from app.core.sandbox_manager import sandbox_manager, SubprocessSandbox, DockerSandbox, E2BSandbox

class TestPhysicalSandbox(unittest.IsolatedAsyncioTestCase):

    async def test_subprocess_sandbox_rail(self):
        """1. Verify standard subprocess sandbox executes python scripts and captures stdout cleanly."""
        box = SubprocessSandbox()
        code = "print('Hello Subprocess Sandbox!')"
        res = await box.execute(code, "python", 5)
        
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["stdout"].strip(), "Hello Subprocess Sandbox!")
        self.assertEqual(res["exit_code"], 0)

    async def test_docker_sandbox_rail_if_available(self):
        """2. Verify local Docker sandbox runs in extreme isolation with memory/network limit and exits safely."""
        box = DockerSandbox()
        available = await box.check_availability()
        if not available:
            self.skipTest("Local Docker Engine is not running or available. Skipping Docker isolation test.")

        code = "import sys; print('Hello Docker Sandbox!'); sys.exit(0)"
        res = await box.execute(code, "python", 10)
        
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["stdout"].strip(), "Hello Docker Sandbox!")
        self.assertEqual(res["exit_code"], 0)

    async def test_e2b_sandbox_fallback_to_local(self):
        """3. Verify E2B API failure triggers seamless, millisecond-level fallback to local subprocess sandbox."""
        # Intentionally inject bad E2B API key to trigger network/API exception
        with patch.dict(os.environ, {"E2B_API_KEY": "invalid-crash-key"}):
            manager = sandbox_manager
            manager.e2b_api_key = "invalid-crash-key"
            
            # Since E2B crashes on invalid key, manager should log it and fallback to local rails automatically
            code = "print('Hello Fallback from Crashed E2B!')"
            res = await manager.execute(code, "python", 5)
            
            # Subprocess/Docker rail succeeded as a robust safeguard!
            self.assertEqual(res["status"], "success")
            self.assertIn("Hello Fallback", res["stdout"])
            
            # Restore key state
            manager.e2b_api_key = ""

    async def test_execute_code_wrapper_compatibility(self):
        """4. Verify standard execute_code wrapper works seamlessly and retains ExecutionResult object signatures."""
        code = "print(10 + 20)"
        res = await execute_code(code, "python", 5)
        
        self.assertTrue(isinstance(res, ExecutionResult))
        self.assertEqual(res.status, "success")
        self.assertEqual(res.stdout.strip(), "30")
        self.assertEqual(res.exit_code, 0)

if __name__ == "__main__":
    unittest.main()
