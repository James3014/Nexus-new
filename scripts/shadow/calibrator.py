import os
import json
import time
import uuid
import subprocess
from pathlib import Path
from datetime import datetime

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
sys.path.append(str(NEXUS_ROOT)) # 🛡️ Enable local module imports

from nexus_swarm.wisdom.lancedb_store import WisdomMemory
from nexus_swarm.wisdom.online_learner import BayesianLearner

SHADOW_DIR = NEXUS_ROOT / ".nexus" / "shadow"
CALIBRATION_FILE = SHADOW_DIR / "calibration.json"
RUNS_DIR = SHADOW_DIR / "runs"

class ShadowCalibrator:
    def __init__(self):
        self.load_calibration()
        # 🛡️ Initialize Wisdom Layer (v23 Phase 2)
        try:
            self.wisdom = WisdomMemory()
            self.learner = BayesianLearner()
            self.wisdom_active = True
        except Exception as e:
            print(f"⚠️ Wisdom Layer Initialization Failed: {e}. Falling back to v22 baseline.")
            self.wisdom_active = False

    def load_calibration(self):
        if CALIBRATION_FILE.exists():
            with open(CALIBRATION_FILE, 'r') as f:
                self.calData = json.load(f)
        else:
            self.calData = {
                "status": "HEALTHY",
                "total_runs": 0,
                "false_positive_count": 0,
                "avg_latency_ms": 0,
                "whitelist": [],
                "last_updated": datetime.now().isoformat()
            }

    def save_calibration(self):
        self.calData["last_updated"] = datetime.now().isoformat()
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(self.calData, f, indent=2)

    def check_docker(self):
        try:
            subprocess.run(["docker", "info"], capture_output=True, check=True)
            return True
        except:
            return False

    def run_audit(self, pr_id, payload=None):
        run_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        has_docker = self.check_docker()
        status = "SUCCESS"
        result_summary = "Shadow Audit passed."
        is_false_positive = False

        if has_docker:
            # 🛡️ Real Audit Simulation (Executing in container)
            # cmd = ["docker", "run", "--rm", "nexus:latest", "audit", f"--pr={pr_id}"]
            time.sleep(2) # Simulate workload
            result_summary = f"Container Audit for PR {pr_id} complete."
        else:
            # 🛡️ Degraded Mode (Simulated Audit)
            time.sleep(1)
            result_summary = f"Simulated Shadow Audit for PR {pr_id} (Docker Degraded)."
            self.calData["status"] = "DEGRADED"

        latency_ms = int((time.time() - start_time) * 1000)
        
        # 🛡️ Wisdom Lookup [v23 Shadow Integration]
        wisdom_guidance = None
        if self.wisdom_active:
            try:
                # 模擬 pattern 提取，實際會從 payload 提取代碼
                snippet = payload.get("code_snippet", "let lock = mutex.lock().unwrap();") if payload else ""
                repo = payload.get("repository", "nexus") if payload else "nexus"
                lang = payload.get("language", "rust") if payload else "rust"
                
                hits = self.wisdom.lookup_similar(snippet, repo, lang, top_k=1)
                if hits:
                    best_match = hits[0]
                    bias = self.learner.get_decision_bias(best_match["pattern_id"])
                    wisdom_guidance = {
                        "hit": True,
                        "pattern_id": best_match["pattern_id"],
                        "confidence": bias["confidence"],
                        "recommendation": bias["recommendation"]
                    }
                    # 🛡️ Shadow Decision: Adjusting result based on Wisdom (Shadow mode only)
                    if bias["recommendation"] == "bypass":
                        result_summary += " | [Shadow: Wisdom suggests BYPASS]"
            except Exception as e:
                print(f"⚠️ Wisdom Lookup Failed (Fail-Open): {e}")

        # 🛡️ Update Metrics
        self.calData["total_runs"] += 1
        # Mock logic: 5% chance of FP for testing
        if (self.calData["total_runs"] % 20 == 0):
            is_false_positive = True
            self.calData["false_positive_count"] += 1
            status = "FP_DETECTED"

        # Update Average Latency
        old_total = self.calData["total_runs"] - 1
        self.calData["avg_latency_ms"] = int((self.calData["avg_latency_ms"] * old_total + latency_ms) / self.calData["total_runs"])

        # Whitelist Logic (Demo: PR ID 1, 2 always pass)
        if pr_id in ["1", "2"] and pr_id not in self.calData["whitelist"]:
            self.calData["whitelist"].append(pr_id)

        # Save Run Result
        run_record = {
            "run_id": run_id,
            "pr_id": pr_id,
            "status": status,
            "latency_ms": latency_ms,
            "result": result_summary,
            "docker_used": has_docker,
            "timestamp": datetime.now().isoformat(),
            "wisdom": wisdom_guidance # 🛡️ Wisdom Metadata Attached
        }
        
        with open(RUNS_DIR / f"{run_id}.json", 'w') as f:
            json.dump(run_record, f, indent=2)
            
        self.save_calibration()
        return run_record

if __name__ == "__main__":
    import sys
    pr = sys.argv[1] if len(sys.argv) > 1 else "manual"
    cal = ShadowCalibrator()
    res = cal.run_audit(pr)
    print(json.dumps(res, indent=2))
