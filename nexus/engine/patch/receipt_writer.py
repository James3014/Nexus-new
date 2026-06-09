import json
import hashlib
from pathlib import Path
from typing import Dict, Any

class ApplyReceiptWriter:
    """
    🛡️ ApplyReceiptWriter: 套用證據寫入器
    封裝套用過程為可重放的 Artifact。
    """
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_receipt(self, task_id: str, data: Dict[str, Any]) -> Path:
        receipt_path = self.output_dir / f"patch_receipt_{task_id}.json"
        receipt_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return receipt_path
