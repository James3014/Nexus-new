# 🛡️ Nexus v23.1 Hardened Backtest Engine
# [ARCH-EVO: v23.1 STABILIZATION PACK]

import json
import time
import os
import shutil
from pathlib import Path
from datetime import datetime
from nexus_swarm.wisdom.online_learner import BayesianLearner

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_METRICS_DIR = REPO_ROOT / ".nexus" / "metrics" / "test_runs"
BACKTEST_REPORT_DIR = REPO_ROOT / ".nexus" / "reports"

class HardenedBacktest:
    def __init__(self, rounds: int = 5):
        self.rounds = rounds
        self.timestamp = int(time.time())
        self.run_dir = TEST_METRICS_DIR / str(self.timestamp)
        os.makedirs(self.run_dir, exist_ok=True)
        
        self.learner = BayesianLearner(str(REPO_ROOT / "nexus_swarm" / "wisdom" / "learner_stats.json"))
        self.results = {
            "rounds": [],
            "decision_change_detected": False,
            "final_confidence": 0.0
        }

    def simulate_round(self, round_num: int, pattern_id: str = "backtest-missing-symbol"):
        """模擬單輪反饋並記錄"""
        print(f"🔄 Round {round_num}: Simulating feedback for '{pattern_id}'...")
        
        # 🛡️ Test-run isolated logging
        log_entry = {
            "task_id": f"backtest-{self.timestamp}-{round_num}",
            "pattern_id": pattern_id,
            "type": "unsafe_missed",
            "actor": "backtest_harness",
            "tag": "test-run",
            "timestamp": datetime.now().isoformat()
        }
        
        with open(self.run_dir / "test_feedback.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
            
        # 貝氏更新 (模擬 Admin 反饋以加快收斂)
        self.learner.update_feedback(pattern_id, "unsafe_missed", actor_role="admin")
        
        stats = self.learner._get_pattern_entry(pattern_id)
        self.results["rounds"].append({
            "round": round_num,
            "confidence": stats["confidence"],
            "bypass_score": stats["bypass_score"]
        })

    def run_backtest(self):
        pattern = "backtest-missing-symbol"
        for i in range(1, self.rounds + 1):
            self.simulate_round(i, pattern)
            
        # 檢查決策變更：Confidence 應顯著下降 (對於 unsafe_missed)
        start_conf = self.results["rounds"][0]["confidence"]
        end_conf = self.results["rounds"][-1]["confidence"]
        self.results["decision_change_detected"] = (end_conf < start_conf)
        self.results["final_confidence"] = end_conf
        
        # 歸檔與報告
        report_path = BACKTEST_REPORT_DIR / "v23_1_learning_backtest.json"
        with open(report_path, "w") as f:
            json.dump(self.results, f, indent=2)
            
        md_path = BACKTEST_REPORT_DIR / "v23_1_learning_backtest.md"
        with open(md_path, "w") as f:
            f.write("# v23.1 Learning Backtest Report\n\n")
            f.write(f"Rounds: {self.rounds}\n")
            f.write(f"Isolation Path: `{self.run_dir}`\n")
            f.write(f"Decision Change Detected: {'✅' if self.results['decision_change_detected'] else '❌'}\n\n")
            f.write("| Round | Confidence | Action Change Potential |\n| --- | --- | --- |\n")
            for r in self.results["rounds"]:
                f.write(f"| {r['round']} | {r['confidence']:.4f} | {'GUARD_TRIGGERED' if r['confidence'] < 0.3 else 'NOMINAL'} |\n")
        
        # 📦 Archive test data
        archive_name = shutil.make_archive(str(self.run_dir), 'gztar', self.run_dir)
        shutil.rmtree(self.run_dir)
        print(f"📦 [Backtest] Test data archived to {archive_name}")
        print(f"✅ [Reports] Generated at {BACKTEST_REPORT_DIR}")

if __name__ == "__main__":
    HardenedBacktest().run_backtest()
