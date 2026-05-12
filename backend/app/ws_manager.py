"""WebSocket connection manager — broadcast prediction events ra mọi client.

WHY in-memory thay vì Redis pub/sub: deploy 1 worker FastAPI trên EC2 t3.micro
→ 1 process duy nhất, không cần cross-process bus. Khi scale ra nhiều worker
mới cần Redis.

WHY giữ set thay vì list: O(1) add/remove khi client disconnect.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._active: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._active.add(ws)
        logger.info("WS connected. Total: %d", len(self._active))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._active.discard(ws)
        logger.info("WS disconnected. Total: %d", len(self._active))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Gửi payload tới tất cả client. Client lỗi → drop khỏi set."""
        async with self._lock:
            targets = list(self._active)

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception as exc:
                # Client disconnect giữa chừng — log debug, không cần stack trace.
                logger.debug("WS send failed, dropping: %s", exc)
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._active.discard(ws)

    def size(self) -> int:
        return len(self._active)


# Singleton — import từ consumer + websocket router.
manager = ConnectionManager()
