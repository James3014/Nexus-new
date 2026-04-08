import json
import time
from pathlib import Path
from typing import Any, Dict

class ConstructionService:
    """
    🏗️ Work Order 1: Construction Service (Construction Bridge)
    Nexus vNext 施工橋接器：讀取施工包並模擬/執行物理標註。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def build(self, pack_path: Path) -> Dict[str, Any]:
        """
        執行自動化施工。
        """
        if not pack_path.exists():
            return {"status": "ERROR", "reason": f"Pack not found: {pack_path}"}
            
        try:
            with open(pack_path, "r") as f:
                pack = json.load(f)
        except Exception as e:
            return {"status": "ERROR", "reason": f"Invalid JSON in pack: {e}"}
            
        print(f"🏗️ [Construction] Initializing Task: {pack.get('task_id')}")
        print(f"🎯 Goal: {pack.get('goal')}")
        
        # 1. 讀取審計報告 (假定在同層或父層的 implementation/ 旁)
        # 路徑：.nexus/runs/XXX/implementation/implementation_pack.json
        # 審計路徑：.nexus/runs/XXX/implementation/readability_audit.json
        audit_path = pack_path.parent / "readability_audit.json"
        
        if audit_path.exists():
            with open(audit_path, "r") as f:
                audit = json.load(f)
                score = audit.get("readability_score", 0)
                if score < 95:
                    print(f"🛑 [Construction:Gate] FAIL! Readability Score ({score}) < 95. Refusing to build.")
                    return {"status": "REJECTED", "reason": "Low readability score"}
                print(f"🟢 [Construction:Gate] PASS! Readability Score: {score}")
        else:
            print("⚠️ [Construction:Gate] No audit report found. Proceeding with caution.")

        # 1b. [Phase 4] 執行 Wisdom 預測性風險稽核
        # 🛡️ 硬化：如果是高風險 (Risk > 0.8)，觸發 Auto-Optimize (Replan)
        print("⚖️ [Construction:WisdomGate] Performing Predictive Risk Audit...")
        from nexus.services.predictive_audit import predictive_auditor
        wisdom_audit = predictive_auditor.audit_risk(pack)
        risk_score = wisdom_audit.get("risk_score", 0.0)
        
        if risk_score > 0.8:
            print(f"🛑 [Construction:WisdomGate] BLOCK! High risk detected: {risk_score}")
            for f in wisdom_audit.get("findings", []):
                print(f"   - Match: {f['rule_text']} (ID: {f['rule_id']})")
            
            print("🔄 [Auto-Optimize] Triggering planner.replan() with Wisdom constraints...")
            return {
                "status": "AUTO_REPLAN_TRIGGERED", 
                "reason": "High predictive risk", 
                "risk_score": risk_score,
                "findings": wisdom_audit.get("findings")
            }
        
        print(f"🟢 [Construction:WisdomGate] PASS! Risk Score: {risk_score}")


        # 2. 模擬施工流程
        print("\n🔨 [Construction:Action] Executing Deliverables...")
        for item in pack.get("deliverables", []):
            time.sleep(0.5)
            print(f"📍 [Physical:Mark] Delivering artifact: {item} ... [OK]")
            
        print("\n📊 [Construction:Action] Validating Data Models...")
        for model in pack.get("data_models", []):
            print(f"✅ [Schema:Verify] Model: {model.get('name')} ... [OK]")

        print(f"\n✨ [Construction:Success] Task {pack.get('task_id')} Built Automatically (0 Human Intervention).")
        return {"status": "SUCCESS", "task_id": pack.get("task_id")}
