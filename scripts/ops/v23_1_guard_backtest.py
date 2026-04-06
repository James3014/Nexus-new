# 🛡️ Nexus v23.1 Guard Backtest Engine
# [ARCH-EVO: v23.1 STABILIZATION PACK]

import json
from pathlib import Path
from nexus_swarm.guard.consensus_guard import ConsensusGuard

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_SET_PATH = REPO_ROOT / "nexus_swarm" / "guard" / "golden_set_v23.json"
REPORT_DIR = REPO_ROOT / ".nexus" / "reports"

class GuardBacktest:
    def __init__(self):
        self.guard = ConsensusGuard(REPO_ROOT)
        with open(GOLDEN_SET_PATH, "r") as f:
            self.golden_set = json.load(f)
        self.results = {
            "total_scenarios": len(self.golden_set["scenarios"]),
            "passes": 0,
            "details": []
        }

    def run(self):
        print(f"🚀 [v23.1] Running Consensus Guard Backtest...")
        for scenario in self.golden_set["scenarios"]:
            res = self.guard.validate_scenario(
                scenario["id"], 
                scenario["action"], 
                risk_score_prior=scenario.get("risk_score_prior", 0.4)
            )
            
            passed = (res["outcome"]["outcome"] == scenario["expected_outcome"])
            if passed: self.results["passes"] += 1
            
            self.results["details"].append({
                "id": scenario["id"],
                "passed": passed,
                "expected": scenario["expected_outcome"],
                "actual": res["outcome"]["outcome"],
                "reason": res["outcome"]["reason"]
            })

        # Save MD Report
        md_path = REPORT_DIR / "v23_1_guard_backtest.md"
        with open(md_path, "w") as f:
            f.write("# v23.1 Guard Backtest Report\n\n")
            f.write(f"Scenarios: {self.results['passes']} / {self.results['total_scenarios']} PASS\n\n")
            f.write("| ID | Expected | Actual | Status | Reason |\n| --- | --- | --- | --- | --- |\n")
            for d in self.results["details"]:
                f.write(f"| {d['id']} | {d['expected']} | {d['actual']} | {'✅' if d['passed'] else '❌'} | {d['reason']} |\n")

        print(f"✅ [Reports] Generated at {REPORT_DIR}")

if __name__ == "__main__":
    import os
    import sys
    sys.path.append(str(REPO_ROOT))
    GuardBacktest().run()
