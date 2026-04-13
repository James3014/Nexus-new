import json
import shutil
from pathlib import Path
from datetime import datetime, UTC

class WisdomSynthesizer:
    """
    💎 Work Order H: Crystal-to-Template Feedback Loop
    將 Phase C 結晶後的成功實作模式轉化為可重用的模板。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.template_dir = project_root / ".nexus" / "knowledge" / "templates"
        self.template_dir.mkdir(parents=True, exist_ok=True)

    def synthesize_template(self, task_id: str, i_pack: dict, score: float):
        """
        將高品質實作包 (I-Pack) 提取為模板。
        """
        if score < 95:
            return None

        task_type = i_pack.get("task_type", "default")
        template_path = self.template_dir / f"{task_type}_best_practice.json"
        
        # 提取可重用模式 (去 UUID 化)
        template_data = {
            "template_name": f"{task_type}_best_practice",
            "derived_from": task_id,
            "typical_deliverables": i_pack.get("deliverables", []),
            "typical_data_models": i_pack.get("data_models", []),
            "common_edge_cases": i_pack.get("edge_cases", []),
            "successful_formulas": ["acceptancePassed && auditPassed"],
            "last_updated": datetime.now(UTC).isoformat()
        }

        with open(template_path, "w") as f:
            json.dump(template_data, f, indent=2, ensure_ascii=False)
        
        print(f"💎 [Wisdom] New template synthesized: {template_path}")
        return template_path

    def log_learning_event(self, task_id: str, category: str, outcome: str, metadata: dict):
        """
        將施工經驗寫入全域教訓鏈。
        """
        lesson_file = self.project_root / ".nexus" / "knowledge" / "lesson_events.jsonl"
        event = {
            "lesson_id": f"IMPL-{int(datetime.now(UTC).timestamp())}",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "category": category, # e.g., "SPEC_QUALITY", "SOT_DRIFT"
            "task_id": task_id,
            "outcome": outcome,
            "metadata": metadata
        }
        with open(lesson_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def sync_all(self) -> dict:
        """Compatibility API for legacy synthesis loop tests."""
        lesson_file = self.project_root / ".nexus" / "knowledge" / "lesson_events.jsonl"
        if not lesson_file.exists():
            return {"status": "EMPTY", "rules_synthesized": 0}
        try:
            count = sum(1 for line in lesson_file.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            return {"status": "EMPTY", "rules_synthesized": 0}
        return {"status": "SUCCESS" if count else "EMPTY", "rules_synthesized": count}
