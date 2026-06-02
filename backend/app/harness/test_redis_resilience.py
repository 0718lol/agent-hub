import sys
import os
import time
import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.redis import redis_manager
from app.core.websocket import ConnectionManager
from app.core.llm_client import CircuitBreaker


class TestRedisResilience(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Reset redis_manager state before each test
        await redis_manager.close()
        redis_manager._is_connected = None

    async def asyncTearDown(self):
        await redis_manager.close()
        redis_manager._is_connected = None

    async def test_circuit_breaker_offline_fallback(self):
        """Test that CircuitBreaker falls back seamlessly to in-memory state when Redis is offline."""
        # Point redis_manager to a non-existent port to force connection failure
        redis_manager.redis_url = "redis://localhost:9999/0"
        
        # Initialize a circuit breaker
        cb = CircuitBreaker("offline-provider", threshold=2, cooldown=0.5)
        
        # Verify initial state
        self.assertEqual(cb.state, "CLOSED")
        self.assertEqual(cb.failed_attempts, 0)
        self.assertTrue(await cb.allow_request())

        # Record 1 failure -> check in-memory update
        await cb.record_failure()
        self.assertEqual(cb.state, "CLOSED")
        self.assertEqual(cb.failed_attempts, 1)

        # Record 2nd failure -> Trips
        await cb.record_failure()
        self.assertEqual(cb.state, "OPEN")
        self.assertFalse(await cb.allow_request())

    async def test_websocket_offline_fallback(self):
        """Test that ConnectionManager falls back seamlessly to local broadcast when Redis is offline."""
        redis_manager.redis_url = "redis://localhost:9999/0"
        
        manager = ConnectionManager()
        
        # Mock a WebSocket
        mock_ws = AsyncMock()
        await manager.connect(mock_ws, "test-session")
        
        # Verify local connections list is populated
        self.assertIn(mock_ws, manager.active_connections["test-session"])
        
        # Broadcast a message while Redis is offline
        test_msg = {"type": "test", "content": "hello"}
        await manager.broadcast("test-session", test_msg)
        
        # Verify local WebSocket received the text
        mock_ws.send_text.assert_called_once()
        
        # Cleanup
        manager.disconnect(mock_ws, "test-session")
        if manager.pubsub_task:
            manager.pubsub_task.cancel()
            try:
                await manager.pubsub_task
            except asyncio.CancelledError:
                pass

    @patch("app.core.redis.redis_manager.check_connection", new_callable=AsyncMock)
    @patch("app.core.redis.redis_manager.get_client")
    async def test_circuit_breaker_redis_active(self, mock_get_client, mock_check_connection):
        """Test that CircuitBreaker retrieves and stores state in Redis when active."""
        mock_check_connection.return_value = True
        
        # Setup mock Redis client
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        
        # Mock hgetall to return OPEN state
        mock_client.hgetall.return_value = {
            "state": "OPEN",
            "failed_attempts": "3",
            "last_state_change": str(time.time() - 10)
        }

        
        cb = CircuitBreaker("active-provider", threshold=3, cooldown=30.0)
        
        # Allow request should check state in Redis and return False (since 10s < 30s cooldown)
        self.assertFalse(await cb.allow_request())
        mock_client.hgetall.assert_called_once_with("agenthub:cb:active-provider")
        
        # Record success should write CLOSED state to Redis
        mock_client.hgetall.reset_mock()
        await cb.record_success()
        mock_client.hset.assert_called_once()
        mapping = mock_client.hset.call_args[1]["mapping"]
        self.assertEqual(mapping["state"], "CLOSED")
        self.assertEqual(mapping["failed_attempts"], "0")

    @patch("app.core.redis.redis_manager.check_connection", new_callable=AsyncMock)
    @patch("app.core.redis.redis_manager.get_client")
    async def test_websocket_redis_active(self, mock_get_client, mock_check_connection):
        """Test that ConnectionManager publishes to Redis Pub/Sub when active."""
        mock_check_connection.return_value = True
        
        # Setup mock Redis client
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        
        manager = ConnectionManager()
        
        test_msg = {"type": "test", "content": "broadcast-active"}
        
        await manager.broadcast("test-session", test_msg)
        
        # Verify it published to the Redis channel and did not call local broadcast
        mock_client.publish.assert_called_once()
        channel, payload_str = mock_client.publish.call_args[0]
        self.assertEqual(channel, "agenthub:ws_broadcast")
        
        import json
        payload_data = json.loads(payload_str)
        self.assertEqual(payload_data["conversation_id"], "test-session")
        self.assertEqual(payload_data["message"], test_msg)


if __name__ == "__main__":
    unittest.main()
