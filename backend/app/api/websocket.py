"""WebSocket endpoint cho realtime predictions.

Consumer thread → manager.broadcast() → tất cả connected client nhận event.
Frontend subscribe `/ws/predictions` qua hook useWebSocket.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.ws_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/predictions")
async def ws_predictions(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        # Giữ connection mở — đọc message để detect disconnect.
        # Client không cần gửi gì, chỉ là heartbeat handshake.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
