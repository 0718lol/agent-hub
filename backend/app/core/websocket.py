import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.locks: Dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str):
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = set()
        self.active_connections[conversation_id].add(websocket)
        self.locks[websocket] = asyncio.Lock()

    def disconnect(self, websocket: WebSocket, conversation_id: str):
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].discard(websocket)
        self.locks.pop(websocket, None)

    async def broadcast(self, conversation_id: str, message: dict):
        if conversation_id in self.active_connections:
            data = json.dumps(message, ensure_ascii=False)
            for connection in list(self.active_connections[conversation_id]):
                lock = self.locks.get(connection)
                if lock:
                    async with lock:
                        try:
                            await connection.send_text(data)
                        except Exception:
                            pass
                else:
                    try:
                        await connection.send_text(data)
                    except Exception:
                        pass


manager = ConnectionManager()
