import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from nexus.services.source_of_truth_resolver import SourceOfTruthResolver
from nexus.services.status_normalizer import StatusNormalizer
from nexus.services.decision_formula_engine import DecisionFormulaEngine
from nexus.services.readability_gate import ReadabilityGate

class ImplementationPackGenerator:
    """
    ⚔️ Work Order A: Implementation Pack Generator (Orchestrator)
    Nexus vNext 編譯器核心：將 P-Phase 產物轉化為硬性施工包。
    """

    def __init__(self, project_root: Path, task_id: str):
        self.project_root = project_root
        self.task_id = task_id
        self.run_dir = project_root / ".nexus" / "runs" / task_id
        self.impl_dir = self.run_dir / "implementation"
        self.impl_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, planner_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行全量編譯。
        """
        results = {}

        # 1. 執行真值解析 (SOT Resolver)
        resolver = SourceOfTruthResolver(self.project_root, self.task_id)
        sot_map = resolver.resolve()
        results["sot_map"] = sot_map

        # 2. 執行命名歸一化 (Status Normalizer)
        norm_artifact = StatusNormalizer.generate_normalization_artifact()
        with open(self.impl_dir / "state_normalization.json", "w") as f:
            json.dump(norm_artifact, f, indent=2, ensure_ascii=False)

        # 3. 執行公式計算 (Decision Formula Engine)
        # 準備上下文：從 SOT Map 中提取真值
        data_ctx = {}
        for field, info in sot_map.get("field_map", {}).items():
            # 這裡簡化：假設我們能從對應檔案讀到值
            src_path = self.run_dir / info["source"]
            if src_path.exists():
                with open(src_path, "r") as f:
                    content = json.load(f)
                    data_ctx[field] = content.get(field)
        
        formula_engine = DecisionFormulaEngine(data_ctx)
        formulas = formula_engine.generate_artifact()
        with open(self.impl_dir / "decision_formula.json", "w") as f:
            json.dump(formulas, f, indent=2)

        # 4. 生成實作包主體 (Implementation Pack)
        # 這裡會結合 Planner 的輸出與 SOT 邏輯
        i_pack = {
            "task_id": self.task_id,
            "goal": planner_output.get("goal", "UNDEFINED"),
            "data_models": planner_output.get("data_models", []),
            "deliverables": planner_output.get("deliverables", []),
            "acceptance_criteria": planner_output.get("acceptance_criteria", []),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        with open(self.impl_dir / "implementation_pack.json", "w") as f:
            json.dump(i_pack, f, indent=2, ensure_ascii=False)

        # 5. 執行 3 秒判讀稽核 (Readability Gate)
        gate = ReadabilityGate(i_pack, sot_map)
        audit_report = gate.save_report(self.run_dir)
        results["audit"] = audit_report

        # 6. 高質量自動封版 (Auto-Tagging Logic)
        if audit_report["readability_score"] > 95 and audit_report["jargon_count"] == 0:
            self._execute_auto_tag(audit_report["readability_score"])

        return results

    def _execute_auto_tag(self, score: float):
        """
        執行 git tag spec-vX.Y。
        """
        try:
            # 獲取當前版本號（簡化處理，實際可能從 config 讀取）
            tag_name = f"spec-v1.{int(score)}"
            subprocess.run(["git", "tag", "-a", tag_name, "-m", f"High Quality I-Pack (Score: {score})"], 
                           cwd=str(self.project_root), check=True)
            print(f"✅ [Auto-Tag] {tag_name} created.")
        except Exception as e:
            print(f"⚠️ [Auto-Tag:Error] {e}")

if __name__ == "__main__":
    # 測試
    import sys
    root = Path("/Users/jameschen/Workspace/nexus")
    tid = "test-task-001" # 需確保目錄存在
    
    # 模擬 Planner 輸出
    mock_planner = {
        "goal": "建立一個具備 SOT 解析能力的總包編譯器。",
        "data_models": [{"name": "IPack", "fields": {"task_id": "string"}}],
        "deliverables": ["implementation_pack.py"],
        "acceptance_criteria": ["Score > 95"]
    }
    
    gen = ImplementationPackGenerator(root, tid)
    print(json.dumps(gen.generate(mock_planner), indent=2, ensure_ascii=False))
