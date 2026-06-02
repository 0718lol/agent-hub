import sys
import os
import unittest
import asyncio
import json
from unittest.mock import AsyncMock, patch

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.main import export_workflow, import_workflow, compile_workflow, get_custom_agents, _remove_custom_agent

class TestVisualToCode(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Clear custom agents if they exist to keep test clean
        for ca in list(get_custom_agents()):
            _remove_custom_agent(ca["agent_id"])

    def tearDown(self):
        # Cleanup custom agents
        for ca in list(get_custom_agents()):
            _remove_custom_agent(ca["agent_id"])

    async def test_workflow_export_and_import(self):
        """Test JSON Workflow serialization export and clean deserialization import."""
        # 1. Create a dummy custom agent configuration to simulate user canvas state
        custom_agent_payload = {
            "custom_agents": [
                {
                    "agent_id": "agent_custom_test_exporter",
                    "name": "测试导出辅助",
                    "avatar": "🧪",
                    "role": "导出测试",
                    "style": "极客风",
                    "system_prompt": "你是一个测试智能体。",
                    "tools": ["file_read", "file_write"]
                }
            ],
            "hil": {
                "human_input_mode": "COOLDOWN",
                "cooldown_steps": 3
            },
            "llm": {
                "provider": "ollama",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "qwen2.5-coder:7b",
                "temperature": 0.3,
                "max_tokens": 4096
            }
        }

        # 2. Run Import
        import_res = await import_workflow(custom_agent_payload)
        self.assertEqual(import_res["status"], "ok")
        self.assertEqual(import_res["imported_agents_count"], 1)

        # Verify custom agent actually got written into SQLite
        db_agents = get_custom_agents()
        test_agent = next((a for a in db_agents if a["agent_id"] == "agent_custom_test_exporter"), None)
        self.assertIsNotNone(test_agent)
        self.assertEqual(test_agent["name"], "测试导出辅助")

        # 3. Run Export
        export_res = await export_workflow("conv_test_visual_to_code")
        self.assertEqual(export_res["conversation_id"], "conv_test_visual_to_code")
        self.assertEqual(export_res["llm"]["provider"], "ollama")
        self.assertEqual(export_res["hil"]["human_input_mode"], "COOLDOWN")
        self.assertEqual(export_res["hil"]["cooldown_steps"], 3)
        self.assertEqual(len(export_res["custom_agents"]), 1)
        self.assertEqual(export_res["custom_agents"][0]["agent_id"], "agent_custom_test_exporter")

    async def test_workflow_standalone_compilation(self):
        """Test compiling active visual team into a syntactically correct self-contained Python script."""
        # 1. Compile the active team workflow
        compile_res = await compile_workflow("conv_test_visual_to_code")
        self.assertEqual(compile_res["status"], "ok")
        self.assertEqual(compile_res["filename"], "exported_team.py")
        
        code_content = compile_res["code"]
        self.assertIsNotNone(code_content)

        # 2. Syntax Validation: compile the generated code string to check for Python syntax errors!
        try:
            compiled_code = compile(code_content, "exported_team.py", "exec")
            self.assertIsNotNone(compiled_code)
        except SyntaxError as se:
            self.fail(f"Generated standalone Python script has syntax errors! Details: {se}")

        # 3. Structural checks: ensure essential components are embedded
        self.assertIn("class StateGraph:", code_content)
        self.assertIn("class StandaloneLLMClient:", code_content)
        self.assertIn("def select_next_speaker", code_content)
        self.assertIn("AGENTS = {", code_content)
        self.assertIn("LLM_CONFIG = {", code_content)
        self.assertIn("if __name__ == \"__main__\":", code_content)


if __name__ == "__main__":
    unittest.main()
