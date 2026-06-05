import threading
from typing import Any, Dict, List

class TelemetryCollector:
    def __init__(self):
        self._store = threading.local()
        
    @property
    def records(self) -> List[Dict[str, Any]]:
        if not hasattr(self._store, "records"):
            self._store.records = []
        return self._store.records

    @records.setter
    def records(self, value: List[Dict[str, Any]]) -> None:
        self._store.records = value

    def clear(self) -> None:
        self._store.records = []

    def record_call(self, model: str, api_type: str, data: Dict[str, Any]) -> None:
        record = {
            "model": model,
            "api_type": api_type,
            "total_duration_ms": round(data.get("total_duration", 0) / 1e6, 2),
            "load_duration_ms": round(data.get("load_duration", 0) / 1e6, 2),
            "prompt_eval_count": data.get("prompt_eval_count", 0),
            "eval_count": data.get("eval_count", 0),
            "prompt_eval_duration_ms": round(data.get("prompt_eval_duration", 0) / 1e6, 2),
            "eval_duration_ms": round(data.get("eval_duration", 0) / 1e6, 2),
        }
        self.records.append(record)
