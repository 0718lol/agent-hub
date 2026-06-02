import sys
import os
import unittest
import shutil
from unittest.mock import AsyncMock, patch, MagicMock

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.database import init_db
from app.core.event_stream import (
    event_stream_manager, MessageEvent, ThoughtEvent, ActionCallEvent, ObservationEvent
)
from app.agents.base import BaseAgent
from app.core.llm_client import llm_client

class TestEventStreamAndStatelessAgent(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        init_db()  # Ensure database schemas are fully up-to-date
        self.conv_id = "test_event_stream_conv_id"
        event_stream_manager.clear_stream(self.conv_id)

    def tearDown(self):
        event_stream_manager.clear_stream(self.conv_id)

    def test_event_persistence(self):
        """1. Verify standard temporal events are persisted in SQLite index."""
        # 1. Message Event
        msg_ev = MessageEvent(sender="user", content="Hello event stream!")
        event_stream_manager.append_event(self.conv_id, msg_ev)

        # 2. Thought Event
        thought_ev = ThoughtEvent(agent_id="agent_pm", content="Thinking about tasks...")
        event_stream_manager.append_event(self.conv_id, thought_ev)

        # 3. Action Call Event
        call_ev = ActionCallEvent(tool_name="web_search", params={"query": "E2B"})
        event_stream_manager.append_event(self.conv_id, call_ev)

        # 4. Observation Event
        obs_ev = ObservationEvent(tool_name="web_search", success=True, output={"results": ["OK"]})
        event_stream_manager.append_event(self.conv_id, obs_ev)

        # Retrieve chronological stream
        stream = event_stream_manager.get_stream(self.conv_id)
        self.assertEqual(len(stream), 4)
        
        self.assertTrue(isinstance(stream[0], MessageEvent))
        self.assertEqual(stream[0].sender, "user")
        self.assertEqual(stream[0].content, "Hello event stream!")

        self.assertTrue(isinstance(stream[1], ThoughtEvent))
        self.assertEqual(stream[1].agent_id, "agent_pm")
        self.assertEqual(stream[1].content, "Thinking about tasks...")

        self.assertTrue(isinstance(stream[2], ActionCallEvent))
        self.assertEqual(stream[2].tool_name, "web_search")
        self.assertEqual(stream[2].params["query"], "E2B")

        self.assertTrue(isinstance(stream[3], ObservationEvent))
        self.assertEqual(stream[3].tool_name, "web_search")
        self.assertTrue(stream[3].success)
        self.assertEqual(stream[3].output["results"][0], "OK")

    def test_messages_compilation(self):
        """2. Verify compilation from Event Stream logs to standard OpenAI messages."""
        # Push event sequence: User message -> Thought -> Tool Call -> Tool Result
        event_stream_manager.append_event(self.conv_id, MessageEvent(sender="user", content="Explain ACI"))
        event_stream_manager.append_event(self.conv_id, ThoughtEvent(agent_id="agent_backend", content="I will query details."))
        event_stream_manager.append_event(
            self.conv_id, ActionCallEvent(tool_name="web_search", params={"query": "Princeton SWE-agent ACI"})
        )
        event_stream_manager.append_event(
            self.conv_id, ObservationEvent(tool_name="web_search", success=True, output={"results": ["SWE-agent ACI is great"]})
        )
        event_stream_manager.append_event(self.conv_id, ThoughtEvent(agent_id="agent_backend", content="Finished querying."))

        messages = event_stream_manager.compile_to_messages(self.conv_id)
        self.assertEqual(len(messages), 4)

        # Message 1: User Prompt
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Explain ACI")

        # Message 2: Assistant Thought + Tool Call Block
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertIn("I will query details.", messages[1]["content"])
        self.assertIn("[tool_call:web_search]", messages[1]["content"])
        self.assertIn("Princeton SWE-agent ACI", messages[1]["content"])

        # Message 3: Tool Result User message
        self.assertEqual(messages[2]["role"], "user")
        self.assertIn("[工具结果: web_search]", messages[2]["content"])
        self.assertIn("SWE-agent ACI is great", messages[2]["content"])

        # Message 4: Assistant Trailing Thought
        self.assertEqual(messages[3]["role"], "assistant")
        self.assertEqual(messages[3]["content"], "Finished querying.")

    async def test_stateless_agent_loop(self):
        """3. Verify BaseAgent loop compiles and mutates event streams correctly."""
        agent = BaseAgent()
        agent.agent_id = "test_stateless_agent"
        agent.system_prompt = "You are a helpful assistant."

        # Let's mock llm_client.chat_stream to return a tool call chunk in round 1 and final text in round 2
        async def mock_chat_stream(messages, system):
            if len(messages) == 1:
                # Round 1: Yield tool call tag
                yield "Thinking... Let me search.\n[tool_call:web_search]{\"query\": \"OpenHands\"}[/tool_call]"
            else:
                # Round 2: Yield final text
                yield "OpenHands is an amazing agent platform."

        with patch.object(llm_client, "is_configured", return_value=True), \
             patch.object(llm_client, "chat_stream", side_effect=mock_chat_stream):

            chunks = []
            async for chunk in agent.stream_reply("Tell me about OpenHands", conversation_id=self.conv_id):
                chunks.append(chunk)

            # Retrieve final event log stream
            stream = event_stream_manager.get_stream(self.conv_id)
            
            # Events expected:
            # 1. MessageEvent (user prompt)
            # 2. ThoughtEvent ("Thinking... Let me search.")
            # 3. ActionCallEvent (tool_name="web_search")
            # 4. ObservationEvent (tool output)
            # 5. ThoughtEvent ("OpenHands is an amazing agent platform.")
            self.assertEqual(len(stream), 5)
            
            self.assertTrue(isinstance(stream[0], MessageEvent))
            self.assertEqual(stream[0].content, "Tell me about OpenHands")

            self.assertTrue(isinstance(stream[1], ThoughtEvent))
            self.assertEqual(stream[1].content.strip(), "Thinking... Let me search.")

            self.assertTrue(isinstance(stream[2], ActionCallEvent))
            self.assertEqual(stream[2].tool_name, "web_search")

            self.assertTrue(isinstance(stream[3], ObservationEvent))
            self.assertEqual(stream[3].tool_name, "web_search")

            self.assertTrue(isinstance(stream[4], ThoughtEvent))
            self.assertEqual(stream[4].content, "OpenHands is an amazing agent platform.")
