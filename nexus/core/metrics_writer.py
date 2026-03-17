import json
from pathlib import Path
from datetime import datetime

class MetricsWriter:
    def __init__(self, path: Path):
        self.path = Path(path)
        
    def write(self, task_id: str, tokens: int, **kwargs):
        data = {
            "task_id": task_id,
            "total_tokens": tokens,
            "last_updated": datetime.now().isoformat(),
            **kwargs
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
