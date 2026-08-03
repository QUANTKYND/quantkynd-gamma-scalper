"""In-memory active broker connection state."""

from __future__ import annotations

import threading


class ConnectionState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_broker: str | None = None

    def set_connected(self, broker: str) -> None:
        with self._lock:
            self._active_broker = broker

    def clear(self) -> None:
        with self._lock:
            self._active_broker = None

    def active_broker(self) -> str | None:
        with self._lock:
            return self._active_broker


connection_state = ConnectionState()
