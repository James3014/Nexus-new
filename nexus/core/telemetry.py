import json
import time
from typing import Dict, Any, List, Optional, Protocol, runtime_checkable
from pathlib import Path

@runtime_checkable
class TelemetryProvider(Protocol):
    def log_span(self, name: str, start_ts: float, end_ts: float, decision_id: str, metadata: Optional[Dict[str, Any]] = None): ...

class FileTelemetryProvider:
    def __init__(self, metrics_path: Path, io_queue: Any):
        self.metrics_path = metrics_path
        self.io_queue = io_queue

    def log_span(self, name: str, start_ts: float, end_ts: float, decision_id: str, metadata: Optional[Dict[str, Any]] = None):
        payload = {
            "span_name": name,
            "decision_id": decision_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "duration_ms": (end_ts - start_ts) * 1000,
            "metadata": metadata or {}
        }
        self.io_queue.put(str(self.metrics_path), json.dumps(payload, ensure_ascii=False) + "\n")

class NoopTelemetryProvider:
    def log_span(self, *args, **kwargs): pass
