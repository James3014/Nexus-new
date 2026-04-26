from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json


class JsonlEventLogStore:
    """Append/read access for event JSONL persistence."""

    def __init__(self):
        self.event_log_path: Optional[Path] = None

    def configure(self, project_root: Path) -> Tuple[Path, Path]:
        log_dir = project_root / ".nexus" / "events"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.event_log_path = log_dir / "event_log.jsonl"
        return log_dir, self.event_log_path

    def append_record(self, record: Dict[str, Any]) -> None:
        if not self.event_log_path:
            return
        with open(self.event_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def read_recent(self, event_type: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        if not self.event_log_path or not self.event_log_path.exists():
            return []
        lines = self.event_log_path.read_text(encoding="utf-8").strip().split("\n")
        events = [json.loads(l) for l in lines[-limit:] if l.strip()]
        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        return events
