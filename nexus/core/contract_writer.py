import json
from pathlib import Path
from typing import Any

class ContractWriter:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        
    def write(self, filename: str, data: Any):
        target = self.run_dir / filename
        with open(target, "w", encoding="utf-8") as f:
            if hasattr(data, "model_dump"):
                json.dump(data.model_dump(), f, indent=4)
            else:
                json.dump(data, f, indent=4)
