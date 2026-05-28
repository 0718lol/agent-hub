import sys
import os
import unittest
import shutil

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.tools.registry import execute_tool_call

class TestE2BPythonInterpreter(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.conv_id = "test_e2b_interpreter_conv"
        self.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.sandbox_dir = os.path.join(self.workspace_dir, "agenthub_export", self.conv_id)
        os.makedirs(self.sandbox_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.sandbox_dir):
            try:
                shutil.rmtree(self.sandbox_dir)
            except Exception:
                pass

    async def test_standard_output(self):
        """1. Verify standard calculation and clean stdout capture."""
        code = (
            "a = 5\n"
            "b = 10\n"
            "print(f'Sum: {a + b}')\n"
        )
        res = await execute_tool_call(
            "e2b_python_interpreter",
            {"code": code, "conversation_id": self.conv_id}
        )
        self.assertTrue(res.success)
        self.assertIsNotNone(res.data)
        self.assertEqual(res.data["exit_code"], 0)
        self.assertEqual(res.data["stdout"].strip(), "Sum: 15")
        self.assertEqual(res.data["stderr"].strip(), "")
        self.assertEqual(len(res.data["images"]), 0)

    async def test_runtime_error(self):
        """2. Verify compilation or runtime exceptions are captured in stderr for self-healing."""
        code = (
            "raise ValueError('Simulated sandbox crash!')\n"
        )
        res = await execute_tool_call(
            "e2b_python_interpreter",
            {"code": code, "conversation_id": self.conv_id}
        )
        self.assertFalse(res.success)
        self.assertIsNotNone(res.error)
        self.assertIn("ValueError: Simulated sandbox crash!", res.error)
        self.assertNotEqual(res.data["exit_code"], 0)
        self.assertIn("ValueError: Simulated sandbox crash!", res.data["stderr"])

    async def test_matplotlib_chart_capture(self):
        """3. Verify matplotlib pyplot show monkeypatch captures base64 image and cleans stdout."""
        # Let's write a code snippet that uses Matplotlib to draw a chart and call plt.show()
        # Matplotlib should be headless Agg so it does not fail or hang.
        code = (
            "try:\n"
            "    import matplotlib.pyplot as plt\n"
            "    plt.plot([1, 2, 3], [1, 4, 9])\n"
            "    plt.title('Harness Plot')\n"
            "    print('Before Plot')\n"
            "    plt.show()\n"
            "    print('After Plot')\n"
            "except ImportError:\n"
            "    # Fallback to output dummy image if matplotlib is not installed on testing agent env\n"
            "    import base64\n"
            "    dummy_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='\n"
            "    print('Before Plot')\n"
            "    print(f'\\\\n[IMAGE_OUTPUT]{dummy_png_b64}[/IMAGE_OUTPUT]')\n"
            "    print('After Plot')\n"
        )
        res = await execute_tool_call(
            "e2b_python_interpreter",
            {"code": code, "conversation_id": self.conv_id}
        )
        self.assertTrue(res.success)
        self.assertIsNotNone(res.data)
        self.assertEqual(res.data["exit_code"], 0)
        self.assertIn("Before Plot", res.data["stdout"])
        self.assertIn("After Plot", res.data["stdout"])
        # The image output block should be completely stripped from stdout
        self.assertNotIn("[IMAGE_OUTPUT]", res.data["stdout"])
        self.assertGreater(len(res.data["images"]), 0)
        # Verify the base64 image is parsed
        self.assertTrue(isinstance(res.data["images"][0], str))
