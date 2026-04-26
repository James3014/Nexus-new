from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List

from nexus.events.signal_ingress import SignalIngress


class SignalQueueService:
    """Thread-safe queue wrapper over SignalIngress utilities."""

    def __init__(self, ingress: SignalIngress | None = None):
        self._ingress = ingress or SignalIngress()
        self._queue: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    @property
    def queue(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._queue

    def reset(self, queue: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
        with self._lock:
            self._queue = list(queue or [])
            return self._queue

    def load_from_inbox(self, signal_file: Path) -> List[Dict[str, Any]]:
        with self._lock:
            self._queue = self._ingress.load_from_inbox(signal_file)
            return self._queue

    def inject(self, signal_type: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        with self._lock:
            self._queue = self._ingress.inject(self._queue, signal_type, payload)
            return self._queue

    def drain(self, signal_type: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            drained, remaining = self._ingress.drain(self._queue, signal_type)
            self._queue = remaining
            return drained
