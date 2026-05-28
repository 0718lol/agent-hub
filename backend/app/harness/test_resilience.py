import sys
import os
import json
import unittest
import asyncio
import httpx
from typing import AsyncGenerator

# Ensure the app folder is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.llm_client import (
    ContextOptimizer,
    CircuitBreaker,
    ResilienceManager,
    LLMClient,
    LLMAPIError
)


class TestContextOptimizer(unittest.TestCase):

    def test_compress_single_message_under_limit(self):
        """Test that content below threshold is not compressed."""
        text = "Hello, world!"
        compressed = ContextOptimizer.compress_single_message(text, max_chars=100)
        self.assertEqual(compressed, text)

    def test_compress_single_message_over_limit(self):
        """Test that content above threshold is compressed, preserving start and end."""
        text = "A" * 10000
        compressed = ContextOptimizer.compress_single_message(text, max_chars=6000)
        self.assertIn("此处已自动压缩中段", compressed)
        self.assertEqual(len(compressed[:1500]), 1500)
        self.assertEqual(len(compressed[-1500:]), 1500)
        self.assertTrue(compressed.startswith("A" * 1500))
        self.assertTrue(compressed.endswith("A" * 1500))

    def test_optimize_messages_history_trimming(self):
        """Test history compaction when total length exceeds threshold."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "[工具结果: file_list]\n" + "B" * 5000 + "\n请处理。"},
            {"role": "assistant", "content": "C" * 2000},
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
            {"role": "user", "content": "Tell me more."},
        ]

        # Trigger history compaction by setting a low max_total_chars limit
        optimized = ContextOptimizer.optimize_messages(messages, max_total_chars=4000)

        # The last 3 turns (6 messages) should remain fully intact
        self.assertEqual(len(optimized), 6)
        self.assertEqual(optimized[-1]["content"], "Tell me more.")
        
        # The tool result user message in history should be compressed
        # Let's see if the first messages got optimized.
        # Wait, since keep_last_count = 6, if the length of optimized is 6, it kept only the last 6 messages
        # which are the system prompt plus history.
        # Let's test with a slightly larger list of messages.
        long_messages = [
            {"role": "system", "content": "System constraints"},
            {"role": "user", "content": "[工具结果: test_tool]\n" + "Z" * 8000},
            {"role": "assistant", "content": "A" * 1500},
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Reply 2"},
            {"role": "user", "content": "Turn 3"},
            {"role": "assistant", "content": "Reply 3"},
        ]
        
        optimized = ContextOptimizer.optimize_messages(long_messages, max_total_chars=3000)
        
        # Verify that the older tool message (index 1) in history got compacted
        self.assertIn("此处已自动清除较早的历史工具执行大文本", optimized[1]["content"])
        # Verify that the older assistant message (index 2) got truncated
        self.assertIn("此处已自动截断较早的历史回复内容", optimized[2]["content"])
        # Verify that the last 6 messages are fully intact
        self.assertEqual(optimized[-1]["content"], "Reply 3")
        self.assertEqual(optimized[-6]["content"], "Turn 1")


class TestCircuitBreaker(unittest.IsolatedAsyncioTestCase):

    async def test_circuit_breaker_transitions(self):
        """Test transitions CLOSED -> OPEN -> HALF-OPEN -> CLOSED."""
        breaker = CircuitBreaker("test-provider", threshold=2, cooldown=0.5)
        
        self.assertEqual(breaker.state, "CLOSED")
        self.assertTrue(await breaker.allow_request())

        # Record 1 failure
        await breaker.record_failure()
        self.assertEqual(breaker.state, "CLOSED")

        # Record 2nd failure -> Trips the breaker
        await breaker.record_failure()
        self.assertEqual(breaker.state, "OPEN")
        self.assertFalse(await breaker.allow_request())

        # Wait for cooldown to expire
        await asyncio.sleep(0.6)

        # Allow request will transition to HALF-OPEN
        self.assertTrue(await breaker.allow_request())
        self.assertEqual(breaker.state, "HALF-OPEN")

        # Record success -> Recovers back to CLOSED
        await breaker.record_success()
        self.assertEqual(breaker.state, "CLOSED")
        self.assertEqual(breaker.failed_attempts, 0)


class TestResilienceManager(unittest.IsolatedAsyncioTestCase):

    async def test_retry_success_after_transient_failure(self):
        """Test exponential backoff retries succeeding after transient failures."""
        manager = ResilienceManager()
        client = LLMClient()
        client.provider = "test-openai"
        
        attempts = 0

        # Simulating a stream generator that fails twice with 429 and succeeds on the third
        async def mock_stream(messages, system):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                if False:
                    yield None
                raise LLMAPIError(429, "Rate limit exceeded")
            yield "Success chunk"

        # Mocking backoffs to make tests run instantly
        original_backoffs = [1.5, 3.0, 6.0]
        # We can temporarily patch the backoffs to be very small
        import app.core.llm_client as lc
        lc.resilience_manager.breakers["test-openai"] = CircuitBreaker("test-openai", threshold=3, cooldown=30.0)
        
        # Execute streaming under manager
        # Since execute_with_retry expects custom backoffs, let's verify if we can mock sleep
        # Or let's mock lc.asyncio.sleep
        original_sleep = lc.asyncio.sleep
        lc.asyncio.sleep = lambda s: original_sleep(0.01)  # fast sleep

        try:
            chunks = []
            async for chunk in manager.execute_with_retry(client, mock_stream, [], ""):
                chunks.append(chunk)

            # Assert we retried and eventually succeeded
            self.assertEqual(attempts, 3)
            # The backoff warnings will be part of the yielded output
            self.assertTrue(any("指数退避重试" in c for c in chunks))
            self.assertTrue(any("Success chunk" in c for c in chunks))
            self.assertEqual(manager.get_breaker("test-openai").state, "CLOSED")
        finally:
            lc.asyncio.sleep = original_sleep

    async def test_circuit_breaker_trip_and_failover(self):
        """Test circuit breaker tripping on continuous failures and triggering failover to local Ollama."""
        manager = ResilienceManager()
        client = LLMClient()
        client.provider = "test-faulty"
        
        # Initialize breaker with threshold=1 to trip immediately on one final failure
        manager.breakers["test-faulty"] = CircuitBreaker("test-faulty", threshold=1)
        
        # Configure local Ollama mock endpoint
        client.is_ollama_active = lambda: True
        
        async def mock_faulty_stream(messages, system):
            if False:
                yield None
            raise LLMAPIError(500, "Internal Server Error")

        # Mock Ollama stream fallback
        async def mock_ollama_fallback(messages, system):
            yield "Ollama fallback stream"
            
        client._openai_stream_fallback_ollama = mock_ollama_fallback

        import app.core.llm_client as lc
        original_sleep = lc.asyncio.sleep
        lc.asyncio.sleep = lambda s: original_sleep(0.01)  # fast sleep

        try:
            chunks = []
            async for chunk in manager.execute_with_retry(client, mock_faulty_stream, [], ""):
                chunks.append(chunk)

            # Should trip circuit breaker, show failure messages, and trigger failover to Ollama
            self.assertTrue(any("故障已触发熔断保护" in c for c in chunks))
            self.assertTrue(any("降级至本地 Ollama" in c for c in chunks))
            self.assertTrue(any("Ollama fallback stream" in c for c in chunks))
            self.assertEqual(manager.get_breaker("test-faulty").state, "OPEN")
        finally:
            lc.asyncio.sleep = original_sleep


if __name__ == "__main__":
    unittest.main()
