from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import json
import time
import logging

logger = logging.getLogger(__name__)


class SignalIngress:
    """Signal queue ingress/drain utilities."""

    def load_from_inbox(self, signal_file: Path) -> List[Dict[str, Any]]:
        if not signal_file.exists():
            return []
        try:
            loaded = [
                json.loads(line)
                for line in signal_file.read_text(encoding="utf-8").strip().split("\n")
                if line.strip()
            ]
            signal_file.write_text("", encoding="utf-8")  # consume then clear
            return loaded
        except Exception as e:
            logger.debug("signal_inbox load failed: %s", e)
            return []

    def inject(self, queue: List[Dict[str, Any]], signal_type: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        queue.append({
            "signal_type": signal_type,
            "payload": payload,
            "injected_at": time.time(),
        })
        return queue

    def drain(self, queue: List[Dict[str, Any]], signal_type: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not signal_type:
            return list(queue), []
        matched = [s for s in queue if s["signal_type"] == signal_type]
        remaining = [s for s in queue if s["signal_type"] != signal_type]
        return matched, remaining
