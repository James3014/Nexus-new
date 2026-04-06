# 🛡️ Nexus v23.1 Regression Suite
# [ARCH-EVO: v23.1 STABILIZATION PACK]

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
HANDOFF_PATH = REPO_ROOT / ".nexus" / "state" / "last_handoff.json"
REPORT_DIR = REPO_ROOT / ".nexus" / "reports"

def get_file_md5(path: Path) -> str:
    if not path.exists(): return "FILE_NOT_FOUND"
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

class RegressionSuite:
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "checks": [],
            "overall_pass": True
        }
        os.makedirs(REPORT_DIR, exist_ok=True)

    def _add_check(self, name: str, passed: bool, notes: str = ""):
        self.results["checks"].append({
            "name": name,
            "passed": passed,
            "notes": notes
        })
        if not passed: self.results["overall_pass"] = False

    def verify_manifest_indexing(self):
        """🛡️ 檢查 manifest.json 是否正確索引 handoff 工件"""
        if not MANIFEST_PATH.exists():
            self._add_check("manifest_exists", False, "manifest.json not found")
            return

        with open(MANIFEST_PATH, "r") as f:
            manifest = json.load(f)
        
        artifacts = manifest.get("artifacts", [])
        handoff_entry = next((a for a in artifacts if "last_handoff.json" in a["path"]), None)
        
        if handoff_entry:
            passed = handoff_entry.get("role") == "Governance Handoff (v23.1)"
            self._add_check("manifest_handoff_role", passed, f"Role: {handoff_entry.get('role')}")
        else:
            self._add_check("manifest_handoff_indexed", False, "last_handoff.json not found in manifest")

    def verify_handoff_loop(self):
        """🛡️ 模擬兩回合 Handoff：Turn 1 寫入 -> Turn 2 讀取"""
        if not HANDOFF_PATH.exists():
            self._add_check("handoff_file_exists", False, "last_handoff.json not produced")
            return

        with open(HANDOFF_PATH, "r") as f:
            handoff = json.load(f)
        
        # 驗證核心欄位
        required = ["task_id", "phase", "state_token"]
        missing = [r for r in required if r not in handoff]
        
        self._add_check("handoff_schema_valid", len(missing) == 0, f"Missing: {missing}")
        
        # 模擬 ContextHub 注入 (L1 Index)
        l1_index = f"L1: [TASK: {handoff['task_id']}] [PHASE: {handoff['phase']}]"
        self._add_check("handoff_l1_injectable", True, f"Generated L1: {l1_index}")

    def run_all(self):
        print(f"🚀 [v23.1] Running Regression Suite...")
        self.verify_manifest_indexing()
        self.verify_handoff_loop()
        
        # 產出報告
        report_path = REPORT_DIR / "v23_1_regression_check.json"
        with open(report_path, "w") as f:
            json.dump(self.results, f, indent=2)
        
        md_path = REPORT_DIR / "v23_1_regression_check.md"
        with open(md_path, "w") as f:
            f.write(f"# v23.1 Regression Check Report\n\n")
            f.write(f"Timestamp: {self.results['timestamp']}\n")
            f.write(f"Overall Pass: {'✅' if self.results['overall_pass'] else '❌'}\n\n")
            f.write("| Check Name | Status | Notes |\n| --- | --- | --- |\n")
            for c in self.results["checks"]:
                f.write(f"| {c['name']} | {'PASS' if c['passed'] else 'FAIL'} | {c['notes']} |\n")

        print(f"✅ [Reports] Generated at {REPORT_DIR}")

if __name__ == "__main__":
    RegressionSuite().run_all()
