import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AmbiguityGuard")

class AmbiguityGuard:
    """🛡️ Nexus v25.6 Governance Gate - Blade 3: Ambiguity Resolver."""

    # 責任對位表 (Responsibility Table) - 嵌進 ARCH_03
    RESPONSIBILITY_REGISTRY = {
        "planner_enhancer.py": {"owner": "task_state", "proxy": "manifest.json"},
        "ui_budget.py": {"owner": "resource_map", "proxy": ".nexus/ui/"},
        "normalization_engine.py": {"owner": "naming_standard", "proxy": "AGENT_SCHEMA.md"}
    }

    def scan_plan(self, plan_data: Dict[str, Any]) -> List[str]:
        """🔍 掃描雙重來源與判定歧義。"""
        warnings = []
        
        # 1. 檢查 ViewModel 是否存在
        if "view_model" not in plan_data:
            warnings.append("⚠️ Missing ViewModel block (v25.6 Requirement Violation)")
        
        # 2. 檢查真相源衝突 (AGENTSCHEMA 2.1)
        # 模擬偵測：若 view_model 包含額外 data_proxy 則視為衝突
        view_model = plan_data.get("view_model", {})
        proxy = view_model.get("data_proxy", "")
        if "manifest.json" not in proxy and proxy != "":
             warnings.append(f"❌ Parallel Truth Detected: {proxy} (Should only ref manifest.json)")

        # 3. 檢查命名規範 (Blade 1 整合)
        # 若存在 A_PASSED 則報警
        raw_content = json.dumps(plan_data)
        if "A_PASSED" in raw_content or "APASSED" in raw_content:
            warnings.append("❌ Naming Drift Detected: 'A_PASSED' detected (Run normalization_engine first)")

        return warnings

    def audit_governance(self, plan_path: str):
        """⚖️ 執行 P6a Draft 之前的終極判定。"""
        if not Path(plan_path).exists():
            logger.error(f"File not found: {plan_path}")
            return 1

        with open(plan_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                logger.error("Invalid JSON format.")
                return 1

        warnings = self.scan_plan(data)
        
        print("--- 🛡️ AMBIGUITY-GUARD AUDIT REPORT ---")
        if not warnings:
            print("Status: 🟢 CLEAN (0 Ambiguities Found)")
            print("Action: PROMOTE TO P6a DRAFT")
            return 0
        else:
            print(f"Status: 🔴 REJECTED ({len(warnings)} Warnings)")
            for w in warnings:
                print(w)
            return 1

if __name__ == "__main__":
    guard = AmbiguityGuard()
    if len(sys.argv) > 1 and sys.argv[1] == "--plan":
        target = sys.argv[2] if len(sys.argv) > 2 else "plan.json"
        sys.exit(guard.audit_governance(target))
    else:
        print("Usage: python3 ambiguity_guard.py --plan <file>")
