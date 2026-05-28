import sys
import os
import unittest
import shutil
import asyncio

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.repo_map import codebase_map_scanner
from app.tools.registry import execute_tool_call
from app.core.git_sandbox import git_init

class TestAiderMapsAndBlockEditor(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.conv_id = "test_aider_maps_conv"
        self.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.sandbox_dir = os.path.join(self.workspace_dir, "agenthub_export", self.conv_id)
        os.makedirs(self.sandbox_dir, exist_ok=True)

        # Create a mock Python file for symbol scan and block patch
        self.py_file = "utils_helper.py"
        self.py_path = os.path.join(self.sandbox_dir, self.py_file)
        self.py_content = (
            "import os\n"
            "import sys\n\n"
            "def calculate_tax(income):\n"
            "    # Standalone function\n"
            "    return income * 0.2\n\n"
            "class InvoiceProcessor:\n"
            "    def __init__(self, invoice_id):\n"
            "        self.invoice_id = invoice_id\n\n"
            "    def process_invoice(self, amount):\n"
            "        return f'Processed {self.invoice_id} with amount {amount}'\n"
        )
        with open(self.py_path, "w", encoding="utf-8") as f:
            f.write(self.py_content)

        # Create a mock TypeScript file for multi-language symbol scanning verification
        self.ts_file = "helper.ts"
        self.ts_path = os.path.join(self.sandbox_dir, self.ts_file)
        self.ts_content = (
            "import { useState } from 'react';\n"
            "import axios from 'axios';\n\n"
            "export function formatCurrency(value: number): string {\n"
            "    return `$${value.toFixed(2)}`;\n"
            "}\n\n"
            "export class OrderManager {\n"
            "    constructor(private orderId: string) {}\n\n"
            "    async processOrder(amount: number) {\n"
            "        console.log('Processing order ' + this.orderId);\n"
            "    }\n"
            "}\n"
        )
        with open(self.ts_path, "w", encoding="utf-8") as f:
            f.write(self.ts_content)

    def tearDown(self):
        if os.path.exists(self.sandbox_dir):
            try:
                shutil.rmtree(self.sandbox_dir)
            except Exception:
                pass

    def test_repo_map_scanner(self):
        """1. Verify AST & Regex symbol map constructs correct markdown hierarchy of classes and functions for PY and JS/TS."""
        repo_map = codebase_map_scanner.scan_directory(self.sandbox_dir)
        # Python checks
        self.assertIn("utils_helper.py", repo_map)
        self.assertIn("imports: `os`, `sys`", repo_map)
        self.assertIn("function: `calculate_tax(income)`", repo_map)
        self.assertIn("class: `InvoiceProcessor`", repo_map)
        self.assertIn("method: `process_invoice(self, amount)`", repo_map)

        # JS/TS checks
        self.assertIn("helper.ts", repo_map)
        self.assertIn("imports: `react`, `axios`", repo_map)
        self.assertIn("function: `formatCurrency(value: number)`", repo_map)
        self.assertIn("class: `OrderManager`", repo_map)
        self.assertIn("method: `processOrder(amount: number)`", repo_map)

    async def test_block_patch_success(self):
        """2. Verify SEARCH/REPLACE block replacement applies high-tolerance modifications correctly."""
        # Standard conflict markers patch
        patch_code = (
            "<<<<<<< SEARCH\n"
            "def calculate_tax(income):\n"
            "    # Standalone function\n"
            "    return income * 0.2\n"
            "=======\n"
            "def calculate_tax(income):\n"
            "    # Upgraded with high-tolerance brackets\n"
            "    if income < 0:\n"
            "        return 0\n"
            "    return income * 0.25\n"
            ">>>>>>> REPLACE"
        )

        res = await execute_tool_call(
            "file_patch_block",
            {
                "path": self.py_file,
                "patch_blocks": patch_code,
                "conversation_id": self.conv_id
            }
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data["applied_blocks_count"], 1)

        # Read content back and verify
        with open(self.py_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Upgraded with high-tolerance brackets", content)
        self.assertIn("income * 0.25", content)
        self.assertNotIn("income * 0.2\n", content)

    async def test_block_patch_linter_rollback(self):
        """3. Verify linter compile failure forces transaction rollback on Git sandbox."""
        # Initialize Git in sandboxed directory so that rollback logic operates
        await git_init(self.sandbox_dir)

        # Apply a patch block that yields invalid python syntax (unbalanced parenthesis)
        broken_patch = (
            "<<<<<<< SEARCH\n"
            "    def process_invoice(self, amount):\n"
            "        return f'Processed {self.invoice_id} with amount {amount}'\n"
            "=======\n"
            "    def process_invoice(self, amount):\n"
            "        # Broken parenthesis syntax error\n"
            "        print('Broken syntax!'\n"
            "        return f'Processed {self.invoice_id} with amount {amount}'\n"
            ">>>>>>> REPLACE"
        )

        res = await execute_tool_call(
            "file_patch_block",
            {
                "path": self.py_file,
                "patch_blocks": broken_patch,
                "conversation_id": self.conv_id
            }
        )
        self.assertFalse(res.success)
        self.assertIn("代码块替换失败", res.error)
        self.assertIn("SyntaxError", res.error)

        # Verify content was rolled back and original script remains intact and unbroken
        with open(self.py_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("Broken syntax!", content)
        self.assertIn("return f'Processed {self.invoice_id} with amount {amount}'", content)
