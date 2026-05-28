import asyncio
import sys
import os
import json
import unittest

# Ensure the app folder is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.pipeline import StreamContext, StreamPipeline, UnifiedTagMiddleware, CodeBlockMiddleware

class MockWebSocketManager:
    def __init__(self):
        self.messages = []

    async def broadcast(self, conversation_id: str, message: dict):
        self.messages.append(message)


class TestStreamPipeline(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_manager = MockWebSocketManager()
        self.context = StreamContext(
            conversation_id="test_conv_id",
            agent_id="test_agent_id",
            websocket_manager=self.mock_manager
        )
        self.pipeline = StreamPipeline(self.context)
        self.pipeline.add_middleware(UnifiedTagMiddleware())
        self.pipeline.add_middleware(CodeBlockMiddleware())

    async def test_standard_pipeline_flow(self):
        """Test clean text accumulation and tag extraction on a complete text block."""
        input_text = (
            "[thinking] 思考中... [/thinking]"
            "[tool_execution] 正在读取文件 [/tool_execution]"
            "好的，主气泡内容在这里。"
            "```html\n<h1>Hello</h1>\n```"
            "[assign:agent_frontend]"
        )

        processed = await self.pipeline.process_chunk(input_text)
        flushed = await self.pipeline.finalize()
        final_text = (processed + flushed).strip()

        # Check main output is clean
        expected_text = "好的，主气泡内容在这里。\n[code_generated]"
        self.assertEqual(final_text, expected_text)

        # Check websocket events
        thinking_events = [m for m in self.mock_manager.messages if m["type"] == "thinking"]
        code_events = [m for m in self.mock_manager.messages if m["type"] == "code"]
        preview_events = [m for m in self.mock_manager.messages if m["type"] == "preview"]

        self.assertEqual(len(thinking_events), 3)
        # Check thinking block capture
        self.assertEqual(thinking_events[0]["text"], "思考中...")
        self.assertEqual(thinking_events[1]["text"], "")
        # Check tool execution captured as thinking event
        self.assertEqual(thinking_events[2]["text"], "正在读取文件")

        # Check code block capture
        self.assertEqual(len(code_events), 1)
        self.assertEqual(code_events[0]["code"], "<h1>Hello</h1>")
        self.assertEqual(code_events[0]["language"], "html")

        # Check preview capture
        self.assertEqual(len(preview_events), 1)
        self.assertEqual(preview_events[0]["html"], "<h1>Hello</h1>")

        # Check assign lifecycle state
        assigned = self.context.state.get("assigned_agents", [])
        self.assertEqual(assigned, ["agent_frontend"])

    async def test_token_fragmentation_sliding_buffer(self):
        """
        Extremely granular fragmentation test.
        Splits the text into tiny chunks of 1 to 3 characters and feeds them chunk-by-chunk.
        """
        input_text = (
            "[thinking] 正在进行沙盒编译 [/thinking] "
            "好的，我已经完成了代码修改：\n"
            "```html\n<h1>Success</h1>\n``` "
            "[assign:agent_designer]"
        )

        # Break text into chunks of random/various small sizes
        chunks = []
        i = 0
        while i < len(input_text):
            step = (i % 3) + 1  # 1, 2, or 3 chars
            chunks.append(input_text[i:i+step])
            i += step

        # Feed the chunks into pipeline
        accumulated_clean = ""
        for chunk in chunks:
            processed = await self.pipeline.process_chunk(chunk)
            accumulated_clean += processed

        flushed = await self.pipeline.finalize()
        final_text = (accumulated_clean + flushed).strip()

        # Verify final typewriter output is perfectly reconstructed and stripped
        expected_text = "好的，我已经完成了代码修改：\n\n[code_generated]"
        self.assertEqual(final_text, expected_text)

        # Verify we captured thinking content perfectly
        thinking_events = [m for m in self.mock_manager.messages if m["type"] == "thinking" and m["text"]]
        self.assertEqual(thinking_events[-1]["text"], "正在进行沙盒编译")

        # Verify we captured code/preview content perfectly
        code_events = [m for m in self.mock_manager.messages if m["type"] == "code"]
        self.assertEqual(code_events[-1]["code"], "<h1>Success</h1>")

        # Verify assign tag captured perfectly
        assigned = self.context.state.get("assigned_agents", [])
        self.assertEqual(assigned, ["agent_designer"])

    async def test_unclosed_tag_graceful_flush(self):
        """Test that unclosed tags are gracefully flushed at the end of the stream without losing text."""
        input_text = "这是正常开头 [thinking] 我在思考但在流结束前没有闭合"
        processed = await self.pipeline.process_chunk(input_text)
        flushed = await self.pipeline.finalize()
        final_text = processed + flushed

        # Since it was never closed, it is flushed back as normal text
        self.assertEqual(final_text, "这是正常开头 [thinking] 我在思考但在流结束前没有闭合")


if __name__ == "__main__":
    unittest.main()
