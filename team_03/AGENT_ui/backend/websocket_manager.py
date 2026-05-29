"""
WebSocket connection manager for real-time agent communication.
"""
from __future__ import annotations

import json
from enum import Enum
from typing import List

from fastapi import WebSocket


class MessageType(str, Enum):
    chat_message = "chat_message"
    agent_response = "agent_response"
    agent_event = "agent_event"
    state_update = "state_update"
    selection_sync = "selection_sync"


class ConnectionManager:
    """Manages all active WebSocket connections and message broadcasting."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and register it."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active list."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to every connected client."""
        payload = json.dumps(message)
        dead: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """Send a JSON message to a single client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            self.disconnect(websocket)
