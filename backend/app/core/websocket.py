import asyncio
import json
import logging
from uuid import uuid4

from fastapi import WebSocket

logger = logging.getLogger("websocket_manager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}
        self.locks: dict[WebSocket, asyncio.Lock] = {}
        self.pubsub_task: asyncio.Task | None = None
        self._publisher_id = uuid4().hex

    async def connect(self, websocket: WebSocket, conversation_id: str):
        await websocket.accept()
        self.active_connections.setdefault(conversation_id, set()).add(websocket)
        self.locks[websocket] = asyncio.Lock()

        # Start the background Pub/Sub listener task lazily on the first connection
        if self.pubsub_task is None or self.pubsub_task.done():
            self.pubsub_task = asyncio.create_task(self._redis_listener())

    def disconnect(self, websocket: WebSocket, conversation_id: str):
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].discard(websocket)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
        self.locks.pop(websocket, None)

    async def broadcast(self, conversation_id: str, message: dict):
        """Deliver locally and use Redis Pub/Sub to reach clients on other processes."""
        from app.core.redis import redis_manager

        if await redis_manager.check_connection():
            try:
                client = redis_manager.get_client()
                payload = {
                    "conversation_id": conversation_id,
                    "message": message,
                    "publisher_id": self._publisher_id,
                }
                await client.publish("agenthub:ws_broadcast", json.dumps(payload, ensure_ascii=False))
            except Exception as e:
                logger.warning(f"Could not relay WebSocket broadcast through Redis: {e}")
                redis_manager._is_connected = False

        # Local delivery works even before the Redis subscription is ready.
        await self._local_broadcast(conversation_id, message)

    async def _local_broadcast(self, conversation_id: str, message: dict):
        """Broadcasts a message directly to WebSockets hosted on this local server process."""
        if conversation_id in self.active_connections:
            from app.core.tenancy import public_conversation_id
            outgoing = dict(message)
            if outgoing.get("conversation_id"):
                outgoing["conversation_id"] = public_conversation_id(outgoing["conversation_id"])
            data = json.dumps(outgoing, ensure_ascii=False)
            stale_connections = []
            for connection in list(self.active_connections[conversation_id]):
                lock = self.locks.get(connection)
                try:
                    if lock:
                        async with lock:
                            await asyncio.wait_for(connection.send_text(data), timeout=5.0)
                    else:
                        await asyncio.wait_for(connection.send_text(data), timeout=5.0)
                except TimeoutError:
                    logger.warning(f"WebSocket send timeout for connection in conv {conversation_id}, removing stale connection")
                    stale_connections.append(connection)
                except Exception:
                    stale_connections.append(connection)
            # Clean up stale connections that failed to receive
            for conn in stale_connections:
                self.disconnect(conn, conversation_id)

    async def _redis_listener(self):
        """Background listener subscribing to the Redis broadcast channel.
        Processes distributed broadcast events and forwards them locally.
        Uses exponential backoff on connection failures (1s → 2s → 4s → ... → 30s).
        """
        from redis.exceptions import ConnectionError, TimeoutError

        from app.core.redis import redis_manager

        logger.info("Initializing Redis Pub/Sub WebSocket listener background task...")
        backoff = 1  # 指数退避起始秒数
        max_backoff = 30  # 最大退避秒数

        while True:
            if not await redis_manager.check_connection():
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
                continue

            # 连接成功，重置退避
            backoff = 1

            pubsub = None
            try:
                client = redis_manager.get_client()
                pubsub = client.pubsub()
                await pubsub.subscribe("agenthub:ws_broadcast")
                logger.info("Redis WebSocket Pub/Sub listener successfully subscribed.")

                while True:
                    try:
                        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                        if message:
                            data = json.loads(message["data"])
                            if data.get("publisher_id") == self._publisher_id:
                                continue
                            conv_id = data.get("conversation_id")
                            payload = data.get("message")
                            if conv_id and payload:
                                await self._local_broadcast(conv_id, payload)
                    except asyncio.CancelledError:
                        logger.info("Redis WebSocket Pub/Sub listener task cancelled.")
                        return
                    except Exception as e:
                        if isinstance(e, (ConnectionError, TimeoutError)):
                            logger.warning(f"Redis connection lost in Pub/Sub listener: {e}. Reconnecting...")
                            redis_manager._is_connected = False
                            break
                        else:
                            logger.error(f"Unexpected error in Redis Pub/Sub listener loop: {e}")
                            await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"Error subscribing to Redis Pub/Sub: {e}. Retrying in {backoff}s...")
                redis_manager._is_connected = False
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            finally:
                try:
                    if pubsub:
                        await pubsub.unsubscribe("agenthub:ws_broadcast")
                        await pubsub.close()
                except Exception as e:
                    logger.debug(f"Failed to close Redis pubsub during cleanup: {e}")


manager = ConnectionManager()
