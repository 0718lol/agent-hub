import sys
import os
import unittest
import asyncio
import shutil
from unittest.mock import AsyncMock, patch

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import app.tools  # noqa: F401
from app.tools.registry import execute_tool_call
from app.core.terminal import stateful_terminal_manager

class TestACISuite(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.conv_id = "test_aci_suite_conv"
        self.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.sandbox_dir = os.path.join(self.workspace_dir, "agenthub_export", self.conv_id)
        os.makedirs(self.sandbox_dir, exist_ok=True)

        # Create a test file with multiple lines
        self.file_name = "multi_line.py"
        self.file_path = os.path.join(self.sandbox_dir, self.file_name)
        self.file_lines = [
            "# Line 1: Header\n",
            "def add(a, b):\n",
            "    return a + b\n",
            "\n",
            "def subtract(a, b):\n",
            "    return a - b\n",
            "\n",
            "# Line 8: Footer\n"
        ]
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.writelines(self.file_lines)

    def tearDown(self):
        # Clean up sandboxed workspace
        if os.path.exists(self.sandbox_dir):
            try:
                shutil.rmtree(self.sandbox_dir)
            except Exception:
                pass

    async def asyncTearDown(self):
        # Clean up any stateful terminal processes
        await stateful_terminal_manager.close_all()

    async def test_windowed_file_view(self):
        """Test file_view_windowed with slicing, scroll indicators, and line numbers."""
        # 1. Read first 3 lines
        res = await execute_tool_call(
            "file_view_windowed",
            {"path": self.file_name, "start_line": 1, "line_count": 3, "conversation_id": self.conv_id}
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data["start_line"], 1)
        self.assertEqual(res.data["end_line"], 3)
        self.assertEqual(res.data["total_lines"], 8)
        self.assertIn("1: # Line 1: Header", res.data["message"])
        self.assertIn("[Start of file] | [Scroll down available]", res.data["message"])

        # 2. Read lines 4 to 8
        res2 = await execute_tool_call(
            "file_view_windowed",
            {"path": self.file_name, "start_line": 4, "line_count": 5, "conversation_id": self.conv_id}
        )
        self.assertTrue(res2.success)
        self.assertEqual(res2.data["start_line"], 4)
        self.assertEqual(res2.data["end_line"], 8)
        self.assertIn("5: def subtract(a, b):", res2.data["message"])
        self.assertIn("[Scroll up available] | [End of file]", res2.data["message"])

    async def test_line_level_edit_success(self):
        """Test precise line replacement with file edit tool succeeding on valid syntax."""
        replacement = "def add(a, b):\n    print('Adding values')\n    return a + b\n"
        
        # Replace lines 2-3 (which is 'def add...' and 'return a + b')
        res = await execute_tool_call(
            "file_edit_line",
            {
                "path": self.file_name,
                "start_line": 2,
                "end_line": 3,
                "replacement_code": replacement,
                "conversation_id": self.conv_id
            }
        )
        self.assertTrue(res.success)
        self.assertIn("静态语法编译校验 100% 通过", res.data["message"])

        # Read back and verify the file content
        with open(self.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Adding values", content)

    async def test_line_level_edit_linter_fail(self):
        """Test syntax check failure is detected and triggers self-healing auto-rollback."""
        bad_replacement = "def add(a, b):\n    print('broken syntax'  # Missing closing paren\n"
        
        res = await execute_tool_call(
            "file_edit_line",
            {
                "path": self.file_name,
                "start_line": 2,
                "end_line": 3,
                "replacement_code": bad_replacement,
                "conversation_id": self.conv_id
            }
        )
        self.assertFalse(res.success)
        self.assertIn("检测到代码存在语法缺陷", res.error)
        self.assertIn("SyntaxError", res.error)

        # Read back and verify that the file remains perfectly untouched (unbroken)
        with open(self.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("broken syntax", content)
        self.assertIn("return a + b", content)

    async def test_stateful_terminal_navigation(self):
        """Test stateful terminal shell retains paths and environment variables across multiple commands."""
        # 1. Create a subdirectory inside sandbox
        sub_dir = "sub_folder"
        sub_dir_path = os.path.join(self.sandbox_dir, sub_dir)
        os.makedirs(sub_dir_path, exist_ok=True)

        # 2. Change directory in stateful shell
        res1 = await execute_tool_call(
            "run_stateful_command",
            {"command": f"cd {sub_dir}", "conversation_id": self.conv_id}
        )
        self.assertTrue(res1.success)

        # 3. Check current working directory in next step (should be inside sub_folder)
        cmd = "pwd" if os.name != "nt" else "Get-Location"
        res2 = await execute_tool_call(
            "run_stateful_command",
            {"command": cmd, "conversation_id": self.conv_id}
        )
        self.assertTrue(res2.success)
        self.assertIn(sub_dir, res2.data["output"])
