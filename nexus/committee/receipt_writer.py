import json
import os
from nexus.committee.models import CommitteeReceipt

class CommitteeReceiptWriter:
    """
    📝 Task T9: Committee Receipt Writer
    職責: 將委員會決策結果永久化存檔，對齊 Rust Ledger。
    """
    def __init__(self, storage_dir: str = ".nexus/reports/committee"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def write(self, receipt: CommitteeReceipt):
        file_path = os.path.join(self.storage_dir, f"{receipt.task_id}_committee.json")
        
        # 轉換為可序列化格式
        data = {
            "task_id": receipt.task_id,
            "winner_id": receipt.winner_id,
            "k": receipt.k,
            "failure_bucket": receipt.failure_bucket,
            "candidates": [c.candidate_id for c in receipt.candidates],
            "verdicts": [v.critic_name for v in receipt.verdicts]
        }
        
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        return file_path
