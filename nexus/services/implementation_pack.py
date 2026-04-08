import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from nexus.services.source_of_truth_resolver import SourceOfTruthResolver
from nexus.services.status_normalizer import StatusNormalizer
from nexus.services.decision_formula_engine import DecisionFormulaEngine
from nexus.services.readability_gate import ReadabilityGate
from nexus.services.wisdom_synthesizer import WisdomSynthesizer
from nexus.services.mem_palace import MemPalace

class ImplementationPackGenerator:
    """
    ⚔️ Work Order A: Implementation Pack Generator (Orchestrator)
    Nexus vNext 編譯器核心：將 P-Phase 產物轉化為硬性施工包。
    """

    def __init__(self, project_root: Path, task_id: str, tenant_id: str = "default"):
        self.project_root = project_root
        self.task_id = task_id
        self.tenant_id = tenant_id
        self.run_dir = project_root / ".nexus" / "runs" / task_id
        self.impl_dir = self.run_dir / "implementation"
        self.impl_dir.mkdir(parents=True, exist_ok=True)
        self.wisdom = WisdomSynthesizer(project_root)
        self.palace = MemPalace(str(project_root))

    def generate(self, planner_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行全量編譯與 v25.5 記憶閉環。
        """
        results = {}
        # ... (解析 SOT, Normalizer, Formula Engine 的邏輯)
        resolver = SourceOfTruthResolver(self.project_root, self.task_id)
        sot_map = resolver.resolve()
        results["sot_map"] = sot_map

        # ... (產出 normalization.json 與 decision_formula.json)
        norm_artifact = StatusNormalizer.generate_normalization_artifact()
        with open(self.impl_dir / "state_normalization.json", "w") as f:
            json.dump(norm_artifact, f, indent=2, ensure_ascii=False)

        formula_engine = DecisionFormulaEngine({})
        formulas = formula_engine.generate_artifact()
        with open(self.impl_dir / "decision_formula.json", "w") as f:
            json.dump(formulas, f, indent=2)

        # 4. 生成實作包主體 (Implementation Pack)
        i_pack = {
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "goal": planner_output.get("goal", "UNDEFINED"),
            "task_type": planner_output.get("task_type", "fullstack"),
            "deliverables": planner_output.get("deliverables", []),
            "files_to_modify": planner_output.get("files_to_modify", []),
            "files_to_create": planner_output.get("files_to_create", []),
            "data_models": planner_output.get("data_models", []),
            "ui_blocks": planner_output.get("ui_blocks", []),
            "commands_to_wire": planner_output.get("commands_to_wire", []),
            "edge_cases": planner_output.get("edge_cases", []),
            "error_handling": planner_output.get("error_handling", ["Standard Fallback"]),
            "out_of_scope": planner_output.get("out_of_scope", ["Any unrelated code modification"]),
            "acceptance_targets": planner_output.get("acceptance_criteria", []),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open(self.impl_dir / "implementation_pack.json", "w") as f:
            json.dump(i_pack, f, indent=2, ensure_ascii=False)

        # 🏛️ [MemPalace] v25.5 Physical Sharding & AAAK Compression
        self.palace.ingest_to_shards(self.tenant_id, "i_pack", i_pack)

        # ... (產出 Matrix 與 Checklist)
        with open(self.impl_dir / "component_responsibility.md", "w") as f:
            f.write("# 責任矩陣\n")
        with open(self.impl_dir / "acceptance_checklist.json", "w") as f:
            json.dump({"targets": []}, f)

        # 5. 執行 3 秒判讀稽核 (Readability Gate)
        gate = ReadabilityGate(i_pack, sot_map)
        audit_report = gate.save_report(self.run_dir)
        results["audit"] = audit_report

        # 🧬 學習閉環接入 (Learning Loop)
        self.wisdom.log_learning_event(self.task_id, "SPEC_QUALITY", "success", {
            "score": audit_report["readability_score"],
            "jargon_count": audit_report["jargon_count"]
        })

        # 💎 結晶化 (Crystallization)
        if audit_report["readability_score"] >= 95:
            # 🔄 [Arweave] Trigger Metabolism
            tx_id = self.palace.trigger_arweave_distillation(i_pack)
            results["arweave_tx"] = tx_id
            
            self.wisdom.synthesize_template(self.task_id, i_pack, audit_report["readability_score"])
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
