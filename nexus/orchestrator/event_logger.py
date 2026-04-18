import json
import time
from pathlib import Path
from datetime import datetime, timezone

class EventLogger:
    def __init__(self, log_file: str = ".nexus/multi_agent/runs/events.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: str, data: dict):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "data": data
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def get_events(self) -> list[dict]:
        if not self.log_file.exists():
            return []
        events = []
        with open(self.log_file, "r") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events
# v24.13 final hardening
