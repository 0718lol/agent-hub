import json
import asyncio
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket

logger = logging.getLogger("websocket_manager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.locks: Dict[WebSocket, asyncio.Lock] = {}
        self.pubsub_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, conversation_id: str):
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = set()
        self.active_connections[conversation_id].add(websocket)
        self.locks[websocket] = asyncio.Lock()

        # Start the background Pub/Sub listener task lazily on the first connection
        if self.pubsub_task is None or self.pubsub_task.done():
            self.pubsub_task = asyncio.create_task(self._redis_listener())

    def disconnect(self, websocket: WebSocket, conversation_id: str):
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].discard(websocket)
        self.locks.pop(websocket, None)

    async def broadcast(self, conversation_id: str, message: dict):
        """Broadcasts a message to all connected clients under a conversation_id.
        If Redis is online, publishes to Redis Pub/Sub. Otherwise, broadcasts locally.
        """
        from app.core.redis import redis_manager
        
        if await redis_manager.check_connection():
            try:
                client = redis_manager.get_client()
                payload = {
                    "conversation_id": conversation_id,
                    "message": message
                }
                await client.publish("agenthub:ws_broadcast", json.dumps(payload, ensure_ascii=False))
                return
            except Exception as e:
                logger.warning(f"Failed to publish broadcast to Redis: {e}. Falling back to local broadcast.")
                redis_manager._is_connected = False

        # Fallback to local broadcast
        await self._local_broadcast(conversation_id, message)

    async def _local_broadcast(self, conversation_id: str, message: dict):
        """Broadcasts a message directly to WebSockets hosted on this local server process."""
        if conversation_id in self.active_connections:
            data = json.dumps(message, ensure_ascii=False)
            stale_connections = []
            for connection in list(self.active_connections[conversation_id]):
                lock = self.locks.get(connection)
                try:
                    if lock:
                        async with lock:
                            await asyncio.wait_for(connection.send_text(data), timeout=5.0)
                    else:
                        await asyncio.wait_for(connection.send_text(data), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(f"WebSocket send timeout for connection in conv {conversation_id}, removing stale connection")
                    stale_connections.append(connection)
                except Exception:
                    stale_connections.append(connection)
            # Clean up stale connections that failed to receive
            for conn in stale_connections:
                self.active_connections.get(conversation_id, set()).discard(conn)
                self.locks.pop(conn, None)

    async def _redis_listener(self):
        """Background listener subscribing to the Redis broadcast channel.
        Processes distributed broadcast events and forwards them locally.
        """
        from app.core.redis import redis_manager
        from redis.exceptions import ConnectionError, TimeoutError

        logger.info("Initializing Redis Pub/Sub WebSocket listener background task...")
        
        while True:
            if not await redis_manager.check_connection():
                # Redis not online, wait and retry later
                await asyncio.sleep(5)
                continue

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
                            conv_id = data.get("conversation_id")
                            payload = data.get("message")
                            if conv_id and payload:
                                await self._local_broadcast(conv_id, payload)
                    except asyncio.CancelledError:
                        logger.info("Redis WebSocket Pub/Sub listener task cancelled.")
                        try:
                            await pubsub.unsubscribe("agenthub:ws_broadcast")
                            await pubsub.close()
                        except Exception:
                            pass
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
                logger.warning(f"Error subscribing to Redis Pub/Sub: {e}. Retrying in 5 seconds...")
                redis_manager._is_connected = False
                await asyncio.sleep(5)


manager = ConnectionManager()
